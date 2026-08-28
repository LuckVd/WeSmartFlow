"""知识图谱节点抽取（LLM + DB 写入）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

from agent_core.llm.base import BaseLLM

from models.node import NodeContent, NodeCreate, NodeOrigin, NodeRelation, NodeUpdate
from repositories import NodeRepository

logger = logging.getLogger(__name__)


def _parse_json_array(text: str):
    """解析 LLM 返回的 JSON 数组，容错 LaTeX 反斜杠转义。

    数学/物理课程的 description/key_points 常含 \\frac、\\lambda 等 LaTeX 命令，
    裸 json.loads 会因非法转义直接抛 JSONDecodeError（导致整批抽取静默失败）。
    这里与 generate_speaker_notes 采用相同的三层反斜杠保护，逐层兜底。
    """
    text = (text or "").strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    # 第一层：把 "\后跟≥2 个连续字母" 的序列翻倍，让 \frac/\nu/\lambda 保持字面
    protected = re.sub(r"(?<!\\)\\([A-Za-z]{2,})", r"\\\\\1", text)
    try:
        data = json.loads(protected)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    # 第二层：再兜底非法转义反斜杠通配翻倍
    fixed = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", protected)
    try:
        data = json.loads(fixed)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return None


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

    if llm is None:
        logger.warning("知识图谱抽取已跳过：未提供可用的 LLM 实例（llm=None）")
        return []

    chapter_count = len(chapters)
    max_nodes = min(20, max(5, chapter_count * 3))

    system = "你是知识图谱构建专家。只输出JSON数组。"

    # deepseek-v4-flash 对长输出/复杂 prompt 会偶发返回空 content（finish_reason=length），
    # 因此按知识点分批抽取，且 prompt 保持极简（实测复杂规则/长前缀会触发空返回）。
    batch_size = 3
    all_nodes_data: List[dict] = []
    for bi in range(0, len(all_kps), batch_size):
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
            match = re.search(r"\[[\s\S]*\]", response.content or "")
            if match:
                parsed = _parse_json_array(match.group())
                if isinstance(parsed, list):
                    data = parsed
                    break
            logger.warning(
                "知识图谱抽取第%d批第%d次空返回，%s",
                bi // batch_size,
                attempt,
                "重试" if attempt == 0 else "放弃该批",
            )
        if isinstance(data, list):
            all_nodes_data.extend(data)
        else:
            logger.warning("知识图谱抽取第%d批最终失败", bi // batch_size)

    if not all_nodes_data:
        logger.warning("知识图谱抽取：所有批次均失败，未抽到任何节点")
        return []

    created_nodes: List[Dict[str, str]] = []
    node_repo = NodeRepository()
    for nd in all_nodes_data[:max_nodes]:
        title = nd.get("title", "").strip()
        if not title:
            continue

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
