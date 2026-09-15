**[English](./README_EN.md) | 中文**

# WeSmartFlow Frontend

基于 Vue 3 的单页应用，提供自适应学习的完整交互界面。

## 模块结构

```
frontend/
├── public/              # 静态资源
│   ├── logo.jpg         #   应用 Logo
│   ├── logo.png         #   浏览器标签图标（圆角处理）
│   └── icons.svg        #   SVG 图标集
├── src/
│   ├── views/           # 页面视图
│   │   ├── LoginView.vue       # 登录页（邮箱 / GitHub / 微信）
│   │   ├── DashboardView.vue   # 今日学习（学习计划 + 热力图）
│   │   ├── ChatView.vue        # AI 辅导（交互式 + 沉浸式）
│   │   ├── GraphView.vue       # 知识图谱可视化
│   │   ├── KnowledgeBase.vue   # 知识库管理
│   │   ├── QuizView.vue        # 测验中心
│   │   ├── DocumentsView.vue   # 文档管理
│   │   ├── SessionsView.vue    # 学习记录
│   │   ├── DailyBrief.vue      # 每日简报
│   │   ├── LearningPath.vue    # 学习路径
│   │   ├── ProfileView.vue     # 个人中心
│   │   └── SettingsView.vue    # 系统设置
│   ├── components/      # 可复用组件
│   │   ├── EduViz/      #   交互式可视化沙盒
│   │   │   ├── EduVizSandbox.vue  # iframe 沙盒渲染器
│   │   │   ├── eduviz-sdk.js      # EduViz SDK 核心库
│   │   │   └── sandboxTemplate.js # 沙盒 HTML 模板
│   │   ├── HtmlCard/    #   HTML 知识卡片渲染
│   │   │   └── HtmlCard.vue       # 安全渲染 Agent 生成的 HTML 卡片
│   │   ├── QuizCard/    #   测验卡片
│   │   │   └── QuizCard.vue       # 多题型测验交互组件
│   │   ├── VizCard/     #   可视化卡片
│   │   │   └── VizCard.vue        # 可视化结果展示卡片
│   │   └── chat/        #   对话辅助组件
│   │       ├── ThinkBlock.vue     # Agent 思考过程展示
│   │       └── ToolCallBlock.vue  # 工具调用过程展示
│   ├── api/             # API 客户端
│   │   ├── base.js      #   基础请求封装（含 Token 管理）
│   │   ├── index.js     #   统一导出
│   │   ├── auth.js      #   认证 API
│   │   ├── sessions.js  #   会话 API（含 SSE 流式）
│   │   ├── documents.js #   文档 API
│   │   ├── nodes.js     #   知识节点 API
│   │   ├── quizzes.js   #   测验 API
│   │   ├── settings.js  #   设置 API
│   │   ├── brief.js     #   简报 API
│   │   └── user.js      #   用户 API
│   ├── composables/     # Vue 组合式函数
│   │   ├── useAuth.js   #   认证状态管理
│   │   └── useTheme.js  #   主题切换
│   ├── styles/          # 全局样式
│   │   └── page-list.css#   列表页通用样式
│   ├── assets/          # 构建时处理的资源
│   ├── App.vue          # 根组件（侧边栏布局）
│   ├── main.js          # 应用入口（路由 + 全局样式）
│   └── style.css        # 全局 CSS 变量与基础样式
├── index.html           # HTML 入口
├── package.json         # 依赖配置
├── vite.config.js       # Vite 构建配置
├── eslint.config.js     # ESLint 配置
└── stylelint.config.cjs # Stylelint 配置
```

## 环境要求

| 依赖    | 版本            | 说明     |
| ------- | --------------- | -------- |
| Node.js | 24+             | 运行时   |
| npm     | 随 Node.js 安装 | 包管理器 |

## 安装与启动

以下命令在 `frontend/` 目录执行；Conda 环境配置见[主 README](../README.md#-快速开始)，当前使用 Node.js 25。

```bash
# 安装依赖，包括后端 EduViz 校验需要的 ESLint
npm install --include=dev

# 自动构建探索主题所需的依赖
npm --prefix ../examples/Magic_English_Town install
npm --prefix ../examples/chemastry_lab install

# 开发模式（端口 5173）
npm run dev

# 生产构建
npm run build

# 预览生产构建
npm run preview
```

`npm run dev` 和 `npm run build` 都会先构建[目录中登记的本地探索主题](../examples/explore-catalog.json)。运行前请完成上面的主题依赖安装。

开发环境的 `/api`、`/files` 请求由 [vite.config.js](vite.config.js) 代理到 `http://localhost:8080`；生产部署需要单独配置 API 转发。`npm run preview` 用于预览构建产物，不会启动后端。

## 核心依赖

| 包         | 版本  | 用途               |
| ---------- | ----- | ------------------ |
| vue        | ^3.5  | UI 框架            |
| vue-router | ^4.6  | 路由管理           |
| marked     | ^18.0 | Markdown 渲染      |
| katex      | ^0.16 | LaTeX 数学公式渲染 |
| dompurify  | ^3.3  | HTML 安全净化      |
| pdfjs-dist | ^5.6  | PDF 文件渲染       |
| pdf-lib    | ^1.17 | PDF 文件操作       |

## 页面功能

| 页面     | 路由         | 功能                                     |
| -------- | ------------ | ---------------------------------------- |
| 登录     | `/login`     | 多方式登录（邮箱验证码 / GitHub / 微信） |
| AI 辅导  | `/chat`      | 交互式对话学习                           |
| 今日学习 | `/dashboard` | 个性化学习计划、学习热力图、待复习节点   |
| 知识图谱 | `/graph`     | 力导向图可视化、节点详情、掌握度展示     |
| 知识库   | `/knowledge` | 兼容旧地址，重定向到 `/graph`            |
| 测验     | `/quiz`      | 多题型测验（单选/填空/判断/开放题）      |
| 文档     | `/documents` | 文档上传与知识抽取                       |
| 学习记录 | `/sessions`  | 历史会话列表                             |
| 每日简报 | `/brief`     | AI 生成的每日学习资讯                    |
| 个人中心 | `/profile`   | 用户画像与学习统计                       |
| 设置     | `/settings`  | LLM 配置、系统设置                       |
| 项目首页 | `/`          | 公开介绍页                               |
| 探索主题 | `/explore`   | 独立的互动学习体验                       |
| 沉浸课程 | `/immersive` | 章节课件、讲解与练习                     |
| 微信助手 | `/weclaw`    | WeClaw 绑定与通道管理                    |

路由使用 hash 模式，例如 `/chat` 对应 `http://localhost:5173/#/chat`。首页与登录页公开访问，学习页面需要登录。

## 特性

- **SSE 流式对话** — 实时展示 AI 回复，支持 Markdown + LaTeX + 代码高亮渲染
- **HTML 知识卡片** — 在 iframe 中展示后端规范化的 HTML 知识卡片，支持公式与插图
- **EduViz 交互式可视化** — iframe 沙盒渲染 Agent 生成的教学可视化（算法演示、参数探索等）
- **测验卡片** — 内嵌式多题型测验，即时反馈与评分
- **沉浸式学习** — 多章节课件渐进式展示，支持音频播放
- **知识图谱可视化** — 力导向图 + 三维掌握度展示
- **Agent 透明度** — 展示 Agent 思考过程与工具调用详情
- **暗色主题** — 支持亮色 / 暗色主题切换
- **离开确认** — 生成中离开页面时弹出确认提示，防止意外中断
- **响应式布局** — 适配桌面端浏览器

## 流式生成与渲染

| 入口               | 传输与结果                                                                            |
| ------------------ | ------------------------------------------------------------------------------------- |
| 辅导对话中的工具   | `/api/sessions/{session_id}/chat/stream` 通过 SSE 推送工具进度与最终结果              |
| 独立 HTML 卡片生成 | `/api/cards/generate-html` 通过 SSE 推送进度与结果                                    |
| 独立可视化生成     | `/api/viz/generate` 在消费后端工具流后返回 JSON `{ok, viz_id, error}`                 |
| 已保存内容         | `/api/documents/{id}/raw` 读取主文件，同一文档下的 `/asset/{asset_path}` 读取伴生资源 |

[HtmlCard.vue](src/components/HtmlCard/HtmlCard.vue) 将生成的文档加载到 iframe；[VizCard.vue](src/components/VizCard/VizCard.vue) 读取 JavaScript，再交给 [EduVizSandbox.vue](src/components/EduViz/EduVizSandbox.vue) 注入 SDK 与沙盒模板执行。

EduViz 在约 900px 的内部宽度上渲染，再整体缩放以适配卡片。执行完成、尺寸就绪后才显示内容；运行异常显示在卡片中，主题切换会通知 iframe。后端的 600px 重排检查是提示项，不是前端缩放卡片的实际方式。

修改 SDK API 时，也要同步 [CORE.md](../backend/agents/prompts/skills/eduviz_sdk/CORE.md)、[注册表](../backend/agents/tools/viz_registry.py) 与相关浏览器检查。部署时保持前端产物和后端校验使用的 SDK 版本一致。检查能力及局限见[后端指南](../backend/README.md#内容生成工具)。

## 检查与排障

在 `frontend/` 目录执行：

```bash
npm run validate:examples
npx eslint src/components/EduViz/EduVizSandbox.vue src/components/EduViz/sandboxTemplate.js src/components/EduViz/eduviz-sdk.js
```

- 探索主题构建提示找不到 Vite：进入对应主题目录安装依赖。
- API 请求失败：检查后端健康接口，以及开发代理或生产反向代理配置。
- 可视化空白：查看卡片错误和浏览器控制台；重试已有代码不会重新生成一份代码。
- Chromium 安装与浏览器回归命令见[后端指南](../backend/README.md#验证)。

## 开发规范

- ESLint + Prettier 代码格式化
- Stylelint CSS 规范检查
- 组件采用 `<script setup>` 组合式 API
- CSS 变量统一管理主题色
