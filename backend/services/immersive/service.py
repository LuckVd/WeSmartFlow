"""沉浸式学习主编排（SSE 异步生成器）。

显式逐步编排，非 orchestrator 黑盒：
  Step 1: PlannerAgent → outline.json
  Step 2: 逐章循环（researcher → tex_writer → exercises → speaker_notes → TTS）
  Step 3: 知识图谱节点抽取
  Step 4: sessions/study_logs/documents 落库

每步完成后立即通过 SSE 推送给前端，前端可以在生成过程中浏览已完成的章节。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Awaitable, Callable

from agent_core.agent import ReActAgent
from agent_core.context.static import StaticPromptBuilder
from agent_core.tool import (
    ArxivSearch,
    TavilySearch,
    ToolRegistry,
    WebFetch,
    WriteFileTool,
)

from agent_core.layout import UserDataLayout, slugify as _slugify
from agent_core.tool.pdf_compile import (
    pdf_artifact_revision,
    validate_chapter_pdf,
)

from services.asset_service import archive_immersive_chapter, pack_chapter_bundle
from services.immersive.agents import build_sub_agents
from services.immersive.layout import CourseLayout
from services.immersive.node_extractor import extract_and_persist_nodes
from services.immersive.persistence import (
    create_session,
    read_workspace,
    register_chapter_audio,
    register_chapter_exercises,
    register_chapter_notes,
    register_chapter_overview,
    register_chapter_pdf,
    register_course_outline,
    register_course_plan,
    update_workspace,
    upsert_canvas_block,
    append_session_file,
)
from services.immersive.sse import sse_event, stream_agent_events
from services.immersive.tts import (
    count_beamer_frames,
    generate_speaker_notes,
    run_tts_for_chapter,
)
from services.immersive.utils import to_rel_path
from config import DOCUMENTS_DIR, COURSES_DIR
from services.llm_factory import get_llm
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)

MAX_PARALLEL_TEX_CHAPTERS = 3
# Per generate/resume request local limit for post-PDF enrichment; do not use a
# module-global semaphore because independent user requests must not block each other.
MAX_PARALLEL_ENRICH_CHAPTERS = 3
MAX_CHAPTER_PDF_ATTEMPTS = 2


# Only an explicit next-*chapter* cue is validated here.  Words such as
# “接下来” can introduce another concept in the *same* chapter and must not
# turn a correct lecture into a false negative.
#
# Important: Beamer/Latex often writes a structural title such as
# ``\begin{block}{下一章}`` or ``\begin{frame}{下一章}``.  The old loose regex
# matched only ``下一章}``, then incorrectly failed the already compiled PDF
# during resume audit.  We therefore extract those environments as one semantic
# cue and ignore standalone structural titles.
_CHAPTER_NAVIGATION_RE = re.compile(r"(?:下一章|下章)(?!\s*[}\]])[^\n。；]{0,120}")
_CHAPTER_NAVIGATION_ENV_RE = re.compile(
    r"\\begin\{(?P<env>frame|block|alertblock|exampleblock)\}"
    r"(?:\[[^\]]*\])?\{(?P<title>[^}]*(?:下一章|下章)[^}]*)\}"
    r"(?P<body>[\s\S]{0,1200}?)\\end\{(?P=env)\}",
    re.MULTILINE,
)
_LATEX_COMMAND_RE = re.compile(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?")


def _plain_tex_text(text: str) -> str:
    """Best-effort plain text extraction for short navigation snippets."""
    text = re.sub(r"%.*", "", text)
    text = _LATEX_COMMAND_RE.sub("", text)
    text = re.sub(r"[{}]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _chapter_navigation_cues(source: str) -> list[str]:
    """Extract explicit next-chapter cues without mistaking Beamer titles for text."""
    cues: list[str] = []
    occupied: list[tuple[int, int]] = []

    for match in _CHAPTER_NAVIGATION_ENV_RE.finditer(source):
        title = match.group("title") or ""
        body = match.group("body") or ""
        cue = _plain_tex_text(f"{title} {body}")
        if cue:
            cues.append(cue)
            occupied.append(match.span())

    def in_structural_env(pos: int) -> bool:
        return any(start <= pos < end for start, end in occupied)

    for match in _CHAPTER_NAVIGATION_RE.finditer(source):
        if in_structural_env(match.start()):
            continue
        cue = _plain_tex_text(match.group(0))
        if cue:
            cues.append(cue)

    return cues


def _chapter_label(chapter: dict, fallback_index: int) -> str:
    """Render one outline item as a stable label for prompts and diagnostics."""
    chapter_id = chapter.get("chapter_id", fallback_index + 1)
    return f"第{chapter_id}章「{chapter.get('title') or f'第{chapter_id}章'}」"


def _chapter_navigation_context(chapters: list[dict], index: int) -> dict:
    """Return the canonical previous/current/next outline context for a chapter."""
    current = chapters[index]
    return {
        "previous": chapters[index - 1] if index > 0 else None,
        "current": current,
        "next": chapters[index + 1] if index + 1 < len(chapters) else None,
        "index": index,
        "total": len(chapters),
    }


def _build_tex_prompt(
    *,
    topic: str,
    chapters: list[dict],
    index: int,
    research_path: Path,
    tex_path: Path,
    images_dir: Path,
) -> str:
    """Build a chapter prompt with authoritative outline continuity context."""
    context = _chapter_navigation_context(chapters, index)
    current = context["current"]
    current_id = current.get("chapter_id", index + 1)
    previous = context["previous"]
    following = context["next"]
    roadmap = " → ".join(
        _chapter_label(chapter, position) for position, chapter in enumerate(chapters)
    )
    previous_text = (
        _chapter_label(previous, index - 1) if previous else "无（这是第一章）"
    )
    next_text = (
        _chapter_label(following, index + 1) if following else "无（这是最后一章）"
    )
    navigation_rule = (
        f"不必强行预告下一章，可以独立收束；如需在结尾预告下一章，只能指向「{next_text}」；若明确写出下一章章号或标题，仍不得改写其章节号或主题，不得倒退到上一章或跳到其他章节。"
        if following
        else "这是最后一章：禁止写“下一章 / 下章 / 接下来进入某章”等课程导航语。"
    )
    return (
        f"为课程「{topic}」{_chapter_label(current, index)}生成 Beamer 讲义。\n"
        f"课程总进度：第 {index + 1}/{len(chapters)} 个位置；当前正式章节编号为 {current_id}。\n"
        f"完整课程路线（唯一权威顺序）：{roadmap}\n"
        f"上一章：{previous_text}\n"
        f"下一章：{next_text}\n"
        f"课程衔接规则：{navigation_rule}\n"
        "不要根据学科常识猜测章节顺序；不要引用课程路线以外的章节作为“下一章”。\n"
        f"参考资料文件：{research_path}\n"
        f"TeX 输出路径：{tex_path}\n"
        f"图片输出目录：{images_dir}\n"
        f"知识点：{', '.join(current.get('knowledge_points', []))}\n"
        f"难度：{current.get('difficulty', '基础')}"
    )


def _chapter_refs_in_cue(cue: str, chapters: list[dict]) -> dict[int, str]:
    """Return outline chapters explicitly referenced by a navigation cue."""
    refs: dict[int, str] = {}
    for position, chapter in enumerate(chapters):
        chapter_id = str(chapter.get("chapter_id", position + 1))
        title = str(chapter.get("title") or "").strip()
        has_id = bool(re.search(rf"第\s*{re.escape(chapter_id)}\s*章", cue))
        has_title = bool(title and title in cue)
        if has_id or has_title:
            refs[position] = _chapter_label(chapter, position)
    return refs


def validate_chapter_navigation(
    tex_path: Path, chapters: list[dict], index: int
) -> str | None:
    """Reject only explicit next-chapter cues that point to the wrong outline item."""
    if not tex_path.is_file():
        return f"TeX 文件不存在，无法校验章节衔接: {tex_path}"
    try:
        source = tex_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return f"TeX 文件读取失败: {exc}"

    context = _chapter_navigation_context(chapters, index)
    cues = _chapter_navigation_cues(source)
    if not cues:
        return None
    next_chapter = context["next"]
    if next_chapter is None:
        return f"最后一章不应出现课程导航语: {cues[0]}"

    expected_index = index + 1
    expected_label = _chapter_label(next_chapter, expected_index)
    for cue in cues:
        refs = _chapter_refs_in_cue(cue, chapters)
        # A generic cue such as "下一章我们继续深化这个想法" is allowed.  The
        # validator is only here to catch explicit wrong-direction references,
        # e.g. chapter 3 pointing back to chapter 2 or skipping to chapter 5.
        if not refs or expected_index in refs:
            continue
        wrong_label = next(iter(refs.values()))
        return (
            f"章节衔接错误：{_chapter_label(context['current'], index)} 的导航语"
            f"「{cue}」显式指向 {wrong_label}，不是下一章 {expected_label}"
        )
    return None


def _log_generation_timing(
    session_id: str | None, milestone: str, started_at: float, **fields
) -> int:
    """Log an aggregate milestone without recording course content or prompts."""
    elapsed_ms = round((time.perf_counter() - started_at) * 1000)
    logger.info(
        "immersive_timing session=%s milestone=%s elapsed_ms=%d %s",
        safe_log(session_id or ""),
        milestone,
        elapsed_ms,
        " ".join(f"{key}={value}" for key, value in fields.items()),
    )
    return elapsed_ms


def _replace_chapter_workspace_state(
    session_id: str, chapter_id: int, patch: dict
) -> list[dict]:
    """Persist one chapter state without discarding the other chapters.

    ``learning_ready`` means its verified PDF can be read now.  It is separate
    from ``ready``, which still means every selected enrichment has completed.
    """
    current = update_workspace(session_id)
    workspace = current.get("workspace", {}) or {}
    chapters = list(workspace.get("chapters", []) or [])
    for index, item in enumerate(chapters):
        if item.get("chapter_id") == chapter_id:
            chapters[index] = {**item, **patch}
            break
    else:
        chapters.append(patch)
    return chapters


def _chapter_pdf_error(
    pdf_path: Path,
    tex_path: Path | None = None,
    images_dir: Path | None = None,
    chapters: list[dict] | None = None,
    chapter_index: int | None = None,
) -> str | None:
    """Return the publication error for a PDF, including its visual assets."""
    if tex_path is None:
        tex_path = pdf_path.with_suffix(".tex")
    if images_dir is None:
        images_dir = tex_path.parent / "images"
    artifact_error = validate_chapter_pdf(pdf_path, tex_path, images_dir)
    if artifact_error:
        return artifact_error
    if chapters is not None and chapter_index is not None:
        return validate_chapter_navigation(tex_path, chapters, chapter_index)
    return None


def _pdf_is_ready(
    pdf_path: Path,
    tex_path: Path | None = None,
    images_dir: Path | None = None,
    chapters: list[dict] | None = None,
    chapter_index: int | None = None,
) -> bool:
    """判断 PDF 是否真实可交付，而不是仅仅存在。"""
    error = _chapter_pdf_error(pdf_path, tex_path, images_dir, chapters, chapter_index)
    if error:
        if pdf_path.exists():
            logger.warning("PDF 校验失败，将视为不可用: %s，原因: %s", pdf_path, error)
        return False
    return True


def _published_pdf_doc_id(session_id: str, chapter_id: int) -> str:
    """Return the already registered doc_id for a chapter PDF, if any."""
    workspace = read_workspace(session_id)
    for item in (workspace.get("workspace", {}) or {}).get("chapters", []) or []:
        if item.get("chapter_id") == chapter_id and item.get("pdf_doc_id"):
            return str(item.get("pdf_doc_id") or "")
    for block in workspace.get("canvas_blocks", []) or []:
        if block.get("id") == f"pdf_ch{chapter_id}":
            data = block.get("data") or {}
            if data.get("doc_id"):
                return str(data.get("doc_id") or "")
    return ""


async def _publish_chapter_pdf_ready(
    *,
    session_id: str,
    topic: str,
    user_id: str,
    course: "CourseLayout",
    chapters: list[dict],
    index: int,
    ch_info: dict,
    total_ch: int,
    enable_audio: bool,
    generation_started_at: float | None = None,
    all_files_for_session: list[dict] | None = None,
    set_current_chapter: bool = False,
) -> dict | None:
    """Publish a verified chapter PDF immediately, before optional enrichments.

    The TeX stage can run in parallel, but user-visible publication must not wait
    for an earlier chapter's quiz/audio/node extraction.  This helper performs
    the complete publication transaction: document registration, pdf block upsert,
    chapter ``learning_ready`` workspace state, and SSE payload preparation.
    """
    ch_id = ch_info.get("chapter_id", index + 1)
    ch_title = ch_info.get("title", f"第{ch_id}章")
    tex_path = course.tex_file(ch_id)
    pdf_path = course.pdf_file(ch_id)
    images_dir = course.chapter_images_dir(ch_id)
    if not _pdf_is_ready(pdf_path, tex_path, images_dir, chapters, index):
        return None

    pdf_rel = to_rel_path(str(pdf_path))
    pdf_revision = _pdf_revision(pdf_path)
    num_frames = count_beamer_frames(tex_path)
    pdf_doc_id = _published_pdf_doc_id(session_id, ch_id)
    if not pdf_doc_id:
        try:
            pdf_doc_id = (
                await asyncio.to_thread(
                    lambda: register_chapter_pdf(
                        session_id=session_id,
                        topic=topic,
                        chapter_id=ch_id,
                        chapter_title=ch_title,
                        pdf_path=pdf_path,
                        num_pages=num_frames,
                        user_id=user_id,
                        node_ids=[],
                    ),
                )
                or ""
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("单章 PDF 登记失败 ch=%s: %s", ch_id, exc)

    if not pdf_doc_id:
        logger.warning("跳过 PDF 即时发布：第%s章登记 doc_id 失败", ch_id)
        return None

    pdf_file = {
        "file_id": pdf_doc_id,
        "file_type": "chapter_pdf",
        "title": f"第{ch_id}章 {ch_title}",
    }
    if all_files_for_session is not None and not any(
        item.get("file_id") == pdf_doc_id for item in all_files_for_session
    ):
        all_files_for_session.append(pdf_file)
    append_session_file(
        session_id, pdf_doc_id, f"第{ch_id}章 {ch_title}", "chapter_pdf"
    )

    pdf_block = {
        "id": f"pdf_ch{ch_id}",
        "type": "pdf",
        "title": f"第{ch_id}章 {ch_title}",
        "status": "ready",
        "chapter_id": ch_id,
        "data": {
            "url": f"/api/documents/{pdf_doc_id}/raw",
            "pdf_path": pdf_rel,
            "doc_id": pdf_doc_id,
            "artifact_revision": pdf_revision,
            "num_pages": num_frames,
            "audio_enabled": enable_audio,
            "audio_files": [],
            "audio_doc_id": "",
        },
    }
    upsert_canvas_block(session_id, pdf_block)

    status_block = {
        "id": f"chapter_{ch_id}_status",
        "type": "chapter_status",
        "title": f"第{ch_id}章 {ch_title}",
        "status": "learning_ready",
        "chapter_id": ch_id,
        "data": {
            "stage": "learning_ready",
            "index": index,
            "total": total_ch,
            "block_ids": [f"chapter_{ch_id}_status", pdf_block["id"]],
            "message": "PDF 已就绪，可先开始学习；其余资源继续补全。",
        },
    }
    upsert_canvas_block(session_id, status_block)

    learning_state = {
        "chapter_id": ch_id,
        "title": ch_title,
        "status": "learning_ready",
        "block_ids": [status_block["id"], pdf_block["id"]],
        "files": [pdf_rel],
        "pdf_doc_id": pdf_doc_id,
        "pdf_revision": pdf_revision,
        "audio_enabled": enable_audio,
        "audio_files": [],
        "speaker_notes_count": 0,
        "learning_ready_at_ms": (
            _log_generation_timing(
                session_id,
                "first_chapter_ready" if index == 0 else "chapter_pdf_ready",
                generation_started_at,
                chapter_id=ch_id,
            )
            if generation_started_at is not None
            else 0
        ),
    }
    chapters_state = _replace_chapter_workspace_state(session_id, ch_id, learning_state)
    generated_chapters = len(
        [item for item in chapters_state if _chapter_is_user_available(item)]
    )
    workspace_patch = {
        "chapters": chapters_state,
        "generated_chapters": generated_chapters,
        "planned_chapters": total_ch,
    }
    if set_current_chapter:
        workspace_patch["current_chapter_id"] = ch_id
    update_workspace(
        session_id,
        stage="partial_ready",
        next_actions=[
            {"type": "start_learning", "label": "开始学习本章"},
            {"type": "continue_generation", "label": "继续补全课程"},
        ],
        workspace=workspace_patch,
    )

    return {
        "chapter_id": ch_id,
        "title": ch_title,
        "pdf_block": pdf_block,
        "status_block": status_block,
        "pdf_doc_id": pdf_doc_id,
        "pdf_rel": pdf_rel,
        "pdf_revision": pdf_revision,
        "num_frames": num_frames,
        "events": [
            sse_event(
                "workspace_update",
                event="block_created",
                session_id=session_id,
                block=pdf_block,
            ),
            sse_event(
                "workspace_update",
                event="block_updated",
                session_id=session_id,
                block=status_block,
            ),
            sse_event(
                "chapter_learning_ready",
                index=index,
                total=total_ch,
                session_id=session_id,
                data={
                    "chapter_id": ch_id,
                    "title": ch_title,
                    "pdf_exists": True,
                    "pdf_path": pdf_rel,
                    "pdf_doc_id": pdf_doc_id,
                    "pdf_revision": pdf_revision,
                    "num_frames": num_frames,
                },
            ),
        ],
    }


def _file_is_ready(path: Path, min_size: int = 50) -> bool:
    """判断普通文本/媒体产物是否已实际落盘。"""
    try:
        return path.exists() and path.is_file() and path.stat().st_size > min_size
    except OSError:
        return False


def _chapter_is_user_available(chapter: dict) -> bool:
    """章节已能被用户学习：完整 ready 或至少 PDF 已发布。"""
    return chapter.get("status") in {"ready", "learning_ready"}


def _chapter_artifact_status(
    course: CourseLayout,
    ch_info: dict,
    index: int,
    chapters: list[dict] | None = None,
    enable_audio: bool = False,
    enable_exercises: bool = True,
) -> dict:
    """扫描章节磁盘产物，返回恢复生成时可信的真实状态。"""
    ch_id = ch_info.get("chapter_id", index + 1)
    chapter_dir = course.chapter_dir(ch_id)
    research_path = chapter_dir / "research.json"
    tex_path = course.tex_file(ch_id)
    pdf_path = course.pdf_file(ch_id)
    exercises_path = course.exercises_file(ch_id)
    overview_path = chapter_dir / f"chapter_{ch_id:02d}_overview.md"
    notes_path = chapter_dir / "speaker_notes.json"
    audio_dir = chapter_dir / "audio"

    tex_ready = _file_is_ready(tex_path)
    pdf_error = _chapter_pdf_error(
        pdf_path, tex_path, chapter_dir / "images", chapters, index
    )
    num_frames = count_beamer_frames(tex_path) if tex_ready else 0
    audio_files = (
        sorted(f.name for f in audio_dir.iterdir() if f.suffix.lower() == ".wav")
        if audio_dir.exists()
        else []
    )

    checks = {
        "research": _file_is_ready(research_path),
        "tex": tex_ready,
        "pdf": pdf_error is None,
        "exercises": _file_is_ready(exercises_path),
        "overview_md": _file_is_ready(overview_path),
        "speaker_notes": _file_is_ready(notes_path, min_size=2),
        "audio": num_frames > 0 and len(audio_files) >= num_frames,
    }
    # `research.json` is necessary before a chapter is generated, but it should
    # not make resume regenerate a chapter whose user-facing artifacts already
    # exist and pass validation. Older interrupted runs can have a valid PDF,
    # exercises, and audio while the researcher failed to persist research.json.
    required_keys = ["tex", "pdf"]
    if not checks["pdf"]:
        required_keys.insert(0, "research")
    if enable_exercises:
        required_keys.append("exercises")
    if enable_audio:
        required_keys.extend(["speaker_notes", "audio"])
    required_checks = {key: checks[key] for key in required_keys}
    missing = [name for name, ready in required_checks.items() if not ready]
    optional_keys = ["overview_md"]
    optional_missing = [name for name in optional_keys if not checks[name]]
    if checks["pdf"] and not checks["research"]:
        optional_missing.append("research")
    if pdf_error and pdf_path.exists():
        missing.append(f"pdf_invalid: {pdf_error}")

    files = []
    if checks["pdf"]:
        files.append(to_rel_path(str(pdf_path)))
    if checks["exercises"]:
        files.append(to_rel_path(str(exercises_path)))
    if checks["overview_md"]:
        files.append(to_rel_path(str(overview_path)))

    # audio url 由前端依据 audio_doc_id 自行拼接 /api/documents/{doc_id}/asset/{filename}，
    # 这里只给 filename 占位（doc_id 在外层 _audit_resume_chapters 阶段补登记后回填）。
    audio_files_data = (
        [
            {
                "filename": filename,
                "url": "",
                "duration_seconds": 0,
                "success": True,
            }
            for filename in audio_files
        ]
        if enable_audio
        else []
    )

    return {
        "ready": not missing,
        "checks": checks,
        "missing": missing,
        "optional_missing": optional_missing,
        "files": files,
        "pdf_revision": _pdf_revision(pdf_path) if checks["pdf"] else "",
        "num_frames": num_frames,
        "audio_files_count": len(audio_files_data),
        "audio_files": audio_files_data,
    }


def _read_speaker_notes(notes_path: Path) -> list[str]:
    """Best-effort load of persisted speaker notes for audio re-registration."""
    if not notes_path.exists() or notes_path.stat().st_size <= 0:
        return []
    try:
        data = json.loads(notes_path.read_text(encoding="utf-8"))
    except Exception:  # pylint: disable=broad-except
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def _with_audio_urls(audio_files: list[dict], audio_doc_id: str) -> list[dict]:
    """Attach document asset URLs to audio frame metadata once doc_id exists."""
    hydrated: list[dict] = []
    for item in audio_files or []:
        frame = dict(item or {})
        filename = frame.get("filename") or ""
        if audio_doc_id and filename and not frame.get("url"):
            frame["url"] = f"/api/documents/{audio_doc_id}/asset/{filename}"
        hydrated.append(frame)
    return hydrated


def _chapter_requires_followup(chapter: dict) -> bool:
    """Whether a chapter still needs generation/resume work before final completion."""
    if chapter.get("status") != "ready":
        return True
    if chapter.get("audio_enabled"):
        if not chapter.get("audio_doc_id"):
            return True
        if not chapter.get("audio_files"):
            return True
    return False


def _pdf_revision(pdf_path: Path) -> str:
    """Return a revision only for a fully publishable PDF."""
    try:
        return pdf_artifact_revision(pdf_path)
    except OSError as exc:
        logger.warning("无法生成 PDF revision: %s", exc)
        return ""


def _audit_resume_chapters(
    session_id: str,
    course: CourseLayout,
    chapters: list[dict],
    chapters_state: list[dict],
    *,
    topic: str = "",
    user_id: str = "",
    enable_audio: bool = False,
    enable_exercises: bool = True,
) -> tuple[list[dict], set[int], int]:
    """恢复生成前全量审计章节产物，并用真实磁盘状态覆盖旧 workspace。"""
    state_by_id = {
        item.get("chapter_id"): item
        for item in chapters_state
        if item.get("chapter_id") is not None
    }
    audited_state: list[dict] = []
    pending_ids: set[int] = set()

    for index, ch_info in enumerate(chapters):
        ch_id = ch_info.get("chapter_id", index + 1)
        title = ch_info.get("title", f"第{ch_id}章")
        old_item = state_by_id.get(ch_id, {})
        artifact_status = _chapter_artifact_status(
            course,
            ch_info,
            index,
            chapters=chapters,
            enable_audio=enable_audio,
            enable_exercises=enable_exercises,
        )
        status = (
            "ready"
            if artifact_status["ready"]
            else "learning_ready"
            if artifact_status["checks"].get("pdf")
            else "pending"
        )
        if status != "ready":
            pending_ids.add(ch_id)
            logger.warning(
                "resume: 章节产物审计未通过 ch=%s missing=%s",
                ch_id,
                artifact_status["missing"],
            )

        pdf_doc_id = old_item.get("pdf_doc_id", "") or ""
        exercises_doc_id = old_item.get("exercises_doc_id", "") or ""
        audio_doc_id = old_item.get("audio_doc_id", "") or ""
        notes_doc_id = old_item.get("notes_doc_id", "") or ""
        if topic and user_id:
            if artifact_status["checks"].get("pdf") and not pdf_doc_id:
                try:
                    pdf_doc_id = (
                        register_chapter_pdf(
                            session_id=session_id,
                            topic=topic,
                            chapter_id=ch_id,
                            chapter_title=title,
                            pdf_path=course.pdf_file(ch_id),
                            num_pages=artifact_status["num_frames"],
                            user_id=user_id,
                        )
                        or ""
                    )
                    if pdf_doc_id:
                        append_session_file(
                            session_id,
                            pdf_doc_id,
                            f"第{ch_id}章 {title}",
                            "chapter_pdf",
                        )
                        logger.info(
                            "resume: 已补登记既有 PDF ch=%s doc_id=%s",
                            ch_id,
                            pdf_doc_id,
                        )
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("resume: 补登记既有 PDF 失败 ch=%s: %s", ch_id, exc)
            if (
                enable_exercises
                and artifact_status["checks"].get("exercises")
                and not exercises_doc_id
            ):
                try:
                    exercises_doc_id = (
                        register_chapter_exercises(
                            session_id=session_id,
                            topic=topic,
                            chapter_id=ch_id,
                            chapter_title=title,
                            exercises_path=course.exercises_file(ch_id),
                            user_id=user_id,
                        )
                        or ""
                    )
                    if exercises_doc_id:
                        append_session_file(
                            session_id,
                            exercises_doc_id,
                            f"第{ch_id}章 {title} · 小测",
                            "chapter_exercises",
                        )
                        logger.info(
                            "resume: 已补登记既有习题 ch=%s doc_id=%s",
                            ch_id,
                            exercises_doc_id,
                        )
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("resume: 补登记既有习题失败 ch=%s: %s", ch_id, exc)
            if enable_audio and artifact_status["checks"].get("speaker_notes"):
                notes_path = course.chapter_dir(ch_id) / "speaker_notes.json"
                speaker_notes = _read_speaker_notes(notes_path)
                if not notes_doc_id:
                    try:
                        notes_doc_id = (
                            register_chapter_notes(
                                session_id=session_id,
                                topic=topic,
                                chapter_id=ch_id,
                                chapter_title=title,
                                notes_path=notes_path,
                                user_id=user_id,
                            )
                            or ""
                        )
                        if notes_doc_id:
                            append_session_file(
                                session_id,
                                notes_doc_id,
                                f"第{ch_id}章 {title} · 讲解稿",
                                "chapter_notes",
                            )
                            logger.info(
                                "resume: 已补登记既有讲解稿 ch=%s doc_id=%s",
                                ch_id,
                                notes_doc_id,
                            )
                    except Exception as exc:  # pylint: disable=broad-except
                        logger.warning(
                            "resume: 补登记既有讲解稿失败 ch=%s: %s", ch_id, exc
                        )
                if artifact_status["checks"].get("audio") and not audio_doc_id:
                    try:
                        audio_results = [
                            {
                                "filename": item.get("filename", ""),
                                "duration_seconds": item.get("duration_seconds", 0),
                                "success": True,
                            }
                            for item in artifact_status["audio_files"]
                            if item.get("filename")
                        ]
                        audio_doc_id = (
                            register_chapter_audio(
                                session_id=session_id,
                                topic=topic,
                                chapter_id=ch_id,
                                chapter_title=title,
                                audio_dir=course.chapter_dir(ch_id) / "audio",
                                audio_results=audio_results,
                                speaker_notes=speaker_notes,
                                user_id=user_id,
                            )
                            or ""
                        )
                        if audio_doc_id:
                            append_session_file(
                                session_id,
                                audio_doc_id,
                                f"第{ch_id}章 {title} · 音频",
                                "chapter_audio",
                            )
                            logger.info(
                                "resume: 已补登记既有音频 ch=%s doc_id=%s",
                                ch_id,
                                audio_doc_id,
                            )
                    except Exception as exc:  # pylint: disable=broad-except
                        logger.warning(
                            "resume: 补登记既有音频失败 ch=%s: %s", ch_id, exc
                        )

        audio_files = _with_audio_urls(artifact_status["audio_files"], audio_doc_id)
        if enable_exercises and status == "ready" and not exercises_doc_id:
            status = "learning_ready"
            pending_ids.add(ch_id)
            if "exercises_doc_id" not in artifact_status["missing"]:
                artifact_status["missing"].append("exercises_doc_id")
            logger.warning(
                "resume: 章节习题未发布 ch=%s missing=%s",
                ch_id,
                artifact_status["missing"],
            )
        if enable_audio and status == "ready" and not audio_doc_id:
            status = "learning_ready"
            pending_ids.add(ch_id)
            if "audio_doc_id" not in artifact_status["missing"]:
                artifact_status["missing"].append("audio_doc_id")
            logger.warning(
                "resume: 章节音频未发布 ch=%s missing=%s",
                ch_id,
                artifact_status["missing"],
            )

        block_ids = [f"chapter_{ch_id}_status"]
        if artifact_status["checks"].get("overview_md"):
            block_ids.append(f"md_ch{ch_id}")
        if artifact_status["checks"].get("pdf"):
            block_ids.append(f"pdf_ch{ch_id}")
        if enable_exercises and artifact_status["checks"].get("exercises"):
            block_ids.append(f"quiz_ch{ch_id}_bank")
        for block_id in old_item.get("block_ids") or []:
            if block_id not in block_ids:
                block_ids.append(block_id)

        audited_item = {
            **old_item,
            "chapter_id": ch_id,
            "title": title,
            "status": status,
            "block_ids": block_ids,
            "files": artifact_status["files"],
            "pdf_revision": artifact_status["pdf_revision"],
            "audio_enabled": enable_audio,
            "audio_files": audio_files,
            "speaker_notes_count": len(audio_files),
            "artifact_status": artifact_status["checks"],
            "artifact_missing": artifact_status["missing"],
            "artifact_optional_missing": artifact_status["optional_missing"],
        }
        if pdf_doc_id:
            audited_item["pdf_doc_id"] = pdf_doc_id
        if exercises_doc_id:
            audited_item["exercises_doc_id"] = exercises_doc_id
        if audio_doc_id:
            audited_item["audio_doc_id"] = audio_doc_id
        if notes_doc_id:
            audited_item["notes_doc_id"] = notes_doc_id
        audited_state.append(audited_item)

        if status != "ready":
            upsert_canvas_block(
                session_id,
                {
                    "id": f"chapter_{ch_id}_status",
                    "type": "chapter_status",
                    "title": f"第{ch_id}章 {title}",
                    "status": status,
                    "chapter_id": ch_id,
                    "data": {
                        "stage": status,
                        "artifact_status": artifact_status["checks"],
                        "artifact_missing": artifact_status["missing"],
                        "artifact_optional_missing": artifact_status[
                            "optional_missing"
                        ],
                    },
                },
            )

    generated_chapters = len(
        [item for item in audited_state if _chapter_is_user_available(item)]
    )
    return audited_state, pending_ids, generated_chapters


def _backfill_chapter_block_doc_ids(session_id: str, chapters_state: list[dict]) -> int:
    """回填 canvas_blocks 里 pdf/quiz 块缺失的 doc_id。

    早期生成的章节（尤其第 1 章）存在 canvas_blocks 中 pdf_chX.doc_id、
    quiz_chX_bank.doc_id 为空的历史数据（chapters_state 里 pdf_doc_id /
    exercises_doc_id 其实已登记）。前端 PDF 渲染和习题拉取都依赖这些 doc_id，
    缺失会导致"PDF 不可用 / 习题不显示"。此处在 resume 时统一补齐。
    """
    state_by_id = {
        c.get("chapter_id"): c
        for c in (chapters_state or [])
        if c.get("chapter_id") is not None
    }
    blocks = read_workspace(session_id).get("canvas_blocks", []) or []
    by_id = {b.get("id"): b for b in blocks}
    backfilled = 0

    for ch_id, st in state_by_id.items():
        pdf_block = by_id.get(f"pdf_ch{ch_id}")
        if pdf_block:
            data = dict(pdf_block.get("data") or {})
            changed = False
            if not data.get("doc_id") and st.get("pdf_doc_id"):
                data["doc_id"] = st["pdf_doc_id"]
                changed = True
            if not data.get("url") and st.get("pdf_doc_id"):
                data["url"] = f"/api/documents/{st['pdf_doc_id']}/raw"
                changed = True
            audio_doc_id = st.get("audio_doc_id") or data.get("audio_doc_id") or ""
            if not data.get("audio_doc_id") and audio_doc_id:
                data["audio_doc_id"] = audio_doc_id
                changed = True
            if st.get("audio_files"):
                hydrated_audio = _with_audio_urls(
                    st.get("audio_files") or [], audio_doc_id
                )
                current_audio = data.get("audio_files") or []
                if len(current_audio) < len(hydrated_audio) or any(
                    item.get("filename") and not item.get("url")
                    for item in current_audio
                ):
                    data["audio_files"] = hydrated_audio
                    changed = True
            if changed:
                upsert_canvas_block(session_id, {**pdf_block, "data": data})
                backfilled += 1
                logger.info("回填 pdf_ch%s 的文档/音频信息", ch_id)

        quiz_block = by_id.get(f"quiz_ch{ch_id}_bank")
        if quiz_block:
            data = dict(quiz_block.get("data") or {})
            if not data.get("doc_id") and st.get("exercises_doc_id"):
                data["doc_id"] = st["exercises_doc_id"]
                data["exercises_doc_id"] = st["exercises_doc_id"]
                upsert_canvas_block(session_id, {**quiz_block, "data": data})
                backfilled += 1
                logger.info(
                    "回填 quiz_ch%s_bank 的 doc_id=%s",
                    ch_id,
                    data.get("doc_id"),
                )

    return backfilled


def _difficulty_label(value: str) -> str:
    mapping = {
        "easy": "基础",
        "medium": "进阶",
        "hard": "挑战",
        "基础": "基础",
        "中等": "进阶",
        "困难": "挑战",
    }
    return mapping.get(str(value or "").strip(), str(value or "基础"))


def build_plan_markdown(topic: str, outline: dict) -> str:
    """将 Planner 产出的 outline 转成面向学习者的可读计划（精简版）。
    仅作为 LLM 个性化生成失败时的 fallback。
    """
    chapters = outline.get("chapters") or []
    lines = [f"# {topic} 学习计划", ""]

    # 章节路线（核心信息）
    lines.append("## 章节路线")
    for i, ch in enumerate(chapters, start=1):
        title = ch.get("title") or f"第{i}章"
        difficulty = _difficulty_label(ch.get("difficulty", "基础"))
        kps = ch.get("knowledge_points") or []
        kp_text = "、".join(kps[:4]) if kps else ""
        line = f"{i}. **{title}**（{difficulty}）"
        if kp_text:
            line += f"：{kp_text}"
        lines.append(line)

    # 首章引导（仅一句）
    if chapters:
        first_title = chapters[0].get("title") or "第一节"
        lines.extend(
            [
                "",
                f"> 先从「{first_title}」开始；PDF / 小测会在后台继续生成，不阻塞阅读。",
            ]
        )
    return "\n".join(lines)


def _clean_plan_markdown(raw: str, topic: str) -> str:
    """后处理 LLM 生成的学习建议 Markdown，确保格式质量。

    处理内容：
    1. 去除 ```markdown ``` 代码块包裹
    2. 去除其他语言标记的代码块包裹（如 ```text ```）
    3. 确保有一级标题
    4. 去除首尾多余空行
    """
    import re

    content = raw.strip()

    # 去除最外层的代码块包裹（支持 ```markdown、```md、```text、``` 等）
    # 匹配模式：开头的 ```xxx\n 和结尾的 \n```
    code_block_pattern = re.compile(
        r"^```(?:markdown|md|text|plain)?\s*\n(.*?)\n```\s*$",
        re.DOTALL,
    )
    match = code_block_pattern.match(content)
    if match:
        content = match.group(1).strip()

    # 如果整个内容仍然被代码块包裹（可能有多层），继续剥离
    while content.startswith("```") and content.endswith("```"):
        # 去掉第一行（```xxx）和最后一行（```）
        lines = content.split("\n")
        if len(lines) >= 3:
            content = "\n".join(lines[1:-1]).strip()
        else:
            break

    # 确保有一级标题
    if not content.startswith("#"):
        content = f"# {topic} 学习建议\n\n{content}"

    # 确保标题后有空行
    lines = content.split("\n")
    if len(lines) >= 2 and lines[0].startswith("#") and lines[1].strip() != "":
        lines.insert(1, "")
        content = "\n".join(lines)

    return content


async def build_personalized_plan(
    topic: str,
    outline: dict,
    user_id: str,
    profile_content: str = "",
) -> str:
    """结合用户画像和课程大纲，调用 LLM 生成个性化学习建议。

    与大纲不同，学习建议侧重于：
    - 根据用户背景给出学习策略
    - 根据已有知识基础推荐学习重点/可跳过的内容
    - 给出时间分配建议
    - 提供学习方法建议

    如果 LLM 调用失败，fallback 到 build_plan_markdown。
    """

    # 构建大纲摘要（供 LLM 参考，不需要全部细节）
    chapters = outline.get("chapters") or []
    outline_summary_lines = []
    for i, ch in enumerate(chapters, start=1):
        title = ch.get("title") or f"第{i}章"
        difficulty = ch.get("difficulty", "基础")
        kps = ch.get("knowledge_points") or []
        kp_text = "、".join(kps[:6]) if kps else "无"
        outline_summary_lines.append(
            f"{i}. {title}（难度：{difficulty}）- 知识点：{kp_text}"
        )
    outline_summary = "\n".join(outline_summary_lines)

    # 构建用户画像上下文
    profile_section = ""
    if profile_content and profile_content.strip():
        profile_section = f"""
## 用户画像
{profile_content.strip()}
"""
    else:
        profile_section = """
## 用户画像
暂无用户画像信息（新用户）。请给出通用的学习建议。
"""

    system_prompt = """你是一位经验丰富的学习顾问，擅长根据学生的背景和目标制定个性化学习策略。
你的任务是根据课程大纲和用户画像，生成一份个性化的学习建议。

要求：
1. 直接输出 Markdown 正文，**禁止**用 ```markdown ``` 代码块包裹内容
2. 内容要与大纲有明显差异化——大纲展示"学什么"，你要告诉学生"怎么学"
3. 根据用户的已有知识基础，指出哪些章节可以快速浏览、哪些需要重点攻克
4. 给出合理的时间分配建议（如每章建议花多少时间）
5. 提供具体的学习方法建议（如先看PDF再做题、还是边看边练等）
6. 如果用户有学习历史，参考其掌握度给出针对性建议
7. 语气亲切自然，像一位学长/导师在给建议
8. 总长度控制在 300-600 字之间，不要太长
9. 不要重复罗列大纲中已有的章节标题和知识点列表

格式规范（非常重要，请严格遵守）：
- 第一行必须是 `# 课程名 学习建议` 格式的一级标题
- 开头用 1-2 句话点明这门课对用户的价值和整体学习策略
- 用 `**加粗小标题：**` 分隔不同建议板块（如"建议重点分层："、"时间分配建议："、"具体学法："、"特别建议："）
- 列表项用 `-` 无序列表，步骤用 `1. 2. 3.` 有序列表
- 重点内容用 `**加粗**` 标注
- 段落之间用空行分隔
- 不要使用二级标题(##)，用加粗文本代替小标题
- 不要使用表格"""

    user_prompt = f"""# 课程主题：{topic}

## 课程大纲（共 {len(chapters)} 章）
{outline_summary}
{profile_section}
请为这位学习者生成个性化的学习建议。"""

    try:
        llm = get_llm(user_id, scene="immersive")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = await llm.async_think(
            messages, config={"temperature": 0.7, "max_tokens": 2048}
        )

        if response and response.content and not response.is_error:
            # deepseek 对超长输出会返回 finish_reason=length 硬截断（末句残缺）；
            # 检测到就用更大额度重试一次，避免建议被拦腰截断。
            if getattr(response, "finish_reason", "stop") == "length":
                logger.warning("个性化学习建议被 max_tokens 截断，用 3072 重试一次")
                try:
                    response = await llm.async_think(
                        messages, config={"temperature": 0.7, "max_tokens": 3072}
                    )
                except Exception as retry_err:  # pylint: disable=broad-except
                    logger.warning("学习建议截断重试失败: %s", retry_err)
            content = _clean_plan_markdown(response.content, topic)
            return content
        else:
            logger.warning("LLM 生成个性化学习计划返回空或错误，使用 fallback")
            return build_plan_markdown(topic, outline)
    except Exception as e:
        logger.warning("LLM 生成个性化学习计划失败: %s，使用 fallback", e)
        return build_plan_markdown(topic, outline)


def _safe_load_research(research_path: "Path") -> dict:
    """安全加载 research.json，重点保护 LaTeX 反斜杠序列。

    LLM 写出的 JSON 经常把 LaTeX 命令直接塞进字符串，比如
    ``"...单个能量子满足 $\\epsilon=h\\nu$..."``，这里的 ``\\nu`` 在原始字节
    里其实只有一个反斜杠（``\\n``），结果：
      - 严格 JSON 视为非法转义（如 ``\\f``、``\\v``）→ 直接 loads 失败；
      - 即便解析成功，``\\nu`` 中的 ``\\n`` 也会被 JSON 解释成换行符
        → ``\\nu`` 变 ``\n + u``，``\\frac`` 变 ``\f + rac``，公式被吞。

    因此本函数采用更激进的策略：**任何 ``\\<字母>`` 序列在 loads 之前都先翻倍**，
    这样无论 JSON 视它为合法转义还是非法转义，最终解析出的字符串里都会保留
    完整的 ``\\nu`` / ``\\frac`` 字面，给前端 KaTeX 正常渲染。
    """
    import json as _json
    import re as _re

    if not research_path.exists():
        return {}

    raw = research_path.read_text(encoding="utf-8")

    # 只在"公式分隔符内部"翻倍反斜杠，避免把段落里的 JSON 换行 \n / 制表符 \t
    # 误判成 LaTeX 命令而翻倍——例如 LLM 写的 `$$\nE_n=...`，本意是 `$$` 后接
    # 换行 + `E_n=...`，旧实现会把 `\nE` 当成 LaTeX 命令翻倍成 `\\nE`，结果
    # JSON 解析后字面字符 `\nE_n` 残留到 markdown 里，前端 KaTeX 报错。
    #
    # 公式分隔符列举：$$...$$（多行）、$...$（单行）、\[...\]、\(...\)。
    _MATH_SPAN = _re.compile(
        r"(?P<dd>\$\$[\s\S]+?\$\$)"
        r"|(?P<sd>\$[^\$\n]+?\$)"
        r"|(?P<br>\\\[[\s\S]+?\\\])"
        r"|(?P<pa>\\\([\s\S]+?\\\))"
    )

    def _protect_latex(s: str) -> str:
        # 在公式 span 内，把"孤立的单反斜杠 + LaTeX 命令/标点"翻倍。
        #
        # 难点：raw 字节序列里 ``\\`` 与 ``\\\\`` 都可能合法存在，必须精确
        # 区分"当前 ``\`` 是不是已成对反斜杠的一部分"。Python 正则的
        # ``(?<!\\)`` 只能往前看 1 字节，无法判断成对。因此改用**逐字节
        # 状态机**：扫描时数前面连续反斜杠的奇偶——奇数表示这是孤立 ``\``，
        # 后面紧跟 LaTeX 命令或标点时需要翻倍；偶数表示已成对（已经是合法
        # 的 ``\\`` raw 对，JSON 解码后是单 ``\``，即 LaTeX 行分隔/字面 ``\\``），
        # 保持原样。
        #
        # JSON 解码下，``\\b`` ``\\f`` ``\\n`` ``\\r`` ``\\t`` ``\\u``
        # 是合法转义对（→ 控制字符），但在公式 span 内几乎一定是 LaTeX 命令
        # 前缀（``\beta \frac \nu \rho \tau \upsilon``）：状态机把它们当
        # 成"奇数 ``\`` + 字母"处理——即翻倍——能正确恢复 LaTeX 命令。

        def _double_backslashes_in(span: str) -> str:
            # 检测 span 内 \begin{多行环境}...\end{...} 区间。这些环境里
            # 的 ``\\`` 几乎一定是 LaTeX 行分隔（cases/aligned/array/matrix
            # 等），LLM 常把 raw 写成 2 反斜杠（不够，应 4）。需要在区间内
            # 对 ``\\`` + 字母做"再翻倍"补救。
            #
            # 普通 ``$...$`` 行内公式里的 ``\\psi`` ``\\rangle`` 等是 LLM
            # 写对的 LaTeX 命令前缀，绝不能翻倍。
            MULTI_LINE_ENVS = (
                "cases",
                "aligned",
                "align",
                "gather",
                "gathered",
                "array",
                "matrix",
                "pmatrix",
                "bmatrix",
                "vmatrix",
                "Bmatrix",
                "Vmatrix",
                "split",
                "multline",
                "eqnarray",
            )
            ml_intervals = []  # list of (begin_pos, end_pos, has_newline_decor)
            # 用宽松正则找出 \begin{<env>}…\end{<env>}，无论 raw 反斜杠数
            for bm in _re.finditer(
                r"\\+begin\{(" + "|".join(MULTI_LINE_ENVS) + r")\}",
                span,
            ):
                env = bm.group(1)
                em = _re.search(
                    r"\\+end\{" + env + r"\}",
                    span[bm.end() :],
                )
                if em:
                    abs_end = bm.end() + em.end()
                    region = span[bm.start() : abs_end]
                    # 检测 LLM 是否用 ``\\n`` 做行装饰：raw 里出现"两个反斜杠
                    # + n + 后非字母"就是 JSON 转义换行装饰，"\\ + 字母" 在
                    # 这种 region 里几乎一定是 JSON 转义而非 LaTeX 行分隔。
                    has_newline_decor = bool(_re.search(r"\\\\n(?![A-Za-z])", region))
                    ml_intervals.append((bm.start(), abs_end, has_newline_decor))

            def in_multiline(pos: int) -> bool:
                return any(s <= pos < e for s, e, _ in ml_intervals)

            def multiline_has_newline_decor(pos: int) -> bool:
                for s, e, has in ml_intervals:
                    if s <= pos < e:
                        return has
                return False

            out = []
            i = 0
            n = len(span)
            while i < n:
                c = span[i]
                if c != "\\":
                    out.append(c)
                    i += 1
                    continue
                # 数当前位置开始的连续反斜杠数量
                j = i
                while j < n and span[j] == "\\":
                    j += 1
                run = j - i  # 连续反斜杠数量
                # 后接字符（无则 None）
                nxt = span[j] if j < n else None
                # LaTeX 命令/标点：字母、{ } | , ; : ! # & _ 空格、( ) [ ]
                # 加 () [] 是因为 LaTeX 行内/块公式定界符 \( \) \[ \] 在 JSON
                # 中也是非法转义，必须翻倍。
                is_latex_follow = nxt is not None and (
                    nxt.isalpha() or nxt in "{}|,;:!#&_ ()[]"
                )
                # JSON 合法单字符转义起头：``\n`` ``\r`` ``\t`` ``\b`` ``\f``
                # ``\u``。LaTeX 中虽然 ``\b`` ``\t`` 单字母命令存在但极少用，
                # 常用的都是 ``\nu \neq \nabla \tau \theta \beta \frac \rho``
                # 等多字母——所以"奇数反斜杠 + 单字符 [nrtbfu] + 后面再无字母"
                # 几乎一定是 LLM 写的 JSON 转义换行/制表符等。绝不能翻倍——
                # 翻倍会把 ``\n``(换行) 变成字面 ``\\n``（公式里的红色 ``\n``）。
                # 检测方式：看 nxt 是不是 [nrtbfu] 且 nxt+1 不是字母（即
                # ``\nu`` 这种连续字母 LaTeX 命令不在此列）。
                is_json_short_escape = (
                    run % 2 == 1
                    and nxt in ("n", "r", "t", "b", "f", "u")
                    and (j + 1 >= n or not span[j + 1].isalpha())
                )
                # 后接是否字母/数字（仅在多行环境内用于检测 LLM 写错的
                # LaTeX 行分隔 ``\\`` raw 写成 2 反斜杠的情况）
                # 数字也算：pmatrix 内 ``0&1\\1&0`` 这种 raw，1 是数字。
                nxt_is_alnum = nxt is not None and (nxt.isalpha() or nxt.isdigit())
                # 但 ``\\begin{...}`` ``\\end{...}`` 是 LaTeX 命令本身（前
                # 导双反斜杠 raw 是 LLM 写对的命令前缀），绝不能再翻倍。
                is_begin_end = span[j : j + 5] == "begin" or span[j : j + 3] == "end"

                if run % 2 == 1 and is_latex_follow and not is_json_short_escape:
                    # 奇数反斜杠 + LaTeX 命令/标点（且非 JSON 合法单字符转义）
                    # → 翻倍最后一个反斜杠
                    out.append("\\" * (run + 1))
                elif (
                    run == 2
                    and nxt_is_alnum
                    and not is_begin_end
                    and in_multiline(i)
                    and not multiline_has_newline_decor(i)
                ):
                    # 多行环境内（且非 begin/end）的双反斜杠 + 字母/数字：
                    # LLM 写错的 LaTeX 行分隔（raw 应 4 反斜杠才对，写 2
                    # 不够），补成 4 让 JSON 解码后得到 ``\\``（合法 LaTeX
                    # 行分隔）。
                    #
                    # 但若该多行区间内已有 ``\\n`` JSON 换行装饰（说明 LLM
                    # 用真换行/字面 \\n 来分行），就不应再把 ``\\`` + 字母
                    # 当成行分隔——那时它几乎一定是 JSON 转义，翻倍反而会
                    # 把 ``\n`` 字面化（残留红字）。
                    out.append("\\" * 4)
                else:
                    # 偶数（已成对）或后面不是 LaTeX 字符 → 原样保留
                    out.append("\\" * run)
                i = j
            return "".join(out)

        def _repl(m: "_re.Match") -> str:
            return _double_backslashes_in(m.group(0))

        return _MATH_SPAN.sub(_repl, s)

    # 第一次尝试：保护 LaTeX 反斜杠后解析（首选，最干净）
    try:
        return _json.loads(_protect_latex(raw))
    except Exception:
        pass

    # 第二次尝试：再叠加"非法反斜杠通配翻倍"，覆盖偶发的 \空格 / \中文 等
    try:
        protected = _protect_latex(raw)
        # 此时仍可能存在 \X (X 非 ["\\/bfnrtu] 也非字母) 的非法转义，再翻一次
        fixed = _re.sub(r'\\(?!["\\/bfnrtu]|[A-Za-z])', r"\\\\", protected)
        return _json.loads(fixed)
    except Exception:
        pass

    # 第三次尝试：先公式保护，再用最宽松的"翻倍所有非法反斜杠"
    # 注意必须先 _protect_latex，否则公式里 \frac \beta \theta \tau \rho 这些
    # 以 JSON 合法转义首字母（\f \b \t \r）开头的命令会被解析为 form-feed/退格/
    # 制表符/CR，公式被破坏。
    try:
        protected = _protect_latex(raw)
        fixed = _re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", protected)
        return _json.loads(fixed)
    except Exception:
        pass

    # 兜底：从原文里只抠 sources 字段（title + url），其它一律放弃
    result = {}
    try:
        m = _re.search(r'"sources"\s*:\s*(\[.*?\])', raw, flags=_re.DOTALL)
        if m:
            try:
                result["sources"] = _json.loads(m.group(1))
            except Exception:
                pairs = _re.findall(
                    r'\{\s*"title"\s*:\s*"([^"]+)"\s*,\s*"url"\s*:\s*"([^"]+)"',
                    m.group(1),
                )
                result["sources"] = [{"title": t, "url": u} for t, u in pairs]
    except Exception as e:
        logger.warning("解析 sources 字段时出错: %s", e)
    return result


def _normalize_math_in_text(text: str) -> str:
    """对从 raw_text 抽出的 markdown 做一些防御性规范化。

    - 把 ``\\[ ... \\]`` 转为 ``$$ ... $$``、``\\( ... \\)`` 转为 ``$ ... $``，
      让前端老的 marked 即使没识别到 \\[\\] 也能渲染；
    - 把孤立成行的 ``$$ ... $$`` 前后强制留空行（避免被 marked 视为段落内文本）。
    """
    import re as _re

    if not text:
        return text

    # \[ ... \]  →  $$ ... $$
    text = _re.sub(
        r"\\\[([\s\S]+?)\\\]",
        lambda m: "\n$$" + m.group(1).strip() + "$$\n",
        text,
    )
    # \( ... \)  →  $ ... $
    text = _re.sub(r"\\\((.+?)\\\)", r"$\1$", text)

    # 清理公式 span 内字面 ``\n``/``\r``/``\t`` 残留，但 **必须** 严格限定
    # 在"后面紧跟另一个反斜杠"的场景，否则会误伤 LaTeX 命令：
    #   - ``\rho`` ``\rangle`` ``\right`` ``\rfloor`` ``\rceil``
    #   - ``\theta`` ``\times`` ``\top`` ``\to`` ``\tan`` ``\tau`` ``\text``
    #     ``\triangle`` ``\tilde``
    #   - ``\nabla`` ``\nu`` ``\neq`` ``\ne`` ``\not`` ``\notin`` ``\ni``
    # 这些命令的首字母都是 n/r/t —— 一旦把"\n/\r/\t + 字母"也清理，命令就被
    # 整段吞掉（``\rho`` → ``ho``、``\times`` → ``imes``、``\top`` → ``op`` 等）。
    #
    # 因此本步只删除 ``\n\X`` ``\r\X`` ``\t\X`` 这种"两个反斜杠紧贴"形态——
    # 这种几乎一定是 LLM 写错的 JSON 换行后又紧跟下一条 LaTeX 命令所致。
    # 仍然保留前导 ``\X``，让命令本身完整。
    def _clean_span(m: "_re.Match") -> str:
        s = m.group(0)
        multiline_env_re = (
            r"\\begin\{(?:cases|aligned|align|gather|gathered|array|matrix|pmatrix|"
            r"bmatrix|vmatrix|Bmatrix|Vmatrix|split|multline|eqnarray)\}"
        )
        has_multiline_env = bool(_re.search(multiline_env_re, s))
        is_block_math = s.startswith("$$") and s.endswith("$$")
        if has_multiline_env:
            # 多行环境里，LLM 有时把 LaTeX 行分隔 ``\\`` 写成了行尾单 ``\``。
            # 只在真实换行前修复，避免误伤 ``\nu``、``\neq`` 等正常命令。
            s = _re.sub(
                r"(?<!\\)\\([ \t]*\n[ \t]*)(?=(?:\\(?:vdots|cdots|dots|begin|end)\b|[A-Za-z0-9]))",
                r"\\\\\1",
                s,
            )
            # 多行环境里，``\\n`` 经常表示"行分隔 + JSON 换行残留 n"，
            # 例如 ``\\na_{m1}`` / ``\\n a_{m1}`` 应恢复为 ``\\\na_{m1}``。
            # 限定后续形态为普通变量/数字行首，保护 ``\\\nabla`` 这类命令。
            s = _re.sub(
                r"(\\\\)n[ \t]*(?=(?:[A-Za-z](?:[_\{]|\d)|[0-9]))",
                r"\1\n",
                s,
            )
            if is_block_math:
                # 块级多行环境若被压成一行，Markdown/KaTeX 边界容易把
                # ``\\vdots\\a_{m1}`` 解析成同一行或残留 ``n``。这里统一展开：
                #   $$\begin{cases}a=...\\\vdots\\a_m=...\end{cases}$$
                # 变成 $$、\begin、每个行分隔、\end 各自占稳定边界。
                s = _re.sub(r"(\$\$)[ \t]*(\\begin\{[a-zA-Z]+\})[ \t]*", r"\1\n\2\n", s)
                s = _re.sub(r"[ \t]*(\\end\{[a-zA-Z]+\})[ \t]*(\$\$)", r"\n\1\n\2", s)
                s = _re.sub(
                    r"(\\\\)(?=(?:\\[A-Za-z]+\b|[A-Za-z0-9]))",
                    r"\1\n",
                    s,
                )
                s = _re.sub(
                    r"(?m)^([ \t]*)(vdots|cdots|dots)([ \t]*\\\\)",
                    r"\1\\\2\3",
                    s,
                )
                s = _re.sub(r"\n{2,}(?=\\end\{[a-zA-Z]+\})", "\n", s)
        # ① ``\n\X`` ``\r\X`` ``\t\X`` 紧贴下一条 LaTeX 命令——LLM 写错的
        #    JSON 换行残留。删除前导 ``\n``/``\r``/``\t``，保留后续命令。
        s = _re.sub(r"(?<!\\)\\[nrt](?=\\)", "", s)
        # ② 公式起始 ``$$\n``/``$\n``——LLM 在 raw 里写公式时把段首换行
        #    误用 JSON 转义 ``\n`` 嵌入。**严格** 要求 ``\n`` 后不接字母，
        #    否则会把 ``\rho \nu \tau \theta`` 等以 r/n/t 开头的 LaTeX 命令
        #    首字母吃掉（``$$\rho=`` 误读为 ``$$\r ho=`` 把 ``\r`` 当噪声删）。
        s = _re.sub(r"(\$\$|\$)\\[nrt](?![A-Za-z])", r"\1", s)
        # ③ 公式末尾 ``\n$$``/``\n$``——同 ②，严格要求 ``\n`` 前不在字母旁
        s = _re.sub(r"(?<![A-Za-z])\\[nrt](\$\$|\$)", r"\1", s)
        # ④ ``\n``/``\r``/``\t`` + 单字母 + 非字母——cases 等多行环境内
        #    LLM 段首装饰被翻倍后的字面残留（如 ``\na_{11}`` ``\nx_1+`` 等）。
        #    严格要求"字母后必须是非字母"，避免误伤 ``\nabla \neq \nu``
        #    ``\theta \times \top \tau`` 这种连续字母 LaTeX 命令。
        #    同时仅在多行环境内生效，且字母后必须紧跟下标/上标/数字/运算符，
        #    否则 ``\to `` ``\nu$`` 会被误删成 ``o `` ``u$``。
        if has_multiline_env:
            s = _re.sub(
                r"(?<!\\)\\[nrt](?=[A-Za-z](?:[_^{0-9=+\-]))",
                "",
                s,
            )
        # ⑤ 公式 span 内紧跟在 ``\begin{<env>}`` 之后的 ``\n``/``\r``/``\t``
        #    严格要求后不接字母（避免 ``\begin{cases}\rho`` 被误删 ``\r``）
        s = _re.sub(
            r"(\\begin\{[a-zA-Z]+\})\\[nrt](?![A-Za-z])",
            r"\1",
            s,
        )
        # ⑥ 公式 span 内紧贴在 ``\end{<env>}`` 之前的 ``\n``/``\r``/``\t``
        s = _re.sub(
            r"(?<![A-Za-z])\\[nrt](\\end\{[a-zA-Z]+\})",
            r"\1",
            s,
        )
        # ⑦ LaTeX 行分隔 ``\\`` 后接的 ``\n``/``\r``/``\t`` 装饰残留
        #    严格要求其后不接字母（保护 ``\\\rho`` 这种 LaTeX 行分隔后命令）
        s = _re.sub(
            r"(\\\\)\\[nrt](?![A-Za-z])",
            r"\1",
            s,
        )
        return s

    # 块级 $$..$$
    text = _re.sub(r"\$\$[\s\S]+?\$\$", _clean_span, text)
    # 行内 $..$
    text = _re.sub(r"\$[^\$\n]+?\$", _clean_span, text)

    # 多余空行收敛到 2 行
    text = _re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _normalize_research_raw_text_file(research_path: "Path") -> bool:
    """规范化 research.json 里的 raw_text，并在内容变化时回写源缓存。"""
    research = _safe_load_research(research_path)
    raw_text = research.get("raw_text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        return False

    normalized = _normalize_math_in_text(raw_text)
    if normalized == raw_text:
        return False

    research["raw_text"] = normalized
    research_path.write_text(
        json.dumps(research, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def _build_chapter_summary_md(
    ch_title: str,
    ch_info: dict,
    research_path: "Path",
) -> str:
    """基于 research.json 生成章节预习手册 Markdown（不依赖 TeX）。

    定位：在 PDF 讲义生成之前就推送给用户阅读的"预习文档"，
    帮助用户快速了解本章核心内容，为后续 PDF 讲义的深入学习做铺垫。

    内容布局：
      ## 📖 {章节名} — 预习手册
      ### 🎯 本章学习目标      ← outline.description + knowledge_points
      ### 📝 核心内容          ← research.raw_text 全文（带公式）
      ### 🔗 延伸阅读          ← research.sources（带超链接）
      ### 💡 预习提示          ← 基于知识点生成的学习建议

    LaTeX 公式保护由 _safe_load_research 完成，这里只做 markdown 防御性规范化。
    """

    lines = [f"## 📖 {ch_title} — 预习手册", ""]

    # 1) 本章学习目标
    kps = ch_info.get("knowledge_points", []) or []
    desc = (ch_info.get("description") or "").strip()
    if kps or desc:
        lines.append("### 🎯 本章学习目标")
        if desc:
            lines.append(f"> {desc}")
            lines.append("")
        if kps:
            lines.append("学完本章，你应该能够理解以下知识点：")
            lines.append("")
            for idx, kp in enumerate(kps, 1):
                lines.append(f"{idx}. {kp}")
            lines.append("")

    # 2) 核心内容（来自 research.raw_text，最具信息量的一段）
    research = _safe_load_research(research_path)
    raw_text = (research.get("raw_text") or "").strip()
    if raw_text:
        normalized = _normalize_math_in_text(raw_text)
        lines.append("### 📝 核心内容")
        lines.append(normalized)
        lines.append("")

    # 3) 延伸阅读（参考来源）
    sources = research.get("sources") or []
    if sources:
        lines.append("### 🔗 延伸阅读")
        for src in sources[:6]:
            title = (src.get("title") or "").strip()
            url = (src.get("url") or "").strip()
            summary = (src.get("summary") or "").strip()
            if title and url:
                lines.append(f"- [{title}]({url})")
                if summary:
                    lines.append(f"  {summary}")
            elif title:
                lines.append(f"- {title}")
        lines.append("")

    # 4) 预习提示
    if kps:
        lines.append("### 💡 预习提示")
        lines.append("阅读以上内容时，建议你带着以下问题思考：")
        lines.append("")
        # 从知识点中提取前 3 个作为思考问题
        for kp in kps[:3]:
            lines.append(f"- 什么是「{kp}」？它解决了什么问题？")
        lines.append("")
        lines.append("---")
        lines.append("*📑 详细的图文讲义（PDF）正在生成中，稍后将自动推送给你。*")
        lines.append("")

    # 6) 路标提示（仅当没有 raw_text 时才提示去看 PDF；有内容时不必强调）
    if not raw_text:
        lines.append(
            "> 完整推导、公式与配图请打开本章 PDF 查看；本页用于快速建立全局印象。"
        )

    if len(lines) <= 3:
        return ""

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# 并行 Research 辅助函数
# ─────────────────────────────────────────────────────────────────────


def _build_research_fallback_payload(ch_id: int, ch_title: str, ch_info: dict) -> dict:
    """Build a minimal research.json so resume never loops forever on search failure."""
    desc = (ch_info.get("description") or "").strip()
    knowledge_points = [
        str(item).strip()
        for item in ch_info.get("knowledge_points", [])
        if str(item).strip()
    ]
    keywords = [
        str(item).strip()
        for item in ch_info.get("search_keywords", [])
        if str(item).strip()
    ]
    lines = [
        "### 本章定位",
        desc or f"本章围绕「{ch_title}」建立核心概念与基本方法。",
        "",
    ]
    if knowledge_points:
        lines.extend(["### 核心知识点"])
        lines.extend(f"- **{point}**" for point in knowledge_points)
        lines.append("")
    if keywords:
        lines.extend(["### 后续检索关键词"])
        lines.extend(f"- {keyword}" for keyword in keywords[:6])
        lines.append("")
    lines.extend(
        [
            "### 学习提示",
            "资料检索暂时未完成，本节先依据课程大纲生成基础讲义；生成过程会继续保留章节目标、概念边界与必要例子，避免课程卡死在单章检索失败上。",
        ]
    )
    return {
        "chapter_id": ch_id,
        "chapter_title": ch_title,
        "sources": [],
        "raw_text": "\n".join(lines),
        "fallback": True,
    }


async def _run_single_chapter_research(
    agent: "ReActAgent",
    topic: str,
    ch_id: int,
    ch_title: str,
    ch_info: dict,
    research_path: "Path",
) -> dict:
    """并发执行单章 Research，返回收集到的 SSE 事件列表和结果信息。

    不直接 yield SSE 事件，而是收集到列表中，供调用方统一推送。
    """
    events = []
    success = False
    used_fallback = False

    try:
        researcher_prompt = (
            f"为课程「{topic}」第 {ch_id} 章「{ch_title}」检索学习资料。\n"
            f"知识点：{', '.join(ch_info.get('knowledge_points', []))}\n"
            f"搜索关键词：{', '.join(ch_info.get('search_keywords', []))}\n"
            f"将结果写入：{research_path}"
        )

        async for ev in stream_agent_events(
            agent,
            researcher_prompt,
            "researcher",
            start_msg=f"开始检索第{ch_id}章资料",
            finish_msg="检索完成",
        ):
            events.append(ev)

        success = research_path.exists() and research_path.stat().st_size > 50
        if not success:
            fallback_payload = _build_research_fallback_payload(
                ch_id, ch_title, ch_info
            )
            research_path.parent.mkdir(parents=True, exist_ok=True)
            research_path.write_text(
                json.dumps(fallback_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            success = True
            used_fallback = True
            logger.warning(
                "并行 Researcher 未写入 research.json，已使用大纲 fallback: 第%d章 %s",
                ch_id,
                ch_title,
            )
        logger.info(
            "并行 Researcher 完成: 第%d章 %s (success=%s, fallback=%s)",
            ch_id,
            ch_title,
            success,
            used_fallback,
        )

        # 规范化 research.raw_text
        try:
            if _normalize_research_raw_text_file(research_path):
                logger.info(
                    "并行已规范化 research.raw_text: 第%d章 %s", ch_id, ch_title
                )
        except Exception as exc:
            logger.warning("并行规范化 research.raw_text 失败 ch=%s: %s", ch_id, exc)

    except Exception as exc:
        logger.error("并行 Researcher 异常: 第%d章 %s: %s", ch_id, ch_title, exc)
        try:
            fallback_payload = _build_research_fallback_payload(
                ch_id, ch_title, ch_info
            )
            research_path.parent.mkdir(parents=True, exist_ok=True)
            research_path.write_text(
                json.dumps(fallback_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            success = True
            used_fallback = True
            logger.warning(
                "并行 Researcher 异常后已使用大纲 fallback: 第%d章 %s", ch_id, ch_title
            )
        except Exception as fallback_exc:
            logger.error(
                "写入 fallback research.json 失败: 第%d章 %s: %s",
                ch_id,
                ch_title,
                fallback_exc,
            )

    return {
        "ch_id": ch_id,
        "ch_title": ch_title,
        "ch_info": ch_info,
        "events": events,
        "success": success,
        "used_fallback": used_fallback,
        "research_path": research_path,
    }


def _build_researcher_agent(layout: "UserDataLayout", user_id: str) -> "ReActAgent":
    """为并行 research 构建独立的 researcher agent 实例。

    每个并发任务需要独立的 agent 实例，避免内部 history 冲突。
    """
    from services.search_factory import get_search_client

    return ReActAgent(
        llm=get_llm(user_id, scene="immersive"),
        prompt_builder=StaticPromptBuilder(
            "你是信息检索与整理助手。根据章节信息检索资料，整理为 JSON 写入指定路径。\n\n"
            "**JSON 输出格式**：\n"
            '{"chapter_id": N, "chapter_title": "...",\n'
            '  "sources": [{"title": "标题", "url": "https://...", "summary": "一句话摘要"}],\n'
            '  "raw_text": "整合后的 Markdown 正文（不超过 2000 字）"}\n\n'
            "**raw_text 必须遵守的格式规范**（前端会以 Markdown 直接渲染，质量直接影响用户体验）：\n"
            "1. 必须使用 Markdown 结构：用 `### 小节标题` 分块，每块下用短段落 + 列表，避免出现整段大段文字。\n"
            "2. 严禁出现裸 URL；若需引用网址，**必须**写成 `[显示文本](https://...)` 的 markdown 链接形式。\n"
            "3. 数学公式使用 LaTeX：行内用 `$...$`，独立公式用 `$$...$$`。\n"
            "4. 重要术语和关键概念用 `**加粗**`，对易混淆点可用 `> 引用块` 提醒。\n"
            "5. 不要把 sources 里的链接列表再原样附在 raw_text 末尾（前端会单独展示）。\n"
            "6. 内容要求循序渐进：先给定义/直观解释，再给关键性质/算法步骤，最后给注意事项或常见误区。\n"
            "7. 优先使用中文资料；如果只有英文，请翻译为中文表达。\n\n"
            "**工作流程**：\n"
            "1. 用 search 工具检索 2-4 条权威资料\n"
            "2. （可选）对最相关的 1-2 条用 web_fetch 抓取详细内容\n"
            "3. 整合为符合上述规范的 raw_text，并将 sources 列表填好\n"
            "4. 用 write_file 写入指定的 research.json 路径"
        ),
        tool_registry=ToolRegistry(
            [
                TavilySearch(client=get_search_client(user_id, scene="immersive")),
                ArxivSearch(),
                WebFetch(),
                WriteFileTool(),
            ]
        ),
        max_steps=14,
    )


def _build_agent_by_name(
    spec_name: str, layout: "UserDataLayout", user_id: str
) -> "ReActAgent":
    """Build a fresh agent instance for one chapter pipeline.

    Chapter-level parallelism must not share one ReActAgent across chapters,
    because history/tool state can leak between concurrent runs.
    """
    from agents.registry import build_agent

    return build_agent(spec_name, user_id=user_id, workspace_dir=layout.root)


async def _run_tex_writer_with_retry(
    *,
    topic: str,
    chapters: list[dict],
    index: int,
    course: "CourseLayout",
    layout: "UserDataLayout",
    user_id: str,
    emit: Callable[[str], Awaitable[None]],
    max_attempts: int = MAX_CHAPTER_PDF_ATTEMPTS,
) -> dict:
    """Generate one chapter PDF with immediate course-level retries.

    The ReAct agent already has an internal tool-repair loop, but transient
    network failures or an exhausted loop can still leave PDF invalid.  This
    wrapper starts a fresh tex_writer agent per attempt and feeds the last
    validation error back into the next attempt before exposing the chapter as
    pending to the learner.
    """
    ch_info = chapters[index]
    ch_id = ch_info.get("chapter_id", index + 1)
    ch_title = ch_info.get("title", f"第{ch_id}章")
    chapter_dir = course.chapter_dir(ch_id)
    research_path = chapter_dir / "research.json"
    tex_path = course.tex_file(ch_id)
    pdf_path = course.pdf_file(ch_id)
    images_dir = course.chapter_images_dir(ch_id)
    last_error = ""

    if _pdf_is_ready(pdf_path, tex_path, images_dir, chapters, index):
        return {"ok": True, "attempts": 0, "error": ""}

    for attempt in range(1, max_attempts + 1):
        prompt = _build_tex_prompt(
            topic=topic,
            chapters=chapters,
            index=index,
            research_path=research_path,
            tex_path=tex_path,
            images_dir=images_dir,
        )
        if last_error:
            prompt += (
                "\n\n【自动重试上下文】\n"
                f"上一轮第 {ch_id} 章 PDF 未通过发布校验，原因：{last_error}\n"
                "请直接修复同一个 TeX 输出文件，优先保证可编译、图片完整、章节导航正确，"
                "不要改变课程大纲里的章节编号和标题。"
            )
        if attempt > 1:
            await emit(
                sse_event(
                    "progress",
                    stage="tex_retry",
                    pct=0,
                    message=f"🔁 自动重试第 {ch_id} 章 PDF（第 {attempt}/{max_attempts} 次）: {ch_title}",
                )
            )
        try:
            tex_writer = _build_agent_by_name("course.tex_writer", layout, user_id)
            async for ev in stream_agent_events(
                tex_writer,
                prompt,
                "tex_writer",
                skill_names=["tex_beamer_writing"],
                start_msg=f"开始生成第{ch_id}章PDF",
                finish_msg="PDF生成完成",
            ):
                await emit(ev)
        except Exception as exc:  # pylint: disable=broad-except
            last_error = f"tex_writer 异常: {exc}"
            logger.warning(
                "第%d章 tex_writer 第%d/%d次尝试异常: %s",
                ch_id,
                attempt,
                max_attempts,
                exc,
            )
        else:
            last_error = (
                _chapter_pdf_error(pdf_path, tex_path, images_dir, chapters, index)
                or ""
            )
            if not last_error:
                logger.info(
                    "第%d章 PDF 生成成功（attempt=%d/%d）",
                    ch_id,
                    attempt,
                    max_attempts,
                )
                return {"ok": True, "attempts": attempt, "error": ""}
            logger.warning(
                "第%d章 PDF 第%d/%d次尝试仍未通过校验: %s",
                ch_id,
                attempt,
                max_attempts,
                last_error,
            )

    return {"ok": False, "attempts": max_attempts, "error": last_error}


async def _stream_parallel_tex_prefetch(
    *,
    topic: str,
    chapters: list[dict],
    chapter_items: list[tuple[int, dict]],
    course: "CourseLayout",
    layout: "UserDataLayout",
    user_id: str,
    max_concurrency: int = MAX_PARALLEL_TEX_CHAPTERS,
    publish_ready: Callable[[int, dict], Awaitable[list[str]]] | None = None,
) -> AsyncGenerator[str, None]:
    """Prefetch chapter PDFs concurrently, streaming worker events through a queue.

    This helper performs the expensive TeX/PDF writing work.  When
    ``publish_ready`` is provided, the caller publishes a chapter as soon as that
    worker validates its PDF, while the remaining workers continue running.

    ``max_concurrency`` is intentionally scoped to this one generator invocation
    (one immersive generate/resume request).  Do not replace the local semaphore
    with a module-global semaphore: different immersive requests must keep their
    own independent 3-chapter windows.
    """
    targets: list[tuple[int, dict]] = []
    for index, ch_info in chapter_items:
        ch_id = ch_info.get("chapter_id", index + 1)
        tex_path = course.tex_file(ch_id)
        pdf_path = course.pdf_file(ch_id)
        images_dir = course.chapter_images_dir(ch_id)
        if not _pdf_is_ready(pdf_path, tex_path, images_dir, chapters, index):
            targets.append((index, ch_info))

    if not targets:
        return

    concurrency = max(1, min(max_concurrency, len(targets)))
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    semaphore = asyncio.Semaphore(concurrency)

    async def _worker(item: tuple[int, dict]) -> None:
        index, ch_info = item
        ch_id = ch_info.get("chapter_id", index + 1)
        ch_title = ch_info.get("title", f"第{ch_id}章")
        try:
            async with semaphore:
                await queue.put(
                    sse_event(
                        "progress",
                        stage="tex_parallel",
                        pct=0,
                        message=f"🚀 并行生成第 {ch_id} 章 PDF: {ch_title}",
                    )
                )
                result = await _run_tex_writer_with_retry(
                    topic=topic,
                    chapters=chapters,
                    index=index,
                    course=course,
                    layout=layout,
                    user_id=user_id,
                    emit=queue.put,
                )
                if result.get("ok"):
                    await queue.put(
                        sse_event(
                            "progress",
                            stage="tex_parallel",
                            pct=0,
                            message=f"✅ 第 {ch_id} 章 PDF 并行预生成完成",
                        )
                    )
                    if publish_ready:
                        try:
                            for event in await publish_ready(index, ch_info):
                                await queue.put(event)
                        except Exception as exc:  # pylint: disable=broad-except
                            logger.exception("并行 PDF 即时发布失败 ch=%s", ch_id)
                            await queue.put(
                                sse_event(
                                    "progress",
                                    stage="tex_parallel",
                                    pct=0,
                                    message=f"⚠️ 第 {ch_id} 章 PDF 已生成但即时发布失败，将在有序阶段重试: {exc}",
                                )
                            )
                else:
                    await queue.put(
                        sse_event(
                            "progress",
                            stage="tex_parallel",
                            pct=0,
                            message=f"⚠️ 第 {ch_id} 章 PDF 并行预生成未通过，后续将再做一次有序兜底: {result.get('error') or '未知错误'}",
                        )
                    )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("并行 PDF 预生成 worker 异常 ch=%s", ch_id)
            await queue.put(
                sse_event(
                    "progress",
                    stage="tex_parallel",
                    pct=0,
                    message=f"⚠️ 第 {ch_id} 章 PDF 并行预生成异常，后续将有序兜底: {exc}",
                )
            )
        finally:
            await queue.put(None)

    tasks = [asyncio.create_task(_worker(item)) for item in targets]
    finished = 0
    try:
        while finished < len(tasks):
            item = await queue.get()
            if item is None:
                finished += 1
                continue
            yield item
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()


async def _stream_parallel_chapter_enrichment(
    *,
    session_id: str,
    topic: str,
    chapters: list[dict],
    chapter_items: list[tuple[int, dict]],
    course: "CourseLayout",
    layout: "UserDataLayout",
    user_id: str,
    enable_audio: bool,
    enable_exercises: bool,
    tts_llm,
    total_ch: int,
    pct_per_chapter: float,
    published_pdf_by_chapter: dict[int, dict],
    state_write_lock: asyncio.Lock,
    all_files_for_session: list[dict] | None = None,
    max_concurrency: int = MAX_PARALLEL_ENRICH_CHAPTERS,
    incoming: "asyncio.Queue[tuple[int, dict] | None] | None" = None,
) -> AsyncGenerator[str, None]:
    """Enrich already published chapter PDFs with a request-local rolling window.

    The concurrency limit is intentionally local to this generator invocation.
    All workspace/canvas/session-file mutations are serialized by
    ``state_write_lock``; long LLM/TTS/archive/node work is kept outside it.

    ``incoming`` 为可选的流式入队通道：PDF 一就绪就把 ``(index, ch_info)`` 放入，
    以 ``None`` 结束；这样习题/语音/讲解稿可与后续章节的 PDF 生成并行，
    不必等全部 PDF 完成。未提供时仅处理 ``chapter_items``。
    """
    targets = list(chapter_items)
    if not targets and incoming is None:
        return

    if incoming is None:
        concurrency = max(1, min(max_concurrency, len(targets)))
    else:
        concurrency = max(1, max_concurrency)
    semaphore = asyncio.Semaphore(concurrency)
    queue: asyncio.Queue[Any] = asyncio.Queue()
    results_by_chapter: dict[int, dict] = {}
    nodes_by_chapter: dict[int, list[dict]] = {}
    order_by_chapter = {
        ch_info.get("chapter_id", index + 1): position
        for position, (index, ch_info) in enumerate(targets)
    }

    async def _emit(event: str) -> None:
        await queue.put(event)

    async def _mark_step(ch_id: int, **steps: str) -> None:
        """把章节补全子步骤（exercises/audio/kg）状态写入 workspace，供历史页展示进度。"""
        try:
            async with state_write_lock:
                ws = read_workspace(session_id).get("workspace", {}) or {}
                chapters_state = list(ws.get("chapters", []) or [])
                for idx, item in enumerate(chapters_state):
                    if item.get("chapter_id") == ch_id:
                        chapters_state[idx] = {
                            **item,
                            "enrich_steps": {
                                **(item.get("enrich_steps") or {}),
                                **steps,
                            },
                        }
                        break
                else:
                    return
                update_workspace(session_id, workspace={"chapters": chapters_state})
        except Exception:  # pylint: disable=broad-except
            logger.debug("第%s章补全步骤状态写入失败", ch_id, exc_info=True)

    async def _register_existing_pdf_if_needed(
        index: int, ch_info: dict
    ) -> dict | None:
        ch_id = ch_info.get("chapter_id", index + 1)
        publication = published_pdf_by_chapter.get(ch_id)
        if publication:
            return publication
        async with state_write_lock:
            publication = await _publish_chapter_pdf_ready(
                session_id=session_id,
                topic=topic,
                user_id=user_id,
                course=course,
                chapters=chapters,
                index=index,
                ch_info=ch_info,
                total_ch=total_ch,
                enable_audio=enable_audio,
                generation_started_at=None,
                all_files_for_session=all_files_for_session,
                set_current_chapter=False,
            )
        if publication:
            published_pdf_by_chapter[ch_id] = publication
            for event in publication["events"]:
                await _emit(event)
        return publication

    async def _worker(item: tuple[int, dict]) -> dict | None:
        index, ch_info = item
        ch_id = ch_info.get("chapter_id", index + 1)
        ch_title = ch_info.get("title", f"第{ch_id}章")
        ch_base_pct = int(15 + pct_per_chapter * order_by_chapter.get(ch_id, index))
        tex_path = course.tex_file(ch_id)
        pdf_path = course.pdf_file(ch_id)
        images_dir = course.chapter_images_dir(ch_id)
        exercises_path = course.exercises_file(ch_id)
        chapter_dir = course.chapter_dir(ch_id)
        pdf_block = None
        pdf_doc_id = ""
        pdf_rel = ""
        pdf_revision = ""
        num_frames = count_beamer_frames(tex_path)
        ex_doc_id = ""
        ex_rel = ""
        quiz_block = None
        speaker_notes: list[str] = []
        audio_results: list[dict] = []
        audio_files_data: list[dict] = []
        audio_doc_id = ""
        notes_doc_id = ""

        try:
            async with semaphore:
                publication = await _register_existing_pdf_if_needed(index, ch_info)
                if not publication:
                    await _emit(
                        sse_event(
                            "progress",
                            stage="enrichment",
                            pct=min(int(ch_base_pct + pct_per_chapter), 90),
                            message=f"第 {ch_id} 章 PDF 尚未就绪，跳过补全资源: {ch_title}",
                        )
                    )
                    return None

                pdf_block = publication["pdf_block"]
                pdf_doc_id = publication["pdf_doc_id"]
                pdf_rel = publication["pdf_rel"]
                pdf_revision = publication["pdf_revision"]
                num_frames = publication["num_frames"]
                chapter_status_block = {
                    **publication["status_block"],
                    "status": "generating",
                    "data": {
                        **(publication["status_block"].get("data") or {}),
                        "stage": "enriching",
                        "message": "PDF 已发布，正在继续补全小测和语音。",
                    },
                }
                async with state_write_lock:
                    upsert_canvas_block(
                        session_id,
                        chapter_status_block,
                        stage="generating",
                        workspace_patch={"current_chapter_id": ch_id},
                    )
                await _emit(
                    sse_event(
                        "chapter_start",
                        index=index,
                        total=total_ch,
                        chapter_id=ch_id,
                        title=ch_title,
                        stage="enriching",
                    )
                )
                await _emit(
                    sse_event(
                        "workspace_update",
                        event="block_updated",
                        session_id=session_id,
                        block=chapter_status_block,
                    )
                )

                await _mark_step(
                    ch_id,
                    exercises="running" if enable_exercises else "skipped",
                    audio="running" if enable_audio else "skipped",
                    kg="pending",
                )
                async with state_write_lock:
                    workspace_snapshot = read_workspace(session_id)
                state_by_id = {
                    item.get("chapter_id"): item
                    for item in (workspace_snapshot.get("workspace", {}) or {}).get(
                        "chapters", []
                    )
                    or []
                    if item.get("chapter_id") is not None
                }
                existing_state = state_by_id.get(ch_id, {})
                ex_doc_id = existing_state.get("exercises_doc_id", "") or ""
                audio_doc_id = existing_state.get("audio_doc_id", "") or ""
                notes_doc_id = existing_state.get("notes_doc_id", "") or ""

                step_started = time.time()
                if enable_exercises:
                    exercises_pct = int(ch_base_pct + pct_per_chapter * 0.7)
                    exercises_done = _file_is_ready(exercises_path)
                    if exercises_done:
                        await _emit(
                            sse_event(
                                "progress",
                                stage="exercises",
                                pct=exercises_pct,
                                message=f"已有习题，跳过生成第 {ch_id} 章: {ch_title}",
                            )
                        )
                    else:
                        await _emit(
                            sse_event(
                                "progress",
                                stage="exercises",
                                pct=exercises_pct,
                                message=f"生成习题: 第 {ch_id} 章 {ch_title}",
                            )
                        )
                        exercises_prompt = (
                            f"为课程「{topic}」第 {ch_id} 章「{ch_title}」生成配套习题。\n"
                            f"TeX 讲义文件：{tex_path}\n"
                            f"习题输出路径：{exercises_path}\n"
                            f"知识点：{', '.join(ch_info.get('knowledge_points', []))}"
                        )
                        try:
                            exercises_agent = _build_agent_by_name(
                                "course.exercises", layout, user_id
                            )
                            async for ev in stream_agent_events(
                                exercises_agent,
                                exercises_prompt,
                                "exercises",
                                start_msg=f"开始生成第{ch_id}章习题",
                                finish_msg="习题生成完成",
                            ):
                                await _emit(ev)
                        except Exception as exc:  # pylint: disable=broad-except
                            logger.warning(
                                "第%d章习题生成失败（不阻塞 PDF）: %s", ch_id, exc
                            )
                    ex_rel = (
                        to_rel_path(str(exercises_path))
                        if _file_is_ready(exercises_path)
                        else ""
                    )
                    if ex_rel and not ex_doc_id:
                        try:
                            async with state_write_lock:
                                ex_doc_id = (
                                    await asyncio.to_thread(
                                        lambda p=exercises_path, c=ch_id, t=ch_title: (
                                            register_chapter_exercises(
                                                session_id=session_id,
                                                topic=topic,
                                                chapter_id=c,
                                                chapter_title=t,
                                                exercises_path=p,
                                                user_id=user_id,
                                                node_ids=[],
                                            )
                                        ),
                                    )
                                    or ""
                                )
                                if ex_doc_id:
                                    append_session_file(
                                        session_id,
                                        ex_doc_id,
                                        f"第{ch_id}章 {ch_title} 习题",
                                        "chapter_exercises",
                                    )
                        except Exception as exc:  # pylint: disable=broad-except
                            logger.warning(
                                "第%d章习题登记失败（不阻塞 PDF）: %s", ch_id, exc
                            )
                    if ex_rel:
                        quiz_block = {
                            "id": f"quiz_ch{ch_id}_bank",
                            "type": "quiz_batch",
                            "title": f"第{ch_id}章小测",
                            "status": "ready" if ex_doc_id else "learning_ready",
                            "chapter_id": ch_id,
                            "data": {
                                "source": "exercises_md",
                                "exercises_path": ex_rel,
                                "doc_id": ex_doc_id,
                                "exercises_doc_id": ex_doc_id,
                                "display_limit": 3,
                                "strategy": "show_2_to_3_questions_first",
                            },
                        }
                        async with state_write_lock:
                            upsert_canvas_block(session_id, quiz_block)
                        await _emit(
                            sse_event(
                                "workspace_update",
                                event="block_created",
                                session_id=session_id,
                                block=quiz_block,
                            )
                        )
                else:
                    logger.info("跳过习题生成: 第%d章（用户未启用习题）", ch_id)
                if enable_exercises:
                    logger.info(
                        "第%d章习题阶段耗时 %.1fs ok=%s",
                        ch_id,
                        time.time() - step_started,
                        bool(ex_rel),
                    )
                    await _mark_step(ch_id, exercises="done" if ex_rel else "failed")

                step_started = time.time()
                if enable_audio and tex_path.exists() and num_frames > 0:
                    tts_pct = int(ch_base_pct + pct_per_chapter * 0.85)
                    notes_path = chapter_dir / "speaker_notes.json"
                    audio_dir = chapter_dir / "audio"
                    existing_audio = (
                        sorted(
                            f.name
                            for f in audio_dir.iterdir()
                            if f.suffix.lower() == ".wav"
                        )
                        if audio_dir.exists()
                        else []
                    )
                    tts_done = len(existing_audio) >= num_frames
                    if tts_done:
                        await _emit(
                            sse_event(
                                "progress",
                                stage="tts",
                                pct=tts_pct,
                                message=f"已有语音，跳过第 {ch_id} 章 ({len(existing_audio)} 段): {ch_title}",
                            )
                        )
                        speaker_notes = _read_speaker_notes(notes_path)
                        audio_results = [
                            {
                                "filename": filename,
                                "success": True,
                                "duration_seconds": 0,
                            }
                            for filename in existing_audio
                        ]
                    else:
                        await _emit(
                            sse_event(
                                "progress",
                                stage="tts",
                                pct=tts_pct,
                                message=f"生成语音: 第 {ch_id} 章 {ch_title} ({num_frames}页)",
                            )
                        )
                        try:
                            speaker_notes = _read_speaker_notes(notes_path)
                            if not speaker_notes:
                                speaker_notes = await asyncio.to_thread(
                                    generate_speaker_notes,
                                    tts_llm,
                                    tex_path,
                                    num_frames,
                                )
                                if speaker_notes:
                                    notes_path.write_text(
                                        json.dumps(
                                            speaker_notes, ensure_ascii=False, indent=2
                                        ),
                                        encoding="utf-8",
                                    )
                            if speaker_notes:
                                audio_results = await asyncio.to_thread(
                                    run_tts_for_chapter,
                                    chapter_dir,
                                    speaker_notes,
                                    user_id,
                                )
                        except Exception as exc:  # pylint: disable=broad-except
                            logger.warning(
                                "第%d章语音生成失败（不阻塞 PDF）: %s", ch_id, exc
                            )
                    if speaker_notes and not notes_doc_id and notes_path.exists():
                        try:
                            async with state_write_lock:
                                notes_doc_id = (
                                    await asyncio.to_thread(
                                        lambda p=notes_path, c=ch_id, t=ch_title: (
                                            register_chapter_notes(
                                                session_id=session_id,
                                                topic=topic,
                                                chapter_id=c,
                                                chapter_title=t,
                                                notes_path=p,
                                                user_id=user_id,
                                            )
                                        ),
                                    )
                                    or ""
                                )
                                if notes_doc_id:
                                    append_session_file(
                                        session_id,
                                        notes_doc_id,
                                        f"第{ch_id}章 {ch_title} · 讲解稿",
                                        "chapter_notes",
                                    )
                        except Exception as exc:  # pylint: disable=broad-except
                            logger.warning(
                                "第%d章讲解稿登记失败（不阻塞 PDF）: %s", ch_id, exc
                            )
                    if audio_results and not audio_doc_id:
                        try:
                            async with state_write_lock:
                                audio_doc_id = (
                                    await asyncio.to_thread(
                                        lambda d=audio_dir, c=ch_id, t=ch_title, ar=audio_results, sn=speaker_notes: (
                                            register_chapter_audio(
                                                session_id=session_id,
                                                topic=topic,
                                                chapter_id=c,
                                                chapter_title=t,
                                                audio_dir=d,
                                                audio_results=ar,
                                                speaker_notes=sn,
                                                user_id=user_id,
                                            )
                                        ),
                                    )
                                    or ""
                                )
                                if audio_doc_id:
                                    append_session_file(
                                        session_id,
                                        audio_doc_id,
                                        f"第{ch_id}章 {ch_title} · 音频",
                                        "chapter_audio",
                                    )
                        except Exception as exc:  # pylint: disable=broad-except
                            logger.warning(
                                "第%d章音频登记失败（不阻塞 PDF）: %s", ch_id, exc
                            )
                elif enable_audio:
                    logger.info("跳过语音生成: 第%d章（TeX 不存在或页数为 0）", ch_id)
                if enable_audio:
                    audio_ok = any(r.get("success") for r in audio_results)
                    logger.info(
                        "第%d章语音阶段耗时 %.1fs ok=%s",
                        ch_id,
                        time.time() - step_started,
                        audio_ok,
                    )
                    await _mark_step(ch_id, audio="done" if audio_ok else "failed")

                if enable_audio:
                    for result in audio_results:
                        if result.get("success"):
                            filename = result.get("filename", "")
                            audio_files_data.append(
                                {
                                    "filename": filename,
                                    "url": (
                                        f"/api/documents/{audio_doc_id}/asset/{filename}"
                                        if audio_doc_id
                                        else ""
                                    ),
                                    "duration_seconds": result.get(
                                        "duration_seconds", 0
                                    ),
                                    "success": True,
                                }
                            )

                images = []
                if images_dir.exists():
                    images = [
                        f.name
                        for f in images_dir.iterdir()
                        if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                    ]

                artifact_missing: list[str] = []
                if enable_exercises:
                    if not ex_rel:
                        artifact_missing.append("exercises")
                    elif not ex_doc_id:
                        artifact_missing.append("exercises_doc_id")
                if enable_audio:
                    if not speaker_notes:
                        artifact_missing.append("speaker_notes")
                    if not audio_files_data:
                        artifact_missing.append("audio")
                    elif not audio_doc_id:
                        artifact_missing.append("audio_doc_id")
                    if speaker_notes and not notes_doc_id:
                        artifact_missing.append("notes_doc_id")
                chapter_ready_status = (
                    "ready" if not artifact_missing else "learning_ready"
                )

                if audio_files_data and pdf_block:
                    pdf_block = {
                        **pdf_block,
                        "data": {
                            **(pdf_block.get("data") or {}),
                            "audio_files": audio_files_data,
                            "audio_doc_id": audio_doc_id,
                        },
                    }
                    async with state_write_lock:
                        upsert_canvas_block(session_id, pdf_block)
                    await _emit(
                        sse_event(
                            "workspace_update",
                            event="block_updated",
                            session_id=session_id,
                            block=pdf_block,
                        )
                    )

                chapter_block_ids = [f"chapter_{ch_id}_status", f"pdf_ch{ch_id}"]
                if quiz_block:
                    chapter_block_ids.append(quiz_block["id"])
                for block_id in existing_state.get("block_ids") or []:
                    if block_id not in chapter_block_ids:
                        chapter_block_ids.append(block_id)

                completed_chapter = {
                    "chapter_id": ch_id,
                    "title": ch_title,
                    "status": chapter_ready_status,
                    "block_ids": chapter_block_ids,
                    "files": [path for path in [pdf_rel, ex_rel] if path],
                    "audio_enabled": enable_audio,
                    "audio_files": audio_files_data,
                    "speaker_notes_count": len(speaker_notes),
                    "pdf_doc_id": pdf_doc_id,
                    "pdf_revision": pdf_revision,
                    "exercises_doc_id": ex_doc_id,
                    "audio_doc_id": audio_doc_id,
                    "notes_doc_id": notes_doc_id,
                    "artifact_missing": artifact_missing,
                    "artifact_status": {
                        "pdf": True,
                        "exercises": bool(ex_rel),
                        "speaker_notes": bool(speaker_notes),
                        "audio": bool(audio_files_data),
                    },
                }
                ch_result = {
                    **completed_chapter,
                    "knowledge_points": ch_info.get("knowledge_points", []),
                    "pdf_exists": True,
                    "pdf_path": pdf_rel,
                    "exercises_exists": bool(ex_rel),
                    "exercises_path": ex_rel,
                    "num_frames": num_frames,
                    "images": images,
                    "images_count": len(images),
                }

                async with state_write_lock:
                    workspace_now = read_workspace(session_id)
                    workspace_data = workspace_now.get("workspace", {}) or {}
                    chapters_state = list(workspace_data.get("chapters", []) or [])
                    for idx, existing in enumerate(chapters_state):
                        if existing.get("chapter_id") == ch_id:
                            chapters_state[idx] = {**existing, **completed_chapter}
                            break
                    else:
                        chapters_state.append(completed_chapter)
                    generated_chapters = len(
                        [c for c in chapters_state if _chapter_is_user_available(c)]
                    )
                    pending_chapter_ids = [
                        c.get("chapter_id")
                        for c in chapters_state
                        if _chapter_requires_followup(c)
                    ]
                    next_chapter_id = (
                        pending_chapter_ids[0] if pending_chapter_ids else None
                    )
                    next_actions = [
                        {"type": "start_learning", "label": "先学习已生成内容"}
                    ]
                    if next_chapter_id:
                        next_actions.append(
                            {
                                "type": "continue_generation",
                                "label": f"继续生成第{next_chapter_id}章",
                            }
                        )
                    update_workspace(
                        session_id,
                        stage="partial_ready" if pending_chapter_ids else "ready",
                        next_actions=next_actions,
                        workspace={
                            "chapters": chapters_state,
                            "generated_chapters": generated_chapters,
                            "planned_chapters": total_ch,
                            "current_chapter_id": next_chapter_id,
                            "pending_chapter_ids": pending_chapter_ids,
                        },
                    )
                    chapter_status_block = {
                        **chapter_status_block,
                        "status": chapter_ready_status,
                        "data": {
                            **(chapter_status_block.get("data") or {}),
                            "stage": chapter_ready_status,
                            "block_ids": chapter_block_ids,
                            "artifact_missing": artifact_missing,
                        },
                    }
                    upsert_canvas_block(session_id, chapter_status_block)

                results_by_chapter[ch_id] = ch_result
                await _emit(
                    sse_event(
                        "progress",
                        stage="enrichment",
                        pct=min(int(ch_base_pct + pct_per_chapter), 90),
                        message=f"第 {ch_id} 章补全完成: {ch_title}",
                    )
                )
                await _emit(
                    sse_event(
                        "chapter_done", index=index, total=total_ch, data=ch_result
                    )
                )
                await _emit(
                    sse_event(
                        "workspace_update",
                        event="block_updated",
                        session_id=session_id,
                        block=chapter_status_block,
                        next_actions=next_actions,
                    )
                )

                try:
                    await asyncio.to_thread(
                        archive_immersive_chapter,
                        chapter_dir,
                        topic,
                        chapter_dir.name,
                        session_id,
                    )
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("章节 %d 资产归档失败: %s", ch_id, exc)
                try:
                    bundle_path = await asyncio.to_thread(
                        pack_chapter_bundle,
                        chapter_dir,
                        topic,
                        ch_title,
                        str(ch_id),
                        session_id,
                    )
                    if bundle_path:
                        logger.info("第%d章打包完成: %s", ch_id, bundle_path.name)
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("章节 %d 打包失败: %s", ch_id, exc)

                kg_started = time.time()
                kg_ok = False
                try:
                    single_ch = {
                        "title": ch_title,
                        "knowledge_points": ch_info.get("knowledge_points", []),
                    }
                    ch_nodes = await asyncio.to_thread(
                        extract_and_persist_nodes,
                        session_id,
                        topic,
                        [single_ch],
                        tts_llm or get_llm(user_id, scene="immersive"),
                        user_id,
                    )
                    if ch_nodes:
                        kg_ok = True
                        nodes_by_chapter[ch_id] = ch_nodes
                        ch_new = sum(1 for node in ch_nodes if not node.get("existed"))
                        await _emit(
                            sse_event(
                                "nodes_extracted",
                                chapter_id=ch_id,
                                nodes=[
                                    {"id": node["id"], "title": node["title"]}
                                    for node in ch_nodes
                                ],
                                new_count=ch_new,
                            )
                        )
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("第%d章知识图谱抽取失败（不阻塞）: %s", ch_id, exc)
                logger.info(
                    "第%d章图谱抽取耗时 %.1fs ok=%s",
                    ch_id,
                    time.time() - kg_started,
                    kg_ok,
                )
                await _mark_step(ch_id, kg="done" if kg_ok else "failed")
                return ch_result
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("第%d章补全 worker 异常（PDF 保持可学习）", ch_id)
            try:
                async with state_write_lock:
                    workspace_now = read_workspace(session_id)
                    workspace_data = workspace_now.get("workspace", {}) or {}
                    chapters_state = list(workspace_data.get("chapters", []) or [])
                    fallback_state = {
                        "chapter_id": ch_id,
                        "title": ch_title,
                        "status": "learning_ready",
                        "block_ids": [f"chapter_{ch_id}_status", f"pdf_ch{ch_id}"],
                        "files": [to_rel_path(str(pdf_path))]
                        if pdf_path.exists()
                        else [],
                        "audio_enabled": enable_audio,
                        "artifact_missing": [f"enrichment_error: {exc}"],
                    }
                    for idx, existing in enumerate(chapters_state):
                        if existing.get("chapter_id") == ch_id:
                            settled_steps = {
                                key: (val if val in {"done", "skipped"} else "failed")
                                for key, val in (
                                    existing.get("enrich_steps") or {}
                                ).items()
                            }
                            chapters_state[idx] = {
                                **existing,
                                **fallback_state,
                                "enrich_steps": settled_steps,
                            }
                            break
                    else:
                        chapters_state.append(fallback_state)
                    update_workspace(
                        session_id,
                        stage="partial_ready",
                        next_actions=[
                            {"type": "start_learning", "label": "先学习已生成内容"},
                            {"type": "continue_generation", "label": "继续补全课程"},
                        ],
                        workspace={
                            "chapters": chapters_state,
                            "planned_chapters": total_ch,
                        },
                    )
            except Exception:  # pylint: disable=broad-except
                logger.exception("第%d章补全失败后写入 learning_ready 状态失败", ch_id)
            await _emit(
                sse_event(
                    "progress",
                    stage="enrichment",
                    pct=min(int(ch_base_pct + pct_per_chapter), 90),
                    message=f"第 {ch_id} 章补全失败，PDF 已保留，可续传补齐: {exc}",
                )
            )
            return None
        finally:
            await queue.put(None)

    feed_done = incoming is None
    feed_done_marker = object()
    tasks = [asyncio.create_task(_worker(item)) for item in targets]
    feeder_task: asyncio.Task | None = None

    async def _feeder() -> None:
        try:
            while True:
                item = await incoming.get()  # type: ignore[union-attr]
                if item is None:
                    break
                idx, info = item
                order_by_chapter.setdefault(info.get("chapter_id", idx + 1), idx)
                tasks.append(asyncio.create_task(_worker(item)))
        finally:
            await queue.put(feed_done_marker)

    if incoming is not None:
        feeder_task = asyncio.create_task(_feeder())

    finished = 0
    try:
        while not (feed_done and finished >= len(tasks)):
            item = await queue.get()
            if item is None:
                finished += 1
                continue
            if item is feed_done_marker:
                feed_done = True
                continue
            yield item
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if feeder_task is not None and not feeder_task.done():
            feeder_task.cancel()
        for task in tasks:
            if not task.done():
                task.cancel()

    chapter_items_out = sorted(
        results_by_chapter.items(), key=lambda pair: order_by_chapter.get(pair[0], 0)
    )
    if chapter_items_out:
        published_pdf_by_chapter.setdefault("__chapter_results__", {})
        published_pdf_by_chapter["__chapter_results__"] = {
            ch_id: result for ch_id, result in chapter_items_out
        }
    node_items_out = sorted(
        nodes_by_chapter.items(), key=lambda pair: order_by_chapter.get(pair[0], 0)
    )
    if node_items_out:
        published_pdf_by_chapter.setdefault("__extracted_nodes__", {})
        published_pdf_by_chapter["__extracted_nodes__"] = {
            ch_id: nodes for ch_id, nodes in node_items_out
        }


async def _parallel_research_all_chapters(
    topic: str,
    chapters: list,
    course: "CourseLayout",
    layout: "UserDataLayout",
    user_id: str,
    max_concurrency: int = 0,
) -> list:
    """并发执行所有章节的 Research，返回每章的结果列表。

    max_concurrency=0 表示不限制并发数（即所有章节同时执行）。
    """
    import asyncio

    # max_concurrency <= 0 表示不限制，设为章节总数
    effective_concurrency = max_concurrency if max_concurrency > 0 else len(chapters)
    semaphore = asyncio.Semaphore(effective_concurrency)

    async def _limited_research(agent, topic, ch_id, ch_title, ch_info, research_path):
        async with semaphore:
            return await _run_single_chapter_research(
                agent, topic, ch_id, ch_title, ch_info, research_path
            )

    tasks = []
    for i, ch_info in enumerate(chapters):
        ch_id = ch_info.get("chapter_id", i + 1)
        ch_title = ch_info.get("title", f"第{ch_id}章")
        research_path = course.chapter_dir(ch_id) / "research.json"
        course.chapter_dir(ch_id).mkdir(parents=True, exist_ok=True)

        # 每章创建独立的 researcher agent 实例
        researcher_agent = _build_researcher_agent(layout, user_id)

        tasks.append(
            _limited_research(
                researcher_agent, topic, ch_id, ch_title, ch_info, research_path
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 处理异常情况
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            ch_info = chapters[i]
            ch_id = ch_info.get("chapter_id", i + 1)
            ch_title = ch_info.get("title", f"第{ch_id}章")
            logger.error("并行 research 异常 ch=%s: %s", ch_id, result)
            final_results.append(
                {
                    "ch_id": ch_id,
                    "ch_title": ch_title,
                    "ch_info": ch_info,
                    "events": [],
                    "success": False,
                    "used_fallback": False,
                    "research_path": course.chapter_dir(ch_id) / "research.json",
                }
            )
        else:
            final_results.append(result)

    return final_results


async def immersive_generate(
    topic: str,
    user_id: str,
    user_profile: str = "",
    enable_audio: bool = False,
    enable_exercises: bool = True,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """AI 主导学习 - 显式逐步编排（SSE）。

    SSE 事件类型：
      progress         { stage, pct, message }
      outline          { data }
      chapter_start    { index, total, chapter_id, title, stage }
      chapter_done     { index, total, data }
      nodes_extracted  { nodes, new_count }
      done             { topic, session_id, chapters, ... }
      error            { message }
      agent_event      { agent_type, event_type, content, step }
    """
    start_time = time.time()
    generation_started_at = time.perf_counter()

    try:
        # ── 0. 初始化 ────────────────────────────────────────────
        yield sse_event(
            "progress", stage="init", pct=2, message=f"正在初始化课程「{topic}」..."
        )

        session_id = session_id or create_session(topic, user_id=user_id)
        _log_generation_timing(session_id, "session_created", generation_started_at)
        # 在规划等长耗时操作前下发会话身份，前端可立即保存恢复地址。
        yield sse_event("session_created", session_id=session_id)
        logger.info(
            "沉浸式学习会话: %s (topic=%s, enable_audio=%s)",
            session_id,
            topic,
            enable_audio,
        )

        layout = UserDataLayout(root=DOCUMENTS_DIR, user_id=user_id)
        layout.ensure_dirs()

        course_slug = f"{_slugify(topic)}_{session_id}"
        course = CourseLayout(course_dir=COURSES_DIR / course_slug)
        course.ensure_dirs()

        yield sse_event(
            "progress", stage="init", pct=5, message="正在构建 Agent 团队..."
        )
        agents = build_sub_agents(layout, user_id=user_id)

        # ── 1. Planner：规划大纲 ─────────────────────────────────
        yield sse_event(
            "progress",
            stage="planner",
            pct=8,
            message="📋 Planner：正在规划课程大纲...",
        )

        outline_path = course.outline_file
        planner_prompt = (
            f"请为「{topic}」规划课程大纲。\n将 outline.json 写入：{outline_path}"
        )

        async for ev in stream_agent_events(
            agents["planner"],
            planner_prompt,
            "planner",
            skill_names=["pdf_courseware_orchestration"],
            start_msg="开始规划课程大纲",
            finish_msg="规划完成",
        ):
            yield ev

        logger.info("Planner 完成")
        _log_generation_timing(session_id, "outline_ready", generation_started_at)

        # 读取大纲（load_outline 内部会自动清洗 LLM 输出中的非法控制字符）
        outline = course.load_outline()
        if not outline or not outline.get("chapters"):
            yield sse_event("error", message="大纲生成失败，请重试")
            return

        # 重写清洗后的大纲到磁盘，确保后续所有读取都安全
        course.save_outline(outline)

        chapters = outline["chapters"]
        total_ch = len(chapters)

        # 读取统一用户画像用于生成个性化学习建议；前端显式传入时作为临时覆盖，不落盘。
        profile_content = (user_profile or "").strip()
        if not profile_content:
            try:
                from services.profile_service import ProfileMemoryService

                profile_content = (
                    ProfileMemoryService().build_profile_text(user_id).strip()
                )
            except Exception:
                logger.exception("读取统一画像失败 (user=%s)", safe_log(user_id))

        yield sse_event(
            "progress", stage="plan", pct=12, message="📝 正在生成个性化学习建议..."
        )
        plan_md = await build_personalized_plan(
            topic, outline, user_id, profile_content
        )
        plan_path = course.course_dir / "plan.md"
        plan_path.write_text(plan_md, encoding="utf-8")
        rel_plan_path = to_rel_path(str(plan_path))

        outline_doc_id = (
            await asyncio.to_thread(
                lambda: register_course_outline(
                    session_id=session_id,
                    topic=topic,
                    outline_path=outline_path,
                    user_id=user_id,
                )
            )
            or ""
        )

        outline_block = {
            "id": "outline",
            "type": "outline",
            "title": "学习大纲",
            "status": "ready",
            "data": {
                "outline": outline,
                "doc_id": outline_doc_id,
                "outline_path": to_rel_path(str(outline_path)),
            },
        }
        plan_block = {
            "id": "plan_md",
            "type": "md",
            "title": f"{topic} 个性化学习建议",
            "status": "ready",
            "data": {
                "subtype": "personalized_plan",
                "markdown": plan_md,
                "markdown_path": rel_plan_path,
                "estimated_chapters": total_ch,
            },
        }
        workspace_patch = {
            "topic": topic,
            "enable_audio": enable_audio,
            "enable_exercises": enable_exercises,
            "planned_chapters": total_ch,
            "generated_chapters": 0,
            "current_chapter_id": chapters[0].get("chapter_id", 1)
            if chapters
            else None,
            "chapters": [
                {
                    "chapter_id": ch.get("chapter_id", idx + 1),
                    "title": ch.get("title", f"第{idx + 1}章"),
                    "status": "pending",
                    "block_ids": [],
                }
                for idx, ch in enumerate(chapters)
            ],
        }
        next_actions = [
            {"type": "start_learning", "label": "查看学习建议"},
            {"type": "continue_generation", "label": "后台继续生成第一章"},
        ]
        upsert_canvas_block(
            session_id,
            outline_block,
            current=True,
            stage="planned",
            next_actions=next_actions,
            workspace_patch=workspace_patch,
        )
        upsert_canvas_block(session_id, plan_block, current=True, stage="planned")
        plan_doc_id = await asyncio.to_thread(
            lambda: register_course_plan(
                session_id=session_id,
                topic=topic,
                plan_path=plan_path,
                user_id=user_id,
            )
        )
        if plan_doc_id:
            plan_block["data"]["doc_id"] = plan_doc_id
            if outline_doc_id:
                outline_block["data"]["plan_doc_id"] = plan_doc_id
            # 前面 upsert 时还没拿到 doc_id，这里补持久化，避免 workspace 里 plan block 缺 doc_id
            upsert_canvas_block(session_id, plan_block, current=True, stage="planned")
            append_session_file(
                session_id, plan_doc_id, f"{topic} 个性化学习建议", "course_plan"
            )
        if outline_doc_id:
            append_session_file(
                session_id, outline_doc_id, f"{topic} 课程大纲", "course_outline"
            )

        yield sse_event(
            "progress",
            stage="planner",
            pct=15,
            message=f"✅ 大纲完成，共 {total_ch} 章",
        )
        yield sse_event("outline", data=outline)
        yield sse_event(
            "workspace_update",
            event="block_created",
            session_id=session_id,
            block=outline_block,
            next_actions=next_actions,
        )
        _log_generation_timing(
            session_id, "learning_plan_ready", generation_started_at, chapters=total_ch
        )
        yield sse_event(
            "workspace_update",
            event="block_created",
            session_id=session_id,
            block=plan_block,
            next_actions=next_actions,
        )

        # ── 2. 并行 Research + 预习手册 ─────────────────────

        tts_llm = get_llm(user_id, scene="immersive") if enable_audio else None
        chapter_results = []
        all_extracted_nodes = []  # 每章增量抽取的知识图谱节点（跨章按 id 去重）
        all_files_for_session = []
        pct_per_chapter = 75.0 / max(total_ch, 1)  # 15% ~ 90%

        # ── 2a. 并发执行所有章节的 Research ──────────────────────
        yield sse_event(
            "progress",
            stage="researcher",
            pct=16,
            message=f"🔍 并行检索所有章节资料（共 {total_ch} 章）...",
        )

        research_results = await _parallel_research_all_chapters(
            topic=topic,
            chapters=chapters,
            course=course,
            layout=layout,
            user_id=user_id,
            # Keep retrieval below provider rate limits.  A large course used to
            # launch every chapter at once, creating latency spikes and retries.
            max_concurrency=min(3, total_ch),
        )
        _log_generation_timing(
            session_id, "research_ready", generation_started_at, chapters=total_ch
        )

        # ── 2a+. 逐章推送预习手册（Research 阶段结束后统一推送）──
        # 按章节顺序推送，让前端按序展示。这里区分“真实检索成功”和“大纲兜底”，
        # 避免把 max_steps/工具异常后的 fallback 误报成资料检索完成。
        research_pct_done = 15 + int(pct_per_chapter * total_ch * 0.25)
        real_research_count = sum(
            1
            for item in research_results
            if item.get("success") and not item.get("used_fallback")
        )
        fallback_research_count = sum(
            1 for item in research_results if item.get("used_fallback")
        )
        failed_research_count = total_ch - real_research_count - fallback_research_count
        if failed_research_count:
            research_done_message = (
                f"⚠️ 资料检索阶段结束：{real_research_count} 章检索成功，"
                f"{fallback_research_count} 章使用大纲兜底，{failed_research_count} 章仍未就绪，正在生成预习手册..."
            )
        elif fallback_research_count:
            research_done_message = (
                f"✅ 资料检索阶段结束：{real_research_count} 章检索成功，"
                f"{fallback_research_count} 章使用大纲兜底，正在生成预习手册..."
            )
        else:
            research_done_message = (
                f"✅ 全部 {total_ch} 章资料检索完成，正在生成预习手册..."
            )
        yield sse_event(
            "progress",
            stage="researcher",
            pct=min(research_pct_done, 40),
            message=research_done_message,
        )

        for i, res in enumerate(research_results):
            ch_id = res["ch_id"]
            ch_title = res["ch_title"]
            ch_info = res["ch_info"]
            research_path = res["research_path"]

            # 生成预习手册 Markdown
            chapter_md_content = _build_chapter_summary_md(
                ch_title, ch_info, research_path
            )
            chapter_md_rel = ""
            chapter_md_path = None
            if chapter_md_content:
                chapter_md_path = (
                    course.chapter_dir(ch_id) / f"chapter_{ch_id:02d}_overview.md"
                )
                try:
                    chapter_md_path.parent.mkdir(parents=True, exist_ok=True)
                    chapter_md_path.write_text(chapter_md_content, encoding="utf-8")
                    chapter_md_rel = to_rel_path(str(chapter_md_path))
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning(
                        "预习手册 markdown 落盘失败 ch=%s: %s",
                        ch_id,
                        exc,
                    )
                    chapter_md_path = None

                md_doc_id = ""
                if chapter_md_path is not None:
                    try:
                        md_doc_id = (
                            await asyncio.to_thread(
                                lambda p=chapter_md_path, c=ch_id, t=ch_title: (
                                    register_chapter_overview(
                                        session_id=session_id,
                                        topic=topic,
                                        chapter_id=c,
                                        chapter_title=t,
                                        md_path=p,
                                        user_id=user_id,
                                        node_ids=[],
                                    )
                                ),
                            )
                            or ""
                        )
                    except Exception as exc:  # pylint: disable=broad-except
                        logger.warning(
                            "预习手册 markdown 登记失败 ch=%s: %s",
                            ch_id,
                            exc,
                        )

                chapter_md_block = {
                    "id": f"md_ch{ch_id}",
                    "type": "md",
                    "title": f"第{ch_id}章 {ch_title} — 预习手册",
                    "status": "ready",
                    "chapter_id": ch_id,
                    "data": {
                        "subtype": "chapter_content",
                        "markdown": chapter_md_content,
                        "md_path": chapter_md_rel,
                        "doc_id": md_doc_id,
                    },
                }
                upsert_canvas_block(session_id, chapter_md_block)
                if md_doc_id:
                    append_session_file(
                        session_id,
                        md_doc_id,
                        f"第{ch_id}章 {ch_title} · 预习手册",
                        "chapter_overview",
                    )
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=chapter_md_block,
                )
                logger.info("预习手册已推送: 第%d章 %s", ch_id, ch_title)

        # ── 3. 滚动并行预生成正文/PDF，发布与补充资源解耦 ───────────────
        # 关键：最多保持 3 个 TeX/PDF worker 在跑；任一章节 PDF ready 后立即发布，
        # 并释放并发槽补入下一章。因此第 2 章 ready 后可立即推前端，同时第 4 章
        # 可以接力进入 PDF 生成，不再等待第 1 章小测/语音或固定批次结束。
        published_pdf_by_chapter: dict[int, dict] = {}
        state_write_lock = asyncio.Lock()
        prefetch_queue: asyncio.Queue[Any] = asyncio.Queue()
        prefetch_done = False
        # PDF 一发布即入队，让习题/语音/讲解稿与后续章节的 PDF 生成并行。
        enrich_in: asyncio.Queue[tuple[int, dict] | None] = asyncio.Queue()
        enrich_enqueued: set[int] = set()
        enrich_done_marker = object()

        async def _publish_prefetched_pdf(
            batch_index: int, batch_ch: dict
        ) -> list[str]:
            async with state_write_lock:
                publication = await _publish_chapter_pdf_ready(
                    session_id=session_id,
                    topic=topic,
                    user_id=user_id,
                    course=course,
                    chapters=chapters,
                    index=batch_index,
                    ch_info=batch_ch,
                    total_ch=total_ch,
                    enable_audio=enable_audio,
                    generation_started_at=generation_started_at,
                    all_files_for_session=all_files_for_session,
                    set_current_chapter=False,
                )
                if publication:
                    published_pdf_by_chapter[publication["chapter_id"]] = publication
                    if publication["chapter_id"] not in enrich_enqueued:
                        enrich_enqueued.add(publication["chapter_id"])
                        enrich_in.put_nowait((batch_index, batch_ch))
                    return publication["events"]
                return []

        async def _produce_pdf_prefetch_events() -> None:
            try:
                await prefetch_queue.put(
                    sse_event(
                        "progress",
                        stage="tex_parallel",
                        pct=40,
                        message=f"🚀 滚动并行生成全课讲义（最多 {MAX_PARALLEL_TEX_CHAPTERS} 章同时进行，完成一个立即补入下一章）...",
                    )
                )
                async for event in _stream_parallel_tex_prefetch(
                    topic=topic,
                    chapters=chapters,
                    chapter_items=list(enumerate(chapters)),
                    course=course,
                    layout=layout,
                    user_id=user_id,
                    max_concurrency=MAX_PARALLEL_TEX_CHAPTERS,
                    publish_ready=_publish_prefetched_pdf,
                ):
                    await prefetch_queue.put(event)
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("滚动并行 PDF 预生成失败")
                await prefetch_queue.put(
                    sse_event(
                        "progress",
                        stage="tex_parallel",
                        pct=0,
                        message=f"⚠️ 滚动并行 PDF 预生成异常，将由有序阶段兜底: {exc}",
                    )
                )
            finally:
                await prefetch_queue.put(None)

        async def _wait_for_pdf_prefetch_done() -> AsyncGenerator[str, None]:
            nonlocal prefetch_done
            while not prefetch_done:
                event = await prefetch_queue.get()
                if event is None:
                    prefetch_done = True
                    break
                yield event

        prefetch_task = asyncio.create_task(_produce_pdf_prefetch_events())

        async def _pump_enrichment() -> None:
            try:
                async for ev in _stream_parallel_chapter_enrichment(
                    session_id=session_id,
                    topic=topic,
                    chapters=chapters,
                    chapter_items=[],
                    course=course,
                    layout=layout,
                    user_id=user_id,
                    enable_audio=enable_audio,
                    enable_exercises=enable_exercises,
                    tts_llm=tts_llm,
                    total_ch=total_ch,
                    pct_per_chapter=pct_per_chapter,
                    published_pdf_by_chapter=published_pdf_by_chapter,
                    state_write_lock=state_write_lock,
                    all_files_for_session=all_files_for_session,
                    max_concurrency=MAX_PARALLEL_ENRICH_CHAPTERS,
                    incoming=enrich_in,
                ):
                    await prefetch_queue.put(ev)
            except Exception:  # pylint: disable=broad-except
                logger.exception("流式章节补全异常")
            finally:
                await prefetch_queue.put(enrich_done_marker)

        enrich_task = asyncio.create_task(_pump_enrichment())

        # 持续排空 PDF 预生成事件；某章 PDF 一发布就已入队 enrichment，
        # 习题/语音/讲解稿与后续章节 PDF 生成并行，其事件也经此队列交错输出。
        async for ev in _wait_for_pdf_prefetch_done():
            yield ev
        if not prefetch_task.done():
            await prefetch_task

        enrichment_items: list[tuple[int, dict]] = []
        for i, ch_info in enumerate(chapters):
            ch_id = ch_info.get("chapter_id", i + 1)
            ch_title = ch_info.get("title", f"第{ch_id}章")
            ch_base_pct = int(15 + pct_per_chapter * i)
            tex_path = course.tex_file(ch_id)
            pdf_path = course.pdf_file(ch_id)
            images_dir = course.chapter_images_dir(ch_id)

            if not _pdf_is_ready(pdf_path, tex_path, images_dir, chapters, i):
                yield sse_event(
                    "progress",
                    stage="tex",
                    pct=int(ch_base_pct + pct_per_chapter * 0.4),
                    message=f"并行预生成未完成，正在有序兜底第 {ch_id} 章 PDF: {ch_title}",
                )
                tex_events: list[str] = []

                async def _emit_tex_event(event: str) -> None:
                    tex_events.append(event)

                await _run_tex_writer_with_retry(
                    topic=topic,
                    chapters=chapters,
                    index=i,
                    course=course,
                    layout=layout,
                    user_id=user_id,
                    emit=_emit_tex_event,
                    max_attempts=1,
                )
                for event in tex_events:
                    yield event

            if _pdf_is_ready(pdf_path, tex_path, images_dir, chapters, i):
                if ch_id not in published_pdf_by_chapter:
                    async with state_write_lock:
                        publication = await _publish_chapter_pdf_ready(
                            session_id=session_id,
                            topic=topic,
                            user_id=user_id,
                            course=course,
                            chapters=chapters,
                            index=i,
                            ch_info=ch_info,
                            total_ch=total_ch,
                            enable_audio=enable_audio,
                            generation_started_at=generation_started_at,
                            all_files_for_session=all_files_for_session,
                            set_current_chapter=False,
                        )
                    if publication:
                        published_pdf_by_chapter[ch_id] = publication
                        for event in publication["events"]:
                            yield event
                if ch_id in published_pdf_by_chapter:
                    enrichment_items.append((i, ch_info))
                continue

            pdf_error = _chapter_pdf_error(pdf_path, tex_path, images_dir, chapters, i)
            failed_chapter = {
                "chapter_id": ch_id,
                "title": ch_title,
                "status": "pending",
                "block_ids": [f"chapter_{ch_id}_status"],
                "files": [],
                "audio_enabled": enable_audio,
                "audio_files": [],
                "speaker_notes_count": 0,
                "artifact_status": {"pdf": False},
                "artifact_missing": [f"pdf_invalid: {pdf_error}"],
            }
            async with state_write_lock:
                workspace_now = read_workspace(session_id)
                workspace_data = workspace_now.get("workspace", {}) or {}
                chapters_state = list(workspace_data.get("chapters", []) or [])
                for idx, item in enumerate(chapters_state):
                    if item.get("chapter_id") == ch_id:
                        chapters_state[idx] = {**item, **failed_chapter}
                        break
                else:
                    chapters_state.append(failed_chapter)
                update_workspace(
                    session_id,
                    stage="partial_ready",
                    next_actions=[
                        {"type": "start_learning", "label": "先学习已生成内容"},
                        {"type": "continue_generation", "label": "重新生成缺失章节"},
                    ],
                    workspace={
                        "chapters": chapters_state,
                        "generated_chapters": len(
                            [
                                item
                                for item in chapters_state
                                if _chapter_is_user_available(item)
                            ]
                        ),
                        "planned_chapters": total_ch,
                        "current_chapter_id": ch_id,
                    },
                )
                failed_status_block = {
                    "id": f"chapter_{ch_id}_status",
                    "type": "chapter_status",
                    "title": f"第{ch_id}章 {ch_title}",
                    "status": "failed",
                    "chapter_id": ch_id,
                    "data": {
                        "stage": "failed",
                        "artifact_missing": failed_chapter["artifact_missing"],
                    },
                }
                upsert_canvas_block(session_id, failed_status_block)
            yield sse_event(
                "workspace_update",
                event="block_updated",
                session_id=session_id,
                block=failed_status_block,
            )
            yield sse_event(
                "progress",
                stage="tex",
                pct=min(int(ch_base_pct + pct_per_chapter), 90),
                message=f"第 {ch_id} 章 PDF 未通过发布校验，将在续传时重新生成",
            )

        # 兜底阶段发布的章节也送入 enrichment；随后关闭入队通道并排空剩余补全事件。
        for item in enrichment_items:
            ch_key = item[1].get("chapter_id", item[0] + 1)
            if ch_key not in enrich_enqueued:
                enrich_enqueued.add(ch_key)
                enrich_in.put_nowait(item)
        enrich_in.put_nowait(None)
        while True:
            ev = await prefetch_queue.get()
            if ev is enrich_done_marker:
                break
            yield ev
        await enrich_task

        chapter_results.extend(
            (published_pdf_by_chapter.get("__chapter_results__") or {}).values()
        )
        for node_list in (
            published_pdf_by_chapter.get("__extracted_nodes__") or {}
        ).values():
            all_extracted_nodes.extend(node_list)
        order_by_chapter = {
            ch.get("chapter_id", idx + 1): idx for idx, ch in enumerate(chapters)
        }
        chapter_results.sort(
            key=lambda item: order_by_chapter.get(item.get("chapter_id"), 0)
        )

        # ── 3. 知识图谱节点汇总（每章已增量抽取）──────────────
        yield sse_event(
            "progress", stage="nodes", pct=92, message="🧠 正在汇总知识大脑节点..."
        )

        # 每章已增量抽取，这里按 id 去重汇总；若增量全失败则全量兜底补抽一次
        created_nodes = []
        seen_node_ids = set()
        for n in all_extracted_nodes:
            if n.get("id") and n["id"] not in seen_node_ids:
                seen_node_ids.add(n["id"])
                created_nodes.append(n)

        if not created_nodes:
            extractor_llm = tts_llm or get_llm(user_id, scene="immersive")
            created_nodes = await asyncio.to_thread(
                extract_and_persist_nodes,
                session_id,
                topic,
                chapters,
                extractor_llm,
                user_id,
            )

        node_ids = [n["id"] for n in created_nodes]
        new_node_count = sum(1 for n in created_nodes if not n.get("existed"))

        if created_nodes:
            yield sse_event(
                "nodes_extracted",
                nodes=[{"id": n["id"], "title": n["title"]} for n in created_nodes],
                new_count=new_node_count,
            )

        # ── 4. 生成结束（不自动 complete，等用户确认） ──────────
        duration_minutes = max(1, int((time.time() - start_time) / 60))
        final_workspace = read_workspace(session_id).get("workspace", {}) or {}
        final_chapters = final_workspace.get("chapters", []) or []
        pending_chapter_ids = [
            item.get("chapter_id")
            for item in final_chapters
            if _chapter_requires_followup(item)
        ]

        # 知识节点抽取完成后，回填 node_ids 到本课程已登记的所有章节 doc
        if node_ids:

            def _backfill_node_ids():
                from repositories import DocumentRepository as _DR

                _repo = _DR()
                truncated = node_ids[:15]
                for ch in chapter_results:
                    doc_id = ch.get("pdf_doc_id")
                    if doc_id:
                        try:
                            _repo.set_node_ids(doc_id, truncated)
                        except Exception as exc:  # pylint: disable=broad-except
                            logger.warning(
                                "回填 node_ids 失败 doc_id=%s: %s", doc_id, exc
                            )

            await asyncio.to_thread(_backfill_node_ids)

        # Only a fully audited set may be presented as complete.  A failed
        # compilation remains resumable instead of being masked by a final done
        # event after other chapters happen to finish.
        is_complete = not pending_chapter_ids
        update_workspace(
            session_id,
            stage="ready" if is_complete else "partial_ready",
            next_actions=(
                [
                    {"type": "start_learning", "label": "开始学习"},
                    {"type": "complete_session", "label": "确认完成学习"},
                ]
                if is_complete
                else [
                    {"type": "start_learning", "label": "先学习已生成内容"},
                    {"type": "continue_generation", "label": "重新生成缺失章节"},
                ]
            ),
            workspace={
                "generated_chapters": len(
                    [
                        item
                        for item in final_chapters
                        if _chapter_is_user_available(item)
                    ]
                ),
                "pending_chapter_ids": pending_chapter_ids,
                "generation_duration_minutes": duration_minutes,
                "nodes_extracted": len(created_nodes),
            },
        )

        if is_complete:
            yield sse_event("progress", stage="done", pct=100, message="🎉 全部完成！")
            yield sse_event(
                "done",
                topic=topic,
                session_id=session_id,
                course_dir=str(course.course_dir),
                chapters=chapter_results,
                nodes_extracted=len(created_nodes),
                duration_minutes=duration_minutes,
            )
        else:
            yield sse_event(
                "progress",
                stage="partial_ready",
                pct=90,
                message="部分章节仍有产物未发布完整（PDF/习题/语音），可先学习已就绪内容并在之后继续生成。",
            )

    except Exception as e:  # pylint: disable=broad-except
        logger.exception("沉浸式学习生成失败")
        if session_id:
            try:
                # 检查是否为"空壳"会话（一个 ready 章节都没有）
                from repositories import SessionRepository as _SR

                _repo = _SR()
                _ws = _repo._read_workspace(session_id)
                _chapters_state = (_ws.get("workspace", {}) or {}).get(
                    "chapters", []
                ) or []
                _has_any_ready = any(
                    c.get("status") in {"ready", "learning_ready"}
                    for c in _chapters_state
                )

                if not _has_any_ready:
                    # 完全没产出：清理 DB 记录 + 课程目录 + workspace 文件，避免脏数据
                    try:
                        course_slug = f"{_slugify(topic)}_{session_id}"
                        course_dir = COURSES_DIR / course_slug
                        if course_dir.exists():
                            import shutil as _shutil

                            _shutil.rmtree(course_dir, ignore_errors=True)
                        # 删 workspace 文件
                        ws_path = _repo._workspace_path(session_id)
                        if ws_path.exists():
                            ws_path.unlink()
                        msg_path = _repo._messages_path(session_id)
                        if msg_path.exists():
                            msg_path.unlink()
                        # 删 sessions 表记录
                        _repo._execute("DELETE FROM sessions WHERE id=?", (session_id,))
                        logger.info(
                            "已清理空壳沉浸式会话：%s (topic=%s)", session_id, topic
                        )
                    except Exception:  # pylint: disable=broad-except
                        logger.exception("清理空壳会话失败")
                else:
                    # 有部分章节产出：保留，标记 failed 供前端续传
                    workspace = update_workspace(
                        session_id,
                        stage="failed",
                        next_actions=[
                            {"type": "retry_generation", "label": "重试生成"},
                            {"type": "start_learning", "label": "先学习已生成内容"},
                        ],
                        workspace={"last_error": str(e)},
                    )
                    yield sse_event(
                        "workspace_update",
                        event="workspace_failed",
                        session_id=session_id,
                        workspace=workspace,
                        next_actions=workspace.get("next_actions", []),
                    )
            except Exception:  # pylint: disable=broad-except
                logger.exception("写入失败 workspace 状态失败")
        yield sse_event("error", message=str(e))


async def immersive_resume(
    session_id: str,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """从中断处恢复沉浸式学习生成（断点续传）。

    读取已有 workspace 状态，找到第一个 pending/failed 章节，
    复用已有 outline 和 course_dir 继续生成。

    SSE 事件与 immersive_generate 相同。
    """
    from repositories import SessionRepository

    start_time = time.time()

    try:
        repo = SessionRepository()
        session = repo.get_by_id(session_id)
        if not session:
            yield sse_event("error", message="会话不存在")
            return
        if session.user_id != user_id:
            yield sse_event("error", message="无权操作该会话")
            return

        ws = repo._read_workspace(session_id)
        workspace_data = ws.get("workspace", {}) or {}
        topic = workspace_data.get("topic") or session.topic or "未知主题"
        enable_audio = bool(workspace_data.get("enable_audio", False))
        enable_exercises = bool(workspace_data.get("enable_exercises", True))
        chapters_state = workspace_data.get("chapters", []) or []

        if not chapters_state:
            yield sse_event("error", message="未找到大纲数据，请重新生成")
            return

        # 找到 course_dir
        course_slug = f"{_slugify(topic)}_{session_id}"
        course_dir = COURSES_DIR / course_slug
        if not course_dir.exists():
            yield sse_event("error", message=f"课程目录不存在: {course_slug}")
            return

        course = CourseLayout(course_dir=course_dir)
        outline = course.load_outline()
        if not outline or not outline.get("chapters"):
            yield sse_event("error", message="大纲文件损坏或不存在，请重新生成")
            return

        chapters = outline["chapters"]
        total_ch = len(chapters)

        # 恢复前不信旧 workspace 状态，先全量扫描磁盘产物。
        chapters_state, pending_ids, generated_chapters = _audit_resume_chapters(
            session_id,
            course,
            chapters,
            chapters_state,
            topic=topic,
            user_id=user_id,
            enable_audio=enable_audio,
            enable_exercises=enable_exercises,
        )
        # 回填早期章节缺失的 pdf/quiz block doc_id（修复 PDF 不可用/习题不显示）
        backfilled = _backfill_chapter_block_doc_ids(session_id, chapters_state)
        if backfilled:
            logger.info("resume: 回填 %d 个章节 block 的 doc_id", backfilled)
        pending_chapters = [
            (i, ch)
            for i, ch in enumerate(chapters)
            if ch.get("chapter_id", i + 1) in pending_ids
        ]
        next_chapter_id = (
            pending_chapters[0][1].get("chapter_id", pending_chapters[0][0] + 1)
            if pending_chapters
            else None
        )
        next_actions = [{"type": "start_learning", "label": "先学习已生成内容"}]
        if next_chapter_id:
            next_actions.append(
                {
                    "type": "continue_generation",
                    "label": f"继续生成第{next_chapter_id}章",
                }
            )

        audited_workspace = update_workspace(
            session_id,
            stage="partial_ready" if pending_chapters else "ready",
            next_actions=next_actions,
            workspace={
                "chapters": chapters_state,
                "enable_audio": enable_audio,
                "enable_exercises": enable_exercises,
                "generated_chapters": generated_chapters,
                "planned_chapters": total_ch,
                "current_chapter_id": next_chapter_id,
            },
        )
        yield sse_event(
            "workspace_update",
            event="artifact_audit_done",
            session_id=session_id,
            workspace={
                "enable_audio": enable_audio,
                "generated_chapters": generated_chapters,
                "planned_chapters": total_ch,
                "pending_chapter_ids": sorted(pending_ids),
            },
            canvas_blocks=audited_workspace.get("canvas_blocks", []),
            next_actions=next_actions,
        )

        if not pending_chapters:
            yield sse_event(
                "progress",
                stage="done",
                pct=100,
                message="所有章节产物校验通过，无需继续生成",
            )
            return

        yield sse_event(
            "progress",
            stage="init",
            pct=5,
            message=f"恢复生成：{topic}（已校验 {total_ch} 章，需补生成 {len(pending_chapters)} 章）",
        )

        # ── 推送已完成章节的产物到前端（避免已完成章节在前端不可见）──
        state_by_id = {
            c.get("chapter_id"): c
            for c in chapters_state
            if c.get("chapter_id") is not None
        }
        for idx_done, ch_done in enumerate(chapters):
            ch_done_id = ch_done.get("chapter_id", idx_done + 1)
            if ch_done_id in pending_ids:
                continue
            ch_done_title = ch_done.get("title", f"第{ch_done_id}章")
            ch_done_state = state_by_id.get(ch_done_id, {})
            artifact = _chapter_artifact_status(
                course,
                ch_done,
                idx_done,
                chapters=chapters,
                enable_audio=enable_audio,
                enable_exercises=enable_exercises,
            )
            # 推送预习手册
            overview_done_path = (
                course.chapter_dir(ch_done_id) / f"chapter_{ch_done_id:02d}_overview.md"
            )
            if overview_done_path.exists() and overview_done_path.stat().st_size > 50:
                md_content_done = overview_done_path.read_text(encoding="utf-8")
                md_rel_done = to_rel_path(str(overview_done_path))
                md_block_done = {
                    "id": f"md_ch{ch_done_id}",
                    "type": "md",
                    "title": f"第{ch_done_id}章 {ch_done_title} — 预习手册",
                    "status": "ready",
                    "chapter_id": ch_done_id,
                    "data": {
                        "subtype": "chapter_content",
                        "markdown": md_content_done,
                        "md_path": md_rel_done,
                    },
                }
                upsert_canvas_block(session_id, md_block_done)
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=md_block_done,
                )
            # 推送 PDF
            pdf_done_path = course.pdf_file(ch_done_id)
            if artifact["checks"].get("pdf"):
                pdf_rel_done = to_rel_path(str(pdf_done_path))
                # 从 chapters_state 取已登记的 doc_id，避免用空值覆盖导致 PDF 不可用
                pdf_doc_id_done = ch_done_state.get("pdf_doc_id", "") or ""
                pdf_block_done = {
                    "id": f"pdf_ch{ch_done_id}",
                    "type": "pdf",
                    "title": f"第{ch_done_id}章 {ch_done_title}",
                    "status": "ready",
                    "chapter_id": ch_done_id,
                    "data": {
                        "url": (
                            f"/api/documents/{pdf_doc_id_done}/raw"
                            if pdf_doc_id_done
                            else ""
                        ),
                        "pdf_path": pdf_rel_done,
                        "doc_id": pdf_doc_id_done,
                        "artifact_revision": artifact["pdf_revision"],
                        "num_pages": artifact["num_frames"],
                        "audio_enabled": enable_audio,
                        "audio_files": artifact["audio_files"],
                        "audio_doc_id": ch_done_state.get("audio_doc_id", "") or "",
                    },
                }
                upsert_canvas_block(session_id, pdf_block_done)
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=pdf_block_done,
                )
            # 推送习题
            exercises_done_path = course.exercises_file(ch_done_id)
            if artifact["checks"].get("exercises") and enable_exercises:
                ex_rel_done = to_rel_path(str(exercises_done_path))
                ex_doc_id_done = ch_done_state.get("exercises_doc_id", "") or ""
                quiz_block_done = {
                    "id": f"quiz_ch{ch_done_id}_bank",
                    "type": "quiz_batch",
                    "title": f"第{ch_done_id}章小测",
                    "status": "ready",
                    "chapter_id": ch_done_id,
                    "data": {
                        "source": "exercises_md",
                        "exercises_path": ex_rel_done,
                        "doc_id": ex_doc_id_done,
                        "exercises_doc_id": ex_doc_id_done,
                        "display_limit": 3,
                        "strategy": "show_2_to_3_questions_first",
                    },
                }
                upsert_canvas_block(session_id, quiz_block_done)
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=quiz_block_done,
                )
            # 推送章节状态
            chapter_done_block_ids = [f"chapter_{ch_done_id}_status"]
            if artifact["checks"].get("pdf"):
                chapter_done_block_ids.append(f"pdf_ch{ch_done_id}")
            if artifact["checks"].get("exercises") and enable_exercises:
                chapter_done_block_ids.append(f"quiz_ch{ch_done_id}_bank")
            done_status_block = {
                "id": f"chapter_{ch_done_id}_status",
                "type": "chapter_status",
                "title": f"第{ch_done_id}章 {ch_done_title}",
                "status": "ready",
                "chapter_id": ch_done_id,
                "data": {"stage": "ready", "block_ids": chapter_done_block_ids},
            }
            upsert_canvas_block(session_id, done_status_block)
            yield sse_event(
                "workspace_update",
                event="block_updated",
                session_id=session_id,
                block=done_status_block,
            )
        logger.info(
            "resume: 已推送 %d 个已完成章节的产物到前端",
            total_ch - len(pending_chapters),
        )

        # 重建 layout；并发 enrichment 会为每章单独创建 exercises agent。
        layout = UserDataLayout(root=DOCUMENTS_DIR, user_id=user_id)

        tts_llm = get_llm(user_id, scene="immersive") if enable_audio else None
        chapter_results = []
        all_files_for_session = []
        pct_per_chapter = 75.0 / max(len(pending_chapters), 1)

        # ── 并行 Research（已存在则跳过）──────────────────────────
        # 筛选出需要执行 research 的章节
        chapters_needing_research = []
        chapters_with_research = []
        for orig_idx, ch_info in pending_chapters:
            ch_id = ch_info.get("chapter_id", orig_idx + 1)
            research_path = course.chapter_dir(ch_id) / "research.json"
            course.chapter_dir(ch_id).mkdir(parents=True, exist_ok=True)
            if research_path.exists() and research_path.stat().st_size > 50:
                chapters_with_research.append((orig_idx, ch_info))
                logger.info("resume: 复用已有 research.json ch=%s", ch_id)
            else:
                chapters_needing_research.append((orig_idx, ch_info))

        # 对需要 research 的章节并行执行
        if chapters_needing_research:
            yield sse_event(
                "progress",
                stage="researcher",
                pct=16,
                message=f"🔍 并行检索 {len(chapters_needing_research)} 章资料...",
            )

            research_chapters_list = [
                ch_info for _, ch_info in chapters_needing_research
            ]
            research_results = await _parallel_research_all_chapters(
                topic=topic,
                chapters=research_chapters_list,
                course=course,
                layout=layout,
                user_id=user_id,
                max_concurrency=len(research_chapters_list),
            )
            real_research_count = sum(
                1
                for item in research_results
                if item.get("success") and not item.get("used_fallback")
            )
            fallback_research_count = sum(
                1 for item in research_results if item.get("used_fallback")
            )
            failed_research_count = (
                len(research_results) - real_research_count - fallback_research_count
            )
            logger.info(
                "resume: 并行 research 阶段结束，真实检索成功=%d，fallback=%d，失败=%d",
                real_research_count,
                fallback_research_count,
                failed_research_count,
            )
        else:
            yield sse_event(
                "progress",
                stage="researcher",
                pct=20,
                message="⏭️ 所有章节资料已就绪，跳过检索",
            )

        # ── 逐章推送预习手册（Research 完成后统一推送）──────────────
        for orig_idx, ch_info in pending_chapters:
            ch_id = ch_info.get("chapter_id", orig_idx + 1)
            ch_title = ch_info.get("title", f"第{ch_id}章")
            research_path = course.chapter_dir(ch_id) / "research.json"

            # 规范化 research.raw_text
            try:
                if _normalize_research_raw_text_file(research_path):
                    logger.info("resume: 已规范化 research.raw_text ch=%s", ch_id)
            except Exception as exc:
                logger.warning(
                    "resume: 规范化 research.raw_text 失败 ch=%s: %s", ch_id, exc
                )

            # 预习手册 Markdown
            overview_path_resume = (
                course.chapter_dir(ch_id) / f"chapter_{ch_id:02d}_overview.md"
            )
            overview_exists = (
                overview_path_resume.exists()
                and overview_path_resume.stat().st_size > 50
            )
            if not overview_exists:
                chapter_md_content = _build_chapter_summary_md(
                    ch_title, ch_info, research_path
                )
                if chapter_md_content:
                    try:
                        overview_path_resume.parent.mkdir(parents=True, exist_ok=True)
                        overview_path_resume.write_text(
                            chapter_md_content, encoding="utf-8"
                        )
                    except Exception as exc:
                        logger.warning("resume: 预习手册落盘失败 ch=%s: %s", ch_id, exc)
                        chapter_md_content = ""
            else:
                chapter_md_content = overview_path_resume.read_text(encoding="utf-8")

            if chapter_md_content:
                chapter_md_rel = to_rel_path(str(overview_path_resume))
                md_doc_id = ""
                try:
                    md_doc_id = (
                        await asyncio.to_thread(
                            lambda p=overview_path_resume, c=ch_id, t=ch_title: (
                                register_chapter_overview(
                                    session_id=session_id,
                                    topic=topic,
                                    chapter_id=c,
                                    chapter_title=t,
                                    md_path=p,
                                    user_id=user_id,
                                    node_ids=[],
                                )
                            ),
                        )
                        or ""
                    )
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning(
                        "resume: 预习手册 markdown 登记失败 ch=%s: %s", ch_id, exc
                    )

                chapter_md_block = {
                    "id": f"md_ch{ch_id}",
                    "type": "md",
                    "title": f"第{ch_id}章 {ch_title} — 预习手册",
                    "status": "ready",
                    "chapter_id": ch_id,
                    "data": {
                        "subtype": "chapter_content",
                        "markdown": chapter_md_content,
                        "md_path": chapter_md_rel,
                        "doc_id": md_doc_id,
                    },
                }
                upsert_canvas_block(session_id, chapter_md_block)
                if md_doc_id:
                    append_session_file(
                        session_id,
                        md_doc_id,
                        f"第{ch_id}章 {ch_title} · 预习手册",
                        "md",
                    )
                yield sse_event(
                    "workspace_update",
                    event="block_created",
                    session_id=session_id,
                    block=chapter_md_block,
                )
                logger.info("resume: 预习手册已推送 ch=%s", ch_id)

        # ── 滚动并行预生成缺失 PDF，发布与补齐资源解耦 ───────────────
        published_pdf_by_chapter: dict[int, dict] = {}
        state_write_lock = asyncio.Lock()
        prefetch_queue: asyncio.Queue[Any] = asyncio.Queue()
        prefetch_done = False
        # PDF 一发布即入队，让习题/语音/讲解稿与后续章节的 PDF 生成并行。
        enrich_in: asyncio.Queue[tuple[int, dict] | None] = asyncio.Queue()
        enrich_enqueued: set[int] = set()
        enrich_done_marker = object()

        async def _publish_prefetched_pdf(
            batch_index: int, batch_ch: dict
        ) -> list[str]:
            async with state_write_lock:
                publication = await _publish_chapter_pdf_ready(
                    session_id=session_id,
                    topic=topic,
                    user_id=user_id,
                    course=course,
                    chapters=chapters,
                    index=batch_index,
                    ch_info=batch_ch,
                    total_ch=total_ch,
                    enable_audio=enable_audio,
                    generation_started_at=None,
                    all_files_for_session=all_files_for_session,
                    set_current_chapter=False,
                )
                if publication:
                    published_pdf_by_chapter[publication["chapter_id"]] = publication
                    if publication["chapter_id"] not in enrich_enqueued:
                        enrich_enqueued.add(publication["chapter_id"])
                        enrich_in.put_nowait((batch_index, batch_ch))
                    return publication["events"]
                return []

        async def _produce_pdf_prefetch_events() -> None:
            try:
                await prefetch_queue.put(
                    sse_event(
                        "progress",
                        stage="tex_parallel",
                        pct=35,
                        message=f"🚀 续传滚动并行生成缺失讲义（最多 {MAX_PARALLEL_TEX_CHAPTERS} 章同时进行，完成一个立即补入下一章）...",
                    )
                )
                async for event in _stream_parallel_tex_prefetch(
                    topic=topic,
                    chapters=chapters,
                    chapter_items=pending_chapters,
                    course=course,
                    layout=layout,
                    user_id=user_id,
                    max_concurrency=MAX_PARALLEL_TEX_CHAPTERS,
                    publish_ready=_publish_prefetched_pdf,
                ):
                    await prefetch_queue.put(event)
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("resume: 滚动并行 PDF 预生成失败")
                await prefetch_queue.put(
                    sse_event(
                        "progress",
                        stage="tex_parallel",
                        pct=0,
                        message=f"⚠️ 续传滚动并行 PDF 预生成异常，将由有序阶段兜底: {exc}",
                    )
                )
            finally:
                await prefetch_queue.put(None)

        async def _wait_for_pdf_prefetch_done() -> AsyncGenerator[str, None]:
            nonlocal prefetch_done
            while not prefetch_done:
                event = await prefetch_queue.get()
                if event is None:
                    prefetch_done = True
                    break
                yield event

        prefetch_task = asyncio.create_task(_produce_pdf_prefetch_events())

        async def _pump_enrichment() -> None:
            try:
                async for ev in _stream_parallel_chapter_enrichment(
                    session_id=session_id,
                    topic=topic,
                    chapters=chapters,
                    chapter_items=[],
                    course=course,
                    layout=layout,
                    user_id=user_id,
                    enable_audio=enable_audio,
                    enable_exercises=enable_exercises,
                    tts_llm=tts_llm,
                    total_ch=total_ch,
                    pct_per_chapter=pct_per_chapter,
                    published_pdf_by_chapter=published_pdf_by_chapter,
                    state_write_lock=state_write_lock,
                    all_files_for_session=all_files_for_session,
                    max_concurrency=MAX_PARALLEL_ENRICH_CHAPTERS,
                    incoming=enrich_in,
                ):
                    await prefetch_queue.put(ev)
            except Exception:  # pylint: disable=broad-except
                logger.exception("resume: 流式章节补全异常")
            finally:
                await prefetch_queue.put(enrich_done_marker)

        enrich_task = asyncio.create_task(_pump_enrichment())

        # 已有 PDF 但缺小测/音频的章节无需等待预生成，立即入队补全。
        for early_idx, early_ch in pending_chapters:
            early_id = early_ch.get("chapter_id", early_idx + 1)
            if early_id in enrich_enqueued:
                continue
            if _pdf_is_ready(
                course.pdf_file(early_id),
                course.tex_file(early_id),
                course.chapter_images_dir(early_id),
                chapters,
                early_idx,
            ):
                enrich_enqueued.add(early_id)
                enrich_in.put_nowait((early_idx, early_ch))

        # 持续排空 PDF 预生成/发布事件；补全事件也经同一队列交错输出。
        async for ev in _wait_for_pdf_prefetch_done():
            yield ev
        if not prefetch_task.done():
            await prefetch_task

        enrichment_items: list[tuple[int, dict]] = []
        for progress_idx, (orig_idx, ch_info) in enumerate(pending_chapters):
            ch_id = ch_info.get("chapter_id", orig_idx + 1)
            ch_title = ch_info.get("title", f"第{ch_id}章")
            ch_base_pct = int(15 + pct_per_chapter * progress_idx)
            tex_path = course.tex_file(ch_id)
            pdf_path = course.pdf_file(ch_id)
            images_dir = course.chapter_images_dir(ch_id)

            if not _pdf_is_ready(pdf_path, tex_path, images_dir, chapters, orig_idx):
                yield sse_event(
                    "progress",
                    stage="tex",
                    pct=int(ch_base_pct + pct_per_chapter * 0.4),
                    message=f"并行预生成未完成，正在有序兜底第 {ch_id} 章 PDF: {ch_title}",
                )
                tex_events: list[str] = []

                async def _emit_tex_event(event: str) -> None:
                    tex_events.append(event)

                await _run_tex_writer_with_retry(
                    topic=topic,
                    chapters=chapters,
                    index=orig_idx,
                    course=course,
                    layout=layout,
                    user_id=user_id,
                    emit=_emit_tex_event,
                    max_attempts=1,
                )
                for event in tex_events:
                    yield event

            if _pdf_is_ready(pdf_path, tex_path, images_dir, chapters, orig_idx):
                if (
                    ch_id not in published_pdf_by_chapter
                    and ch_id not in enrich_enqueued
                ):
                    async with state_write_lock:
                        publication = await _publish_chapter_pdf_ready(
                            session_id=session_id,
                            topic=topic,
                            user_id=user_id,
                            course=course,
                            chapters=chapters,
                            index=orig_idx,
                            ch_info=ch_info,
                            total_ch=total_ch,
                            enable_audio=enable_audio,
                            generation_started_at=None,
                            all_files_for_session=all_files_for_session,
                            set_current_chapter=False,
                        )
                    if publication:
                        published_pdf_by_chapter[ch_id] = publication
                        for event in publication["events"]:
                            yield event
                if ch_id in published_pdf_by_chapter or ch_id in enrich_enqueued:
                    enrichment_items.append((orig_idx, ch_info))
                continue

            pdf_error = _chapter_pdf_error(
                pdf_path, tex_path, images_dir, chapters, orig_idx
            )
            failed_chapter = {
                "chapter_id": ch_id,
                "title": ch_title,
                "status": "pending",
                "block_ids": [f"chapter_{ch_id}_status"],
                "files": [],
                "audio_enabled": enable_audio,
                "audio_files": [],
                "speaker_notes_count": 0,
                "artifact_status": {"pdf": False},
                "artifact_missing": [f"pdf_invalid: {pdf_error}"],
            }
            async with state_write_lock:
                workspace_now = read_workspace(session_id)
                workspace_data = workspace_now.get("workspace", {}) or {}
                chapters_state = list(workspace_data.get("chapters", []) or [])
                for idx2, item in enumerate(chapters_state):
                    if item.get("chapter_id") == ch_id:
                        chapters_state[idx2] = {**item, **failed_chapter}
                        break
                else:
                    chapters_state.append(failed_chapter)
                update_workspace(
                    session_id,
                    stage="partial_ready",
                    next_actions=[
                        {"type": "start_learning", "label": "先学习已生成内容"},
                        {"type": "continue_generation", "label": "重新生成缺失章节"},
                    ],
                    workspace={
                        "chapters": chapters_state,
                        "generated_chapters": len(
                            [
                                item
                                for item in chapters_state
                                if _chapter_is_user_available(item)
                            ]
                        ),
                        "planned_chapters": total_ch,
                        "current_chapter_id": ch_id,
                    },
                )
                failed_status_block = {
                    "id": f"chapter_{ch_id}_status",
                    "type": "chapter_status",
                    "title": f"第{ch_id}章 {ch_title}",
                    "status": "failed",
                    "chapter_id": ch_id,
                    "data": {
                        "stage": "failed",
                        "artifact_missing": failed_chapter["artifact_missing"],
                    },
                }
                upsert_canvas_block(session_id, failed_status_block)
            yield sse_event(
                "workspace_update",
                event="block_updated",
                session_id=session_id,
                block=failed_status_block,
            )
            yield sse_event(
                "progress",
                stage="tex",
                pct=min(int(ch_base_pct + pct_per_chapter), 90),
                message=f"第 {ch_id} 章 PDF 未通过发布校验，将在下次续传时重试",
            )

        # 兜底阶段发布的章节也送入 enrichment；随后关闭入队通道并排空剩余补全事件。
        for item in enrichment_items:
            ch_key = item[1].get("chapter_id", item[0] + 1)
            if ch_key not in enrich_enqueued:
                enrich_enqueued.add(ch_key)
                enrich_in.put_nowait(item)
        enrich_in.put_nowait(None)
        while True:
            ev = await prefetch_queue.get()
            if ev is enrich_done_marker:
                break
            yield ev
        await enrich_task

        chapter_results.extend(
            (published_pdf_by_chapter.get("__chapter_results__") or {}).values()
        )
        all_extracted_nodes = []
        for node_list in (
            published_pdf_by_chapter.get("__extracted_nodes__") or {}
        ).values():
            all_extracted_nodes.extend(node_list)
        order_by_chapter = {
            ch.get("chapter_id", idx + 1): idx for idx, ch in enumerate(chapters)
        }
        chapter_results.sort(
            key=lambda item: order_by_chapter.get(item.get("chapter_id"), 0)
        )

        # 知识图谱节点汇总（每章已在 enrichment worker 中增量抽取）
        yield sse_event(
            "progress", stage="nodes", pct=92, message="🧠 正在汇总知识大脑节点..."
        )
        created_nodes = []
        seen_node_ids = set()
        for node in all_extracted_nodes:
            if node.get("id") and node["id"] not in seen_node_ids:
                seen_node_ids.add(node["id"])
                created_nodes.append(node)
        if not created_nodes and enrichment_items:
            extractor_llm = tts_llm or get_llm(user_id, scene="immersive")
            new_chapters_info = [ch for _, ch in enrichment_items]
            created_nodes = await asyncio.to_thread(
                extract_and_persist_nodes,
                session_id,
                topic,
                new_chapters_info,
                extractor_llm,
                user_id,
            )
        if created_nodes:
            yield sse_event(
                "nodes_extracted",
                nodes=[{"id": n["id"], "title": n["title"]} for n in created_nodes],
                new_count=sum(1 for n in created_nodes if not n.get("existed")),
            )

        final_workspace = read_workspace(session_id).get("workspace", {}) or {}
        final_chapters = final_workspace.get("chapters", []) or []
        pending_chapter_ids = [
            item.get("chapter_id")
            for item in final_chapters
            if _chapter_requires_followup(item)
        ]
        if pending_chapter_ids:
            update_workspace(
                session_id,
                stage="partial_ready",
                next_actions=[
                    {"type": "start_learning", "label": "先学习已生成内容"},
                    {"type": "continue_generation", "label": "重新生成缺失章节"},
                ],
                workspace={
                    "generated_chapters": len(
                        [
                            item
                            for item in final_chapters
                            if _chapter_is_user_available(item)
                        ]
                    ),
                    "planned_chapters": total_ch,
                    "pending_chapter_ids": pending_chapter_ids,
                },
            )
            yield sse_event(
                "progress",
                stage="partial_ready",
                pct=90,
                message="仍有章节产物未发布完整（PDF/习题/语音），可先学习并在之后继续生成。",
            )
        else:
            update_workspace(
                session_id,
                stage="ready",
                next_actions=[
                    {"type": "start_learning", "label": "开始学习"},
                    {"type": "complete_session", "label": "确认完成学习"},
                ],
                workspace={
                    "generated_chapters": len(
                        [
                            item
                            for item in final_chapters
                            if _chapter_is_user_available(item)
                        ]
                    ),
                    "planned_chapters": total_ch,
                    "pending_chapter_ids": [],
                },
            )
            yield sse_event(
                "progress", stage="done", pct=100, message="🎉 恢复生成完成！"
            )
            yield sse_event(
                "done",
                topic=topic,
                session_id=session_id,
                course_dir=str(course.course_dir),
                chapters=chapter_results,
                nodes_extracted=len(created_nodes),
                duration_minutes=max(1, int((time.time() - start_time) / 60)),
            )

    except Exception as e:
        logger.exception("沉浸式学习恢复生成失败")
        try:
            current = read_workspace(session_id)
            if current.get("stage") not in {"ready", "completed"}:
                update_workspace(
                    session_id,
                    stage="failed",
                    next_actions=[
                        {"type": "resume_generation", "label": "继续生成"},
                        {"type": "start_learning", "label": "先学习已生成内容"},
                    ],
                    workspace={"generation_status": "failed", "last_error": str(e)},
                )
        except Exception:  # pylint: disable=broad-except
            logger.exception("写入恢复失败 workspace 状态失败")
        yield sse_event("error", session_id=session_id, message=str(e))
