"""
MdAuthorService: 内部写回 Agent 服务

把「proposal approve」这一步与最终的 md 落盘解耦：
  - 任务 1 共性反馈写回 (suggest_facet_pattern approve 后)
        → MdAuthorFacetAgent 读取目标 H1 段,决定 add/merge/replace,落盘
  - 任务 2 新建概念建档 (suggest_missing_concept approve 后)
        → MdAuthorConceptAgent 查重 → smart_search 调研 → 起草 → 落盘

两个 Agent 都基于 ReAct,共用同一组工具集,system prompt 内联,
LLM 走 get_system_llm() (不消耗用户额度,不查 settings 表)。

调用方 (ProposalService) 不需要知道 Agent 的存在,只调本服务的两个公开方法。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agent_core.agent.events import AgentFinishReason
from agent_core.agent.react import ReActAgent
from agent_core.context.simple import SimpleContextBuilder
from agent_core.tool.registry import ToolRegistry

from agents.tools import (
    KGResolveForAuthoringTool,
    KGSearchForAuthoringTool,
    MdCreateConceptTool,
    MdLoadConceptTool,
    MdLoadFacetSectionTool,
    MdWriteFacetSectionTool,
)
from services.llm_factory import get_system_llm
from services.smart_search.tool import SmartSearchTool

logger = logging.getLogger(__name__)


# ============================================================
# 任务 1: 共性反馈写回 system prompt
# ============================================================

_FACET_AUTHOR_SYSTEM_PROMPT = """\
你是【内部写回 Agent】,职责是把一条「已通过审核的共性反馈」写入对应概念的 md 文件。
你**不是**教学 Agent,**不**面对学生,**只**负责把反馈落到 markdown 上。

## 数据流(请牢记自己的位置)

okf → db → wesmartflow agent → queue(facet proposal) → 审核 → **你** → okf

你拿到的反馈已经是管理员人工审核通过的,不要质疑反馈的有效性,也不要再去验证它。
你的任务只是「**怎么把它写好**」。

## 公式格式硬约束 (适用于所有 new_text)

所有数学/物理/化学公式、变量、符号,**必须**用 LaTeX 书写:

- 行内公式:`$...$`,例如 `当 $x \to 0$ 时,$\sin x \approx x$`
- 独立成段公式:`$$...$$`,前后各空一行
- 单个数学变量/常量也算公式,要包起来:写 `$x$` 而不是裸字 `x`,写 `$\pi$` 而不是 `π`
- **禁止**用 Unicode 伪公式凑数:不要写 `∫f(x)dx`、`x²`、`α`、`≤`、`→` 当正文符号,
  统一改成 `$\int f(x)\,dx$`、`$x^2$`、`$\alpha$`、`$\le$`、`$\to$`
- 中英文与公式之间不用强行加空格,正常写就行 (`当 $n \to \infty$ 时极限存在`)

非公式的纯文本 (中文叙述、举例的语言部分) 保持自然书写,不要滥套 `$$`。

## 4 个白名单 H1 (作用域,只能动这些)

- 常见误解 (misconception)
- 易错点 (struggle)
- 有效讲法 (breakthrough / effective_metaphor)
- 学习障碍 (emotional_block)

老师领地的 H1 (如「直观理解」「严格定义」「典型例子」) 你**绝对不能改**,工具会保护它们。

## 工作流程 (read → think → write)

### Step 1 读
调用 `md_load_facet_section`,拿回这个概念这个 H1 段下当前所有条目 items。
items 中每条带 idx 和 text,idx 是临时序号,**只在本次调用内有效**,
后续 write 工具就用这个 idx 定位。

### Step 2 想 (action 三选一)
对照新反馈和 items 里现有条目,决定:

- **add**: 新反馈讲的是个**全新主题**,items 里没有同类条目 → 在末尾追加
- **merge**: 新反馈讲的事和 items 里第 N 条**是同一回事的补充/细化** (不矛盾)
            → 把 A+B 融合成一条更完整的内容,替换 N
- **replace**: 新反馈和 items 里第 N 条**矛盾**,且新反馈推翻旧条目 (旧的错了)
            → 用新反馈的内容直接覆盖 N

判断标准:
  - merge 用于「信息变多」的场景 (互补/细化/补例)
  - replace 用于「信息纠错」的场景 (旧的事实错误)

### Step 3 写
调用 `md_write_facet_section`,传 action / new_text / target_idx (merge/replace 必填)。
new_text 不要带 `- ` 前缀,工具会自动渲染成 bullet。

## 错误处理

工具返回 `error_code` 时,根据错误码自己修:
  - target_idx_out_of_range → 说明你 idx 选错了,重新对照 items 里的 idx 再选
  - new_text_too_long       → 精简到 500 字以内
  - section_not_found       → 段不存在但 action≠add → 改用 add 即可 (工具会自动建段)
其它错误码,看 error 文字描述自行修正。

每次调用工具前先写 Thought,说清楚你为什么这么做。

## 完成

写入成功 (返回 ok=true) 后,直接输出一行总结即可结束:
「[FACET_DONE] action=<add/merge/replace> h1=<...> idx=<N> slug=<...>」
不要再调任何工具,不要复述 prompt。
"""


# ============================================================
# 任务 2: 新建概念 system prompt
# ============================================================

_CONCEPT_AUTHOR_SYSTEM_PROMPT = """\
你是【内部写回 Agent · 建档分支】,职责是把一条「已通过审核的『建议补一个新概念』提议」
真正落成一份 markdown 文件。

## 数据流

okf → db → wesmartflow agent → queue(concept proposal) → 审核 → **你** → okf

提议已经被人工 approve,你不需要再判断「该不该建」,
但**必须自己再做一次查重**,因为审核员看的只是名字,可能跟现有概念其实是同一个。

## 公式格式硬约束 (适用于 sections 中所有 content)

所有数学/物理/化学公式、变量、符号,**必须**用 LaTeX 书写:

- 行内公式:`$...$`,例如 `设 $f(x) = x^2$,则 $f'(x) = 2x$`
- 独立成段公式 (定义式、定理、长推导):`$$...$$`,前后各空一行,例如:

  ```
  设 $f$ 在 $[a,b]$ 上连续,则

  $$\int_a^b f(x)\,dx = F(b) - F(a)$$

  其中 $F$ 是 $f$ 的任一原函数。
  ```
- 单个数学变量/常量也算公式,要包起来:写 `$x$` 而不是裸字 `x`,写 `$\pi$` 而不是 `π`
- **禁止**用 Unicode 伪公式凑数:不要写 `∫f(x)dx`、`x²`、`Σ`、`α`、`≤`、`→`、`≈` 当正文符号,
  统一改成 `$\int f(x)\,dx$`、`$x^2$`、`$\sum$`、`$\alpha$`、`$\le$`、`$\to$`、`$\approx$`
- 中英文与公式之间不用强行加空格,正常写就行 (`当 $n \to \infty$ 时极限存在`)
- summary 字段 (≤80 字一句话定义) 同样适用本规则

非公式的纯文本 (中文叙述、举例的语言部分) 保持自然书写,不要滥套 `$$`。

## 工作流程

### Step 1 查重 (必做,不能跳过)
调用 `kg_resolve_for_authoring(term=<concept_name>)`:

- verdict=exists    → KG 已存在该概念,**立即终止**,输出
                       「[CONCEPT_ABORT] reason=already_exists concept_id=<...>」
- verdict=suspected → 疑似重复,**立即终止**,输出
                       「[CONCEPT_ABORT] reason=suspected concept_id=<...>」
                       (让人工核对,你不要硬建)
- verdict=not_found → 继续

### Step 2 找邻居 (定 subject + 选 prerequisites/related)
调用 `kg_search_for_authoring(query=<concept_name + 简短描述>, top_k=8)`:
- subject_distribution 取**众数**作为 frontmatter 的 subject
  (若分布很散没有明显众数,选与本概念语义最贴近的那一个)
- concepts 列表里挑 1-3 个真正相关的,作为 related_concepts (slug 列表)
  注意挑「和本概念有教学关系」的,不要看到分数高就全收

### Step 3 (可选) 看一篇邻居 md 的写法
调用 `md_load_concept(slug=<某邻居 slug>)` 看一份同领域的 md,
学习其 H1 划分、写作粒度。**不强求,如果邻居都很像就不用看。**

### Step 4 调研
调用 `smart_search(query=<concept_name 相关问题>)` 收集正文素材,
1-3 次足够,不要无止境地搜。

### Step 5 起草各段
自己决定 H1 列表 (至少 3 段),建议覆盖:
  - 直观理解 (是什么,用一句话或类比)
  - 严格定义 (形式化或精确定义)
  - 典型例子 (具体到能让学生看懂)
  - (可选) 适用场景 / 历史背景 / 几何意义 等

**禁用 H1**: 常见误解 / 易错点 / 有效讲法 / 学习障碍 (这 4 个由飞轮维护,
工具会拒绝你预填)

每段 content 长度 50-4000 字,标题不能重复,不能含 '/'。

再次强调: 段内任何公式/数学符号都走 LaTeX (`$...$` 或 `$$...$$`),不要用 Unicode 伪公式。

### Step 6 落盘
调用 `md_create_concept(...)`:
  - subject: Step 2 拿到的众数
  - slug: 自己起一个 kebab-case (如 chain-rule, dynamic-programming),
          不要含空白/'/'。
  - canonical_name: 概念中文规范名
  - summary: ≤80 字一句话定义
  - difficulty: int 0-5 (0=入门, 5=专家),自己评估
  - aliases / tags: 可选
  - prerequisites / related: Step 2 选出的 slug,工具会校验它们必须真实存在
  - sections: 你写的各段

## 错误处理

工具返回 ok=false 时:
  - file_already_exists       → 文件已存在,**立即终止** (终止理由: 物理冲突)
  - relation_slug_not_found   → 把不存在的 slug 从 prerequisites/related 里去掉,重试
  - invalid_h1                → 检查是否用了禁用 H1,改成允许的
  - content_too_short/long    → 调整对应段长度
  - 其它                       → 看 error 文字,自行修正后重试

## 完成

成功 (ok=true) 后,输出一行结束:
「[CONCEPT_DONE] slug=<...> subject=<...> path=<...>」

中止 (查重失败/物理冲突) 时,输出:
「[CONCEPT_ABORT] reason=<...> ...」
"""


# ============================================================
# 服务
# ============================================================


_DONE_TAGS = ("[FACET_DONE]", "[CONCEPT_DONE]", "[CONCEPT_ABORT]")


class MdAuthorService:
    """内部写回 Agent 服务。

    两个公开入口:
      - apply_facet_proposal(...)    → 跑任务 1 Agent
      - apply_concept_proposal(...)  → 跑任务 2 Agent

    两个方法都是异步的 (依赖 agent.async_run),
    供 ProposalService.approve(...) 在 approve 后台流程里调用。
    """

    def __init__(self) -> None:
        # 工具实例可以共享 (无 user 状态)
        self._smart_search = SmartSearchTool()
        self._kg_resolve = KGResolveForAuthoringTool()
        self._kg_search = KGSearchForAuthoringTool()
        self._md_load_concept = MdLoadConceptTool()
        self._md_create_concept = MdCreateConceptTool()
        self._md_load_facet = MdLoadFacetSectionTool()
        self._md_write_facet = MdWriteFacetSectionTool()

    # --------------------------------------------------------------
    # 任务 1: 共性反馈写回
    # --------------------------------------------------------------

    async def apply_facet_proposal(
        self,
        *,
        proposal_id: str,
        slug: str,
        h1: str,
        new_facet_text: str,
        subject: Optional[str] = None,
        proposer: str = "",
        observation_count: int = 0,
        max_steps: int = 8,
    ) -> dict[str, Any]:
        """触发任务 1 Agent,把一条已 approve 的共性反馈写入对应 md。

        Args:
            proposal_id:        审核通过的 proposal id (审计用)
            slug:               目标概念 slug
            h1:                 目标 H1 段 (常见误解 / 易错点 / 有效讲法 / 学习障碍)
            new_facet_text:     新反馈正文 (LLM 归纳后的内容)
            subject:            可选,Agent 缺省也会按 slug 查 KG
            proposer:           谁产的反馈 (审计上下文)
            observation_count:  这条反馈背后聚合了多少观察 (信息量)
            max_steps:          ReAct 最大步数,默认 8

        Returns:
            {ok: bool, finish_reason, output, agent_steps}
        """
        registry = ToolRegistry([self._md_load_facet, self._md_write_facet])
        agent = ReActAgent(
            llm=get_system_llm(timeout=90),
            context_builder=SimpleContextBuilder(_FACET_AUTHOR_SYSTEM_PROMPT),
            tool_registry=registry,
            max_steps=max_steps,
        )

        user_input = self._build_facet_user_input(
            proposal_id=proposal_id,
            slug=slug,
            subject=subject or "",
            h1=h1,
            new_facet_text=new_facet_text,
            proposer=proposer,
            observation_count=observation_count,
        )

        return await self._run_agent(agent, user_input, label="facet")

    # --------------------------------------------------------------
    # 任务 2: 新建概念建档
    # --------------------------------------------------------------

    async def apply_concept_proposal(
        self,
        *,
        proposal_id: str,
        concept_name: str,
        reason_brief: str = "",
        proposer: str = "",
        max_steps: int = 16,
    ) -> dict[str, Any]:
        """触发任务 2 Agent,把一条已 approve 的『建议新增概念』落成一份 md。

        Args:
            proposal_id:    审核通过的 proposal id
            concept_name:   要新建的概念名
            reason_brief:   提议时的理由摘要 (告诉 Agent 这个概念为什么该有)
            proposer:       谁提议的
            max_steps:      ReAct 最大步数,默认 16 (建档涉及多次搜索)
        """
        registry = ToolRegistry(
            [
                self._kg_resolve,
                self._kg_search,
                self._md_load_concept,
                self._smart_search,
                self._md_create_concept,
            ]
        )
        agent = ReActAgent(
            llm=get_system_llm(timeout=120),
            context_builder=SimpleContextBuilder(_CONCEPT_AUTHOR_SYSTEM_PROMPT),
            tool_registry=registry,
            max_steps=max_steps,
        )

        user_input = self._build_concept_user_input(
            proposal_id=proposal_id,
            concept_name=concept_name,
            reason_brief=reason_brief,
            proposer=proposer,
        )

        return await self._run_agent(agent, user_input, label="concept")

    # --------------------------------------------------------------
    # 内部
    # --------------------------------------------------------------

    @staticmethod
    def _build_facet_user_input(
        *,
        proposal_id: str,
        slug: str,
        subject: str,
        h1: str,
        new_facet_text: str,
        proposer: str,
        observation_count: int,
    ) -> str:
        # 直接拼成 Agent 看得懂的格式,不做花哨 Markdown,避免 LLM 误把它当文档
        lines = [
            "# 任务: 共性反馈写回",
            f"proposal_id: {proposal_id}",
            f"slug: {slug}",
            f"subject: {subject or '(未提供, 你可以让工具自动反查 KG)'}",
            f"h1: {h1}",
            f"proposer: {proposer or '(unknown)'}",
            f"observation_count: {observation_count}",
            "",
            "新反馈正文 (已审核通过):",
            "```",
            new_facet_text.strip(),
            "```",
            "",
            "请按 system prompt 描述的 read → think → write 流程完成写入,"
            "完成后输出 [FACET_DONE] 行结束。",
        ]
        return "\n".join(lines)

    @staticmethod
    def _build_concept_user_input(
        *,
        proposal_id: str,
        concept_name: str,
        reason_brief: str,
        proposer: str,
    ) -> str:
        lines = [
            "# 任务: 新概念建档",
            f"proposal_id: {proposal_id}",
            f"concept_name: {concept_name}",
            f"proposer: {proposer or '(unknown)'}",
            "",
            "提议理由:",
            f"  {reason_brief or '(无)'}",
            "",
            "请按 system prompt 描述的 6 步流程完成建档,"
            "完成后输出 [CONCEPT_DONE] 行,或在查重/冲突时输出 [CONCEPT_ABORT] 行。",
        ]
        return "\n".join(lines)

    @staticmethod
    async def _run_agent(
        agent: ReActAgent, user_input: str, *, label: str
    ) -> dict[str, Any]:
        try:
            result = await agent.async_run(user_input)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("md_author[%s] agent 异常", label)
            return {
                "ok": False,
                "finish_reason": "exception",
                "error": str(exc),
                "output": "",
                "agent_steps": 0,
            }

        output = (result.output or "").strip()
        finish_reason = (
            result.finish_reason.value
            if isinstance(result.finish_reason, AgentFinishReason)
            else str(result.finish_reason)
        )

        # 解析尾标记: [FACET_DONE] / [CONCEPT_DONE] = 成功; [CONCEPT_ABORT] = 业务中止 (也算"成功完成任务",
        # 只是没落盘)
        last_line = output.splitlines()[-1].strip() if output else ""
        ok = any(tag in output for tag in _DONE_TAGS)

        # AgentResult 没有显式 steps 字段, 用 history 长度估算
        # (system + user + 每轮 assistant + 每个 tool_result, 粗略反映复杂度)
        history = getattr(result, "history", []) or []
        metadata = getattr(result, "metadata", None) or {}

        return {
            "ok": ok,
            "finish_reason": finish_reason,
            "output": output,
            "last_line": last_line,
            "history_len": len(history),
            "history": history,  # 调用方可从工具返回里抓 md_path 等可靠数据
            "metadata": metadata,
        }


# 单例 (Service 本身无状态,可全局共享)
_singleton: Optional[MdAuthorService] = None


def get_md_author_service() -> MdAuthorService:
    global _singleton  # pylint: disable=global-statement
    if _singleton is None:
        _singleton = MdAuthorService()
    return _singleton


# 暴露 dump 给测试/诊断脚本: 直接看 prompt 文本
def dump_prompts() -> str:
    return json.dumps(
        {
            "facet_prompt": _FACET_AUTHOR_SYSTEM_PROMPT,
            "concept_prompt": _CONCEPT_AUTHOR_SYSTEM_PROMPT,
        },
        ensure_ascii=False,
        indent=2,
    )
