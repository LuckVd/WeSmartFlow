"""「命题造案」forge v3 —— 四幕主线 + 全并行流水线。

速度设计（LLM 耗时 ∝ 输出长度；总时长 = max(单任务) 而非 sum）：
- stage1a（同步，目标 ~8s）：极小案卷——标题/卷宗/悬念/结局/4人物（名字+脾气）
- 返回后立即并行开跑六个线程：
  T-cover   封面图（题目确定即可画）
  T-tl      时间线（幕一用，~15s）
  T-posts   社区首批帖预热（~30s 开张）
  T-1b      完整人设+开场对质（→stage1.5 圆桌可玩）
  T-script  剧本：六帧(带每帧画面)+罗生门+小测+代入（→stage2.5，随后并起 f1-f6 帧图）
  T-whatif  反事实岔口（→stage2.8）
- 前端只按字段就绪解锁（frames/mode2_roles/what_ifs/opening_script），
  stage 数字仅作展示，故并行完成顺序不影响体验。
"""

import asyncio
import json
import logging
import re
import threading
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from services.llm_factory import get_llm
from services.external_usage import current_usage, before_raw, record_raw, UsageThread

logger = logging.getLogger(__name__)

CASES_DIR = Path(__file__).parent / "cases"
CASES_DIR.mkdir(parents=True, exist_ok=True)
# 图片落盘目录：放在 backend/court/.assets 下（与 frontend 路径解耦，部署更稳）
ASSET_DIR = Path(__file__).parent / ".assets"
ASSET_DIR.mkdir(parents=True, exist_ok=True)

FORGE_TASKS: Dict[
    str, Dict[str, Any]
] = {}  # case_id -> {"stage", "images", "error", "ts"}
FORGE_POSTS: Dict[str, List[Dict[str, Any]]] = {}  # case_id -> 帖子流
_CASE_LOCKS: Dict[str, threading.Lock] = {}  # case_id -> json 文件读写锁
IMG_STYLE = "唐代工笔重彩风格，绢本设色，赭石与石青为主色调，细腻的线描，古典构图，无文字。若主题非中国唐代则改用该时代/地域的古典绘画风格"


def _env_cfg() -> Dict[str, str]:
    cfg = {}
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def _parse_json(raw: str) -> Dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _sync_llm(system: str, user: str, user_id: str = "default") -> Dict[str, Any]:
    # court 是用户可玩的 demo：消耗记入对应用户额度（由路由 JWT 上下文确定归属）
    response = get_llm(
        current_usage().user_id if user_id == "default" else user_id, scene="court"
    ).think(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    return _parse_json(response.content)


def _sync_llm_race(system: str, user: str, user_id: str = "default") -> Dict[str, Any]:
    """双发竞速：同一请求并行发两份，先成功解析者胜——对冲 LLM 延迟波动（长尾等待的根因）。"""
    result: Dict[str, Any] = {}
    err: list = []
    done = threading.Event()

    def _one():
        try:
            data = _sync_llm(system, user, user_id)
            if not result:
                result.update(data)
                done.set()
        except Exception as e:  # pylint: disable=broad-except
            err.append(e)

    t1 = UsageThread(target=_one, daemon=True)
    t2 = UsageThread(target=_one, daemon=True)
    t1.start()
    t2.start()
    done.wait(timeout=240)
    if result:
        return result
    raise err[0] if err else TimeoutError("llm race timeout")


async def _async_llm(
    system: str, user: str, user_id: str = "default"
) -> Dict[str, Any]:
    response = await get_llm(
        current_usage().user_id if user_id == "default" else user_id, scene="court"
    ).async_think(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    return _parse_json(response.content)


# ---------------- 阶段 1a'：关键设定反问（Synthetic World 式·3 问钉死歧义） ----------------
_disambiguate_system = """你是历史社会模拟导演。用户给了你一个"如果/事件"。你的任务是在开卷前钉死 3 个最容易产生歧义的关键设定，让世界跑不偏。
要求：
1. 问 3 个问题，覆盖：故事依托的"底色/版本"、事件的关键变量如何生效、世界的核心张力焦点
2. 每问给 3-4 个选项（必须包含"自定义设定"作为最后一个选项）
3. 在每问的 4 个选项中标记 1 个"推荐"（index）
4. 问题语言精炼（≤28字），选项语言精炼（≤24字）
5. 不要直接生成世界，只是反问
输出【只能是 JSON】：
{
  "questions": [
    {
      "q": "问题",
      "opts": ["选项A", "选项B", "选项C", "自定义设定"],
      "recommended": 0
    }
  ] (恰好 3 个)
}"""


async def disambiguate(topic: str, user_id: str = "default") -> Dict[str, Any]:
    """开卷前：生成 3 个关键设定反问（含推荐选项），前端展示给用户 10s 自动采用。"""
    return await _async_llm(_disambiguate_system, f"用户的世界想法：{topic}", user_id)


# ---------------- 阶段 1a：极小首屏（快，~8s） ----------------
_stage1a_system = """你是历史社会模拟导演。根据事件生成"开张卡"。宁可少不可慢：输出必须极炼。
输出【只能是 JSON】：
{
  "title": "案名（≤8字）",
  "year": "年代表述（≤16字）",
  "dossier": "一句话卷宗（≤50字，抛出争议问题）",
  "hook": "贯穿全程的悬念问句（≤24字）",
  "outcome": "真实结局一句话（≤40字）",
  "roles": [
    {"id": "英文拼音", "name": "姓名", "title": "身份（≤10字）",
     "brief": "一句话人设（≤20字）", "temper": "脾气与立场关键词（≤14字，如：傲慢·自辩·甩锅）"}
  ] (4人，立场冲突最强)
}"""


async def forge_stage1a(topic: str, user_id: str = "default") -> Dict[str, Any]:
    return await _async_llm(_stage1a_system, f"历史事件/故事：{topic}", user_id)


# ---------------- 时间线（幕一，并行轻任务） ----------------
_timeline_system = """你是史官。根据事件输出真实历史时间线。必须符合史实。
输出【只能是 JSON】：
{"timeline": [{"t": "时间点（≤12字）", "e": "真实发生的事（≤26字）"}] (按时间顺序5条)}"""


# ---------------- 阶段 1b：完整人设（并行） ----------------
_opening_system = """你是历史法庭编剧。基于案件人物生成圆桌开场对质（快出，精炼）。人人只说对自己有利的真话。
输出【只能是 JSON】：
{
  "opening_script": [{"role": "id", "line": "开场对质台词（≤50字）"}] (6-8条，互相攻击),
  "suggested_questions": ["狠质询×4"]
}"""

_roles_full_system = """你是历史法庭编剧。给已有人物补全"对质档案"。人人只说对自己有利的真话（不撒谎但有立场）。
输出【只能是 JSON】：
{
  "roles_full": [
    {"id": "同上", "persona": "人设（性格+动机+说话特点，80字内）", "speech_style": "语言风格（20字内）",
     "knows": ["事实1"], "hides": ["藏着的事"],
     "break_conditions": ["被问什么才破防"], "break_line": "破防吐真台词（≤60字）",
     "stance_bias": "立场偏移方式（30字内）"}
  ],
  "physical_evidence": {"id": "ev", "name": "物证名", "desc": "内容（含戳破口供的细节）", "unlock_hint": "一句提示"},
  "verdict_reference": "史书/史实对照（80字内）"
}"""


# ---------------- 阶段 2：剧本（并行；不依赖1b） ----------------
_stage2a_system = """你是历史教育剧本编剧。基于案件，生成"实录"部分（快出，精炼）。
输出【只能是 JSON】：
{
  "prologue": ["背景旁白1", "背景旁白2", "背景旁白3"] (每句≤35字),
  "frames": [{"text": "官方记载六帧之一（≤40字）", "ip": "该帧画面描述（25字内，人物+场景+动作）"}] (共6帧，按时间顺序),
  "quiz": [{"q": "选择题", "opts": ["A", "B", "C"], "a": 正确index}] (3题：时间线/人物/因果各一)
}"""

_mode2_meta_system = """你是历史教育剧本编剧。基于案件与人物，生成"代入"角色卡的元信息（不含决策，快出）。
输出【只能是 JSON】：
{
  "mode2_meta": [
    {"key": "pinyin", "name": "角色名", "tag": "主角 · 执棋者" 或 "小人物 · 棋子", "sub": "一句身份钩子",
     "desc": "身份卡描述（80字内，含一个专属线索或秘密）",
     "role_desc": "给结局推演用的角色说明（40字内）"}
  ] (3个角色：2个主角+1个小人物)
}"""

_mode2_detail_system = """你是历史教育剧本编剧。基于给定角色的身份卡，生成他的 3 个决策点（按事件时间顺序）。
每个决策点必须带剧情：先 1-2 条其他人物对该角色说的话（对白要推进冲突，像戏），再出决策。
输出【只能是 JSON】：
{
  "decisions": [
    {"narr": "情境旁白（≤70字）",
     "dialog": [{"r": "说话人角色id", "line": "对白（≤40字，有情绪有冲突）"}] (1-2条),
     "q": "决策问句",
     "opts": [{"t": "选项（≤20字）", "s": "副标题（≤10字）", "react": "选择的即时后果（≤70字）"}] (2项)}
  ] (3个决策点)
}"""

_rashomon_system = """你是历史教育剧本编剧。基于案件与人物，生成"罗生门"视角记忆。
输出【只能是 JSON】：
{
  "rashomon": [
    {"title": "罗生门之一", "sub": "『某个关键瞬间』", "lines": [
      {"r": "角色id", "who": "姓名+记得", "text": "该角色视角的记忆（≤70字，带立场）"}] (3条)}
  ] (共2组，选两个最富争议的瞬间)
}"""


# ---------------- 阶段 3：推演"如果"（并行；不依赖1b/2） ----------------
_stage3_system = """你是历史推演大师。基于案件，设计"如果历史不是这样"的反事实岔口。
要求：岔口站在历史的关键决策时刻，改一个变量，后果推演要合理（蝴蝶效应，但符合时代逻辑与人性格局）。
输出【只能是 JSON】：
{
  "what_ifs": [
    {
      "title": "岔口名（≤14字，如：如果关羽没放走曹操）",
      "pivot": "改动的变量与时刻（≤40字）",
      "roles_desc": "推演用的角色说明（≤50字，含该岔口下用户的身份处境）",
      "choices": ["抉择A（≤16字）", "抉择B（≤16字）", "抉择C（≤16字）"]
    }
  ] (2个岔口：一个军事/政治向，一个人心/性格向)
}"""


# ---------------- 岔口抉择 · 众人反应（推演第二幕） ----------------
_react_system = """你是历史群像导演。玩家在历史岔口做出了一个改写历史的抉择，在场众人当庭炸锅。
规则：每条反应必须符合该角色的脾气与立场——或支持、或反对、或哀叹、或窃喜、或已开始盘算下一步。
输出【只能是 JSON】：
{"reactions": [{"role": "角色id", "line": "反应台词（≤40字，口语化，有情绪）"}] (3-4条，覆盖立场冲突最强的人)}"""


async def whatif_reactions(
    case_id: str,
    title: str,
    pivot: str,
    choice: str,
    user_id: str = "default",
) -> List[Dict[str, Any]]:
    """推演第二幕：众人对你抉择的当庭反应。"""
    try:
        case = json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    roles_desc = "；".join(
        f"{r['id']}={r['name']}（{r.get('temper', '')}）" for r in case.get("roles", [])
    )
    data = await _async_llm(
        _react_system,
        f"案件：{case['title']}（{case.get('dossier', '')}）\n人物：{roles_desc}\n\n"
        f"历史岔口：{title}——{pivot}\n玩家（史官）的抉择：{choice}\n\n请生成众人的当庭反应。",
        user_id,
    )
    out = []
    for rc in data.get("reactions", [])[:4]:
        role = next(
            (r for r in case.get("roles", []) if r["id"] == rc.get("role")), None
        )
        if role:
            out.append(
                {
                    "role": role["id"],
                    "name": role["name"],
                    "temper": role.get("temper", ""),
                    "line": rc.get("line", ""),
                }
            )
    return out


# ---------------- 帖子·史实对照卡（学习层：围观 → 用史实校验立场） ----------------
_learn_system = """你是史学教官。学生（史官）在围观一场历史当事人的社区吵架，他点开了某条帖子的"学"。
请对这条帖子做史实校验与知识提炼。要求：
- fact 必须是该角色立场背后的真实史实（若帖子本身是虚构演绎，指出"演绎"并给出对应的真实史实背景）
- verdict 三选一："符合史实" / "立场修饰"（没说谎但只挑了对自己有利的） / "与史实有出入"
- knowledge 是这张卡要教的核心知识点（一个具体的历史知识点，不是泛泛而谈）
输出【只能是 JSON】：
{
  "claim": "该帖的说法一句话概括",
  "fact": "正史/可靠史料的记载（≤80字）",
  "verdict": "符合史实|立场修饰|与史实有出入",
  "knowledge": "核心知识点（≤40字）",
  "note": "一句点评，帮学生看穿立场（≤30字）"
}"""


async def learn_card(
    case_id: str,
    role_name: str,
    post_text: str,
    user_id: str = "default",
) -> Dict[str, Any]:
    """某条帖子的史实对照卡（学习层）。"""
    try:
        case = json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    data = await _async_llm(
        _learn_system,
        f"案件：{case['title']}（{case.get('year', '')}）\n发言人：{role_name}\n帖子内容：{post_text}",
        user_id,
    )
    return data


# ---------------- 社区帖引擎 ----------------
_posts_system = """你是"活的历史社会"导演：一群当事人（各有脾气与立场）在社区里发帖、对喷、站队、过日子。
规则：
1. 每条帖子必须符合该角色的脾气与立场——只说对自己有利的真话，会 @某人 反驳或阴阳
2. 口语化、有梗、有火气，但内容紧扣案件事实
3. 每批恰好 4 条（短输出快返回）；至少一组互相反驳或接话；允许有人跑题过日子，世界要活；每条务必精炼（≤50字），不要长篇
4. 若有"陌生人的介入帖"：角色们自行决定如何对待——可能炸锅、可能无视、可能借题发挥（他们不一定听）
5. 每批恰好 1-2 条帖子包含"可质询的破绽"（立场漏洞、避重就轻、与常识/史实矛盾的说法），
   这些帖子给 hook 字段（疑点提示，≤18字，如"他为何不提当夜的记录？"），其余帖子 hook 为 null
输出【只能是 JSON】：
{"posts": [{"role": "角色id", "text": "帖子（≤60字，可含@某人）", "reply_to": null 或 所回复帖子的序号(1-based), "hook": null 或 "疑点提示"}]}"""


async def forge_posts(
    case_id: str,
    message: Optional[str] = None,
    n_hint: int = 4,
    user_id: str = "default",
) -> List[Dict[str, Any]]:
    """生成一批社区动态；message 非空 = 用户推剧情。"""
    try:
        case = json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    roles_desc = "；".join(
        f"{r['id']} {r['name']}（脾气：{r.get('temper', '')}，立场：{r.get('brief', '')}）"
        for r in case.get("roles", [])
    )
    history = FORGE_POSTS.get(case_id, [])
    recent = history[-8:]
    hist_text = (
        "\n".join(f"{i + 1}. {p['name']}: {p['text']}" for i, p in enumerate(recent))
        or "（社区刚开张）"
    )
    user_part = (
        f'\n\n一位陌生人刚刚发了帖："{message}"\n角色们会怎么反应？'
        if message
        else "\n\n请让剧情自然向前推一步。"
    )
    data = await _async_llm(
        _posts_system,
        f"案件：{case['title']}（{case.get('year', '')}）。{case.get('dossier', '')}\n人物：{roles_desc}\n\n已有动态（编号供回复引用）：\n{hist_text}{user_part}",
        user_id,
    )
    base = len(history)
    new_posts = []
    for i, p in enumerate(data.get("posts", [])[:n_hint]):
        role = next(
            (r for r in case.get("roles", []) if r["id"] == p.get("role")), None
        )
        if not role:
            continue
        new_posts.append(
            {
                "id": base + i,
                "role": role["id"],
                "name": role["name"],
                "temper": role.get("temper", ""),
                "text": p.get("text", ""),
                "reply_to": p.get("reply_to"),
                "hook": p.get("hook") or None,
            }
        )
    history.extend(new_posts)
    FORGE_POSTS[case_id] = history
    return new_posts


# ---------------- 图片 ----------------
def _gen_one_image(case_id: str, key: str, desc: str, size: str = "1664*928") -> bool:
    cfg = _env_cfg()
    api_key = cfg.get("IMG_API_KEY")
    if not api_key or not desc:
        return False
    out_path = ASSET_DIR / f"{case_id}_{key}.jpg"
    if out_path.exists():
        return True
    base_url = cfg.get(
        "IMG_BASE_URL",
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
    )
    model = cfg.get("IMG_MODEL", "qwen-image-2.0")
    before_raw("image", model=model, provider="qwen")
    try:
        payload = {
            "model": model,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"text": f"{desc}。{IMG_STYLE}"}]}
                ]
            },
            "parameters": {"size": size, "prompt_extend": True, "watermark": False},
        }
        r = requests.post(
            base_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=180,
        )
        if r.status_code != 200:
            return False
        content = r.json()["output"]["choices"][0]["message"]["content"]
        url = next(
            (i.get("image") for i in content if isinstance(i, dict) and i.get("image")),
            None,
        )
        if not url:
            return False
        record_raw("image", model=model, provider="qwen")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=120).read()
        # 压缩：qwen 原图 ~2.5MB，浏览器加载慢/卡——缩到 900px 宽 + q78 约 200KB（快 10 倍）
        try:
            import io as _io
            from PIL import Image as _PILImage

            img = _PILImage.open(_io.BytesIO(data)).convert("RGB")
            if img.width > 900:
                h = int(img.height * 900 / img.width)
                img = img.resize((900, h), _PILImage.LANCZOS)
            buf = _io.BytesIO()
            img.save(buf, format="JPEG", quality=78, optimize=True)
            data = buf.getvalue()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("forge 图片压缩失败(用原图) %s/%s: %s", case_id, key, exc)
        out_path.write_bytes(data)
        return True
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("forge 生图失败 %s/%s: %s", case_id, key, e)
        return False


def _bump_stage(case_id: str, stage: float):
    """并行任务完成时推进 stage（只升不降）。"""
    task = FORGE_TASKS.get(case_id)
    if task and stage > task.get("stage", 0):
        task["stage"] = stage


def _update_case(case_id: str, updater) -> Dict[str, Any]:
    """加锁 read-modify-write 案件 JSON（多线程安全）。"""
    lock = _CASE_LOCKS.setdefault(case_id, threading.Lock())
    path = CASES_DIR / f"{case_id}.json"
    with lock:
        case = json.loads(path.read_text(encoding="utf-8"))
        updater(case)
        path.write_text(
            json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return case


# ---------------- 并行线程 ----------------
def _thread_cover(case_id: str, topic: str, title: str):
    ok = _gen_one_image(
        case_id, "cover", f"{topic}：{title}，全景场景，人物群像，时代氛围浓厚"
    )
    if ok:
        FORGE_TASKS[case_id]["images"].append("cover")


def _thread_timeline(case_id: str):
    try:
        case = json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
        data = _sync_llm(
            _timeline_system, f"事件：{case.get('title', '')}（{case.get('year', '')}）"
        )
        _update_case(
            case_id, lambda c: c.update({"timeline": data.get("timeline", [])})
        )
        logger.info(
            "forge %s 时间线完成 %.1fs",
            case_id,
            time.time() - FORGE_TASKS[case_id]["ts"],
        )
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("forge 时间线失败: %s", e)


def _thread_1b(case_id: str):
    """1b 两步：①开场对质快出（圆桌早开）②人设详情后台补齐（质询用）。"""
    try:
        case = json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
        roles_desc = "；".join(
            f"{r['id']}={r['name']}（{r.get('title', '')}，脾气：{r.get('temper', '')}）"
            for r in case.get("roles", [])
        )

        # ① 开场对质（小输出，圆桌即可开）
        opening = _sync_llm_race(
            _opening_system,
            f"案件：{case['title']}（{case.get('dossier', '')}）\n人物：{roles_desc}",
        )
        _update_case(
            case_id,
            lambda c: c.update(
                {
                    "opening_script": opening.get("opening_script", []),
                    "suggested_questions": opening.get("suggested_questions", []),
                }
            ),
        )
        _bump_stage(case_id, 1.5)
        logger.info(
            "forge %s 圆桌开场就绪 %.1fs",
            case_id,
            time.time() - FORGE_TASKS[case_id]["ts"],
        )

        # ② 人设详情（质询/破防用）后台补
        full = _sync_llm_race(
            _roles_full_system,
            f"案件：{case['title']}（{case.get('dossier', '')}）\n人物：{roles_desc}",
        )

        def _upd(c):
            for rf in full.get("roles_full", []):
                role = next((r for r in c["roles"] if r["id"] == rf.get("id")), None)
                if role:
                    role.update({k: v for k, v in rf.items() if k != "id"})
            if full.get("verdict_reference"):
                c["verdict_reference"] = full["verdict_reference"]
            if full.get("physical_evidence"):
                c["physical_evidence"] = full["physical_evidence"]

        _update_case(case_id, _upd)
        logger.info(
            "forge %s 人设详情完成 %.1fs",
            case_id,
            time.time() - FORGE_TASKS[case_id]["ts"],
        )
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("forge 人设失败: %s", e)


def _gen_frame_images(case_id: str, frames: list):
    """六帧配图：f1-f6 并行（信号量限 4 避开限流），失败重试，完成即 bump 3。"""
    sem = threading.Semaphore(4)

    def _one(i, desc):
        if not desc:
            return
        with sem:
            ok = _gen_one_image(case_id, f"f{i}", desc, size="1328*744")
            for delay in (5, 12):  # 限流/偶发失败：退避重试两次
                if ok:
                    break
                time.sleep(delay)
                ok = _gen_one_image(case_id, f"f{i}", desc, size="1328*744")
            if ok:
                FORGE_TASKS[case_id]["images"].append(f"f{i}")

    threads = [
        UsageThread(target=_one, args=(i + 1, f.get("ip", "")), daemon=True)
        for i, f in enumerate(frames[:6])
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    _bump_stage(case_id, 3)
    logger.info(
        "forge %s 帧图全部就绪 %.1fs", case_id, time.time() - FORGE_TASKS[case_id]["ts"]
    )


def _thread_script_a(case_id: str):
    """2a：实录（frames+quiz）——快，完成后立即开始画 f 图。"""
    try:
        case = json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
        extra = _sync_llm(
            _stage2a_system,
            f"案件：{case['title']}（{case.get('dossier', '')}）",
        )
        _update_case(case_id, lambda c: c.update(extra))
        _bump_stage(case_id, 2.3)
        logger.info(
            "forge %s 实录完成(帧图开画) %.1fs",
            case_id,
            time.time() - FORGE_TASKS[case_id]["ts"],
        )
        _gen_frame_images(case_id, extra.get("frames", []))
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("forge 实录失败: %s", e)


def _thread_mode2(case_id: str):
    """代入两步：①角色卡 meta 快出（用户立即可选人）②三角色决策并行补齐。"""
    try:
        case = json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
        roles_desc = "；".join(
            f"{r['id']}={r['name']}（{r.get('temper', '')}）"
            for r in case.get("roles", [])
        )
        meta = _sync_llm_race(
            _mode2_meta_system,
            f"案件：{case['title']}（{case.get('dossier', '')}）\n角色：{roles_desc}",
        )
        metas = meta.get("mode2_meta", [])
        if not metas:
            raise ValueError("empty mode2_meta")
        _update_case(
            case_id, lambda c: c.update({"mode2_meta": metas, "mode2_roles": metas})
        )
        _bump_stage(case_id, 2.4)
        logger.info(
            "forge %s 代入角色卡(meta)完成·可选人 %.1fs",
            case_id,
            time.time() - FORGE_TASKS[case_id]["ts"],
        )

        # ② 三角色决策并行补齐（谁先到谁先可玩）
        def _detail(idx, m):
            try:
                det = _sync_llm_race(
                    _mode2_detail_system,
                    f"案件：{case['title']}（{case.get('dossier', '')}）\n角色卡：{json.dumps(m, ensure_ascii=False)}",
                )

                def _upd(c):
                    for r in c.get("mode2_roles") or []:
                        if r.get("key") == m.get("key") and not r.get("decisions"):
                            r["decisions"] = det.get("decisions", [])

                _update_case(case_id, _upd)
                logger.info(
                    "forge %s 代入决策[%s]完成 %.1fs",
                    case_id,
                    m.get("name", ""),
                    time.time() - FORGE_TASKS[case_id]["ts"],
                )
            except Exception as e:  # pylint: disable=broad-except
                logger.warning("forge 代入决策[%s]失败: %s", m.get("name", ""), e)

        threads = [
            UsageThread(target=_detail, args=(i, m), daemon=True)
            for i, m in enumerate(metas[:3])
        ]
        for t in threads:
            t.start()
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("forge 代入角色包失败: %s", e)


def _thread_rashomon(case_id: str):
    """罗生门视角记忆（与代入并行）。"""
    try:
        case = json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
        roles_desc = "；".join(f"{r['id']}={r['name']}" for r in case.get("roles", []))
        extra = _sync_llm(
            _rashomon_system,
            f"案件：{case['title']}（{case.get('dossier', '')}）\n角色：{roles_desc}",
        )
        _update_case(case_id, lambda c: c.update(extra))
        _bump_stage(case_id, 2.5)
        logger.info(
            "forge %s 罗生门完成 %.1fs",
            case_id,
            time.time() - FORGE_TASKS[case_id]["ts"],
        )
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("forge 罗生门失败: %s", e)


def _thread_whatif(case_id: str):
    try:
        case = json.loads((CASES_DIR / f"{case_id}.json").read_text(encoding="utf-8"))
        roles_desc = "；".join(f"{r['id']}={r['name']}" for r in case.get("roles", []))
        whatif = _sync_llm(
            _stage3_system,
            f"案件：{case['title']}（{case.get('dossier', '')}）\n真实结局：{case.get('outcome', '')}\n人物：{roles_desc}",
        )
        _update_case(case_id, lambda c: c.update(whatif))
        _bump_stage(case_id, 2.8)
        logger.info(
            "forge %s 推演岔口完成 %.1fs",
            case_id,
            time.time() - FORGE_TASKS[case_id]["ts"],
        )
        # 预生成岔口场景图 w1/w2（用户点开推演时图已就位）
        for i, w in enumerate((whatif.get("what_ifs") or [])[:2]):
            desc = f"{w.get('title', '')}：{w.get('pivot', '')}，历史岔口的关键瞬间画面"
            if _gen_one_image(case_id, f"w{i + 1}", desc, size="1328*744"):
                FORGE_TASKS[case_id]["images"].append(f"w{i + 1}")
        logger.info(
            "forge %s 岔口图预生成完毕 %.1fs",
            case_id,
            time.time() - FORGE_TASKS[case_id]["ts"],
        )
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("forge 推演岔口失败: %s", e)


def _thread_posts_warm(case_id: str):
    """社区预热：首屏返回后连跑两小批帖（各2条，间隔短），进动态时已开张。"""
    try:
        time.sleep(2)
        asyncio.run(forge_posts(case_id))
        logger.info(
            "forge %s 社区首批帖就绪 %.1fs",
            case_id,
            time.time() - FORGE_TASKS[case_id]["ts"],
        )
        time.sleep(6)
        asyncio.run(forge_posts(case_id))
        logger.info(
            "forge %s 社区二批帖就绪 %.1fs",
            case_id,
            time.time() - FORGE_TASKS[case_id]["ts"],
        )
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("forge 社区预热失败: %s", e)


# ---------------- 入口 ----------------
def _slug(topic: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "", topic)[:12] or "case"


def start_forge(topic: str) -> str:
    case_id = "forge_" + _slug(topic) + "_" + uuid.uuid4().hex[:4]
    FORGE_TASKS[case_id] = {"stage": 1, "images": [], "error": "", "ts": time.time()}
    FORGE_POSTS[case_id] = []
    return case_id


def save_case(case_id: str, package: Dict[str, Any]):
    package = dict(package)
    package["case_id"] = case_id
    package.setdefault("roles", [])
    package.setdefault("opening_script", [])
    package.setdefault("suggested_questions", [])
    package.setdefault(
        "physical_evidence", {"id": "ev", "name": "物证", "desc": "", "unlock_hint": ""}
    )
    package.setdefault("verdict_reference", "")
    package.setdefault(
        "poet", {"id": "narrator", "name": "旁白", "role": "终幕叙事者", "prompt": ""}
    )
    path = CASES_DIR / f"{case_id}.json"
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")


def start_background(case_id: str, topic: str, core: Dict[str, Any]):
    """六个任务全并行：总时长 = max(单任务)，而非逐个相加。"""
    UsageThread(
        target=_thread_cover,
        args=(case_id, topic, core.get("title", topic)),
        daemon=True,
    ).start()
    UsageThread(target=_thread_timeline, args=(case_id,), daemon=True).start()
    UsageThread(target=_thread_1b, args=(case_id,), daemon=True).start()
    UsageThread(target=_thread_script_a, args=(case_id,), daemon=True).start()
    UsageThread(target=_thread_mode2, args=(case_id,), daemon=True).start()
    UsageThread(target=_thread_rashomon, args=(case_id,), daemon=True).start()
    UsageThread(target=_thread_whatif, args=(case_id,), daemon=True).start()
    UsageThread(target=_thread_posts_warm, args=(case_id,), daemon=True).start()
