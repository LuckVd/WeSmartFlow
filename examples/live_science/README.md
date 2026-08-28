# 知识之境 · Live Science

沉浸式（恋与深空风）科学知识沉浸体验**平台**。学生沿历史时间线穿越到知识诞生的现场，与科学家 NPC 对话、在历史困境中做选择、亲手操作探究实验、每站回到课本完成衔接。

## 运行

```bash
cd live_science
python3 server.py    # 零依赖：自动继承 edu-agent/.env（LLM/TTS/图像全部接入）
# 打开 http://127.0.0.1:8767
```

## 目录结构（篇章并列）

```
live_science/                    ← 「知识之境」项目总目录
├── index.html                   ← 门户页（篇章列表 + 生成入口）
├── server.py                    ← 共享服务器（静态 + /api/llm /api/tts /api/generate /api/chapters）
├── generate.html                ← 篇章生成器（topic + 画像 → AI 现场打造）
├── voice_lab.html               ← 音色试听实验室
├── assets/voice_samples/        ← TTS 音色样本
└── chapters/                    ← 篇章并列存放，一个 topic 一个目录
    ├── conic-sections/          ← 圆锥曲线（出厂预装）
    │   ├── index.html           ← 播放器引擎
    │   ├── story.js             ← 剧本数据（STORY/RIVER/META）
    │   └── assets/              ← 场景 CG
    └── gravity-apple-to-stars/  ← 万有引力（AI 生成）
        └── （同构）
```

## 生成新篇章

打开 `/generate.html`，输入科学主题 + 选画像（小学/初中/高中/大学/大众），AI 现场完成：科学史调研与剧本 → qwen-image 电影级 CG → 装配。约 4-6 分钟，完成后自动出现在门户。

## .env 配置（edu-agent 根目录，server.py 自动读取）

```
LLM_BASE_URL / LLM_API_KEY / LLM_MODEL   # 剧本生成 + 自由问答（当前 deepseek-v4-flash）
DASHSCOPE_API_KEY                        # qwen3-tts-instruct-flash 配音（10 音色+语气指令）
IMG_BASE_URL / IMG_API_KEY / IMG_MODEL   # qwen-image-2.0 场景 CG（电影级质感 prompt 内置）
```
