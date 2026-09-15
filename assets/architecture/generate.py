"""Generate README architecture diagrams: python3 assets/architecture/generate.py.

Only the standard library is needed. Keep the shared layout and labels here so
both README languages stay in sync using the selected sketch style.
"""

from html import escape
from pathlib import Path


PALETTE = dict(bg="#FFFBF1", card="#FFFEF8", ink="#3D413C", muted="#757669",
               line="#9D9C88", accent="#427C67", soft="#EEF2DC", core="#E9EFDD",
               core_card="#FAFBEF", core_ink="#35483C", core_muted="#667C62", wire="#8A9780")


def render(language):
    p = PALETTE
    zh = language == "zh"
    pick = lambda cn, en: cn if zh else en
    font = "'Chalkboard SE', 'Kaiti SC', KaiTi, cursive"
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1192" viewBox="0 0 1200 1192" role="img" aria-labelledby="title desc" xml:lang="{language}">
  <title id="title">{pick('WeSmartFlow 系统架构', 'WeSmartFlow system architecture')}</title>
  <desc id="desc">{pick('网页、独立探索主题与微信入口接入教育业务服务。业务通过 Agent 注册表使用 agent_core，并读写个人学习记忆和公共知识图谱。业务负责持久化，模型与工具通过适配器接入外部能力。', 'Web, independent Explore apps and WeChat connect to education services. Services assemble agent_core through an Agent registry and access personal learning memory and a shared knowledge graph. Services own persistence; model and tool adapters connect external capabilities.')}</desc>
  <defs>
    <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M1 1 L7 4 L1 7" fill="none" stroke="{p['wire']}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></marker>
    <pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="0.7" fill="{p['line']}" opacity="0.5"/></pattern>
  </defs>
  <rect width="1200" height="1192" rx="24" fill="{p['bg']}"/>
  <g font-family="{font}">''']
    parts.append('<rect x="20" y="20" width="1160" height="1152" fill="url(#dots)"/>')

    def text(x, y, value, size=20, weight=400, color=None, extra=""):
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color or p["ink"]}" {extra}>{escape(value)}</text>')

    def box(x, y, w, h, fill=None, stroke=None):
        fill, stroke = fill or p["card"], stroke or p["line"]
        # Slightly uneven, deterministic strokes; text stays sharp and selectable.
        d = (f'M{x+12} {y+1} Q{x+w/2} {y-2} {x+w-12} {y+1} '
             f'Q{x+w+1} {y+1} {x+w-1} {y+14} L{x+w+1} {y+h-13} '
             f'Q{x+w} {y+h+1} {x+w-12} {y+h-1} '
             f'Q{x+w/2} {y+h+2} {x+12} {y+h} Q{x-1} {y+h} {x+1} {y+h-13} '
             f'L{x-1} {y+13} Q{x} {y} {x+12} {y+1} Z')
        parts.append(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')

    def wire(d, dashed=False, both=False):
        attrs = (' stroke-dasharray="6 5"' if dashed else '') + (' marker-start="url(#arrow)"' if both else '')
        parts.append(f'<path d="{d}" fill="none" stroke="{p["wire"]}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#arrow)"{attrs}/>')

    # Header and entry points.
    text(48, 54, "WeSmartFlow", 22, 700)
    text(1152, 54, "SYSTEM ARCHITECTURE", 14, 600, p["muted"], 'text-anchor="end" letter-spacing="2"')
    text(48, 108, pick("同一套 Agent，连接每一种学习体验", "One Agent foundation. Many ways to learn."), 36, 700)
    text(48, 140, pick("多端接入 · 教育业务编排 · 通用 Agent 内核 · 学习记忆", "Learning interfaces · Education services · Agent runtime · Learning memory"), 19, color=p["muted"])
    text(48, 186, pick("01  学习入口", "01  LEARNING INTERFACES"), 16, 600, p["accent"])

    entries = [
        (48, pick("Web 学习工作台", "Web learning workspace"), pick("辅导 / 课程 / 图谱 / 测验", "Tutoring / courses / graph / quizzes"), "frontend/ · Vue 3 + Vite"),
        (424, pick("独立探索主题", "Independent Explore apps"), pick("独立构建，同源发布，按需接 API", "Independent builds; optional APIs"), "examples/ · explore-catalog.json"),
        (800, pick("微信学习入口", "WeChat interfaces"), pick("原生小程序 + WeClaw 消息通道", "Mini program + WeClaw messaging"), "miniprogram/ · backend/channels/"),
    ]
    for x, title, detail, path in entries:
        box(x, 208, 352, 120)
        text(x+22, 245, title, 23, 600)
        text(x+22, 276, detail, 18, color=p["muted"])
        text(x+22, 306, path, 15, color=p["accent"])
    wire('M224 328 V348 H530 V370')
    wire('M600 328 V370', dashed=True)
    wire('M976 328 V348 H670 V370')
    box(48, 372, 1104, 56, p["soft"])
    text(72, 407, "FastAPI + Channels", 22, 600)
    text(1128, 407, pick("REST / SSE · 身份认证 · 积分钱包 · 消息桥接", "REST / SSE · Authentication · Credits · Message bridge"), 19, color=p["muted"], extra='text-anchor="end"')
    wire('M416 428 V458')

    # Services, domain memory and Agent core are distinct ownership boundaries.
    box(48, 460, 736, 210)
    text(72, 498, pick("02  教育业务编排", "02  EDUCATION SERVICES"), 23, 600)
    text(760, 498, "backend/services/", 16, color=p["muted"], extra='text-anchor="end"')
    for x, title, a, b in [
        (72, pick("个性化辅导", "Tutoring"), "TutorService", pick("会话 / 流式反馈", "Sessions / streaming")),
        (304, pick("沉浸式课程", "Immersive courses"), "ImmersiveService", pick("规划 / 研究 / 撰写 / 出题", "Plan / research / write / quiz")),
        (536, pick("教学内容与工具", "Learning tools"), pick("卡片 / EduViz / 测验", "Cards / EduViz / quizzes"), pick("文档 / 搜索 / 音视频", "Documents / search / media")),
    ]:
        box(x, 522, 224, 94, p["bg"])
        text(x+16, 550, title, 20, 600)
        text(x+16, 576, a, 16, color=p["muted"])
        text(x+16, 599, b, 15, color=p["muted"])
    text(72, 646, "Agent registry", 18, 600, p["accent"])
    text(250, 646, pick("声明 Agent · 注入工具、提示词与上下文", "Agent definitions · tools · prompts · context"), 17, color=p["muted"])

    box(824, 460, 328, 440, p["soft"])
    text(846, 498, pick("学习记忆与知识", "Memory & knowledge"), 23, 600)
    box(844, 520, 288, 130)
    text(862, 551, pick("个人学习记忆", "Personal learning memory"), 20, 600)
    text(862, 582, pick("用户画像 · 掌握度 · 复习计划", "Profile · mastery · review plan"), 17, color=p["muted"])
    text(862, 610, pick("按用户保存学习状态", "Learning state for each user"), 17, color=p["muted"])
    text(862, 634, "services/ · repositories/", 15, color=p["accent"])
    box(844, 670, 288, 162)
    text(862, 701, pick("公共知识图谱", "Shared knowledge graph"), 20, 600)
    text(862, 730, "Graph RAG · Concept / Facet", 17, color=p["muted"])
    text(862, 758, pick("观察 → 提议 → 人工审核", "Observe → propose → review"), 17, color=p["muted"])
    text(862, 785, pick("通过 kg_facade 访问", "Access through kg_facade"), 17, color=p["muted"])
    text(862, 812, "backend/kg/", 15, color=p["accent"])
    text(846, 863, pick("由业务层检索、写入与注入上下文", "Services retrieve, persist and inject"), 17, color=p["muted"])
    text(846, 886, pick("个人状态与公共知识分开管理", "Personal state stays separate"), 16, color=p["muted"])
    wire('M786 566 H822', both=True)

    wire('M416 670 V712')
    box(48, 714, 736, 260, p["core"], p["core"])
    text(72, 754, "03  agent_core", 26, 700, p["core_ink"])
    text(760, 754, pick("通用推理与运行时", "REUSABLE AGENT RUNTIME"), 17, 500, p["core_muted"], 'text-anchor="end"')
    for i, (title, a, b) in enumerate([
        ("Agent", "ReAct", pick("DAG 工作流", "DAG workflow")),
        ("Context", "Assemble", pick("统一消息装配", "Messages")),
        ("History", "SessionMemory", pick("会话与摘要", "Summaries")),
        ("Tools", "Registry / MCP", pick("技能与子 Agent", "Skills / agents")),
        ("LLM", "OpenAI API", pick("兼容协议适配", "Compatible API")),
    ]):
        x = 72 + i*140
        box(x, 780, 128, 116, p["core_card"], p["core_card"])
        text(x+12, 813, title, 21, 600, p["core_ink"])
        text(x+12, 844, a, 14, color=p["core_muted"])
        text(x+12, 871, b, 14, color=p["core_muted"])
    text(72, 937, "RunContext", 18, 600, p["core_ink"])
    text(230, 937, pick("预算 · 取消 · 追踪 · 事件", "Budgets · cancellation · tracing · events"), 18, color=p["core_muted"])

    # Persistence belongs to the business layer, not to agent_core.
    wire('M48 584 H26 V1076 H46')
    wire('M600 974 V998 H880 V1022')
    box(48, 1024, 536, 112)
    text(72, 1058, pick("业务持久化", "Business persistence"), 22, 600)
    text(72, 1088, "SQLite (WAL) · sqlite-vec · Files", 19, color=p["muted"])
    text(72, 1116, pick("会话 / 画像 / 积分 / 知识 / 课程资产", "Sessions / profiles / credits / knowledge / assets"), 17, color=p["muted"])
    box(608, 1024, 544, 112)
    text(632, 1058, pick("模型与工具接入", "Model & tool integrations"), 22, 600)
    text(632, 1088, "LLM · Search · Image · TTS · MCP", 19, color=p["muted"])
    text(632, 1116, pick("通过适配器与工厂接入，可按场景替换", "Adapters and factories; replaceable per use case"), 17, color=p["muted"])
    text(48, 1172, pick("箭头表示主要调用与数据关系；虚线表示探索主题可选的 API 接入。", "Arrows show primary calls and data access; dashed line = optional Explore API access."), 15, color=p["muted"])
    parts.append('  </g>\n</svg>\n')
    return '\n'.join(parts)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    for language in ("zh", "en"):
        (root / f"sketch-{language}.svg").write_text(render(language), encoding="utf-8")
