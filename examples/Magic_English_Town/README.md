# Magic English Town

魔法英语小镇是面向 8–16 岁学习者的连续英语互动故事课程。孩子和会回应、会陪伴的 Agent 角色用英语互动，在探索小镇、寻找线索、完成任务和创作故事中自然开口；Agent 负责理解表达和生成角色回应，真正的地点、任务、奖励和通关条件始终由本地白名单状态机决定。

作者：Zexi Jia

当前包含两节可以独立进入、共享课程记忆的故事课：

| 课程 | Story ID | 核心学习内容 | 完成结果 |
|---|---|---|---|
| Lesson 1 · The Missing Puppy | `missing-puppy` | 位置描述、询问线索、介绍 Coco、关心朋友 | 完成个人故事书与 1–3 颗课程星 |
| Lesson 2 · The Welcome Home Moonlight Festival | `moonlight-festival` | 礼貌请求、颜色与形状、步骤表达、邀请 | 完成月光节故事书与 1–3 颗课程星 |

主线必须包含学习者自己的英语表达，不能只靠连续点击通关。麦克风始终是可选能力，键盘输入可以完成全部主线。

## 1. 统一启动

生产和日常联调都使用 WeSmartFlow 的一套前后端，不再单独启动 Magic Town Agent 服务。

### 启动后端

先确保 `backend/.env` 已配置 WeSmartFlow 模型：

```bash
cd backend
cp .env.example .env
# 编辑 .env 中的 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL
conda run --no-capture-output -n agent zsh -c 'set -a; source .env; set +a; exec python main.py'
```

### 启动主前端

```bash
cd frontend
npm install
npm run dev
```

`predev` 会自动构建本课程到 `frontend/public/magic-english-town/`。访问：

```text
http://localhost:5173/#/explore
http://localhost:5173/magic-english-town/index.html?source=wesmartflow
```

直接进入某一课：

```text
http://localhost:5173/magic-english-town/index.html?story=missing-puppy
http://localhost:5173/magic-english-town/index.html?story=moonlight-festival
```

## 2. 只调试课程页面

需要独立热更新课程前端时，仍然使用 WeSmartFlow 的 `8080` 后端，然后启动课程自己的 Vite：

```bash
cd examples/Magic_English_Town
npm install
npm run dev
```

访问 `http://localhost:5188/magic-english-town/`。Vite 会把全部 `/api` 请求代理到 `http://127.0.0.1:8080`；如需改目标，可设置 `MAGIC_TOWN_API_TARGET`。

这条开发链路只启动页面，不会启动第二个 Agent 后端，也不会复制模型配置。

## 3. 构建

从主前端只构建本主题：

```bash
cd frontend
npm run build:examples -- --only magic-english-town
```

该命令通过通用集成协议调用课程的 `build:wesmartflow`，由主站注入公开路径和临时输出目录；课程独立执行 `npm run build` 时仍输出自己的 `dist/`。

完整主前端构建会同时验证主题目录、构建课程和构建 WeSmartFlow：

```bash
cd frontend
npm run validate:examples
npm run build
```

## 4. 目录职责

```text
Magic_English_Town/
├── README.md
├── index.html
├── package.json
├── vite.config.js                  # 独立/集成构建路径与 /api 开发代理
├── agent_contract.py               # Agent 动作白名单与状态校验
├── magic_town_api.py               # 供主后端挂载的 APIRouter
├── src/
│   ├── main.js                     # 课程首页/故事入口与返回 WeSmartFlow
│   ├── course-hub.js               # 两节课卡片、续学、重开
│   ├── app.js                      # Lesson 1 的 magic-town-v1 运行时
│   ├── runtimes/
│   │   ├── index.js                # runtime 注册表
│   │   └── moonlight-festival.js   # Lesson 2 运行时
│   ├── core/
│   │   ├── story-engine.js         # Lesson 1 状态、表达证据、线索与写作
│   │   ├── moonlight-engine.js     # Lesson 2 状态、任务与通关条件
│   │   ├── scene-unlocks.js        # 共用场景/挑战解锁规则
│   │   ├── course-memory.js        # localStorage 读写、恢复与单课重置
│   │   ├── course-stars.js         # 共用 1–3 星计算和完成组件
│   │   ├── learning-challenges.js  # 选择、填空、描述、对话判题
│   │   ├── lesson-input-dock.js    # 共用文字/语音输入区
│   │   ├── agent-client.js         # Lesson 1 Agent 请求和响应校验
│   │   ├── festival-agent-client.js # Lesson 2 Agent 请求和响应校验
│   │   ├── agent-limits.js         # 前端请求长度与超时常量
│   │   ├── speech-input.js         # Web Speech 识别与降级
│   │   └── browser.js              # 朗读、分段与 HTML 转义
│   ├── story-kit/
│   │   ├── define-story.js         # 故事包协议与加载时校验
│   │   └── story-registry.js       # 故事注册、默认值与回退
│   ├── stories/                    # 每节课自己的清单、题库和奖励
│   ├── style.css                   # Lesson 1 与课程通用视觉
│   ├── moonlight.css               # 课程首页和 Lesson 2 视觉
│   ├── lesson-dock.css             # 两节课共用操作台/响应式规则
│   ├── course-stars.css            # 共用星级与完成状态
│   └── ui-scale.css                # 视口、安全区和浏览器兼容层
```

维护边界：

- 故事专属角色、词汇、题目、奖励和写作内容放在 `stories/`；
- 可复用的状态、判题、语音和浏览器能力放在 `core/`；
- 场景渲染与指令编排放在版本化 `runtime`；
- API 凭据与模型配置只属于 WeSmartFlow 后端；
- `dist/`、`node_modules/`、缓存和 `.env` 都不是源码。

## 5. 运行链路与 API

课程只请求相对 API：

```text
POST /api/demo/magic-town/agent
POST /api/demo/magic-town/festival-agent
GET  /api/demo/magic-town/health
```

挂载链路：

```text
backend/main.py
└── backend/routers/examples.py
    └── backend/routers/magic_town.py
        └── Magic_English_Town/magic_town_api.py:router
```

接口请求包含学习者消息、有限对话历史和紧凑世界状态。后端执行输入安全检查、频率限制、结构化模型调用和动作白名单归一化。模型异常、响应无法解析或网络不可用时，前端保留本地指令解析与明确降级提示，主线仍可继续。

可调后端环境变量：

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `MAGIC_TOWN_AGENT_RPM` | `24` | 每 IP 每分钟请求上限，范围 1–120 |
| `MAGIC_TOWN_LLM_TIMEOUT` | `60` | 模型请求超时秒数，范围 10–120 |

## 6. 进度与兼容

课程进度继续保存在浏览器：

```text
localStorage: magic-english-town:course-memory:v1
sessionStorage: magic-english-town:wesmartflow-entry
```

第一阶段不把课程进度迁移到 WeSmartFlow 数据库。`course-memory:v1` 同时保存两节课；重开一节课只删除该课的数据，不影响另一节课。修改存储结构时应升级版本或提供兼容迁移。

响应式与浏览器约定：

- `ui-scale.css` 提供 `100vh` 回退，在支持时切换到 `100dvh`；
- 刘海屏使用 `env(safe-area-inset-*)`；
- 900px 以下操作台转为流式布局，避免固定高度裁切；
- 不使用 `:has()` 等缺少旧浏览器退路的关键选择器；
- 语音识别不可用时始终保留文字输入；
- 动画不能作为唯一状态提示。

真实发布前需人工检查 Chrome、Safari、Firefox 及 360px / 768px / 1366px 三档宽度。

## 7. 新增故事课

同一世界与同一交互语法下新增课程：

1. 复制 `src/stories/missing-puppy.js` 和对应子目录。
2. 修改唯一 kebab-case `id`、课程信息、角色、词汇、题库、奖励和写作内容。
3. 复用现有小镇动线时保留 `runtime: "magic-town-v1"`。
4. 在 `world.sceneUnlocks` 与 `learning.challengeUnlocks` 声明解锁条件。
5. 在 `course.rating` 声明隐藏挑战与 1–3 星规则。
6. 在 `src/stories/index.js` 注册故事包。
7. 人工验证状态恢复、主线门槛、完成页和响应式布局。

如果新课拥有不同世界、地点或指令语法，应新增 runtime 并在 `src/runtimes/index.js` 注册，不要在共享核心中按故事 ID 堆条件判断。

完整故事包字段与分层规则见 [src/stories/README.md](./src/stories/README.md)。

## 8. 提交前清单

- 两节课都可以从课程首页进入、续学和单独重开；
- Lesson 1 完成页显示完成状态和 1–3 颗星；
- Lesson 2 最终故事书、回顾页和完成星级可达；
- 键盘输入可以完成所有必做任务；
- Agent 不可用时有清晰降级，且不会绕过状态机；
- `npm run validate:examples` 和主前端 `npm run build` 全部通过；
- 源码中没有 `dist/`、`__pycache__/`、日志、截图或真实密钥。
