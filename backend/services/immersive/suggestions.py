"""
个性化推荐云朵生成器

根据统一用户画像总览和学习历史，调用 LLM 生成个性化的推荐主题标签，用于首页飘浮云朵展示。

推荐策略：
1. 薄弱知识点 → 建议巩固
2. 已学主题的进阶方向 → 建议深入
3. 基于用户兴趣/背景推荐新领域
4. 新用户/LLM 临时异常 → 后端直接返回默认推荐，避免前端空白或反复打模型
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from json_repair import repair_json

from services.llm_factory import get_llm
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)

# 缓存：避免每次登录都调用 LLM（缓存 10 分钟）
_suggestions_cache: Dict[str, Dict[str, Any]] = {}  # user_id -> {data, timestamp}
_CACHE_TTL_SECONDS = 600  # 10 分钟
_MAX_LLM_ATTEMPTS = 2

_DEFAULT_SUGGESTIONS: List[Dict[str, str]] = [
    {"text": "递归算法", "emoji": "🌀", "size": "md", "reason": "训练分治与自相似思维"},
    {
        "text": "微积分",
        "emoji": "∫",
        "size": "xl",
        "reason": "理解变化率与累积的核心工具",
    },
    {
        "text": "机器学习",
        "emoji": "🤖",
        "size": "lg",
        "reason": "从数据中学习规律的通用方法",
    },
    {
        "text": "量子力学",
        "emoji": "⚛️",
        "size": "md",
        "reason": "建立现代物理的概率图景",
    },
    {
        "text": "英语写作",
        "emoji": "✍️",
        "size": "xs",
        "reason": "提升表达结构与论证质量",
    },
    {
        "text": "操作系统",
        "emoji": "💻",
        "size": "lg",
        "reason": "理解计算机资源管理机制",
    },
    {
        "text": "数据结构",
        "emoji": "🧩",
        "size": "sm",
        "reason": "建立算法问题的组织方式",
    },
    {
        "text": "线性代数",
        "emoji": "📐",
        "size": "xs",
        "reason": "连接几何、数据与机器学习",
    },
    {
        "text": "编译原理",
        "emoji": "⚙️",
        "size": "md",
        "reason": "理解代码如何变成可执行程序",
    },
    {"text": "概率论", "emoji": "🎲", "size": "sm", "reason": "刻画不确定性和统计推断"},
    {
        "text": "神经网络",
        "emoji": "🧠",
        "size": "xl",
        "reason": "理解大模型与深度学习基础",
    },
    {
        "text": "哲学导论",
        "emoji": "💭",
        "size": "sm",
        "reason": "训练概念辨析与批判性思维",
    },
]


async def generate_suggestions(user_id: str) -> Dict[str, Any]:
    """生成个性化推荐云朵内容。

    Returns:
        {
            "suggestions": [{"text": ..., "emoji": ..., "size": ..., "reason": ...}, ...],
            "source": "personalized" | "default"
        }
    """
    import time

    # 检查缓存
    cached = _suggestions_cache.get(user_id)
    if cached and (time.time() - cached["timestamp"]) < _CACHE_TTL_SECONDS:
        return cached["data"]

    # 读取统一用户画像与学习历史
    profile_content = _read_profile(user_id)
    learned_topics = _get_learned_topics(user_id)

    # 如果没有任何画像数据，也直接返回后端默认推荐，保证接口语义始终可展示。
    if not profile_content and not learned_topics:
        result = _default_result()
        _suggestions_cache[user_id] = {"data": result, "timestamp": time.time()}
        return result

    # 调用 LLM 生成推荐；失败时返回后端默认推荐并缓存，避免每次进入页面都卡一次 LLM。
    try:
        suggestions = await _call_llm_for_suggestions(
            user_id, profile_content, learned_topics
        )
        if suggestions:
            result = {"suggestions": suggestions, "source": "personalized"}
        else:
            result = _default_result()
        _suggestions_cache[user_id] = {"data": result, "timestamp": time.time()}
        return result
    except Exception as e:
        logger.warning("LLM 生成推荐失败，使用默认推荐: %s", e)
        result = _default_result()
        _suggestions_cache[user_id] = {"data": result, "timestamp": time.time()}
        return result


def _default_result() -> Dict[str, Any]:
    """返回可直接展示的默认推荐，避免接口给前端空列表。"""
    return {
        "suggestions": [dict(item) for item in _DEFAULT_SUGGESTIONS],
        "source": "default",
    }


def _read_profile(user_id: str = "") -> str:
    """读取统一画像总览文本。"""
    try:
        from services.profile_service import ProfileMemoryService

        return ProfileMemoryService().build_profile_text(user_id).strip()
    except Exception:
        logger.exception("读取统一画像失败 (user=%s)", safe_log(user_id))
        return ""


def _get_learned_topics(user_id: str) -> List[str]:
    """从 sessions 表获取用户已学过的课程主题。"""
    try:
        from database import get_db

        topics = []
        with get_db() as conn:
            cur = conn.execute(
                "SELECT topic, title FROM sessions WHERE user_id = ? AND status = 'completed'",
                (user_id,),
            )
            for row in cur.fetchall():
                topic = row["topic"] or row["title"] or ""
                topic = topic.replace("[AI课程]", "").strip()
                if topic:
                    topics.append(topic)
        return topics
    except Exception:
        return []


async def _call_llm_for_suggestions(
    user_id: str,
    profile_content: str,
    learned_topics: List[str],
) -> List[Dict[str, str]]:
    """调用 LLM 生成推荐主题列表。"""

    # 构建上下文
    context_parts = []

    if profile_content:
        context_parts.append(f"## 用户画像\n{profile_content}")

    if learned_topics:
        context_parts.append("## 已学过的课程\n" + "、".join(learned_topics))

    context = "\n\n".join(context_parts)

    system_prompt = """你是一个智能学习推荐系统。根据用户的画像和学习历史，推荐 8-12 个学习主题。

推荐策略：
1. 如果用户有薄弱知识点（正确率低），推荐相关的巩固主题（标注为巩固类）
2. 如果用户已掌握某些主题，推荐进阶方向（标注为进阶类）
3. 根据用户的学习背景和兴趣，推荐新的探索方向（标注为探索类）
4. 推荐的主题应该多样化，涵盖不同领域
5. 每个主题名称要简洁（2-6个字），适合作为标签展示

你必须严格按照以下 JSON 格式输出，不要输出任何 Markdown 代码块、解释或前后缀文字：
[
  {"text": "主题名", "emoji": "合适的emoji", "size": "xl|lg|md|sm|xs", "reason": "一句话推荐理由"}
]

size 规则：
- xl: 最重要/最推荐的（1-2个）
- lg: 比较推荐的（2-3个）
- md: 一般推荐（3-4个）
- sm: 可选探索（2-3个）
- xs: 轻度推荐（1-2个）

emoji 要求：选择与主题最相关的 emoji，让标签更生动。"""

    user_prompt = f"""请根据以下用户信息，生成个性化的学习主题推荐：

{context}

请生成 8-12 个推荐主题，只输出 JSON 数组。"""

    llm = get_llm(user_id, scene="immersive")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    config = {
        "temperature": 0.3,
        "max_tokens": 1536,
        # DeepSeek V4/Reasoner 类模型在短 JSON 任务上可能把预算消耗在 reasoning，
        # 导致最终 content 为空；支持该参数的模型会关闭推理，不支持的模型会在 LLM 层过滤。
        "reasoning_effort": "none",
    }

    for attempt in range(1, _MAX_LLM_ATTEMPTS + 1):
        response = await llm.async_think(messages, config=config)
        if not response or response.is_error or not (response.content or "").strip():
            logger.info(
                "LLM 推荐生成第 %d/%d 次返回空或错误: finish_reason=%s error=%s usage=%s",
                attempt,
                _MAX_LLM_ATTEMPTS,
                getattr(response, "finish_reason", None),
                getattr(response, "is_error", None),
                getattr(response, "usage", None),
            )
            continue

        suggestions = _parse_suggestions(response.content)
        if suggestions:
            return suggestions

        logger.info(
            "LLM 推荐生成第 %d/%d 次 JSON 为空或不可用: finish_reason=%s content=%s",
            attempt,
            _MAX_LLM_ATTEMPTS,
            getattr(response, "finish_reason", None),
            response.content[:200],
        )

    logger.info("LLM 推荐生成返回空或错误，使用默认推荐")
    return []


def _json_candidates(content: str) -> List[str]:
    """从模型输出中提取可能的 JSON 片段。"""
    text = (content or "").strip()
    if not text:
        return []

    candidates = []
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        candidates.append(fence.group(1).strip())
    candidates.append(text)

    array_match = re.search(r"\[[\s\S]*\]", text)
    if array_match:
        candidates.append(array_match.group(0).strip())
    object_match = re.search(r"\{[\s\S]*\}", text)
    if object_match:
        candidates.append(object_match.group(0).strip())

    unique = []
    for item in candidates:
        if item and item not in unique:
            unique.append(item)
    return unique


def _parse_suggestions(content: str) -> List[Dict[str, str]]:
    """解析并清洗 LLM 返回的推荐列表。兼容数组或 {suggestions: [...]}。"""
    for candidate in _json_candidates(content):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                parsed = repair_json(candidate, return_objects=True)
            except Exception:  # pylint: disable=broad-except
                continue

        if isinstance(parsed, dict):
            parsed = parsed.get("suggestions") or parsed.get("courses") or []
        if not isinstance(parsed, list):
            continue

        cleaned = _clean_suggestions(parsed)
        if cleaned:
            return cleaned
    return []


def _clean_suggestions(suggestions: List[Any]) -> List[Dict[str, str]]:
    """验证和清洗推荐数据。"""
    valid_sizes = {"xl", "lg", "md", "sm", "xs"}
    cleaned = []
    for item in suggestions[:12]:  # 最多取 12 个
        if not isinstance(item, dict) or "text" not in item:
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        cleaned.append(
            {
                "text": text[:10],  # 限制长度
                "emoji": str(item.get("emoji", "📚"))[:4],
                "size": item.get("size", "md")
                if item.get("size") in valid_sizes
                else "md",
                "reason": str(item.get("reason", "")).strip()[:30],
            }
        )

    return cleaned


def invalidate_cache(user_id: str) -> None:
    """清除指定用户的推荐缓存（画像更新后调用）。"""
    _suggestions_cache.pop(user_id, None)
