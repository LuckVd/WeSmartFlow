"""
GenerateInteractiveVizTool：两阶段流式生成交互式可视化代码

阶段一 Design 循环（纯 LLM，无工具）：
  design → 结构校验 → 修正（必要时）→ VizSpec（最多 MAX_DESIGN_ROUNDS 轮）

阶段二 Code 循环：
  code → 静态检查 → 浏览器交互检查 → judge → 修复（最多 MAX_CODE_ROUNDS 轮）

生成的代码保存至 documents/viz/{viz_id}/viz.js，
metadata 保存至 documents/viz/{viz_id}/meta.json，
async_stream_run 透传子 Agent 事件及阶段进度，最后输出 viz_id。
前端按 viz_id 拉取代码并用 EduVizSandbox 渲染。
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from agent_core.tool.base import BaseTool
from agent_core.agent.events import AgentFinalEvent, AgentFinishReason
from agent_core.agent.react import ReActAgent
from agent_core.context.static import StaticPromptBuilder
from agent_core.tool.registry import ToolRegistry
from config import VIZ_DIR
from repositories.document_repo import DocumentRepository
from services.llm_factory import get_llm
from utils.log_safe import safe_log

from .validate_viz_code import ValidateVizCodeTool
from .viz_registry import list_patterns_with_meta, load_pattern
from .viz_quality import VizQualityError, VizSpec, VizReview, parse_contract
from .viz_runtime import VizRuntimeUnavailable, async_check_viz_runtime


logger = logging.getLogger(__name__)

MAX_DESIGN_ROUNDS = 3  # Design 循环最大轮数
MAX_CODE_ROUNDS = 3  # Code 循环最大轮数

# --------------------------------------------------------------------------
# 文档路径
# --------------------------------------------------------------------------

_CORE_PATH = (
    Path(__file__).parent.parent / "prompts" / "skills" / "eduviz_sdk" / "CORE.md"
)


def _load_core_doc() -> str:
    content = _CORE_PATH.read_text(encoding="utf-8")
    if not content.strip():
        raise VizQualityError("SDK 文档为空，无法生成可视化")
    return content


@dataclass
class _StageResult:
    """Internal stage result; never forwarded to the tool event stream."""

    value: object


async def _stream_turn(llm, messages, ctx=None, *, stage):
    """Use the same streaming Agent loop as HTML cards, including shared budgets."""
    agent = ReActAgent(
        llm=llm,
        prompt_builder=StaticPromptBuilder(messages[0]["content"]),
        tool_registry=ToolRegistry(),
        max_steps=1,
        llm_config={"temperature": 0.2},
    )
    child_ctx = ctx.child(scope=f"{ctx.scope}/{stage}") if ctx else None
    final = None
    async for event in agent.async_stream(
        messages[-1]["content"],
        ctx=child_ctx,
        chat_history=messages[1:-1],
    ):
        yield event
        if isinstance(event, AgentFinalEvent):
            final = event
    if final is None:
        raise RuntimeError(f"{stage} 未返回完整结果")
    reason = getattr(final.finish_reason, "value", final.finish_reason)
    if reason != AgentFinishReason.STOP.value:
        raise RuntimeError(f"{stage} 已停止（{reason}），未保存不完整内容")


# --------------------------------------------------------------------------
# 阶段一：Design 循环
# --------------------------------------------------------------------------


def _build_designer_system() -> str:
    """动态构建 Designer system prompt，viz_pattern 说明从 registry frontmatter 自动派生。"""
    metas = list_patterns_with_meta()

    # 生成 pattern 选择指引：每个 pattern 一行，包含名称、适用场景、推荐控件
    if metas:
        pattern_lines = []
        for m in metas:
            name = m.get("name", "")
            label = m.get("label", name)
            when = m.get("when_to_use", "")
            controls = m.get("controls", "")
            line = f"  - **{name}**（{label}）：{when}"
            if controls:
                line += f"\n    推荐控件：{controls}"
            pattern_lines.append(line)
        pattern_guide = "\n".join(pattern_lines)
        pattern_enum = " | ".join(m.get("name", "") for m in metas) + " | other"
    else:
        pattern_guide = "  - other：其他场景"
        pattern_enum = "other"

    return f"""\
你是「交互式可视化设计师」，专门为教学场景设计 EduViz 交互用例。

你的任务是输出一份结构化的 VizSpec（JSON），描述这个可视化的完整设计方案。

## viz_pattern 选择指南

根据概念的核心交互方式选择最合适的 pattern：

{pattern_guide}
  - **other**：以上均不适合时使用

## VizSpec 格式

```json
{{
  "title": "可视化标题",
  "concept": "核心概念一句话",
  "viz_pattern": "{pattern_enum}",
  "controls": [
    {{"type": "slider", "name": "控件名", "purpose": "作用说明", "expected_change": "操作后画面和反馈怎样变化", "range": {{"min": 0.1, "max": 2, "step": 0.1, "default": 1}}}}
  ],
  "canvas": {{
    "type": "axis2d | raw_canvas | svg_d3 | p5 | three | plotly | none",
    "description": "画布内容描述"
  }},
  "display": [
    {{"type": "latex|text|metric|progress", "name": "名称", "purpose": "展示什么"}}
  ],
  "initial_state": "默认参数、首屏图形、引导语和关键数值",
  "interaction_checks": [{{"action": "具体操作一", "expected": "可核对的图形或数值变化"}}, {{"action": "极值或边界操作", "expected": "正确的边界行为"}}],
  "interaction_flow": "用一段话描述用户如何操作、画面如何响应、学生能从中理解什么",
  "key_insight": "学生操作后应该获得的核心洞察"
}}
```

## 设计原则

- 每个可视化只讲一个概念，不要贪多
- 控件数量 1-5 个；类型可以是 slider/toggle/select/stepper/timeline/button
- 默认用 1-3 个必要控件、一张主图和简短反馈；仅在用户明确需要时增加模式和辅助按钮
- slider 的 range 必须给出有限数值 min/max/step/default；select 的 choices 是至少两项的对象数组，每项包含 label、value 字符串；其他控件不填 range/choices
- 每个控件都需要 expected_change，禁止只改控件标签而不影响教学内容的假交互
- 交互要直接体现概念的本质，不是装饰
- canvas 类型选最合适的，不要强行用复杂库
- 首屏就有可理解的主图、操作提示和结果反馈；明确坐标轴、单位、图例和适用条件
- 优先原生 Canvas/SVG 和 SDK，确有必要才引入第三方库；聚焦一个可完整实现的关系
- 主画布内部宽度约 900px，前端整体缩放适配窄屏；优先清晰紧凑，不要求在 600px 下重新布局
- 数字、按钮停点与公式使用同一组参数推导；不要把有限采样值写成精确的极限值

**只输出 JSON，不要有任何其他文字。**
"""


async def _design_viz(llm, title: str, concept: str, interaction_hint: str, ctx=None):
    request = f"标题：{title}\n概念：{concept}\n交互建议：{interaction_hint}"
    messages = [
        {"role": "system", "content": _build_designer_system()},
        {"role": "user", "content": request},
    ]
    feedback = ""
    for round_i in range(1, MAX_DESIGN_ROUNDS + 1):
        yield f"正在设计可视化方案（第 {round_i}/{MAX_DESIGN_ROUNDS} 轮）..."
        raw = ""
        async for event in _stream_turn(llm, messages, ctx, stage="design"):
            yield event
            if isinstance(event, AgentFinalEvent):
                raw = event.content or ""
        messages.append({"role": "assistant", "content": raw})
        try:
            spec = parse_contract(raw, VizSpec).model_dump(exclude_none=True)
            # A design is an implementation brief, not a second scored artifact.
            # Validate structure here; verify factual claims against the actual code.
            yield _StageResult(spec)
            return
        except VizQualityError as exc:
            feedback = str(exc)
        logger.info("[Design] 第 %d 轮未通过：%s", round_i, safe_log(feedback[:300]))
        messages.append(
            {
                "role": "user",
                "content": "本轮未通过，请根据反馈输出完整修订 JSON：\n" + feedback,
            }
        )
    raise VizQualityError("设计结构无效：" + feedback[:1200])


# --------------------------------------------------------------------------
# 阶段二：Code 循环
# --------------------------------------------------------------------------


def _build_coder_system(core_doc: str, pattern_examples: str) -> str:
    examples_section = (
        f"\n\n---\n\n# 示例参考\n\n{pattern_examples}" if pattern_examples else ""
    )
    return f"""你是「交互式可视化代码生成器」，专门为教学场景生成 EduViz 沙箱代码。

## 任务

根据用户提供的 VizSpec（可视化设计方案），输出一段完整可运行的 JavaScript 代码。
如果用户反馈了上一轮的校验错误或评审意见，请针对性修复后重新输出完整代码。

## 输出规范

- **只输出 JavaScript 代码，不要有任何解释文字、markdown 代码块标记**
- 不要写 `<html>` `<body>` 等 HTML 标签
- 不要写 `import` / `require`，所有库通过 `await EduViz.loadLib(...)` 加载
- 直接写顶层代码，外层已经是 async function，可以直接 `await`
- 用 `EduViz.colors()` 取主题色，保持视觉一致
- 不以行数牺牲完整性；实现清楚、紧凑、可维护的代码

## 代码原则

- **代码必须能跑**：不要写演示性的伪代码，每一行都要能在 iframe 沙箱中执行
- 以 VizSpec 的教学目标为准；发现方案中的数值或公式矛盾时，统一修正参数、读数和说明，不要照抄错误
- 收到反馈时只修正对应问题，保留已验证的图形与交互，不要重新设计整个可视化
- **只用 SDK 文档中的 API**：不要发明没有的方法
- 先创建所有控件、画布和反馈元素，最后绑定回调；SDK onChange/onStep/onFrame 注册时会立即执行
- 所有交互共用一个 render/update，首屏立即绘制，主题变化也重绘；每个控件必须有实际效果
- slider 的 min/max/step/default 必须与设计一致，极值和零附近不应出现 NaN、Infinity 或除零
- 主图应有坐标标签、单位和图例；反馈说明变化意味着什么；不要用随机数伪造算法或科学关系
- 内部渲染宽度约 900px，前端会整体缩放；不要求在 600px 下重新布局。canvas 保持比例，SVG 使用 viewBox
- 读数和结论由同一份状态计算，按钮停点、公式代入与说明必须一致；区分采样近似值和理论极限
- 检查步骤必须可由真实操作复现；算法展示中间状态，动画时间应决定模拟状态，不能只播放装饰
- 示例只提供 API 用法，必须补全逻辑，禁止省略号、TODO、空回调、无效开关、占位图

---

# EduViz SDK 核心文档

{core_doc}{examples_section}
"""


_CODE_JUDGE_SYSTEM = """你是可视化代码审查员，只识别影响使用或误导学习的确定性错误。

需要阻止发布的情况：
- 核心公式、计算结果或算法步骤错误；例如按钮实际停在 x=0.99，解释却声称当前读数取自 x=0.999。
- 必要交互在代码中明确未实现、接错变量、必定抛错，或关键图形无法显示。
- 实现遗漏了用户要求的核心教学内容。
每个 blocking_issues 必须说明代码中的具体证据、触发操作、实际与正确结果，以及最小修复办法。
不要臆测缺失需求，不要以未实现的额外功能阻止发布。

仅写入 suggestions 的情况（不阻止发布）：
- 配色、图例位置、文案润色、控件数量偏好、增加辅助信息、进一步优化响应式布局。
- 浏览器报告中的 warnings：这些是非阻塞提示，不能直接升级为阻塞问题。
- 方案与实现的非关键命名/参数调整：如果实现内部一致、教学目标正确，不要求恢复方案中的错误数值。
前端使用约 900px 的内部画布并整体缩放，600px 重排不是发布条件。
有限点的函数读数可以是近似值，但不能与代码参数矛盾，也不能冒充精确极限。
先验证实际代码；设计方案只是参考。不要打总分，不要求零改进空间。

只输出 JSON，两个字段都必须存在：
{
  "blocking_issues": [],
  "suggestions": []
}
"""


async def _review_code(llm, spec_str, code, report, ctx=None):
    messages = [
        {"role": "system", "content": _CODE_JUDGE_SYSTEM},
        {
            "role": "user",
            "content": f"设计：\n{spec_str}\n代码：\n{code}\n浏览器报告：\n{json.dumps(report, ensure_ascii=False)}",
        },
    ]
    # A malformed review is a reviewer failure, not a reason to regenerate working JS.
    for attempt in range(2):
        raw = ""
        async for event in _stream_turn(llm, messages, ctx, stage="code_review"):
            yield event
            if isinstance(event, AgentFinalEvent):
                raw = event.content or ""
        try:
            review = parse_contract(raw, VizReview)
        except VizQualityError as exc:
            if attempt:
                raise RuntimeError("代码评审未返回有效结果，请重试") from exc
            messages.extend(
                [
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": "请仅修正评审 JSON 格式，不要生成代码：" + str(exc),
                    },
                ]
            )
            continue
        yield _StageResult(review)
        return


def _extract_code(raw: str) -> str:
    """从 LLM 输出中提取纯 JS 代码（去掉 markdown 代码块标记）。"""
    text = raw.strip()
    # 去掉 ```javascript ... ``` 或 ```js ... ``` 或 ``` ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉首行（```javascript）和末行（```）
        start = 1
        end = len(lines)
        if lines[-1].strip() == "```":
            end -= 1
        text = "\n".join(lines[start:end])
    return text.strip()


async def _run_code_loop(
    work_dir: Path,
    spec: dict,
    user_id,
    core_doc: str,
    pattern_examples: str,
    ctx=None,
):
    validator = ValidateVizCodeTool()
    unavailable = validator.environment_error()
    if unavailable:
        raise VizRuntimeUnavailable(unavailable)
    llm = get_llm(user_id, scene="chat")
    spec_str = json.dumps(spec, ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": _build_coder_system(core_doc, pattern_examples)},
        {"role": "user", "content": f"根据以下设计输出完整 JavaScript：\n{spec_str}"},
    ]
    feedback = ""
    for round_i in range(1, MAX_CODE_ROUNDS + 1):
        yield f"正在生成可视化代码（第 {round_i}/{MAX_CODE_ROUNDS} 轮）..."
        raw = ""
        async for event in _stream_turn(llm, messages, ctx, stage="code"):
            yield event
            if isinstance(event, AgentFinalEvent):
                raw = event.content or ""
        code = _extract_code(raw)
        messages.append({"role": "assistant", "content": raw})
        path = work_dir / f"viz_r{round_i}.js"
        path.write_text(code, encoding="utf-8")
        try:
            if ctx:
                ctx.checkpoint()
            yield "正在进行 JavaScript 静态检查..."
            # Node/ESLint use blocking subprocesses; keep the event loop responsive.
            check = asyncio.to_thread(validator.run, file_path=str(path))
            result = await ctx.wait(check) if ctx else await check
            if result != "ok":
                raise VizQualityError(result)
            if ctx:
                ctx.checkpoint()
            yield "正在浏览器中检查画面与交互..."
            remaining = ctx.budget.remaining_seconds if ctx else None
            report = await async_check_viz_runtime(
                path,
                spec,
                timeout=min(35, remaining) if remaining is not None else 35,
                checkpoint=ctx.checkpoint if ctx else None,
            )
            if ctx:
                ctx.checkpoint()
            if not report["ok"]:
                raise VizQualityError(json.dumps(report, ensure_ascii=False))
            yield "正在评审教学逻辑与交互实现..."
            review = None
            async for event in _review_code(llm, spec_str, code, report, ctx):
                if isinstance(event, _StageResult):
                    review = event.value
                else:
                    yield event
            if review is None:
                raise RuntimeError("代码评审未返回有效结果")
            if review.accepted:
                yield _StageResult(
                    (
                        code,
                        {
                            "runtime": report,
                            "review": review.model_dump(),
                            "code_rounds": round_i,
                        },
                    )
                )
                return
            feedback = "\n".join(review.blocking_issues)
        except VizRuntimeUnavailable:
            raise
        except VizQualityError as exc:
            feedback = str(exc)
        logger.info("[Code] 第 %d 轮未通过：%s", round_i, safe_log(feedback[:300]))
        if round_i < MAX_CODE_ROUNDS:
            yield "本轮检查未通过，正在准备修复..."
        messages.append(
            {
                "role": "user",
                "content": "本轮未通过。修复以下问题，输出完整 JavaScript：\n"
                + feedback[:3000],
            }
        )
    raise VizQualityError("代码未通过质量检查：" + feedback[:1600])


# --------------------------------------------------------------------------
# Tool 主类
# --------------------------------------------------------------------------


class GenerateInteractiveVizTool(BaseTool):
    """
    两阶段循环生成交互式可视化代码（基于 EduViz SDK）。

    阶段一：Design 循环 — LLM 设计 VizSpec，结构校验，最多 MAX_DESIGN_ROUNDS 轮
    阶段二：Code 循环  — Coder Agent 写代码，validate + Judge 评审，最多 MAX_CODE_ROUNDS 轮

    成功时返回 viz_id（前端通过 /api/viz/{viz_id} 拉取代码），
    失败时返回 'Error: ...'。
    """

    name = "generate_interactive_viz"
    description = (
        "委派专门的子 Agent 生成一个交互式可视化教学示例。"
        "适用于「需要学生通过动手操作（拖滑块、看动画、逐步执行）才能真正理解的概念」，"
        "如：函数图像变化、算法过程、概率分布演化、物理模拟等。"
        "你只需描述要展示的概念和期望的交互形式，子 Agent 负责设计方案、编写 JavaScript 代码、校验、修复。"
        "生成的可视化会自动登记到文档系统（file_type='viz'），并可通过 node_ids 关联知识节点。"
        "成功返回 viz_id 字符串（同时也是 document_id），失败返回 'Error: ...'。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "可视化标题，简洁明确，如「导数的几何意义」「冒泡排序过程」",
            },
            "concept": {
                "type": "string",
                "description": (
                    "要让学生理解的核心概念。详细说明这个概念是什么、关键点在哪里，"
                    "便于子 Agent 设计合适的可视化。"
                ),
            },
            "interaction_hint": {
                "type": "string",
                "description": (
                    "建议的交互形式。例如：「滑块控制 Δx，观察割线变切线」、"
                    "「步进器逐步展示每一轮比较和交换」、「时间轴自动播放分布演化」。"
                    "可以为空，让子 Agent 自由发挥。"
                ),
            },
            "node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "关联的知识节点 ID 列表，用于把可视化与节点建立链接（便于后续检索/复用）",
            },
        },
        "required": ["title", "concept"],
    }

    def __init__(self, user_id=None, session_id=None):
        super().__init__()
        self.user_id = user_id
        self.session_id = session_id
        self._parent_ctx = None

    def bind_context(self, ctx):
        self._parent_ctx = ctx
        return self

    def run(self, **kwargs):
        raise NotImplementedError(
            "GenerateInteractiveVizTool 仅支持 async_stream_run 调用"
        )

    async def async_stream_run(
        self,
        title: str = "",
        concept: str = "",
        interaction_hint: str = "",
        node_ids: list = None,
        **kwargs,
    ):
        """Yield progress and Agent events, ending with viz_id or an Error string."""
        if not title.strip() or not concept.strip():
            yield "Error: title 和 concept 不能为空"
            return
        if not self.user_id:
            yield "Error: 缺少 user_id，无法登记可视化文档"
            return
        viz_id = str(uuid.uuid4())
        viz_dir = VIZ_DIR / viz_id
        published = False
        try:
            if self._parent_ctx:
                self._parent_ctx.checkpoint()
            core_doc = _load_core_doc()
            unavailable = ValidateVizCodeTool.environment_error()
            if unavailable:
                raise VizRuntimeUnavailable(unavailable)
            llm = get_llm(self.user_id, scene="chat")
            yield f"正在生成交互式可视化「{title}」..."
            spec = None
            async for event in _design_viz(
                llm, title, concept, interaction_hint, self._parent_ctx
            ):
                if isinstance(event, _StageResult):
                    spec = event.value
                else:
                    yield event
            if spec is None:
                raise RuntimeError("设计阶段未返回有效方案")
            with tempfile.TemporaryDirectory(prefix=f"viz_{viz_id}_") as tmp:
                work_dir = Path(tmp)
                result = None
                async for event in _run_code_loop(
                    work_dir,
                    spec,
                    self.user_id,
                    core_doc,
                    load_pattern(spec["viz_pattern"]),
                    self._parent_ctx,
                ):
                    if isinstance(event, _StageResult):
                        result = event.value
                    else:
                        yield event
                if result is None:
                    raise RuntimeError("代码阶段未返回有效结果")
                code, quality = result
                if self._parent_ctx:
                    self._parent_ctx.checkpoint()
                yield "检查通过，正在保存可视化..."
                if self._parent_ctx:
                    self._parent_ctx.checkpoint()
                viz_dir.mkdir(parents=True, exist_ok=False)
                viz_file = viz_dir / "viz.js"
                viz_file.write_text(code, encoding="utf-8")
                meta = {
                    "viz_id": viz_id,
                    "title": title,
                    "concept": concept,
                    "interaction_hint": interaction_hint,
                    "viz_spec": spec,
                    "user_id": self.user_id,
                    "session_id": self.session_id,
                    "quality": quality,
                }
                (viz_dir / "meta.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                preview = work_dir / "preview.png"
                if preview.exists():
                    shutil.copy2(preview, viz_dir / "preview.png")
                self._create_document_record(
                    viz_id,
                    viz_file,
                    title,
                    concept,
                    interaction_hint,
                    spec,
                    node_ids or [],
                )
            published = True
            logger.info("[GenerateViz] 生成成功: viz_id=%s", viz_id)
            yield viz_id
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("可视化生成失败")
            yield f"Error: 可视化生成失败 — {exc}"
        finally:
            if not published:
                shutil.rmtree(viz_dir, ignore_errors=True)

    def _create_document_record(
        self,
        viz_id: str,
        viz_file: Path,
        title: str,
        concept: str,
        interaction_hint: str,
        spec: dict,
        node_ids: list,
    ) -> None:
        generation_prompt = concept
        if interaction_hint:
            generation_prompt += f"\n\n[交互形式]\n{interaction_hint}"
        DocumentRepository().register_produced(
            doc_id=viz_id,
            user_id=self.user_id,
            title=title,
            file_path=viz_file,
            file_type="viz",
            session_id=self.session_id,
            generation_prompt=generation_prompt,
            node_ids=node_ids,
        )
