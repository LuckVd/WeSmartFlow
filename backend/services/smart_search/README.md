# SmartSearch 多源并行检索服务

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Agent 调用 smart_search(query)                                  │
└─────────────────────────────┬───────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Router (router.py)                                              │
│  ① 规则匹配（80% case，0ms）                                    │
│  ② LLM 路由（复杂 case，~300ms）                                │
│  ③ Fallback（全失败兜底）                                        │
│  输出：{sources: [...], sub_queries: {...}}                       │
└─────────────────────────────┬───────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  并行检索 (service.py — asyncio.gather)                          │
│                                                                  │
│  ┌─────────┐ ┌───────────┐ ┌──────────┐ ┌─────────┐            │
│  │ Tavily  │ │ AnySearch │ │   DDG    │ │  arXiv  │            │
│  │ 2-5s    │ │ 2-3s      │ │ 1-3s    │ │ 1-2s    │            │
│  └────┬────┘ └─────┬─────┘ └────┬─────┘ └────┬────┘            │
│       └─────────────┴────────────┴─────────────┘                │
│                     总延迟 = max ≈ 3-5s                          │
└─────────────────────────────┬───────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Filter (filter.py)                                              │
│  L1: 来源可信度评分（域名白名单 + 时效衰减）                      │
│  L2: 去重（URL + 标题相似度 Jaccard > 0.7）                      │
│  L3: 多源交叉验证（2+ 源确认 → verified + 加分）                 │
│  排序: final_score = relevance × credibility × freshness         │
└─────────────────────────────┬───────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  输出：SmartSearchResult                                         │
│  - .to_agent_text()  精简版喂 Agent（控 token）                  │
│  - .to_markdown()    完整版给用户看                               │
└─────────────────────────────────────────────────────────────────┘
```

## 快速测试（独立运行，不需要启动后端）

```bash
cd edu-agent/backend

# 1. 安装依赖
pip install duckduckgo-search httpx arxiv tavily-python trafilatura

# 2. 配置 Key（二选一）
export TAVILY_API_KEY="tvly-xxxxx"              # 你原有的
export ANYSEARCH_API_KEY="as_sk_856ba0fac0a7647206d44584cc1e617f"

# 3. 运行测试
python test_smart_search.py
```

测试会跑 3 个 query，输出每一步详情：路由决策 → 各源返回数 → 筛选过程 → 最终 Markdown。

## 集成到 TutorAgent（替代原有 TavilySearch）

在 `services/tutor_service.py` 的 `_build_tools()` 方法中：

```python
# 原来：
from agent_core.tool.web import TavilySearch, ArxivSearch, WebFetch
tools.extend([
    TavilySearch(api_key=tavily_key, before_call_hook=_search_hook),
    ArxivSearch(),
    WebFetch(),
])

# 改成：
from services.smart_search import SmartSearchTool
tools.append(
    SmartSearchTool(
        tavily_key=tavily_key,
        anysearch_key=os.getenv("ANYSEARCH_API_KEY", ""),
        before_call_hook=_search_hook,
    )
)
```

**Agent 无需任何修改**——它原来调 `tavily_search`，现在调 `smart_search`，参数一模一样（只需一个 `query`）。

## 配置 API Keys

在后端 `.env` 文件中添加：

```bash
# 现有的
TAVILY_API_KEY=tvly-xxxxx

# 新增的
ANYSEARCH_API_KEY=as_sk_856ba0fac0a7647206d44584cc1e617f
```

或在 `database.py` 的 settings 表中配（和 Tavily 同理）。

## 文件结构

```
services/smart_search/
├── __init__.py          # 对外导出 SmartSearchService + SmartSearchTool
├── models.py            # 数据结构（SearchResult / SearchPlan / SmartSearchResult）
├── router.py            # 路由决策（规则 + LLM + fallback 三层）
├── filter.py            # 筛选（可信度 + 去重 + 交叉验证 + 排序）
├── service.py           # 核心调度器（并行 + 统一入口）
├── tool.py              # Agent 工具封装（SmartSearchTool）
├── README.md            # 本文件
└── sources/
    ├── __init__.py
    ├── base_source.py   # 源基类（统一接口）
    ├── tavily_source.py # Tavily（AI 优化搜索，主力）
    ├── anysearch_source.py  # AnySearch（垂直领域）
    ├── duckduckgo_source.py # DuckDuckGo（免费兜底）
    ├── arxiv_source.py  # arXiv（学术论文）
    └── web_fetch_source.py  # URL 抓取（深度获取）
```

## 扩展新源

实现 `BaseSource` 接口即可：

```python
from services.smart_search.sources.base_source import BaseSource
from services.smart_search.models import SearchResult

class MyNewSource(BaseSource):
    source_id = "my_source"
    display_name = "My Source"
    description = "..."

    async def search(self, query, max_results=5, **kwargs):
        # 调 API → 返回 list[SearchResult]
        ...
```

然后在 `service.py` 的 `_init_sources()` 里加一行注册即可。
