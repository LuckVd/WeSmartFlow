"""结构化输出：让 LLM 稳定产出符合 schema 的 JSON。

改造前这段"从 LLM 文本里抠 JSON"的逻辑在项目里至少重复了 4 次
（``plan_and_solve._parse_steps``、``court/forge``、``live_science/server``、
``node_extractor``），各写各的正则与 try/except。本模块统一收敛。

三级策略：
1. 请求 ``response_format={"type": "json_object"}``（多数供应商支持）
2. 失败则从文本中正则提取 JSON 对象 / 数组
3. 仍失败则把解析错误回传给 LLM，要求其修正后重试
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, TypeVar

from .llm.base import BaseLLM
from .runtime.trace import SPAN_LLM

if TYPE_CHECKING:
    from .runtime.run_context import RunContext

logger = logging.getLogger(__name__)

T = TypeVar("T")

_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")
_JSON_ARRAY = re.compile(r"\[[\s\S]*\]")
_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


class StructuredOutputError(ValueError):
    """LLM 输出无法解析为目标结构。"""


def sanitize_json_text(raw: str) -> str:
    """清洗 LLM 输出中常见的 JSON 非法内容。

    处理两类高频问题：
    - 字符串值内混入的裸控制字符
    - LaTeX 命令导致的非法反斜杠转义（``\\to`` / ``\\text`` 等）
    """
    cleaned = re.sub(r"[\x00-\x08\x0a-\x1f]", "", raw)
    # 非法转义：\ 后跟非合法转义字符 → 双写
    cleaned = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", cleaned)
    # 伪合法转义：\t \n \r \b \f 后紧跟字母，多为 LaTeX 命令
    cleaned = re.sub(r"\\([tnrbf])(?=[a-zA-Z])", r"\\\\\1", cleaned)
    return cleaned


def extract_json(text: str) -> Any:
    """从 LLM 输出文本中提取并解析 JSON。

    依次尝试：整体解析 → 去代码围栏 → 正则提取对象 → 正则提取数组，
    每步都配合 :func:`sanitize_json_text` 清洗。

    Raises:
        StructuredOutputError: 所有策略均失败。
    """
    if not text or not text.strip():
        raise StructuredOutputError("LLM 返回空内容")

    candidates: List[str] = [text]

    fence = _FENCE.search(text)
    if fence:
        candidates.append(fence.group(1))

    for pattern in (_JSON_OBJECT, _JSON_ARRAY):
        match = pattern.search(text)
        if match:
            candidates.append(match.group(0))

    last_error: Optional[Exception] = None
    for candidate in candidates:
        for attempt in (candidate, sanitize_json_text(candidate)):
            try:
                return json.loads(attempt)
            except (json.JSONDecodeError, TypeError) as e:
                last_error = e

    raise StructuredOutputError(f"无法从输出中解析 JSON: {last_error}")


def _validate(data: Any, schema: Optional[Type[T]]) -> Any:
    """按 schema 校验数据。schema 为 None 时原样返回。"""
    if schema is None:
        return data

    validator = getattr(schema, "model_validate", None)  # pydantic v2
    if callable(validator):
        return validator(data)

    parser = getattr(schema, "parse_obj", None)  # pydantic v1
    if callable(parser):
        return parser(data)

    return schema(**data) if isinstance(data, dict) else schema(data)


async def structured_think(
    llm: BaseLLM,
    messages: List[Dict[str, Any]],
    schema: Optional[Type[T]] = None,
    *,
    ctx: Optional["RunContext"] = None,
    retries: int = 1,
    config: Optional[Dict[str, Any]] = None,
    request_json_mode: bool = True,
) -> T:
    """调用 LLM 并把输出解析为结构化对象。

    Args:
        llm:      LLM 实例。
        messages: 消息列表。
        schema:   Pydantic 模型或可用 ``**data`` 构造的类；None 表示只解析为
                  原生 dict/list 不做校验。
        ctx:      运行上下文；提供时会做预算检查、token 累加与 trace。
        retries:  解析失败后的重试次数（重试时会把错误信息回传给 LLM）。
        config:   透传给 LLM 的额外参数。
        request_json_mode: 是否请求供应商的 JSON 模式。

    Returns:
        解析并校验后的对象。

    Raises:
        StructuredOutputError: 重试耗尽后仍无法得到合法结构。
    """
    call_config: Dict[str, Any] = dict(config or {})
    if request_json_mode:
        call_config.setdefault("response_format", {"type": "json_object"})

    working = list(messages)
    last_error: Optional[Exception] = None

    for attempt in range(retries + 1):
        if ctx is not None:
            ctx.checkpoint()

        span_ctx = (
            ctx.tracer.span("llm.structured", SPAN_LLM, attempt=attempt)
            if ctx is not None
            else _null_span()
        )
        with span_ctx:
            response = await llm.async_think(working, config=call_config or None)

            if ctx is not None:
                ctx.budget.add_tokens((response.usage or {}).get("total_tokens", 0))

        if response.is_error:
            last_error = StructuredOutputError(
                response.metadata.get("error_message", "LLM 调用失败")
            )
            logger.warning("structured_think 第 %d 次调用失败", attempt + 1)
            continue

        try:
            return _validate(extract_json(response.content), schema)
        except Exception as e:  # pylint: disable=broad-except
            last_error = e
            logger.warning("structured_think 第 %d 次解析失败: %s", attempt + 1, e)
            if attempt >= retries:
                break
            # 把错误回传给 LLM 要求修正
            working = [
                *working,
                {"role": "assistant", "content": response.content or ""},
                {
                    "role": "user",
                    "content": (
                        f"上次输出无法解析：{e}\n"
                        "请只输出合法的 JSON，不要包含解释文字或代码围栏。"
                    ),
                },
            ]

    raise StructuredOutputError(f"结构化输出失败（已重试 {retries} 次）: {last_error}")


class _NullSpan:
    """无 ctx 时的占位 span 上下文。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def set(self, **_kw):
        return self


def _null_span() -> _NullSpan:
    return _NullSpan()


__all__ = [
    "StructuredOutputError",
    "extract_json",
    "sanitize_json_text",
    "structured_think",
]
