**[English](./README_EN.md) | 中文**

# agent_core — 通用 Agent 基础库

与业务解耦的通用 Agent 基础库，封装了推理范式、工具系统、技能加载、上下文构建与记忆管理等核心抽象，可独立复用于任意 LLM 应用。

## 定位

介于 LangChain / AutoGen 与裸写循环之间——**只保留跑通一个工业级 Agent 所必需的抽象**，将扩展点清晰暴露。

## 五个核心部件

一个 Agent 跑起来只需要五样东西，缺一不可、多一不必：

| # | 部件 | 职责 | 位置 |
|---|------|------|------|
| 1 | **LLM** | messages → response | `llm/` |
| 2 | **Tools** | 登记 / schema 投影 / 执行 | `tool/` |
| 3 | **History** | 存消息，按预算产出**纯 history** | `memory/` |
| 4 | **Assemble** | **拼出最终 messages** | `context/assemble.py` |
| 5 | **Loop** | think → act → 重复 | `agent/loop.py` |

横切支撑：`runtime/` 的 `RunContext`（预算 / 取消 / 追踪 / 事件）。

## 模块结构

```
agent_core/
├── runtime/          # 运行期设施（叶子，只依赖标准库）
│   ├── run_context.py  #   RunContext：per-run 状态袋 + 治理信号
│   ├── budget.py       #   Budget：步数/工具数/token/成本/时限
│   ├── settings.py     #   AgentSettings：不可变配置注入
│   ├── trace.py        #   Tracer：调用树追踪（默认零开销）
│   └── events.py       #   DomainEvent：业务事件信封
├── llm/              # LLM 适配层（无状态）
│   ├── base.py         #   BaseLLM / LLMResponse / 流式事件
│   └── openai_llm.py   #   OpenAI 兼容实现（支持任意兼容网关）
├── memory/           # 记忆工程：短期对话历史
│   ├── base.py         #   协议 + safe_cut 截断保护 + 计量
│   ├── strategies.py   #   FullMemory / WindowMemory / SummaryMemory
│   ├── session_memory.py # ★ SessionMemory：跨 run 连续（store 持久化 + 锚点/轨迹/摘要）
│   └── store.py        #   SessionStore 协议（业务实现持久化后端）
├── context/          # 上下文工程：拥有最终 messages
│   ├── assemble.py     #   ★ 唯一装配点（唯一能产生 system 的地方）
│   ├── builder.py      #   SystemPromptBuilder 协议（只出 str）
│   ├── static.py       #   StaticPromptBuilder：固定文本
│   ├── layered.py      #   LayeredPromptBuilder：角色 + 片段 + 技能
│   └── provider.py     #   ContextProvider 协议 + 通用壳
├── tool/             # 工具系统
│   ├── base.py         #   BaseTool + 参数矫正 + JSON Schema 校验
│   ├── decorator.py    #   @tool 装饰器
│   ├── registry.py     #   ToolRegistry
│   ├── agent_tool.py   #   Agent-as-Tool 多 Agent 协作
│   ├── mcp.py          #   MCP 协议（stdio / SSE / streamableHttp）
│   ├── web.py          #   Tavily / arXiv / WebFetch
│   ├── filesystem.py / shell.py / pdf_compile.py
│   ├── image_gen.py    #   图像生成工具壳（客户端见 imagegen/）
│   ├── search/         #   搜索客户端（BaseSearchClient + Tavily 实现）
│   ├── imagegen/       #   图像生成客户端（BaseImageGen + Qwen / OpenAI 实现）
│   └── tts/            #   TTS 客户端（BaseTTS + Qwen / MacSay / CosyVoice / Fallback）
├── agent/            # 编排
│   ├── loop.py         #   tool_calling_loop：唯一的 ReAct 循环
│   ├── react.py        #   ReActAgent
│   ├── base.py         #   BaseAgent：依赖注入 + 三入口
│   ├── history.py      #   消息构造纯函数
│   ├── events.py       #   流式事件类型
│   └── workflow.py     #   声明式 DAG（路径已知的确定性流水线）
├── skills/loader.py  # Markdown 声明式技能解析与加载
├── builtins/         # 内置 agent.md + 5 个技能包
├── structured.py     # 结构化输出：三级 JSON 提取
└── layout.py         # AgentWorkspace 目录布局
```

依赖单向流动，无环：

```
agent → context → memory → runtime
   ↓        ↓
  llm     tool
```

## 三条边界铁律

上下文的四个来源各有归属，互不越界：

| 来源 | 提供方 | 进入位置 |
|------|--------|---------|
| 指令 | `SystemPromptBuilder` | system 段 |
| 知识 | `ContextProvider`（业务实现） | system 段 |
| 历史 | `memory.render()` | history 段 |
| 工具 | `ToolRegistry.get_definitions()` | tools 参数（**计入预算**）|

1. **只有 `context.assemble` 能产生 `role="system"` 消息。** 记忆若越界返回
   system，装配层会剔除并告警——曾因此出现"两条 system"，部分模型原生 API 直接拒绝。
2. **SystemPromptBuilder 只出 `str`，永不出 `Message`。** 它不知道消息列表的存在。
3. **Memory 不决定自己能占多少 token，只执行下发的预算。** 只有装配层知道
   system 与 tool schema 占了多少——曾因漏算这两项，"token 上限"形同虚设。

## ReAct 循环

`ReActAgent` 是框架唯一的推理范式，三个入口共享同一份流式实现：

```python
# 同步
result = agent.run("帮我查一下天气")

# 异步
result = await agent.async_run("帮我查一下天气")

# 流式（yield 强类型事件）
async for event in agent.async_stream("帮我查一下天气", ctx=ctx):
    # AgentThinkChunkEvent / AgentToolCallEvent / AgentToolResultEvent / AgentFinalEvent
    ...
```

`async_stream` 是**唯一的实现点**，另两个入口消费它并只取终态——一份逻辑，
三个入口，行为必然一致。

固定 DAG、需要细粒度进度或断点续跑的确定性流水线，改用 `agent/workflow.py`。

## 工具系统

三种定义方式，按场景选择：

### 1. `@tool` 装饰器

从函数签名 + docstring 自动生成 Function Calling schema：

```python
from agent_core.tool import tool

@tool
def search_web(query: str, max_results: int = 5) -> str:
    """搜索互联网获取最新信息。

    Args:
        query: 搜索关键词
        max_results: 最大返回结果数
    """
    ...
```

### 2. 继承 `BaseTool`

适合需要依赖注入（DB / user_id）的场景：

```python
from agent_core.tool import BaseTool

class CreateNodeTool(BaseTool):
    name = "create_node"
    description = "创建知识图谱节点"
    parameters = { ... }

    def __init__(self, user_id: int):
        self.user_id = user_id

    def run(self, **kwargs) -> str:
        ...
```

### 3. MCP 协议包装

对接外部 MCP 服务器，支持 stdio / SSE / streamableHttp 三种传输：

```python
from agent_core.tool import MCPToolWrapper

tools = await MCPToolWrapper.from_server("http://localhost:3000/mcp")
```

## Agent-as-Tool：多 Agent 协作

任何 Agent 都可通过 `as_tool()` 包装为工具，注册到父 Agent 的 `ToolRegistry` 中：

```python
orchestrator = ReActAgent(
    tool_registry=ToolRegistry([
        researcher.as_tool(name="research",  description="资料检索"),
        writer.as_tool(name="write_tex",  description="撰写 Beamer"),
    ]),
)
```

子 Agent 通过 `ctx.child()` 派生上下文：**预算与取消信号向下传导**（子 Agent
的消耗计入父预算，无法绕过成本上限），**对话历史相互隔离**（子 Agent 看不到
父 Agent 的对话）。

## Markdown 声明式技能

技能以 `SKILL.md` 形式存放，用 frontmatter 声明依赖与加载策略：

```markdown
---
description: 将 TeX 编译为 PDF
always: false
requires:
  bins: [xelatex, latexmk]
  env:  [BEAMER_TEMPLATE_DIR]
---
# TeX Beamer 撰写规范 ...
```

- 缺依赖的技能自动从可用列表剔除
- `workspace/skills/` 优先于 `builtins/skills/`，用户可覆盖默认行为
- `always: true` 常驻 system prompt，其它按需加载，节省 token

## LLM 适配层

基于 `BaseLLM` 抽象接口，内置 OpenAI 兼容实现，支持：

- **流式输出** — `async_stream_chat` 逐 token 返回
- **Function Calling** — 自动解析工具调用
- **多模型切换** — 通过配置切换不同模型
- **自定义适配** — 继承 `BaseLLM` 即可对接任意 LLM 服务

```python
from agent_core.llm import OpenAILLM

llm = OpenAILLM(
    api_key="sk-xxx",
    base_url="https://api.openai.com/v1",
    model="gpt-4o"
)
```

## 记忆工程

框架只管**短期记忆**（本次会话的对话历史），提供三种策略：

| 策略 | 行为 | 适用 |
|------|------|------|
| `FullMemory` | 不裁剪（默认） | 短对话 |
| `WindowMemory` | 滑动窗口，按轮次边界安全裁剪 | 长对话 |
| `SummaryMemory` | 滚动摘要：窗口外旧消息增量压缩 | 超长对话 |

```python
from agent_core.memory import SummaryMemory

agent = ReActAgent(
    llm=llm,
    memory_factory=lambda: SummaryMemory(llm=llm, window=20, trigger=40),
)
```

**跨 run 连续（`SessionMemory`）**：需要跨请求持久化的会话（如 tutor）用
`SessionMemory`——业务实现 `SessionStore` 协议（读消息 / 读写摘要与游标），
框架负责压缩与可见性：`[system+摘要] + [游标后历史·窗口兜底] + [锚点(本轮任务)]
+ [运行轨迹]`。锚点经「运行中第一条 append」内化，Agent 侧零改动；
摘要经 `summary` 属性由装配层自动合并进 system。

压缩是**懒的（render 驱动）**：历史段撞窗或 token 预算紧张时，才把
窗口外增量压进摘要（写 summary + 推进游标，当轮即可见）；正常轮次
零 LLM 调用。压缩不可用（无 LLM / 失败）时退回纯裁剪兜底。

```python
from agent_core.memory import SessionMemory
from services.session_store import SQLiteSessionStore

memory = SessionMemory(SQLiteSessionStore(repo, session_id), llm=llm)
ctx = new_context(principal=f"user:{uid}", scope="tutor", memory=memory)
async for ev in agent.async_stream(user_input, ctx=ctx):  # 不传 chat_history
    ...
# 无需收尾动作：压缩由 render 按需触发
```

**截断安全**：OpenAI 兼容 API 要求 `assistant(tool_calls)` 与其后的 `tool`
消息严格配对，裁剪时切断配对会直接收到 400。所有策略都通过 `safe_cut`
把切点前移到安全的轮次边界。

**长期记忆**（用户画像、知识图谱）属于业务领域，通过 `ContextProvider` 注入
system prompt，不混入本包——框架因此无需反向 import 业务模块：

```python
class ProfileProvider:                 # 业务侧实现
    name = "profile"
    title = "用户画像"

    async def provide(self, ctx, user_input=""):
        return build_profile_text(self._user_id)

builder = LayeredPromptBuilder(providers=[ProfileProvider("u1")])
```
