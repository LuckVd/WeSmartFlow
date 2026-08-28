# WeSmartFlow 探索主题开发指南

`examples/` 存放从 WeSmartFlow「探索」入口进入的独立学习体验。每个 Demo 都可以有完全不同的技术栈、页面风格、交互方式和进度模型；WeSmartFlow 只负责发现、介绍、统一构建和同源访问。

理想的新增流程是：

1. 新建一个独立应用目录；
2. 提供一个符合约定的集成构建命令；
3. 在 `explore-catalog.json` 登记分类和主题。

只要现有目录契约足够表达新主题，就不需要再修改侧边栏、探索页、卡片或介绍抽屉。

## 1. 设计边界

### 1.1 门户层负责什么

WeSmartFlow 门户只负责：

- 在侧边栏提供统一的「探索」入口；
- 从目录生成分类、主题卡片和介绍抽屉；
- 构建本地 Demo，并把产物放到主前端的公开目录；
- 让 Demo 与主站共享域名、端口和可选的后端服务。

卡片和抽屉使用统一信息结构，是“课程入口包装”，不是 Demo 的 UI 框架。目录里的 `cover` 和 `theme` 只改变入口展示，不会限制进入后的页面风格。

### 1.2 Demo 自己负责什么

每个 Demo 独立负责：

- 内部路由、页面布局和视觉设计；
- Vue、React、Svelte、原生 HTML、Canvas、Three.js 等技术选择；
- 学习流程、课程数据和浏览器进度；
- 自己的单元测试、响应式规则和无障碍体验；
- 需要时，通过相对 `/api/...` 地址调用共享后端。

Demo 不应导入 WeSmartFlow 的内部 Vue 组件、Pinia/页面状态或私有 CSS。这个隔离保证主站和各 Demo 可以独立演进，也允许不同 Demo 呈现完全不同的视觉语言。

### 1.3 稳定契约

主站与 Demo 之间只有三类显式契约：

```text
内容契约：explore-catalog.json
构建契约：build:wesmartflow + 3 个环境变量
服务契约：同源静态路径 + 可选的相对 /api 路径
```

不要通过扫描目录、猜测框架或读取 Demo 源码来生成探索入口。

## 2. 目录结构与数据流

```text
examples/
├── README.md                 # 本指南
├── explore-catalog.json      # 探索页唯一内容目录
├── catalog.mjs               # schema 校验和安全路径工具
├── validate.mjs              # 独立目录校验入口
├── build.mjs                 # 与前端框架无关的构建编排器
└── <ExampleName>/            # 完全独立的学习应用
```

主前端只保留通用展示代码：

```text
frontend/src/
├── views/ExploreView.vue
└── features/explore/
    ├── catalog.js
    ├── ExploreTopicCard.vue
    └── ExploreTopicDrawer.vue
```

数据和构建流向：

```text
explore-catalog.json
├── catalog.mjs → validate.mjs
├── build.mjs → Demo 构建命令 → frontend/public/<outputDir>/
└── frontend alias → catalog.js → Card / Drawer → ExploreView
```

本地 Demo 构建后与 WeSmartFlow 共享前端地址。例如 `/magic-english-town/` 实际由主前端开发服务器或部署后的静态站点提供，不需要长期启动第二个 Vite 服务。

## 3. 启动与常用命令

推荐始终启动 WeSmartFlow 主前后端。

后端：

```bash
cd backend
conda run --no-capture-output -n agent zsh -c 'set -a; source .env; set +a; exec python main.py'
```

前端：

```bash
cd frontend
npm install
npm run dev
```

`frontend` 的 `predev` 会先构建目录中所有带 `build` 的本地主题。入口为：

```text
http://localhost:5173/#/explore
```

常用检查：

```bash
cd frontend

# 只校验 JSON 内容、字段和路径边界
npm run validate:examples

# 只构建一个主题
npm run build:examples -- --only magic-english-town

# 构建全部主题，再构建主前端
npm run build
```

顶层构建器不会自动安装各 Demo 的依赖。首次拉取或依赖变化后，需要在对应 Demo 目录运行一次包安装命令。

## 4. 新增任意技术栈的本地 Demo

下面以 `Science_Lab` 为例。目录可以按自己的框架组织；门户不要求一定存在 `src/`、Vite 配置或 Vue 组件。

```text
examples/Science_Lab/
├── README.md
├── package.json
├── package-lock.json
├── index.html
├── src/                      # 可选，结构由 Demo 决定
└── tests/                    # 推荐
```

### 4.1 提供集成构建命令

当前编排器使用 npm 作为统一执行入口，因此目录中需要 `package.json`，并提供目录里指定的 script。推荐统一命名为 `build:wesmartflow`：

```json
{
  "private": true,
  "scripts": {
    "dev": "your-own-dev-command",
    "build": "your-own-standalone-build-command",
    "build:wesmartflow": "your-integrated-build-command",
    "test": "your-own-test-command"
  }
}
```

`build:wesmartflow` 可以调用任意框架、静态站点生成器或自定义 Node 脚本。npm 在这里只是稳定的命令入口，不代表 Demo 必须使用某个前端框架。

执行时，`examples/build.mjs` 会注入：

| 环境变量 | 含义 |
|---|---|
| `WESMARTFLOW_EXAMPLE_ID` | 当前主题 id，例如 `science-lab` |
| `WESMARTFLOW_EXAMPLE_OUT_DIR` | 本次构建必须写入的绝对临时目录 |
| `WESMARTFLOW_EXAMPLE_PUBLIC_PATH` | 部署后的公开根路径，例如 `/science-lab/` |

集成构建必须：

- 把完整、可独立访问的静态产物写入 `WESMARTFLOW_EXAMPLE_OUT_DIR`；
- 让 JS、CSS、图片等资源以 `WESMARTFLOW_EXAMPLE_PUBLIC_PATH` 为基础路径；
- 生成目录中声明的 `entryFile`，一般是 `index.html`；
- 非零退出表示失败，不应悄悄回退到过期或不完整产物。

编排器先构建到 `frontend/public/.examples-staging/`，检查入口文件后才替换该主题原有产物。因此单个主题构建失败时，上一份已成功的公开产物仍然保留。

### 4.2 Vite 示例

Vite 项目可以同时保留独立构建和集成构建：

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "build:wesmartflow": "vite build"
  }
}
```

```js
import { defineConfig } from "vite";

const standalonePath = "/science-lab/";
const integratedOutput = process.env.WESMARTFLOW_EXAMPLE_OUT_DIR;

export default defineConfig({
  base: process.env.WESMARTFLOW_EXAMPLE_PUBLIC_PATH || standalonePath,
  build: integratedOutput
    ? { outDir: integratedOutput, emptyOutDir: true }
    : undefined,
});
```

不要依赖顶层编排器给 Vite 追加 `--outDir` 参数；由 Demo 自己读取契约环境变量，React、Svelte、静态 HTML 或自研构建工具也采用同一方式。

### 4.3 静态 HTML 或其他框架

纯静态 Demo 可以让 `build:wesmartflow` 调用一个很小的 Node 脚本，把 HTML、CSS、JS 和资源复制到 `WESMARTFLOW_EXAMPLE_OUT_DIR`。React、SvelteKit、Astro、Three.js 等项目则在各自配置中把输出目录和 base path 映射到上表中的两个变量。

门户不读取构建产物以外的内部文件，所以目录命名和源码结构可以完全不同。

## 5. 登记分类和主题

### 5.1 分类

已有分类可直接复用。新增分类写入 `categories`：

```json
{
  "id": "school-science",
  "title": "中小学科学",
  "kicker": "LEARNING THEME",
  "icon": "⚗",
  "description": "通过观察、实验和推理理解科学。"
}
```

只有至少包含一个已发布主题的分类会显示。可见分类超过一个时，探索页自动出现分类切换。

### 5.2 完整主题示例

`explore-catalog.json` 当前 schema 版本为 `2`：

```json
{
  "id": "science-lab",
  "categoryId": "school-science",
  "title": "小小科学实验室",
  "type": "互动科学实验",
  "author": "Example Author",
  "badge": "NEW",
  "summary": "通过可操作的实验理解光、声音和力。",
  "href": "/science-lab/index.html?source=wesmartflow",
  "launchLabel": "进入小小科学实验室",
  "facts": ["9–14 岁", "3 个实验", "无需额外设备"],
  "tags": ["适合 9–14 岁", "基础科学", "可重复实验"],
  "hero": {
    "kicker": "SCIENCE LAB",
    "description": "改变条件、观察现象，并说出自己的推理。",
    "symbol": "⚗",
    "sparkles": "· ✦ ·"
  },
  "cover": {
    "kind": "symbol"
  },
  "theme": {
    "primary": "#0f8f83",
    "primaryDark": "#087067",
    "skyStart": "#174b63",
    "skyEnd": "#27879a",
    "surface": "#f6fffc",
    "surfaceText": "#173e3a"
  },
  "sections": [
    {
      "title": "你会探索什么",
      "layout": "grid",
      "items": [
        { "label": "👀", "title": "科学观察", "detail": "记录现象和变化" },
        { "label": "💡", "title": "因果推理", "detail": "提出并验证猜想" }
      ]
    },
    {
      "title": "实验单元",
      "layout": "list",
      "items": [
        { "label": "01", "title": "光的方向", "detail": "光源、影子与角度" }
      ]
    }
  ],
  "audience": {
    "title": "适合怎样的学习者？",
    "description": "适合喜欢动手尝试，并愿意描述发现的 9–14 岁学习者。"
  },
  "persistence": "实验进度会保存在当前浏览器",
  "build": {
    "runner": "npm",
    "script": "build:wesmartflow",
    "packageDir": "Science_Lab",
    "outputDir": "science-lab",
    "entryFile": "index.html"
  }
}
```

### 5.3 字段说明

| 字段 | 必填 | 用途与约束 |
|---|---:|---|
| `id` | 是 | 全局唯一，必须为小写 kebab-case |
| `categoryId` | 是 | 必须引用已登记分类 |
| `title` / `type` / `summary` | 是 | 卡片和抽屉中的基础文案 |
| `author` | 是 | Demo 作者或团队名称，显示在卡片和介绍抽屉中 |
| `badge` | 否 | 卡片短标签，例如 `NEW` |
| `published` | 否 | 默认展示；`false` 时隐藏，但本地主题仍会参与构建 |
| `href` | 是 | 站内路径以 `/` 开头，也可使用 `http(s)` 外部地址 |
| `launchLabel` | 是 | 抽屉主按钮文案 |
| `facts` | 是 | 卡片短事实数组，可以为空 |
| `tags` | 是 | 抽屉标签数组，可以为空 |
| `hero` | 是 | `kicker`、`description`、`symbol`，`sparkles` 可选 |
| `cover` | 是 | 门户封面类型及其配置，见下一节 |
| `theme` | 否 | 只覆盖允许的门户视觉 token |
| `sections` | 是 | 通用详情段落数组，可以为空 |
| `audience` | 否 | `title` 和 `description` 组成的适合人群提示 |
| `persistence` | 否 | 进度保存提示；不代表主站代为存储 |
| `build` | 本地主题必填 | 本地构建协议；外部主题省略 |

`sections[].layout` 当前支持：

| 布局 | 适用内容 |
|---|---|
| `grid` | 学习能力、特色、收获等短信息，桌面双列、手机单列 |
| `list` | 课程、关卡、步骤等顺序信息，始终单列 |

每一项统一使用 `{ "label", "title", "detail" }`。门户不再硬编码“学习收获”或“课程列表”，所以音乐、编程、科学、游戏等主题都可以复用。

### 5.4 封面类型

| `cover.kind` | 配置 | 适用场景 |
|---|---|---|
| `symbol` | 无额外字段 | 默认的抽象符号封面，适合大多数新主题 |
| `storybook` | 无额外字段 | 月亮、地形等故事书式封面；魔法英语小镇使用 |
| `image` | `src`、`alt` | 使用自定义图片表达完全不同的主题风格 |

图片地址必须是以单个 `/` 开头的站内公开地址，或 `http(s)://...` 地址，并提供准确的 `alt`；生产环境的外部图片应使用 HTTPS。建议把站内入口封面放在 `frontend/public/explore-covers/`，不要让门户跨目录引用某个 Demo 的源码文件。

封面只是探索入口的预览。进入 Demo 后，页面不需要延续入口的布局、字体或插画风格。

### 5.5 可覆盖的主题 token

未声明的字段使用门户默认值；未知字段会被校验器拒绝，防止目录逐渐变成无约束 CSS 配置。

| token | 用途 |
|---|---|
| `primary` / `primaryDark` | 标记、编号和主按钮 |
| `skyStart` / `skyEnd` | `symbol`、`storybook` 标题背景 |
| `land` / `landAlt` / `moon` | 故事书装饰及高亮 |
| `surface` / `surfaceText` | 抽屉底色和主要文字 |
| `panel` | 标签与信息项底色 |
| `muted` | 次级说明文字 |
| `line` | 边框与分隔线 |
| `soft` | 图标块与人群提示底色 |
| `footer` | 抽屉粘性底栏背景，可使用带透明度的 CSS 颜色 |

这些 token 只作用于门户入口，不会注入 Demo 页面。

### 5.6 本地构建限制

带 `build` 的主题还必须满足：

- `runner` 当前固定为 `npm`；
- `script` 必须存在于子项目 `package.json`；
- `href` 以 `/<outputDir>/` 开头；
- `outputDir` 在全部主题中唯一，也不能与另一个输出目录互相嵌套；
- `packageDir`、`outputDir`、`entryFile` 都是规范的相对路径，不能含 `.`、`..` 或空路径段；
- `outputDir` 不能使用编排器保留的 `.examples-staging`；
- 构建完成后必须存在 `entryFile`。

目录对象采用严格字段白名单。拼错字段或继续使用旧版 `outcomes`、`lessons` 等字段会直接校验失败，避免内容被门户静默忽略。

### 5.7 外部主题

已部署到外部站点的学习体验可以使用 `https://...` 的 `href` 并省略整个 `build`。卡片、抽屉、封面和详情段落仍可复用。

## 6. 接入后端能力

纯前端 Demo 不需要修改后端。需要模型、数据库或服务器能力时：

1. 在 Demo 内导出带唯一前缀的 FastAPI `APIRouter`，例如 `/api/demo/science-lab`；
2. 在 `backend/routers/` 添加一个很薄的适配器，只定位 Demo 并重新导出 `router`；
3. 在 `backend/routers/examples.py` 中显式 `include_router`；
4. Demo 前端只请求相对地址 `/api/demo/science-lab/...`；
5. API Key、模型地址等只放在 `backend/.env`，不能进入浏览器包。

适配器示例：

```python
import sys
from pathlib import Path

example_dir = Path(__file__).resolve().parents[2] / "examples" / "Science_Lab"
if str(example_dir) not in sys.path:
    sys.path.insert(0, str(example_dir))

from science_lab_api import router  # noqa: E402,F401
```

后端使用显式聚合，不在启动时扫描和执行 `examples/` 中的未知 Python 文件。这样接入点可审查，启动失败也容易定位。

## 7. 状态、导航和样式隔离

- `localStorage` 键必须带 Demo 命名空间和版本，例如 `science-lab:progress:v1`；
- 同一域名下的 `localStorage` 不按路径隔离，禁止使用 `progress`、`state` 等通用键；
- 存储结构变化时升级版本，必要时提供显式迁移；
- 可通过 `source=wesmartflow` 判断是否显示“返回探索”，返回目标为 `/#/explore`；
- 不要复制 WeSmartFlow 登录 token 到 Demo 自己的存储；需要鉴权时使用共享会话和相对 API；
- Demo 的全局 CSS 只存在于自己的 HTML 文档，不应写入主站入口；
- 不要假设主站字体、CSS 变量、Vue 版本或 DOM 结构可用。

## 8. 响应式、浏览器与无障碍底线

新 Demo 至少保证：

- 360px 手机、768px 平板、1366px 桌面宽度没有横向溢出或不可达操作；
- Chrome、Safari、Firefox 当前稳定版可完成核心流程；
- 不依赖 hover、麦克风、触屏或鼠标中的任何单一输入方式；
- 麦克风不可用或拒绝授权时，文字或点击仍能完成主线；
- 弹层支持 `Escape`、合理焦点顺序和清晰的焦点样式；
- 使用 `100dvh` 时保留 `100vh` 回退，并考虑 safe-area；
- 尊重 `prefers-reduced-motion`，关键状态不只依赖动画传达。

探索门户的介绍抽屉已统一处理背景滚动锁、Tab 焦点循环、Escape 关闭、关闭后焦点恢复、手机全宽和视口高度回退。Demo 自己的弹层仍需自行满足这些要求。

## 9. 什么时候需要改哪些文件

| 需求 | 应修改的位置 |
|---|---|
| 新增纯前端本地 Demo | 新 Demo 目录 + `explore-catalog.json` |
| 新增外部 Demo | 只改 `explore-catalog.json` |
| 新增分类 | 只改目录中的 `categories` |
| Demo 需要后端 | Demo + 薄适配器 + `backend/routers/examples.py` |
| 新增所有主题都需要的目录能力 | `catalog.mjs` + 通用组件 + 本 README |
| 只改变某个 Demo 的页面风格 | 只改该 Demo，不改探索通用组件 |

如果一个需求只服务于单个 Demo，优先留在该 Demo 内。只有至少能被多种主题稳定复用的能力，才应进入门户 schema 或通用组件。

## 10. 提交前检查

```bash
cd frontend
npm run validate:examples
npm run build
```

还应人工检查：

- 分类、卡片、介绍抽屉的文案和封面是否完整；
- 作者名称是否准确，并与 Demo 自身 README 保持一致；
- 入口链接、返回探索和直接访问是否都正确；
- 刷新后进度能恢复，重置单课不会误删其他主题数据；
- 后端不可用时有可理解的提示或安全降级；
- 手机横竖屏、键盘操作和浏览器后退正常；
- 源码目录中没有 `dist/`、缓存、截图、日志或真实 `.env`。

## 11. 常见问题

### 修改 Demo 后主站仍是旧页面

```bash
cd frontend
npm run build:examples -- --only <topic-id>
```

主前端读取 `frontend/public/<outputDir>/`，不是子项目自己的 `dist/`。

### 构建提示 href 与 outputDir 不一致

下面三处必须使用同一个公开 slug：

```text
href: /science-lab/index.html
build.outputDir: science-lab
WESMARTFLOW_EXAMPLE_PUBLIC_PATH: /science-lab/（由编排器注入）
```

### 集成构建后没有入口文件

确认 `build:wesmartflow` 使用了 `WESMARTFLOW_EXAMPLE_OUT_DIR`，并生成与 `build.entryFile` 一致的文件。不要把集成产物仍写入默认 `dist/`。

### 子项目独立启动时 API 请求失败

确认 WeSmartFlow 后端已在 `8080` 启动，并在该 Demo 的开发服务器中把 `/api` 代理到后端。Demo 不需要再启动第二个 Agent 后端。

### JSON 能解析，但校验失败

运行 `npm run validate:examples` 查看精确字段。schema 会检查完整的卡片、抽屉、构建和路径契约，而不只是 JSON 语法。

## 12. 当前主题

| 主题 | 目录 | 公开路径 | 后端接口 | 进度方式 |
|---|---|---|---|---|
| 魔法英语小镇 | `Magic_English_Town/` | `/magic-english-town/` | `/api/demo/magic-town` | 带命名空间的 `localStorage` |
| 追剧搭子 BingeMate | `English_clip_mate/` | `/bingemate/` | 无，纯前端 | 带命名空间的 `localStorage` |
| 化学实验室 | `chemastry_lab/` | `/chemistry-lab/` | `/api/demo/chemistry-lab` | 带命名空间的 `localStorage` |

魔法英语小镇自身的课程结构和开发命令见 [Magic_English_Town/README.md](./Magic_English_Town/README.md)。

化学实验室见 [chemastry_lab/README.md](./chemastry_lab/README.md)。

追剧搭子是纯静态主题，`build:wesmartflow` 只做白名单资源复制，详见 [English_clip_mate/README.md](./English_clip_mate/README.md)。
