# 生成世界 · 历史 | Living History

命题式历史沉浸体验：输入任意一段历史——「烛影斧声」「郑和下西洋」——几分钟后它变成一个**活着的世界**：当年的当事人带着脾气在社区里发帖、吵架、站队，你来当史官。

## 玩法

- **围观**：当事人只说真话，但只说对自己有利的那半句；
- **质询**：抓住任何人追问，出示物证可以戳到有人当场破防；
- **学 · 史实对照**：每条帖子带「学」按钮，一键判定"符合史实 / 立场修饰 / 与史实有出入"并附史书记载与知识点——围观吵架就是史料实证训练；
- **推剧情**：发一条消息进去，他们不一定听你的，但一定有反应；
- 另有三个入口：**重演**（六帧画卷+语音+罗生门多视角）、**代入**（附身当事人做真实抉择，AI 推演此后一生）、**圆桌**（升堂听审、结案陈词）。

## 运行（独立模式）

依赖 WeSmartFlow 后端提供 `/api/court/*` 系列接口（案件生成流水线、多角色社区、质询、史实对照、CosyVoice 情感语音、qwen-image 插画）。

```bash
# 1. 启动后端（仓库根目录需有 .env，见下）
cd ../../backend
python main.py            # 默认 :8080；独立部署可设 BACKEND_PORT=18080

# 2. 起静态页
python3 -m http.server 18085    # 本目录
# 打开 http://127.0.0.1:18085
```

通过 WeSmartFlow 主站「探索」入口进入时，页面自动走同源 `/api/court`，无需单独起静态服务。

## 生成一桩新案

在首页输入框写任意历史事件或一个「如果」，约 35 秒内全部内容并行生成完毕：

| 时间 | 就绪内容 |
|---|---|
| ~5s | 案卷（标题/卷宗/悬念/四人物） |
| ~10s | 社区首批帖（当事人开吵） |
| ~20s | 圆桌开场对质、代入角色卡（可选人）、六帧+配图 |
| ~35s | 三角色决策、罗生门、推演岔口、岔口图 |

图片（封面/六帧/岔口/结局插画）由 qwen-image 按案件现场生成，落盘在本目录 `assets/`（运行时产物，不入库）。

## .env 配置（仓库根目录）

```
LLM_BASE_URL / LLM_API_KEY / LLM_MODEL      # 案件/剧本/角色生成（deepseek）
IMG_API_KEY / IMG_MODEL / IMG_BASE_URL      # qwen-image 场景插画
DASHSCOPE_API_KEY（即 IMG_API_KEY）          # CosyVoice 情感语音（分角色声线）
CORS_ORIGINS                                # 独立部署时加入静态页地址
```

## 目录结构

```
living_history/
├── index.html               # 单文件前端（零依赖，绢墨夜色主题）
├── build-wesmartflow.mjs    # WeSmartFlow 集成构建（复制静态产物）
├── package.json
└── assets/                  # 运行时生成的案件插画（.gitignore）
```

## 后端依赖

- `backend/court/`：forge 流水线（两步化并行生成 + 双发竞速）、案件包、史实对照、终幕推演
- `backend/routers/court.py`：`/api/court/*` 路由（forge / posts / interrogate / verdict / learn / tts / illustrate / debrief 等）
