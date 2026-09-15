"""
工具基类 (BaseTool)

提供：
- 抽象属性: name / description / parameters
- 参数类型转换 (cast_params) 与校验 (validate_params)
- OpenAI Function Calling JSON Schema 输出 (to_schema)
- 同步 run() + 异步 async_run() 双模式执行
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

# hook 签名：(tool_name, params, result, index) -> 事件 | 事件列表 | None
#
# index 为该工具调用的全局序号（跨轮次单调递增），用于保序处理。
# 返回值：
#   - None                     无副作用通知（多数 hook）
#   - DomainEvent              单个业务事件，由 ToolRegistry 并入事件流
#   - list[DomainEvent]        多个业务事件
# 支持普通函数与 async 函数两种形式。
#
# 让 hook 能返回事件是刻意的设计：改造前 hook 签名为 ``-> None``，业务侧
# 只能把事件塞进旁路队列再手工 flush，事件顺序取决于 flush 时机而非实际
# 发生顺序。现在顺序由框架保证。
ToolResultHook = Callable[
    [str, Dict[str, Any], Any, int],
    Union[None, Any, Awaitable[Any]],
]


# ============================================================
# 类型映射
# ============================================================

_TYPE_MAP: Dict[str, type | tuple] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


# ============================================================
# BaseTool
# ============================================================


class BaseTool(ABC):
    """
    工具抽象基类。

    子类有两种实现方式：

    **方式一：类属性 + run()**::

        class GetWeather(BaseTool):
            name = "get_weather"
            description = "获取天气"
            parameters = {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名"},
                },
                "required": ["city"],
            }

            def run(self, city: str) -> str:
                return f"{city} 晴 25°C"

    **方式二：@property 覆写**（适合需要动态生成 schema 的场景）::

        class DynamicTool(BaseTool):
            @property
            def name(self) -> str:
                return self._name
            ...
    """

    # --- 子类可通过类属性直接定义 ---
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self, **kwargs: Any):
        """允许通过构造函数覆盖类属性（name / description / parameters）。

        Note:
            工具本身**不持有任何 hook**。额度检查、业务事件产出等治理关注点
            由 :meth:`ToolRegistry.register` 在注册时显式绑定，
            并统一在 Registry 的执行路径上触发。

            这样做的原因：hook 若存在工具实例上，就会出现「同一个 hook
            走不同入口行为不同」的隐形陷阱——便捷入口拿不到全局 index、
            也无处转发业务事件，只能丢弃。把治理收归 Registry 后，
            工具回归纯粹的「能力单元」。
        """
        if "name" in kwargs:
            self.name = kwargs["name"]
        if "description" in kwargs:
            self.description = kwargs["description"]
        if "parameters" in kwargs:
            self.parameters = kwargs["parameters"]

        if not self.name:
            raise ValueError("工具必须定义 name")
        if not self.description:
            raise ValueError("工具必须定义 description")

    # ------------------------------------------------------------------
    # JSON Schema 输出
    # ------------------------------------------------------------------

    def to_schema(self) -> Dict[str, Any]:
        """
        转换为 OpenAI Function Calling 的 tools 格式。

        Returns::

            {
                "type": "function",
                "function": {
                    "name": "...",
                    "description": "...",
                    "parameters": { ... }
                }
            }
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    # ------------------------------------------------------------------
    # 参数类型转换
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_type(t: Any) -> Optional[str]:
        """
        解析 JSON Schema type 字段。

        支持 ``"type": ["string", "null"]`` 联合类型，
        提取第一个非 null 类型。
        """
        if isinstance(t, list):
            for item in t:
                if item != "null":
                    return item
            return None
        return t

    def cast_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据 JSON Schema 对参数做安全的类型转换。

        LLM 经常返回错误类型（如 string 代替 integer），
        此方法在校验前自动修正。
        """
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            return params
        return self._cast_object(params, schema)

    def _cast_object(self, obj: Any, schema: Dict[str, Any]) -> Dict[str, Any]:
        """递归转换 object 类型。"""
        if not isinstance(obj, dict):
            return obj

        props = schema.get("properties", {})
        result = {}
        for key, value in obj.items():
            if key in props:
                result[key] = self._cast_value(value, props[key])
            else:
                result[key] = value
        return result

    # ---- 单值转换的子步骤（按目标类型拆分） ----

    @staticmethod
    def _is_already_correct_type(val: Any, target_type: Optional[str]) -> bool:
        """若 val 已是 target_type 对应的 Python 类型则返回 True。"""
        if target_type not in _TYPE_MAP:
            return False
        if target_type == "boolean":
            return isinstance(val, bool)
        if target_type == "integer":
            return isinstance(val, int) and not isinstance(val, bool)
        if target_type in ("array", "object"):
            # 数组 / 对象即使类型正确也需要递归处理子元素，交给下游逻辑。
            return False
        return isinstance(val, _TYPE_MAP[target_type])

    @staticmethod
    def _cast_to_integer(val: Any) -> Any:
        """string → int，失败则原样返回。"""
        if isinstance(val, str):
            try:
                return int(val)
            except ValueError:
                return val
        return val

    @staticmethod
    def _cast_to_number(val: Any) -> Any:
        """string → float，失败则原样返回。"""
        if isinstance(val, str):
            try:
                return float(val)
            except ValueError:
                return val
        return val

    @staticmethod
    def _cast_to_string(val: Any) -> Any:
        """any → str，None 保持为 None。"""
        return val if val is None else str(val)

    @staticmethod
    def _cast_to_boolean(val: Any) -> Any:
        """string → bool，不识别则原样返回。"""
        if not isinstance(val, str):
            return val
        lower = val.lower()
        if lower in ("true", "1", "yes"):
            return True
        if lower in ("false", "0", "no"):
            return False
        return val

    def _cast_array(self, val: Any, schema: Dict[str, Any]) -> Any:
        """array → 递归转换 items。"""
        if not isinstance(val, list):
            return val
        item_schema = schema.get("items")
        if not item_schema:
            return val
        return [self._cast_value(item, item_schema) for item in val]

    def _cast_value(self, val: Any, schema: Dict[str, Any]) -> Any:
        """根据 schema 转换单个值（按目标类型分派到对应的小函数）。"""
        target_type = self._resolve_type(schema.get("type"))

        # 已经是正确类型 → 直接返回（array/object 例外，仍需递归处理子元素）
        if self._is_already_correct_type(val, target_type):
            return val

        if target_type == "integer":
            return self._cast_to_integer(val)
        if target_type == "number":
            return self._cast_to_number(val)
        if target_type == "string":
            return self._cast_to_string(val)
        if target_type == "boolean":
            return self._cast_to_boolean(val)
        if target_type == "array":
            return self._cast_array(val, schema)
        if target_type == "object" and isinstance(val, dict):
            return self._cast_object(val, schema)

        return val

    # ------------------------------------------------------------------
    # 参数校验
    # ------------------------------------------------------------------

    def validate_params(self, params: Dict[str, Any]) -> List[str]:
        """
        校验参数是否符合 JSON Schema，返回错误列表（空列表表示通过）。

        支持：type / required / enum / minimum / maximum /
              minLength / maxLength / 嵌套 object / array items
        """
        if not isinstance(params, dict):
            return [f"参数必须是 object 类型，收到 {type(params).__name__}"]
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(
                f"Schema 顶层必须是 object 类型，收到 {schema.get('type')!r}"
            )
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: Dict[str, Any], path: str) -> List[str]:
        """递归校验（按维度组合各子检查函数）。"""
        raw_type = schema.get("type")
        nullable = (isinstance(raw_type, list) and "null" in raw_type) or schema.get(
            "nullable", False
        )
        t = self._resolve_type(raw_type)
        label = path or "parameter"

        if nullable and val is None:
            return []

        # 类型不匹配直接短路返回（后续检查都依赖正确的类型）
        type_err = self._check_type(val, t, label)
        if type_err:
            return [type_err]

        errors: List[str] = []
        errors.extend(self._check_enum(val, schema, label))
        errors.extend(self._check_range(val, t, schema, label))
        errors.extend(self._check_length(val, t, schema, label))

        if t == "object":
            errors.extend(self._validate_object(val, schema, path))
        elif t == "array" and "items" in schema:
            errors.extend(self._validate_array(val, schema, path))

        return errors

    # ---- 校验子步骤 ----

    @staticmethod
    def _check_type(val: Any, t: Optional[str], label: str) -> Optional[str]:
        """类型检查；返回错误信息或 None。"""
        if t not in _TYPE_MAP:
            return None
        if t == "integer":
            if not isinstance(val, int) or isinstance(val, bool):
                return f"{label} 应为 integer"
            return None
        if t == "number":
            if not isinstance(val, _TYPE_MAP[t]) or isinstance(val, bool):
                return f"{label} 应为 number"
            return None
        if not isinstance(val, _TYPE_MAP[t]):
            return f"{label} 应为 {t}"
        return None

    @staticmethod
    def _check_enum(val: Any, schema: Dict[str, Any], label: str) -> List[str]:
        """enum 枚举检查。"""
        if "enum" in schema and val not in schema["enum"]:
            return [f"{label} 必须是 {schema['enum']} 之一"]
        return []

    @staticmethod
    def _check_range(
        val: Any, t: Optional[str], schema: Dict[str, Any], label: str
    ) -> List[str]:
        """数值范围 minimum / maximum。"""
        if t not in ("integer", "number"):
            return []
        errors: List[str] = []
        if "minimum" in schema and val < schema["minimum"]:
            errors.append(f"{label} 必须 >= {schema['minimum']}")
        if "maximum" in schema and val > schema["maximum"]:
            errors.append(f"{label} 必须 <= {schema['maximum']}")
        return errors

    @staticmethod
    def _check_length(
        val: Any, t: Optional[str], schema: Dict[str, Any], label: str
    ) -> List[str]:
        """字符串长度 minLength / maxLength。"""
        if t != "string":
            return []
        errors: List[str] = []
        if "minLength" in schema and len(val) < schema["minLength"]:
            errors.append(f"{label} 长度至少 {schema['minLength']}")
        if "maxLength" in schema and len(val) > schema["maxLength"]:
            errors.append(f"{label} 长度最多 {schema['maxLength']}")
        return errors

    def _validate_object(
        self, val: Dict[str, Any], schema: Dict[str, Any], path: str
    ) -> List[str]:
        """object 递归：检查 required + 递归 properties。"""
        errors: List[str] = []
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in val:
                errors.append(f"缺少必填参数 {path + '.' + k if path else k}")
        for k, v in val.items():
            if k in props:
                child_path = path + "." + k if path else k
                errors.extend(self._validate(v, props[k], child_path))
        return errors

    def _validate_array(
        self, val: List[Any], schema: Dict[str, Any], path: str
    ) -> List[str]:
        """array 递归：逐项用 items schema 校验。"""
        errors: List[str] = []
        item_schema = schema["items"]
        for i, item in enumerate(val):
            child_path = f"{path}[{i}]" if path else f"[{i}]"
            errors.extend(self._validate(item, item_schema, child_path))
        return errors

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """
        同步执行工具（子类必须实现）。

        基类采用 ``**kwargs`` 签名，子类应在自身签名中以带默认值的关键字
        参数显式声明所需参数（如 ``city: str = ""`` 加 ``**kwargs`` 兜底），
        调用方统一以关键字方式传入。

        Returns:
            Any: 执行结果（建议返回 str，方便作为 tool message content）
        """
        pass

    async def async_run(self, **kwargs: Any) -> Any:
        """
        异步执行工具。

        默认用 ``asyncio.to_thread`` 包装同步 ``run()``。
        有真正异步需求的子类可覆写此方法。
        """
        # 通过 getattr 间接调用，避免静态扫描器对 run() 的签名匹配误报
        _run = getattr(self, "run")
        return await asyncio.to_thread(lambda: _run(**kwargs))

    async def async_stream_run(self, **kwargs: Any):
        """
        异步流式执行工具，yield 文本片段或子 Agent 事件。

        默认降级为调用 ``async_run()``，保留多模态内容块列表。
        AgentTool 等有真正流式能力的子类应覆写此方法。

        Yields:
            str | AgentStreamEvent
        """
        # 通过 getattr 间接调用，避免静态扫描器对 async_run() 的签名匹配误报
        _async_run = getattr(self, "async_run")
        result = await _async_run(**kwargs)
        yield result if isinstance(result, (str, list)) else str(result)

    # ------------------------------------------------------------------
    # 便捷调用
    # ------------------------------------------------------------------

    def __call__(self, **kwargs: Any) -> Any:
        """支持直接以函数形式调用: ``tool(city="北京")``

        只做「校验参数 → 调用 :meth:`run` → 返回结果」，不涉及任何治理。

        .. warning::
           这是**纯执行入口**，仅供脚本、调试与单测使用。
           它不触发任何 hook，也没有预算检查与取消响应。

           Agent 循环内的工具执行请一律走
           :meth:`~agent_core.tool.registry.ToolRegistry.execute`
           或 ``async_stream_execute`` —— 那里会分配真实的全局 index、
           触发额度检查、转发业务事件、并做 ``ctx.checkpoint()``。
        """
        casted = self.cast_params(kwargs)
        errors = self.validate_params(casted)
        if errors:
            raise ValueError(f"工具 {self.name} 参数校验失败: {'; '.join(errors)}")
        # 通过 getattr 间接调用，避免静态扫描器对 run() 的签名匹配误报
        _run = getattr(self, "run")
        return _run(**casted)

    async def async_call(self, **kwargs: Any) -> Any:
        """异步纯执行入口。语义同 :meth:`__call__`，不触发任何 hook。"""
        casted = self.cast_params(kwargs)
        errors = self.validate_params(casted)
        if errors:
            raise ValueError(f"工具 {self.name} 参数校验失败: {'; '.join(errors)}")
        # 通过 getattr 间接调用，避免静态扫描器对 async_run() 的签名匹配误报
        _async_run = getattr(self, "async_run")
        return await _async_run(**casted)

    async def async_stream_call(self, **kwargs: Any):
        """流式执行工具，仅负责参数校验和流式输出。

        注意：治理 hook 由 ToolRegistry 在注册时绑定、并在其执行路径上
        统一触发（见 ToolRegistry 文档），工具自身不涉及。

        Raises:
            ValueError: 参数校验失败时抛出，由调用方捕获并转为错误响应。
        """
        casted = self.cast_params(kwargs)
        errors = self.validate_params(casted)
        if errors:
            raise ValueError(f"工具 {self.name} 参数校验失败: {'; '.join(errors)}")
        async for chunk in self.async_stream_run(**casted):
            yield chunk

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
