"""知识图谱节点抽取（LLM + DB 写入）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from json_repair import repair_json

from agent_core.llm.base import BaseLLM

from models.node import NodeContent, NodeCreate, NodeOrigin, NodeRelation, NodeUpdate
from repositories import NodeRepository

logger = logging.getLogger(__name__)


def _json_candidates(text: str) -> list[str]:
    """Collect plausible JSON snippets from an LLM response."""
    text = (text or "").strip()
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


def _loads_json_lenient(text: str) -> Any:
    """Parse JSON with json_repair and LaTeX backslash protection."""
    attempts = [text]
    protected = re.sub(r"(?<!\\)\\([A-Za-z]{2,})", r"\\\\\1", text)
    attempts.append(protected)
    attempts.append(re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", protected))
    last_error: Exception | None = None
    for candidate in attempts:
        try:
            return json.loads(candidate)
        except Exception as exc:  # pylint: disable=broad-except
            last_error = exc
        try:
            return repair_json(candidate, return_objects=True)
        except Exception as exc:  # pylint: disable=broad-except
            last_error = exc
    if last_error:
        raise last_error
    raise ValueError("empty JSON candidate")


def _unwrap_node_array(data: Any) -> list | None:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("nodes", "concepts", "items", "knowledge_nodes"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return None


def _parse_json_array(text: str):
    """解析 LLM 返回的 JSON 数组，容错围栏、wrapper object 和 LaTeX 转义。"""
    best: list | None = None
    for candidate in _json_candidates(text):
        try:
            parsed = _loads_json_lenient(candidate)
        except Exception:  # pylint: disable=broad-except
            continue
        array = _unwrap_node_array(parsed)
        if isinstance(array, list):
            if best is None or len(array) > len(best):
                best = array
    return best


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _fallback_node_from_kp(kp: str, chapter_title: str, topic: str) -> dict:
    title = _normalize_text(kp)[:60]
    chapter_title = _normalize_text(chapter_title)
    description = (
        f"{title} 是课程「{topic}」中与「{chapter_title or '本章'}」相关的核心概念。"
        "该节点由章节大纲知识点兜底生成，用于保证知识图谱不断裂。"
    )
    return {
        "title": title,
        "description": description,
        "tags": [topic, chapter_title] if chapter_title else [topic],
        "key_points": [title],
        "fallback": True,
    }


def _normalize_node_payload(nd: Any, topic: str) -> dict | None:
    if isinstance(nd, str):
        title = _normalize_text(nd)
        if not title:
            return None
        return {
            "title": title[:60],
            "description": f"{title} 是课程「{topic}」中的核心概念。",
            "tags": [topic],
            "key_points": [title],
        }
    if not isinstance(nd, dict):
        return None
    title = _normalize_text(
        nd.get("title") or nd.get("name") or nd.get("concept") or nd.get("kp")
    )
    if not title:
        return None
    description = _normalize_text(
        nd.get("description") or nd.get("summary") or nd.get("definition") or title
    )
    raw_tags = nd.get("tags") if isinstance(nd.get("tags"), list) else [topic]
    tags = [_normalize_text(tag) for tag in raw_tags if _normalize_text(tag)] or [topic]
    raw_kps = nd.get("key_points") or nd.get("points") or nd.get("evidence") or []
    if isinstance(raw_kps, str):
        key_points = [_normalize_text(raw_kps)]
    elif isinstance(raw_kps, list):
        key_points = [
            _normalize_text(item) for item in raw_kps if _normalize_text(item)
        ]
    else:
        key_points = []
    return {
        "title": title[:60],
        "description": description,
        "tags": tags,
        "key_points": key_points or [title],
        "fallback": bool(nd.get("fallback")),
    }


def _link_nodes(
    user_id: str, node_items: List[Dict[str, str]], llm: Optional[BaseLLM]
) -> int:
    """用 LLM 判断一批节点间的关系，并建立双向边。

    与聊天 agent 的 create_node 工具保持相同的关系语义：
      - related  : 双向 related
      - extends  : a 是 b 的父概念（a→b extends，b→a prerequisite）
      - contrasts: 双向 contrasts
    返回本次建立的关系条数。
    """
    if llm is None:
        return 0
    title_to_id = {n["title"]: n["id"] for n in node_items if n.get("id")}
    if len(title_to_id) < 2:
        return 0
    titles = list(title_to_id.keys())
    prompt = (
        "判断以下知识图谱节点的关系，输出JSON数组不要围栏：\n"
        + "\n".join(f"- {t}" for t in titles)
        + "\n关系只有三种：extends、related、contrasts。"
        + '每项：{"a":"概念X","b":"概念Y","relation":"related"}'
    )
    edges = None
    for attempt in range(2):  # deepseek-v4-flash 偶发空返回，重试一次
        try:
            resp = llm.think(
                [
                    {"role": "system", "content": "只输出JSON数组。"},
                    {"role": "user", "content": prompt},
                ],
                config={"temperature": 0.2, "max_tokens": 1500},
            )
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("建边 LLM 调用失败: %s", e)
            break
        match = re.search(r"\[[\s\S]*\]", resp.content or "")
        if match:
            parsed = _parse_json_array(match.group())
            if isinstance(parsed, list):
                edges = parsed
                break
    if not edges:
        return 0

    pending: Dict[str, List[NodeRelation]] = {}
    linked = 0
    for e in edges:
        a = title_to_id.get((e.get("a") or "").strip())
        b = title_to_id.get((e.get("b") or "").strip())
        rel = (e.get("relation") or "related").strip()
        if not a or not b or a == b:
            continue
        if rel == "extends":
            pending.setdefault(a, []).append(
                NodeRelation(target_node_id=b, relation_type="extends")
            )
            pending.setdefault(b, []).append(
                NodeRelation(target_node_id=a, relation_type="prerequisite")
            )
            linked += 1
        elif rel == "contrasts":
            pending.setdefault(a, []).append(
                NodeRelation(target_node_id=b, relation_type="contrasts")
            )
            pending.setdefault(b, []).append(
                NodeRelation(target_node_id=a, relation_type="contrasts")
            )
            linked += 1
        else:
            pending.setdefault(a, []).append(
                NodeRelation(target_node_id=b, relation_type="related")
            )
            pending.setdefault(b, []).append(
                NodeRelation(target_node_id=a, relation_type="related")
            )
            linked += 1

    node_repo = NodeRepository()
    for node_id, new_rels in pending.items():
        existing = node_repo.get_by_id(node_id)
        if not existing:
            continue
        merged = list(existing.relations)
        existing_targets = {(r.target_node_id, r.relation_type) for r in merged}
        for nr in new_rels:
            if (nr.target_node_id, nr.relation_type) not in existing_targets:
                merged.append(nr)
        node_repo.update(node_id, NodeUpdate(relations=merged))

    logger.info("建边完成：%d 条关系", linked)
    return linked


def extract_and_persist_nodes(
    session_id: str,
    topic: str,
    chapters: List[Dict],
    llm: Optional[BaseLLM],
    user_id: str,
) -> List[Dict[str, str]]:
    """从章节知识点中抽取知识图谱节点并写入 nodes 表。

    返回值：[{id, title, existed}, ...]，existed=True 表示该节点之前已存在。
    """
    all_kps = []
    for ch in chapters:
        for kp in ch.get("knowledge_points", []):
            all_kps.append({"kp": kp, "chapter": ch.get("title", "")})
    if not all_kps:
        return []

    chapter_count = len(chapters)
    max_nodes = min(20, max(5, chapter_count * 3))

    system = "你是知识图谱构建专家。只输出JSON数组。"

    # deepseek-v4-flash 对长输出/复杂 prompt 会偶发返回空 content（finish_reason=length），
    # 因此按知识点分批抽取，且 prompt 保持极简（实测复杂规则/长前缀会触发空返回）。
    batch_size = 3
    all_nodes_data: List[dict] = []
    if llm is None:
        logger.warning("知识图谱抽取无 LLM 实例，使用 knowledge_points 兜底")
        all_nodes_data.extend(
            _fallback_node_from_kp(it["kp"], it.get("chapter", ""), topic)
            for it in all_kps
            if _normalize_text(it.get("kp"))
        )
    batch_indexes = range(0, len(all_kps), batch_size) if llm is not None else []
    for bi in batch_indexes:
        batch = all_kps[bi : bi + batch_size]
        kp_text = "\n".join(f"- {it['kp']}" for it in batch)
        prompt = (
            f"把以下知识点整理成知识图谱节点，一个节点一个独立概念，直接输出JSON数组不要围栏：\n"
            f"{kp_text}\n"
            '每项：{"title":"概念名","description":"定义","tags":["标签"],"key_points":["要点1","要点2"]}'
        )
        data = None
        for attempt in range(2):  # deepseek-v4-flash 偶发空返回，空则重试一次
            try:
                response = llm.think(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    config={"temperature": 0.3, "max_tokens": 2000},
                )
            except Exception as e:  # pylint: disable=broad-except
                logger.warning(
                    "知识图谱抽取第%d批 LLM 调用失败: %s", bi // batch_size, e
                )
                break
            parsed = _parse_json_array(response.content or "")
            if isinstance(parsed, list) and parsed:
                data = parsed
                break
            logger.warning(
                "知识图谱抽取第%d批第%d次空返回或格式无效，input_kps=%d raw_len=%d，%s",
                bi // batch_size,
                attempt,
                len(batch),
                len(response.content or ""),
                "重试" if attempt == 0 else "使用大纲兜底",
            )
        if isinstance(data, list) and data:
            all_nodes_data.extend(data)
        else:
            logger.warning(
                "知识图谱抽取第%d批最终失败，使用 knowledge_points 兜底",
                bi // batch_size,
            )
            all_nodes_data.extend(
                _fallback_node_from_kp(it["kp"], it.get("chapter", ""), topic)
                for it in batch
                if _normalize_text(it.get("kp"))
            )

    if not all_nodes_data:
        logger.warning("知识图谱抽取：所有批次均失败且无可用 knowledge_points")
        return []

    normalized_nodes: list[dict] = []
    seen_titles: set[str] = set()
    for nd in all_nodes_data:
        normalized = _normalize_node_payload(nd, topic)
        if not normalized:
            continue
        title = normalized["title"]
        if title in seen_titles:
            continue
        seen_titles.add(title)
        normalized_nodes.append(normalized)

    if not normalized_nodes:
        logger.warning("知识图谱抽取：节点字段归一后为空")
        return []

    created_nodes: List[Dict[str, str]] = []
    node_repo = NodeRepository()
    for nd in normalized_nodes[:max_nodes]:
        title = nd["title"]

        # 查重节点
        existing_id = node_repo.find_by_title(user_id, title)
        if existing_id:
            created_nodes.append({"id": existing_id, "title": title, "existed": True})
            continue

        description = nd.get("description", "")
        data = NodeCreate(
            title=title,
            description=description,
            tags=nd.get("tags", [topic]),
            content=NodeContent(
                summary=description,
                key_points=nd.get("key_points", []),
                examples=[],
                common_mistakes=[],
            ),
            origins=[
                NodeOrigin(
                    source_type="session",
                    source_id=session_id,
                    source_title=f"[AI课程] {topic}",
                    location="AI课程自动抽取",
                    excerpt=description[:200],
                )
            ],
        )
        node = node_repo.create(user_id, data, initial_mastery=0.1)
        created_nodes.append({"id": node.id, "title": title, "existed": False})

    # 建边：用 LLM 判断本章节点间的关系，建立双向边（失败不阻塞抽取）
    try:
        _link_nodes(user_id, created_nodes, llm)
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("知识图谱建边失败（不阻塞）: %s", e)

    logger.info("知识图谱抽取完成：%d 个节点", len(created_nodes))
    return created_nodes
