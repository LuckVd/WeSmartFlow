"""TTS 与讲解稿（speaker notes）相关工具。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from json_repair import repair_json

from agent_core.llm.base import BaseLLM

logger = logging.getLogger(__name__)


def count_beamer_frames(tex_path: Path) -> int:
    """统计 Beamer 讲义的 frame 数量。"""
    if not tex_path.exists():
        return 0
    return tex_path.read_text(encoding="utf-8").count(r"\begin{frame}")


def _strip_latex_inline(text: str) -> str:
    """Best-effort cleanup for short frame titles used in fallback narration."""
    text = re.sub(r"%.*", "", text or "")
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?", "", text)
    text = re.sub(r"[{}$]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_frame_titles(tex_content: str, num_pages: int) -> list[str]:
    """Extract simple Beamer frame titles for deterministic note fallback."""
    titles: list[str] = []
    for match in re.finditer(r"\\frametitle(?:\[[^\]]*\])?\{([^{}]*)\}", tex_content):
        title = _strip_latex_inline(match.group(1))
        if title:
            titles.append(title)
    while len(titles) < num_pages:
        titles.append(f"第{len(titles) + 1}页")
    return titles[:num_pages]


def _speaker_note_fallback(frame_number: int, title: str) -> str:
    title = title or f"第{frame_number}页"
    return (
        f"同学们，这一页我们先聚焦“{title}”。请先观察页面中的核心概念、"
        "公式或例子，想一想它和前后内容的联系；接下来我们把关键思路"
        "一步步串起来，抓住这一页最重要的理解入口。"
    )


def _json_candidates(raw: str) -> list[str]:
    """Collect plausible JSON snippets from an LLM response."""
    text = (raw or "").strip()
    if not text:
        return []
    candidates: list[str] = []
    for match in re.finditer(
        r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE
    ):
        block = match.group(1).strip()
        if block:
            candidates.append(block)
    candidates.append(text)
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start >= 0 and end > start:
            candidates.append(text[start : end + 1])
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _loads_json_lenient(candidate: str) -> Any:
    """Parse JSON with json_repair and LaTeX backslash protection."""
    attempts = [candidate]
    protected = re.sub(r"(?<!\\)\\([A-Za-z]{2,})", r"\\\\\1", candidate)
    attempts.append(protected)
    attempts.append(re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", protected))
    last_error: Exception | None = None
    for text in attempts:
        try:
            return json.loads(text)
        except Exception as exc:  # pylint: disable=broad-except
            last_error = exc
        try:
            return repair_json(text, return_objects=True)
        except Exception as exc:  # pylint: disable=broad-except
            last_error = exc
    if last_error:
        raise last_error
    raise ValueError("empty JSON candidate")


def _coerce_frame_number(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group())
    return None


def _normalize_speaker_notes_payload(data: Any, num_pages: int) -> dict[int, str]:
    """Normalize common speaker-note shapes into {frame_number: text}."""
    if isinstance(data, dict):
        for key in (
            "notes",
            "speaker_notes",
            "narrations",
            "scripts",
            "items",
            "frames",
        ):
            value = data.get(key)
            if isinstance(value, list):
                return _normalize_speaker_notes_payload(value, num_pages)
        numeric_items = []
        for key, value in data.items():
            frame = _coerce_frame_number(key)
            if frame is not None:
                numeric_items.append({"frame": frame, "text": value})
        if numeric_items:
            return _normalize_speaker_notes_payload(numeric_items, num_pages)
        return {}

    if not isinstance(data, list):
        return {}

    normalized: dict[int, str] = {}
    next_frame = 1
    for item in data:
        frame = None
        text: Any = None
        if isinstance(item, str):
            frame = next_frame
            text = item
        elif isinstance(item, dict):
            for frame_key in (
                "frame",
                "frame_number",
                "page",
                "page_number",
                "slide",
                "index",
            ):
                if frame_key in item:
                    frame = _coerce_frame_number(item.get(frame_key))
                    break
            for text_key in (
                "text",
                "script",
                "note",
                "narration",
                "content",
                "speaker_note",
            ):
                if item.get(text_key) is not None:
                    text = item.get(text_key)
                    break
            if frame is None:
                frame = next_frame
        if frame is None or frame < 1 or frame > num_pages:
            next_frame += 1
            continue
        note = str(text or "").strip()
        if note:
            normalized[frame] = note
        next_frame = max(next_frame + 1, frame + 1)
    return normalized


def _notes_map_to_list(
    notes_by_frame: dict[int, str], num_pages: int, tex_content: str = ""
) -> list[str]:
    titles = _extract_frame_titles(tex_content, num_pages)
    return [
        notes_by_frame.get(frame) or _speaker_note_fallback(frame, titles[frame - 1])
        for frame in range(1, num_pages + 1)
    ]


def parse_speaker_notes_response(
    raw: str, num_pages: int, tex_content: str = "", *, fill_missing: bool = True
) -> list[str]:
    """Parse speaker notes from imperfect LLM output.

    Supports raw JSON arrays, fenced JSON, wrapper objects such as
    {"notes": [...]}, object arrays with page/frame fields, and numeric-keyed
    objects.  Missing frames can be filled with deterministic narration so a
    single malformed item does not make the whole chapter lose audio.
    """
    if num_pages <= 0:
        return []
    best: dict[int, str] = {}
    last_error: Exception | None = None
    for candidate in _json_candidates(raw):
        try:
            parsed = _loads_json_lenient(candidate)
            notes_by_frame = _normalize_speaker_notes_payload(parsed, num_pages)
        except Exception as exc:  # pylint: disable=broad-except
            last_error = exc
            continue
        if len(notes_by_frame) > len(best):
            best = notes_by_frame
        if len(best) >= num_pages:
            break
    if not best:
        if last_error:
            logger.warning("讲解稿解析失败: %s", last_error)
        return _notes_map_to_list({}, num_pages, tex_content) if fill_missing else []
    if len(best) < num_pages:
        missing = [frame for frame in range(1, num_pages + 1) if frame not in best]
        logger.warning(
            "讲解稿页码不完整：parsed=%d expected=%d missing=%s",
            len(best),
            num_pages,
            missing[:10],
        )
    return (
        _notes_map_to_list(best, num_pages, tex_content)
        if fill_missing
        else [best[frame] for frame in range(1, num_pages + 1) if frame in best]
    )


def generate_speaker_notes(llm: BaseLLM, tex_path: Path, num_pages: int) -> List[str]:
    """根据 LaTeX 源码为每一页生成讲解旁白，返回字符串列表。"""
    if not tex_path.exists():
        return []
    tex_content = tex_path.read_text(encoding="utf-8")
    prompt = (
        f"以下是一份 LaTeX Beamer 讲义的完整源码，共约 {num_pages} 页 (frame)。\n\n"
        f"请你以一位**经验丰富的老师**的身份，为每一页写一段**讲解旁白**。\n\n"
        f"## 要求\n\n"
        f"1. **不要复读幻灯片上的文字**——学生自己能看到。你的角色是启发、引导、补充。\n"
        f"2. **循循善诱**：用提问、类比、生活化例子帮助学生理解，而非干巴巴念定义。\n"
        f"3. **该简短就简短**：如果这页只是标题页或目录页，一两句话即可（20-40字）；\n"
        f"   如果是核心知识点页，可以展开讲（80-150字）。\n"
        f"4. **准确**：不要编造公式含义或错误解释概念。\n"
        f"5. **口语化**：像老师在课堂上自然地说话，可以用'同学们'、'大家注意'、'我们来想一想'等。\n"
        f"6. **连贯**：前后页的讲解要有衔接，像一堂课的连续讲述。\n\n"
        f"## 输出格式\n\n"
        f"严格输出 JSON 数组，长度等于页数（{num_pages}），每项是一个字符串。\n"
        f"不要包含 Markdown 代码围栏，直接输出 JSON。\n\n"
        f"## 讲义源码\n\n"
        f"```tex\n{tex_content[:8000]}\n```"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是一位深受学生喜爱的大学老师，擅长用通俗易懂的语言讲解复杂知识。"
                "你的讲解风格是：先抛出问题引发思考，再给出清晰解释，最后用一句话总结要点。"
                "语气亲切自然，像面对面上课一样。输出必须是可解析 JSON。"
            ),
        },
        {"role": "user", "content": prompt},
    ]
    best_notes: list[str] = []
    best_raw = ""
    for attempt in range(2):
        try:
            response = llm.think(
                messages,
                config={
                    "temperature": 0.5 if attempt == 0 else 0.2,
                    "max_tokens": 5000,
                },
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("讲解稿生成 LLM 调用失败 attempt=%d: %s", attempt + 1, exc)
            break
        raw = response.content or ""
        parsed = parse_speaker_notes_response(
            raw, num_pages, tex_content, fill_missing=False
        )
        if len(parsed) > len(best_notes):
            best_notes = parsed
            best_raw = raw
        if len(parsed) >= num_pages:
            return parsed[:num_pages]
        logger.warning(
            "讲解稿结构化输出不完整 attempt=%d parsed=%d expected=%d raw_len=%d",
            attempt + 1,
            len(parsed),
            num_pages,
            len(raw),
        )
        messages = [
            messages[0],
            {
                "role": "user",
                "content": (
                    f"上一次讲解稿输出无法覆盖全部 {num_pages} 页。"
                    "请重新输出严格 JSON，格式必须是："
                    '[{"frame":1,"text":"第一页讲解"}, ...]。'
                    f"frame 必须从 1 到 {num_pages} 连续覆盖，不要 Markdown 围栏。\n\n"
                    f"讲义源码：\n```tex\n{tex_content[:8000]}\n```"
                ),
            },
        ]
    if best_notes:
        logger.warning(
            "讲解稿最终使用部分解析结果并本地补齐：parsed=%d expected=%d",
            len(best_notes),
            num_pages,
        )
        return parse_speaker_notes_response(
            best_raw,
            num_pages,
            tex_content,
            fill_missing=True,
        )
    logger.warning("讲解稿最终未获得可解析输出，使用 frame 标题本地兜底")
    return _notes_map_to_list({}, num_pages, tex_content)


def run_tts_for_chapter(
    chapter_dir: Path,
    speaker_notes: List[str],
    user_id: str = "",
    *,
    frame_numbers: List[int] | None = None,
    max_concurrency: int = 3,
) -> List[Dict[str, Any]]:
    """对单个章节的讲解稿批量合成语音。

    TTS 客户端走工厂（qwen3-tts 优先，单条失败回退 macOS say，
    都不可用则不生成）；额度拦截与记账挂在客户端上。
    """
    if not speaker_notes:
        return []
    from services.tts_factory import get_tts

    tts = get_tts(user_id, scene="immersive")
    if tts is None:
        logger.warning("无可用 TTS 通道，跳过语音生成（%d 条）", len(speaker_notes))
        return []
    audio_dir = chapter_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    numbers = frame_numbers or list(range(1, len(speaker_notes) + 1))
    if len(numbers) != len(speaker_notes) or any(number < 1 for number in numbers):
        raise ValueError("frame_numbers 必须与 speaker_notes 一一对应且从 1 开始")
    items = [
        {"text": note, "filename": f"frame_{number:03d}.wav"}
        for note, number in zip(speaker_notes, numbers)
    ]
    # Page narration requests are independent.  The default keeps the historical
    # single-chapter behavior, while callers that parallelize chapters can lower
    # this value to cap total provider concurrency.
    result = tts.synthesize_batch(
        items=items, output_dir=str(audio_dir), max_concurrency=max(1, max_concurrency)
    )
    return result.get("results", [])
