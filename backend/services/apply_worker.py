"""
Proposal 异步落盘 Worker（档位 3a：同进程后台 task + DB 队列 + asyncio.Event 信号）

整体链路
========
admin 在审核台点【通过】
  ↓
ProposalRepository.update_status(approved) + mark_apply_queued(queued)
  ↓
notify_apply_pending()              ← 戳 asyncio.Event（事件通知，无轮询）
  ↓
_apply_worker_loop                  ← await event.wait() 被唤醒
  ↓
ProposalRepository.pop_one_queued() ← 原子标记 running
  ↓
MdAuthorService.apply_xxx_proposal  ← ReAct Agent 真正写 OKF .md
  ↓
mark_apply_finished('done'|'aborted'|'failed')

设计要点
--------
- **不轮询**：worker 协程 await asyncio.Event.wait()，approve 时 set，跑完 clear。
  没事的时候 worker 完全不耗 CPU。
- **断点续跑**：startup 时把卡在 running 的全部回滚成 queued，避免上次进程崩溃留死任务。
- **同进程隔离**：worker loop 与 FastAPI 共用 event loop，崩了 try/except 兜底，
  不影响 API 服务。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from kg import ProposalRepository, ProposalSchema

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# 模块级信号 + worker 句柄
# --------------------------------------------------------------------------

_apply_signal: Optional[asyncio.Event] = None
_worker_task: Optional[asyncio.Task] = None
_stopped = False


def notify_apply_pending() -> None:
    """通知 worker：有新的 queued 任务可以跑了。

    安全可重入：worker 没起来时只是 no-op；调用方不需要关心 worker 是否在跑。
    供 ProposalService.approve 在打 queued 后调用。
    """
    if _apply_signal is None:
        return
    _apply_signal.set()


# --------------------------------------------------------------------------
# md 路径推导 + KG 单文件 ingest 钩子
# --------------------------------------------------------------------------

# 解析 [CONCEPT_DONE] 尾标记里的 path=... 字段（仅作兜底；主路径走 history 反查）
# 形如：[CONCEPT_DONE] slug=chain-rule subject=math path=math/chain-rule.md
_CONCEPT_DONE_PATH_RE = re.compile(r"path=([^\s]+)")

# Agent 写盘工具的名字（与 backend.agents.tools.md_writer_tools 中的 name 字段一致）
_TOOL_MD_CREATE = "md_create_concept"
_TOOL_MD_WRITE_FACET = "md_write_facet_section"


def _extract_md_path_from_history(
    history: list, *, tool_names: tuple[str, ...]
) -> Optional[str]:
    """在 ReAct history 中找指定工具的最后一次成功返回，提取里面的 md_path。

    依赖（与 md_writer_tools 实现耦合）：
      - 工具返回是 JSON 字符串
      - 成功路径下含字段 ``md_path``（相对 KNOWLEDGE_ROOT 的相对路径）

    LLM 复述 path 不可靠（会丢字段），但工具返回是代码自己写的，必有。
    返回相对路径字符串；找不到返回 None。
    """
    if not history:
        return None
    # 倒着扫：取该工具的最后一次 ok=true 返回（如果重试过，最后那次才是真正落盘的）
    for msg in reversed(history):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "tool":
            continue
        if msg.get("name") not in tool_names:
            continue
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        try:
            data = json.loads(content)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict) or not data.get("ok"):
            continue
        rel = data.get("md_path") or ""
        if isinstance(rel, str) and rel.strip():
            return rel.strip()
    return None


def _knowledge_root() -> Path:
    """取 KNOWLEDGE_ROOT（与 ingest_okf / md_writer_tools 同源）。"""
    try:
        from config import KNOWLEDGE_ROOT as _CFG_KR  # type: ignore

        return Path(_CFG_KR).resolve()
    except Exception:  # pylint: disable=broad-except
        return Path("knowledge").resolve()


def _resolve_md_path_for_proposal(
    p: ProposalSchema,
    agent_output: str,
    history: Optional[list] = None,
) -> Optional[Path]:
    """根据 proposal + Agent history/output，推导刚被写盘的 md 文件绝对路径。

    解析优先级（高到低）：
      1. **从 ReAct history 抓写盘工具的 ok=true 返回里的 md_path**（最可靠：
         工具返回是代码生成的，结构稳定；不依赖 LLM 复述）
      2. concept 分支：[CONCEPT_DONE] 尾标记里的 path=...（LLM 复述兜底）
      3. facet 分支：payload.slug + KG 反查 subject → <root>/<subject>/<slug>.md

    全部失败返回 None（调用方跳过 KG 同步）。
    """
    root = _knowledge_root()
    payload = p.payload or {}

    # ---------- 优先级 1：从 history 抓工具返回 ----------
    if p.op == "suggest_missing_concept":
        tools = (_TOOL_MD_CREATE,)
    elif p.op == "suggest_facet_pattern":
        tools = (_TOOL_MD_WRITE_FACET,)
    else:
        tools = ()

    if tools:
        rel = _extract_md_path_from_history(history or [], tool_names=tools)
        if rel:
            cand = (root / rel).resolve()
            if cand.exists():
                return cand
            logger.warning(
                "apply_worker: history 中工具返回的 md_path 不存在 id=%s rel=%s root=%s",
                p.id,
                rel,
                root,
            )
            # 不直接 return None，继续走兜底（理论上不应该发生，但留个机会）

    # ---------- 优先级 2：concept 尾标记 path= ----------
    if p.op == "suggest_missing_concept":
        m = _CONCEPT_DONE_PATH_RE.search(agent_output or "")
        if m:
            rel = m.group(1).strip().strip("`'\"")
            cand = (root / rel).resolve()
            if cand.exists():
                return cand
            logger.warning("apply_worker: [CONCEPT_DONE] 给出的 path 不存在: %s", cand)
        logger.warning(
            "apply_worker: concept proposal id=%s 既无工具返回也无 path=，跳过 KG 同步",
            p.id,
        )
        return None

    # ---------- 优先级 3：facet 走 slug + KG.subject 推路径 ----------
    if p.op == "suggest_facet_pattern":
        slug = str(payload.get("slug") or "").strip()
        if not slug:
            return None
        # 优先用 payload.subject；否则查 KG
        subject = str(payload.get("subject") or "").strip()
        if not subject:
            try:
                from kg.repositories import ConceptRepository

                c = ConceptRepository().get_by_slug(slug)
                subject = (c.subject if c else "") or ""
            except Exception:  # pylint: disable=broad-except
                logger.exception(
                    "apply_worker: 反查 concept.subject 失败 slug=%s", slug
                )
                return None
        if not subject:
            return None
        cand = (root / subject / f"{slug}.md").resolve()
        return cand if cand.exists() else None

    return None


def _sync_md_to_kg(
    p: ProposalSchema,
    agent_output: str,
    history: Optional[list] = None,
) -> tuple[bool, str, Optional[Path]]:
    """把 Agent 刚写的 md 同步进 KG（增量、单文件）。

    Args:
        p:            刚跑完的 proposal
        agent_output: Agent 最终一段 assistant 文本（用于解析 [CONCEPT_DONE] 兜底）
        history:      ReAct 完整 history（**主路径**：从 md_create_concept /
                      md_write_facet_section 工具返回 JSON 抓 md_path，最可靠）

    Returns:
        (ok, msg, md_path) — ok=False 时 msg 是简短错误描述（写到 apply_error 里留痕）；
        md_path 是解析出的绝对路径（即使 KG ingest 失败也会返回，供重试使用），
        路径本身都拼不出来时为 None。
        本函数本身不抛异常，外层不需要 try/except。
    """
    md_path = _resolve_md_path_for_proposal(p, agent_output, history)
    if md_path is None:
        return False, "md_path_unresolved", None

    try:
        from ingest_okf import ingest_single_md

        report = ingest_single_md(md_path)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception(
            "apply_worker: ingest_single_md 抛异常 id=%s path=%s", p.id, md_path
        )
        return False, f"exception: {exc}", md_path

    if not report.get("ok"):
        err = str(report.get("error") or "unknown")
        logger.warning(
            "apply_worker: ingest_single_md 失败 id=%s path=%s err=%s",
            p.id,
            md_path,
            err,
        )
        return False, err, md_path

    logger.info(
        "apply_worker: KG 同步成功 id=%s cid=%s action=%s facet=%s edge=%s dangling=%d",
        p.id,
        report.get("cid"),
        report.get("action"),
        report.get("facet"),
        report.get("edge"),
        len(report.get("dangling") or []),
    )
    return True, "", md_path


# --------------------------------------------------------------------------
# 单条 proposal 的执行
# --------------------------------------------------------------------------


async def _run_one(p: ProposalSchema, repo: ProposalRepository) -> None:
    """跑一条 proposal，把结果写回 apply_status / apply_error。

    判定规则：
      - Agent 抛异常              → failed
      - Agent ok=False           → failed（max_steps 用完等）
      - Agent ok=True，含 ABORT  → aborted（业务正常中止，比如查重发现已存在）
      - Agent ok=True，无 ABORT  → done
    """
    # 延迟 import：避免循环依赖 + 让 worker 模块本身轻量
    from services.md_author_service import MdAuthorService

    author = MdAuthorService()
    payload = p.payload or {}

    try:
        if p.op == "suggest_facet_pattern":
            result = await author.apply_facet_proposal(
                proposal_id=p.id,
                slug=str(payload.get("slug") or "").strip(),
                h1=str(payload.get("kind") or "").strip(),
                new_facet_text=str(payload.get("content") or "").strip(),
                subject=str(payload.get("subject") or "") or None,
                proposer=p.proposer,
                observation_count=int(payload.get("observation_count") or 0),
            )
        elif p.op == "suggest_missing_concept":
            result = await author.apply_concept_proposal(
                proposal_id=p.id,
                concept_name=str(payload.get("concept_name") or "").strip(),
                reason_brief=str(payload.get("reason_brief") or ""),
                proposer=p.proposer,
            )
        else:
            repo.mark_apply_finished(p.id, "failed", f"未知 op: {p.op}")
            logger.warning("apply_worker: 未知 op=%s id=%s, 标记 failed", p.op, p.id)
            return
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("apply_worker: Agent 执行异常 id=%s op=%s", p.id, p.op)
        repo.mark_apply_finished(p.id, "failed", f"exception: {exc}")
        return

    ok = bool(result.get("ok"))
    output = str(result.get("output") or "")
    finish_reason = str(result.get("finish_reason") or "")

    if not ok:
        repo.mark_apply_finished(p.id, "failed", finish_reason or "agent unfinished")
        logger.warning(
            "apply_worker: id=%s op=%s 失败 reason=%s",
            p.id,
            p.op,
            finish_reason,
        )
        return

    # 业务级中止（concept 查重发现已有 / facet 主动判断不写 等）
    if "[CONCEPT_ABORT]" in output or "[FACET_ABORT]" in output:
        # 取最后一行作为简明信息
        last_line = output.strip().splitlines()[-1] if output.strip() else ""
        repo.mark_apply_finished(p.id, "aborted", last_line[:500])
        logger.info("apply_worker: id=%s op=%s 业务中止", p.id, p.op)
        return

    # md 已写盘 → 立即把这一个文件同步进 KG（增量、不阻塞主流程）
    history: list[Any] = result.get("history") or []
    sync_ok, sync_err, sync_md = _sync_md_to_kg(p, output, history)
    if sync_ok:
        repo.mark_apply_finished(p.id, "done", "")
        logger.info("apply_worker: id=%s op=%s 已落盘 + KG 同步完成", p.id, p.op)
    else:
        # KG 同步失败不影响 apply 主目标（md 已落盘），但留痕方便 admin 排查
        # 并追加 md=<rel_path>，让重试接口可以准确找到那个文件重新 ingest
        err_text = f"kg_sync_failed: {sync_err}"
        if sync_md is not None:
            try:
                rel = sync_md.relative_to(_knowledge_root())
                err_text += f" | md={rel.as_posix()}"
            except ValueError:
                err_text += f" | md={sync_md.as_posix()}"
        repo.mark_apply_finished(p.id, "done", err_text[:500])
        logger.warning(
            "apply_worker: id=%s op=%s md 已落盘但 KG 同步失败: %s",
            p.id,
            p.op,
            sync_err,
        )


# --------------------------------------------------------------------------
# 主循环
# --------------------------------------------------------------------------


async def _apply_worker_loop() -> None:
    assert _apply_signal is not None
    repo = ProposalRepository()

    # 启动一进来先扫一遍：可能上一次进程刚 approve 完就挂了，DB 里已经躺着 queued
    if repo.count_apply_queued() > 0:
        _apply_signal.set()

    while not _stopped:
        try:
            await _apply_signal.wait()
            # 进入工作模式：把队列里所有任务都消化掉，再回去 wait
            while not _stopped:
                p = repo.pop_one_queued()
                if p is None:
                    break
                await _run_one(p, repo)
            _apply_signal.clear()
        except asyncio.CancelledError:
            logger.info("apply_worker: 收到取消信号，退出")
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception("apply_worker: 主循环异常，5s 后继续")
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                raise


# --------------------------------------------------------------------------
# 启动 / 关闭
# --------------------------------------------------------------------------


def start_apply_worker() -> None:
    """FastAPI startup 钩子里调用：把卡死的 running 回滚 + 起后台 task。"""
    global _apply_signal, _worker_task, _stopped

    if _worker_task is not None and not _worker_task.done():
        logger.info("apply_worker: 已在运行，跳过")
        return

    _stopped = False
    repo = ProposalRepository()
    n = repo.reset_stuck_running_to_queued()
    if n > 0:
        logger.info("apply_worker: 启动时回滚 %d 条卡死的 running -> queued", n)

    _apply_signal = asyncio.Event()
    _worker_task = asyncio.create_task(_apply_worker_loop(), name="apply_worker")
    logger.info("apply_worker: 已启动")


async def stop_apply_worker() -> None:
    """FastAPI shutdown 钩子里调用：取消后台 task，等它退出。"""
    global _stopped, _worker_task

    _stopped = True
    if _apply_signal is not None:
        _apply_signal.set()  # 唤醒 wait()，让循环看到 _stopped=True

    if _worker_task is None:
        return

    _worker_task.cancel()
    try:
        await _worker_task
    except (asyncio.CancelledError, Exception):  # pylint: disable=broad-except
        pass
    _worker_task = None
    logger.info("apply_worker: 已停止")
