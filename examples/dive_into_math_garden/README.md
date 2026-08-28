# 走进数学花园

`dive_into_math_garden` 是 WeSmartFlow `examples/` 下的独立静态学习 Demo，主题为小学数学素养训练。它不导入主站 Vue 组件、状态或私有样式，也不要求单独启动后端服务。

作者：Shipeng Cen

## 定位

- **空间想象**：通过三视图、积木搭建和恢复推理，训练从不同视角理解立体结构的能力。
- **代数策略**：通过“算式炮弹”三选一回合制挑战，训练运算顺序、目标逼近和策略选择。
- **可独立运行**：源码只包含 HTML、CSS、浏览器 JS 和一个静态构建脚本。
- **可集成构建**：由 `build:wesmartflow` 读取 WeSmartFlow 注入的环境变量，输出可部署的静态产物。

## 目录结构

```text
dive_into_math_garden/
├── index.html
├── css/
│   └── style.css
├── js/
│   ├── app.js
│   ├── generator.js
│   ├── guide.js
│   ├── mathcannon.js
│   └── world.js
├── scripts/
│   └── build-wesmartflow.mjs
├── package.json
└── README.md
```

## 本地开发

```bash
npm install
npm run dev
```

`dev` 只启动静态文件服务。Demo 的核心流程可在无后端环境下运行。

## 集成构建

```bash
npm run build:wesmartflow
```

WeSmartFlow 顶层构建器调用该命令时会注入：

| 环境变量 | 用途 |
|---|---|
| `WESMARTFLOW_EXAMPLE_ID` | 当前主题 id |
| `WESMARTFLOW_EXAMPLE_OUT_DIR` | 静态产物输出目录 |
| `WESMARTFLOW_EXAMPLE_PUBLIC_PATH` | 部署后的公开根路径 |

构建脚本会复制 `index.html`、`css/` 和 `js/` 到输出目录，并在集成构建时写入 `<base>`，让 CSS 和 JS 按公开路径加载。

## 后端能力边界

当前 Demo 不需要后端即可完成主线。`app.js` 中的 AI 讲解只把 LLM 作为可选增强：如果未来需要真实模型能力，请按 WeSmartFlow 约定在主后端显式挂载 `/api/demo/dive-into-math-garden/llm`，不要在 Demo 目录内放置私有代理服务，也不要让浏览器包接触 API Key。

## 状态存储

算式炮弹历史记录使用带命名空间的 `localStorage` key：

```text
dive-into-math-garden:mathcannon-history:v3
```

后续新增存储也应使用 `dive-into-math-garden:` 前缀，并在结构变化时升级版本号。
