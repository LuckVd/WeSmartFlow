"""
TutorService：管理会话生命周期，将 HTTP 请求和 Agent 运行解耦

职责：
- 创建 / 恢复会话
- 编排一轮对话（上下文装配 → Agent 流式运行 → 持久化）
- 更新 study_logs（学习时长统计）
- 会话结束时计算时长、汇总掌握度变化

已拆出的职责：
- 交互模式判定 → :mod:`services.policy.interaction`（经 InteractionHintProvider 注入）
- 上下文注入（画像激活 / 交互建议 / KG 前置检索）→ :mod:`agents.providers`
- 会话记忆（游标切片 + 锚点 + 轨迹 + 滚动摘要压缩）→ ``agent_core.memory.SessionMemory``
- 工具副作用收集与产物持久化 → :mod:`services.turn_collector`
- Agent 定义（prompt / 工具集 / 预算）→ :mod:`agents.registry`
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from pathlib import Path

from agent_core.agent.events import (
    AgentFinalEvent,
    AgentFinishReason,
)
from agent_core.runtime import Budget, new_context
from models.session import (
    SessionSchema,
    MessageSchema,
    SessionCreate,
)
from repositories import SessionRepository, StudyLogRepository, NodeRepository
from services.llm_factory import get_llm, get_profile_llm
from services.turn_collector import TurnCollector
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)

# agents 专属 skills 目录
_AGENTS_SKILLS_DIR = Path(__file__).parent.parent / "agents" / "prompts" / "skills"


class TutorService:
    def __init__(self):
        self.session_repo = SessionRepository()
        self.study_log_repo = StudyLogRepository()
        self.node_repo = NodeRepository()

    # ── 权属校验 ──────────────────────────────────────
    def _assert_owner(self, user_id: str, session_id: str) -> SessionSchema | None:
        """断言会话存在且属于该用户；不存在或不属于该用户都返回 None
        （上层统一翻译为 404，避免通过状态码区分'不存在 vs 不属于你'）。"""
        session = self.session_repo.get_by_id(session_id)
        if not session or session.user_id != user_id:
            return None
        return session

    def create_session(self, user_id: str, data: SessionCreate) -> SessionSchema:
        return self.session_repo.create(user_id, data)

    def get_session(self, session_id: str) -> SessionSchema | None:
        return self.session_repo.get_by_id(session_id)

    def list_sessions(self, user_id: str) -> list[SessionSchema]:
        """列出用户的所有会话。"""
        return self.session_repo.get_all(user_id)

    def get_session_detail(self, user_id: str, session_id: str):
        """获取会话详情（含消息），仅限本人；不存在或不属于该用户都返回 None。"""
        if not self._assert_owner(user_id, session_id):
            return None
        return self.session_repo.get_detail(session_id)

    async def stream_chat(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
    ):
        """
        流式处理一条用户消息，逐步 yield 进度事件。

        Yield 类型（可在前端按类型区分展示）：
        - AgentThinkEvent      — LLM 正在思考，content 为思考文本
        - AgentToolCallEvent   — 正在调用工具，tool_name / arguments
        - AgentToolResultEvent — 工具执行完毕，result 为结果摘要
        - DomainEvent          — 业务副作用（卡片生成 / 掌握度变化等）
        - AgentFinalEvent      — 最终回复，content 为完整回复文本

        最终回复产出后，本方法会完成持久化（消息、掌握度、学习日志）。
        """
        session = self._validate_session(user_id, session_id)
        is_immersive = (session.title or "").startswith("[AI课程]")

        detail = self.session_repo.get_detail(session_id)
        chat_history = detail.messages if detail else []
        turn_started_at = datetime.now(timezone.utc)  # 本轮消息的发生时间

        # ── 会话记忆：跨 run 连续（store 持久化 + 压缩策略合一）──────
        # 构造时从游标后切片加载历史（游标前只活在摘要里，不进内存）；
        # 锚点（本轮输入）与运行轨迹刚性不裁，历史段窗口兜底。
        #
        # 顺序契约：本轮 user/assistant 在运行**结束后**成对落库——
        # 构造时 DB 即「本轮开始前」状态，本轮 user 只以 anchor 身份
        # 出现一次，天然无重复。
        from agent_core.memory import SessionMemory
        from services.session_store import SQLiteSessionStore

        memory = SessionMemory(
            SQLiteSessionStore(self.session_repo, session_id),
            llm=get_llm(user_id, scene="chat"),
        )

        # ── 上下文注入：画像 / 交互建议 / KG 前置检索统一经 provider ──
        # 各段由 LayeredPromptBuilder 并发执行、故障隔离（单段失败只丢
        # 那一段）。主路径依旧零 LLM 调用。会话摘要不在此处——由
        # SessionMemory.summary 经装配层自动合并进 system。
        from agent_core.context import StaticProvider
        from agents.providers import (
            ActivatedProfileProvider,
            InteractionHintProvider,
        )

        providers = [
            ActivatedProfileProvider(user_id, user_message),
            InteractionHintProvider(user_message, chat_history, session),
        ]
        # KG 前置检索（钩子①）：文本经 provider 注入 system 段。
        # （历史遗留：曾作为 system 消息插入 chat_history，会被装配层
        #  按「记忆只应产出 history」剔除而失效；provider 是正确通路。）
        kg_pre_msg = self._build_kg_pre_context(user_message)
        if kg_pre_msg:
            providers.append(StaticProvider("kg_pre_rag", kg_pre_msg.content))

        # ── 装配 Agent ──────────────────────────────────────
        # 工具副作用收集器同时充当 on_result_hook：它返回 DomainEvent，
        # 由框架按发生顺序并入事件流（不再需要旁路队列 + 手工 flush）。
        turn = TurnCollector()
        agent = self._build_agent(user_id, session_id, turn, providers)

        from services.credit_quota import budget_credits
        from services.pricing import calc_llm_credits

        ctx = new_context(
            principal=f"user:{user_id}",
            scope="tutor",
            budget=Budget(
                max_steps=20,
                max_tool_calls=40,
                # 单次运行 credits 熔断：剩余额度 + 预借余量；0 表示不限制
                max_credits=budget_credits(user_id) or None,
                credits_fn=calc_llm_credits,
            ),
            memory=memory,  # Agent 优先使用 ctx.memory（不传 chat_history）
        )

        final_content = ""
        try:
            async for event in agent.async_stream(user_message, ctx=ctx):
                yield event
                if isinstance(event, AgentFinalEvent):
                    final_content = event.content

        except asyncio.CancelledError:
            # 被外部 task.cancel() 取消（用户点击停止），静默退出
            return
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Tutor Agent 运行失败")
            final_content = f"抱歉，处理您的消息时遇到了问题：{e}"
            yield AgentFinalEvent(
                content=final_content,
                finish_reason=AgentFinishReason.ERROR,
            )

        # ── 持久化本轮对话（user + assistant 成对落库）────────
        # 延迟到运行结束：a) SessionMemory 构造快照天然是「本轮开始前」
        # 状态，本轮 user 只以 anchor 出现一次；b) 用户中途停止
        # （CancelledError 分支 return）时本轮不落库，避免历史里出现
        # 没有回复的孤立消息。created_at 用对话发生时刻。
        self.session_repo.append_message(
            session_id,
            MessageSchema(
                id=str(uuid.uuid4()),
                role="user",
                content=user_message,
                created_at=turn_started_at,
            ),
        )
        self._persist_assistant_message(
            session=session,
            final_content=final_content,
            turn=turn,
            is_immersive=is_immersive,
        )
        # 短连接模式下 _execute 已自动 commit，无需手动提交
        # （滚动摘要不再需要收尾触发——SessionMemory 为懒压缩：
        #  render 撞窗/预算紧张时按需压缩并推进游标，见其模块文档）

        # ── 异步触发画像更新（不阻塞主流程）─────────────────
        self._maybe_trigger_profile_update(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            assistant_reply=final_content,
            state={"mastery_changes": turn.mastery_changes},
            session=session,
        )

    # ── Agent 装配 ────────────────────────────────────────

    def _build_agent(
        self,
        user_id: str,
        session_id: str,
        turn: TurnCollector,
        providers: list,
    ):
        """按注册表声明装配 Tutor Agent。

        Agent 的 prompt / 工具集 / 预算 / 记忆策略全部在
        :mod:`agents.registry` 中声明，本方法只负责注入运行期依赖
        （用户、会话、副作用收集器、按轮次构造的 ContextProvider）。
        """
        from agents.registry import build_agent

        return build_agent(
            "tutor",
            llm=get_llm(user_id, scene="chat"),
            user_id=user_id,
            session_id=session_id,
            on_result_hook=turn,
            extra_providers=providers,
        )

    def _validate_session(self, user_id: str, session_id: str) -> SessionSchema:
        """校验会话存在、属于本人、且处于可对话状态，返回 session 对象。"""
        session = self._assert_owner(user_id, session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        # AI课程（completed）允许继续对话（智流Agent），其他已结束会话拒绝
        is_immersive = (session.title or "").startswith("[AI课程]")
        if session.status != "active" and not is_immersive:
            raise ValueError("会话已结束")
        return session

    def _persist_assistant_message(
        self,
        session: SessionSchema,
        final_content: str,
        turn: TurnCollector,
        is_immersive: bool,
    ) -> None:
        """持久化 assistant 消息、会话节点列表、会话文件列表。

        产物清单由 :class:`TurnCollector` 汇总——它在工具执行期间按**全局
        序号**收集，因此 html / viz / quiz 三类产物能保持真实生成顺序。
        """
        assistant_msg = turn.build_assistant_message(final_content)
        self.session_repo.append_message(session.id, assistant_msg)

        # 更新会话涉及的节点列表
        if turn.all_node_ids:
            merged = list(set((session.node_ids_covered or []) + turn.all_node_ids))
            self.session_repo.update_nodes_covered(session.id, merged)

        # 将本轮生成的文件按工具调用顺序追加到 SessionSchema.files
        logger.info("本轮生成文件列表（按工具调用顺序）: %s", turn.files)
        for session_file in turn.session_files(assistant_msg.id):
            self.session_repo.append_session_file(session.id, session_file)

    # ── 画像自动更新 ─────────────────────────────────────────────

    # 类级别消息计数器（session_id -> 未触发consolidate的消息数）
    _msg_count_since_consolidate: Dict[str, int] = {}
    # 触发阈值：累积 N 轮对话后触发一次 consolidate
    _CONSOLIDATE_THRESHOLD = 6
    # 有效交互关键词（检测到时立即触发）
    _EFFECTIVE_SIGNALS = [
        "不懂",
        "不理解",
        "太难",
        "太简单",
        "能简单点",
        "能详细点",
        "我之前学过",
        "我的背景",
        "我擅长",
        "我不擅长",
        "我喜欢",
        "我讨厌",
        "我习惯",
        "帮我",
        "我想学",
        "我的目标",
    ]

    def _maybe_trigger_profile_update(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_reply: str,
        state: Dict[str, Any],
        session: SessionSchema,
    ) -> None:
        """检测是否应触发画像更新，满足条件时异步执行 consolidate。

        触发条件（满足任一即可）：
        1. 累积消息数达到阈值（6 轮对话）
        2. 用户消息中包含有效交互信号关键词
        3. 本轮有 mastery_changes（说明有知识点掌握度变化）
        """
        # 累积计数
        count = self._msg_count_since_consolidate.get(session_id, 0) + 1
        self._msg_count_since_consolidate[session_id] = count

        should_trigger = False

        # 条件1：累积达到阈值
        if count >= self._CONSOLIDATE_THRESHOLD:
            should_trigger = True

        # 条件2：有效交互信号
        if not should_trigger:
            msg_lower = user_message.lower()
            for signal in self._EFFECTIVE_SIGNALS:
                if signal in msg_lower:
                    should_trigger = True
                    break

        # 条件3：有 mastery 变化
        if not should_trigger and state.get("mastery_changes"):
            should_trigger = True

        if not should_trigger:
            return

        # 重置计数
        self._msg_count_since_consolidate[session_id] = 0

        # 异步执行 consolidate（不阻塞主流程）
        asyncio.ensure_future(self._do_consolidate(user_id, session_id, session))

    async def _do_consolidate(
        self, user_id: str, session_id: str, session: SessionSchema
    ) -> None:
        """异步执行画像 consolidate，从最近对话中提取用户信息并落入结构化记忆。"""
        try:
            from services.profile_service import ProfileMemoryService

            # 获取最近的对话消息（最多取最近 10 条）
            detail = self.session_repo.get_detail(session_id)
            if not detail or not detail.messages:
                return

            recent_msgs = detail.messages[-10:]
            messages = []
            history_summary = (
                (detail.workspace or {}).get("history_summary") or ""
            ).strip()
            if history_summary:
                messages.append(
                    {
                        "role": "system",
                        "content": "既往对话短期摘要：" + history_summary,
                    }
                )
            for msg in recent_msgs:
                role = msg.role if hasattr(msg, "role") else msg.get("role", "user")
                content = (
                    msg.content if hasattr(msg, "content") else msg.get("content", "")
                )
                messages.append({"role": role, "content": content})

            # 如果是沉浸式课程，在消息前加 topic 上下文
            is_immersive = (session.title or "").startswith("[AI课程]")
            if is_immersive:
                topic = (
                    (session.topic or session.title or "")
                    .replace("[AI课程]", "")
                    .strip()
                )
                if topic:
                    messages.insert(
                        0,
                        {
                            "role": "system",
                            "content": f"以下对话发生在用户学习「{topic}」课程的过程中。",
                        },
                    )

            profile_llm = get_profile_llm(user_id)
            success = await ProfileMemoryService().consolidate_from_messages(
                user_id, messages, profile_llm
            )
            if success:
                logger.info("画像 consolidate 成功 (session=%s)", safe_log(session_id))
            else:
                logger.warning(
                    "画像 consolidate 失败 (session=%s)", safe_log(session_id)
                )

        except Exception:  # pylint: disable=broad-except
            logger.exception("画像 consolidate 异常 (session=%s)", safe_log(session_id))

    # ── KG 前置检索（钩子①）────────────────────────────────────

    def _build_kg_pre_context(self, user_message: str):
        """同步检索 KG，把命中结果作为一条 system 消息返回（用于预置到 chat_history 最前）。

        - 失败 / 超时 / 命中不足 → 返回 None，不插入任何上下文。
        - 设计为在主对话开始前给 LLM 提供"集体潜意识"参考。
        """
        try:
            from kg.config import (
                KG_CHAT_PRERAG_ENABLED,
                KG_CHAT_PRERAG_TIMEOUT_MS,
                KG_CHAT_PRERAG_TOP_CONCEPTS,
                KG_CHAT_PRERAG_TOP_FACETS_PER_CONCEPT,
            )
        except Exception:  # pylint: disable=broad-except
            return None
        if not KG_CHAT_PRERAG_ENABLED:
            return None
        if not user_message or len(user_message.strip()) < 2:
            return None

        try:
            from concurrent.futures import (
                ThreadPoolExecutor,
                TimeoutError as FTTimeoutError,
            )

            from kg import RetrieveRequest
            from services import kg_facade

            req = RetrieveRequest(
                query=user_message.strip(),
                need_facets=True,
                graph_expand=True,
                top_k_facets_per_concept=KG_CHAT_PRERAG_TOP_FACETS_PER_CONCEPT,
                anchor_max_entries=KG_CHAT_PRERAG_TOP_CONCEPTS,
                max_subgraph_size=KG_CHAT_PRERAG_TOP_CONCEPTS + 4,
            )
            # 用线程池跑 + 超时；KG 检索本身是同步阻塞 IO（向量库 + sqlite）
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(kg_facade.retrieve, req)
                try:
                    resp = fut.result(timeout=KG_CHAT_PRERAG_TIMEOUT_MS / 1000.0)
                except FTTimeoutError:
                    logger.info("KG 前置检索超时 (>%d ms)", KG_CHAT_PRERAG_TIMEOUT_MS)
                    return None
        except Exception:  # pylint: disable=broad-except
            logger.exception("KG 前置检索异常")
            return None

        if not resp or resp.degraded or not resp.concepts:
            return None

        lines: list[str] = [
            "## 公共知识图谱参考（系统自动检索）",
            "> 以下内容由系统从公共知识图谱中按当前问题检索而来，仅供参考；",
            "如与用户问题无关请忽略，不要在回复中提到「知识图谱」字样。",
            "",
            "### 相关概念",
        ]
        for c in resp.concepts:
            summary = (c.summary or "").strip()
            lines.append(f"- **{c.canonical_name}** ({c.id}): {summary}")
        if resp.facets:
            lines.append("")
            lines.append("### 相关切面")
            for f in resp.facets:
                lines.append(
                    f"- [{f.kind}] (concept={f.concept_id}, "
                    f"conf={f.confidence:.2f}, sup={f.support_count}) {f.content}"
                )
        kg_text = "\n".join(lines).strip()

        return MessageSchema(
            id=f"kg-ctx-{uuid.uuid4().hex[:8]}",
            role="system",
            content=kg_text,
            created_at=datetime.now(timezone.utc),
        )

    def record_duration(self, user_id: str, session_id: str, minutes: int) -> None:
        """前端离开会话页面时调用，记录本次会话的学习时长"""
        session = self._assert_owner(user_id, session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        minutes = max(1, minutes)
        # 累加到 sessions.duration_minutes（不改变 status）
        self.session_repo.add_duration(session_id, minutes)
        # 同步更新今日学习日志，并异步画像总览中的学习行为快照
        all_node_ids = session.node_ids_covered or []
        self.study_log_repo.upsert_today(user_id, minutes, session_id, all_node_ids)
        try:
            from repositories import ProfileOverviewRepository

            ProfileOverviewRepository().refresh_source_snapshot(user_id)
        except Exception:
            logger.exception("刷新画像学习行为快照失败 (user=%s)", safe_log(user_id))
