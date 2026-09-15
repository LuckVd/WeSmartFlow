"""历史法庭 demo 服务。

核心思路：
- 案件包（JSON）定义人物画像、秘密档案、破防条件、开场剧本
- 开场吵架走预编排剧本（稳定）；质询起走 LLM 实时生成（鲜活）
- Director prompt：LLM 扮演"庭审导演"，根据质询决定谁接话、是否破防，
  返回结构化 JSON
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.llm_factory import get_llm
from services.external_usage import current_usage, before_raw, record_raw

_CASES_DIR = Path(__file__).parent / "cases"

_director_system = """你是"历史法庭"的庭审导演，负责编排一场唐代庭审戏剧。

规则：
1. 每次史官（用户）发问后，你决定由哪位角色回应（也可以让另一人插嘴抢答）。
2. 每个角色【只说真话，但只说对自己有利的真话】——立场偏移，绝不撒谎。
3. 角色说话必须符合各自 speech_style，文白夹杂，每次不超过 80 字。
4. 秘密档案（hides）中的内容：除非触发 break_conditions（或证据已在庭上出示），
   否则绝不主动承认，但可以露出破绽、打太极、顾左右而言他。
5. 一旦破防条件被触发，角色说出 break_line（可略微改写，意思一致）。
6. 你的输出【只能是 JSON】：
   {
     "speaker": "角色id（xuanzong/chenxuanli/gaolishi/liheng）",
     "line": "角色台词（文白夹杂，<=80字）",
     "note": "白话小注（<=30字，给现代学生看的翻译）",
     "broke_defense": true/false（本次是否触发破防）,
     "evidence_hint": "若台词含可存证的关键事实，给出证据卡摘要（<=20字），否则为空字符串"
   }"""


def load_case(case_id: str = "mawei") -> Dict[str, Any]:
    path = _CASES_DIR / f"{case_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"案件不存在: {case_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _roles_digest(case: Dict[str, Any], reveal_evidence: bool) -> str:
    lines = []
    for r in case["roles"]:
        lines.append(
            f"## {r.get('name', '?')}（{r.get('id', '?')}）｜{r.get('title', '')}\n"
            f"人设：{r.get('persona') or r.get('brief') or ''}\n"
            f"语言风格：{r.get('speech_style', '')}\n"
            f"知情：{'; '.join(r.get('knows') or [])}\n"
            f"在藏：{'; '.join(r.get('hides') or [])}\n"
            f"立场偏移：{r.get('stance_bias', '')}\n"
            f"破防条件：{'; '.join(r.get('break_conditions') or [])}\n"
            f"破防台词：{r.get('break_line', '')}"
        )
    ev = case.get("physical_evidence")
    if ev:
        status = "已出示" if reveal_evidence else "未出示（其内容严禁被任何角色提及）"
        lines.append(f"## 物证：{ev['name']}（{status}）\n{ev['desc']}")
    return "\n\n".join(lines)


async def interrogate(
    case_id: str,
    question: str,
    transcript: List[Dict[str, str]],
    evidence_shown: bool = False,
    user_id: str = "default",
) -> Dict[str, Any]:
    """史官质询：Director 编排角色回应。"""
    case = load_case(case_id)
    history = "\n".join(
        f"{t.get('name', t.get('role', '?'))}：{t['line']}" for t in transcript[-16:]
    )
    prompt = (
        f"案件：{case['title']}\n\n"
        f"## 角色档案（导演机密）\n{_roles_digest(case, evidence_shown)}\n\n"
        f"## 庭审记录（最近）\n{history or '（庭审刚开始）'}\n\n"
        f"## 物证状态：{'账本已当庭出示，其内容人人可见' if evidence_shown else '账本未出示'}\n\n"
        f"史官发问：「{question}」\n\n"
        "请决定谁回应、如何回应，按系统要求的 JSON 输出。"
    )
    response = await get_llm(
        current_usage().user_id if user_id == "default" else user_id, scene="court"
    ).async_think(
        messages=[
            {"role": "system", "content": _director_system},
            {"role": "user", "content": prompt},
        ]
    )
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        return {
            "speaker": "gaolishi",
            "name": "高力士",
            "line": raw.strip()[:160],
            "note": "（导演走神了，这句由高公公替他说）",
            "broke_defense": False,
            "evidence_hint": "",
        }
    role_map = {r["id"]: r["name"] for r in case["roles"]}
    data["name"] = role_map.get(data.get("speaker", ""), data.get("speaker", "?"))
    return data


_verdict_system = """你是"历史法庭"的谢幕导演。史官刚下达判决，请输出群臣反应。
输出【只能是 JSON】：
{
  "reactions": [
    {"name": "角色名", "line": "其反应台词（<=50字，符合人设）"}
  ],
  "libai_poem": "李白的四句打油诗点评（押韵、狂放、略讽刺）",
  "historian_note": "一句史官结语（<=40字，点出'每个人物都只说了对自己有利的真话'这一课）"
}"""


async def verdict(
    case_id: str,
    responsibility: Optional[Dict[str, int]] = None,
    evidence_used: Optional[List[str]] = None,
    conclusion: str = "",
    user_id: str = "default",
) -> Dict[str, Any]:
    """结案：群反应 + 李白评诗 + 史书对照（支持责任分配或结案陈词两种形式）。"""
    case = load_case(case_id)
    role_map = {r["id"]: r["name"] for r in case["roles"]}
    if conclusion:
        resp_text = f"史官的结案陈论：{conclusion}"
    elif responsibility:
        resp_text = "责任分配：" + "；".join(
            f"{role_map.get(k, k)} {v}%" for k, v in responsibility.items()
        )
    else:
        resp_text = "史官未下结论"
    ev_text = "；".join(evidence_used or []) or "（史官未引用证据）"
    prompt = (
        f"案件：{case['title']}\n{resp_text}\n"
        f"史官引用的证据：{ev_text}\n\n"
        f"真实史书记载（用于对照）：{case['verdict_reference']}\n\n"
        "请生成各角色（被告与证人）对这份判决的当场反应、李白点评诗、史官结语。"
    )
    response = await get_llm(
        current_usage().user_id if user_id == "default" else user_id, scene="court"
    ).async_think(
        messages=[
            {"role": "system", "content": _verdict_system},
            {"role": "user", "content": prompt},
        ]
    )
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        data = {
            "reactions": [],
            "libai_poem": "（李白喝醉了，今日不评）",
            "historian_note": "史笔如铁，且待来者。",
        }
    data["verdict_reference"] = case["verdict_reference"]
    return data


_finale_system = """你是叙事游戏的终幕导演。玩家刚走完一段真实历史改编的故事，请为结局生成各角色的临别赠言。
输出【只能是 JSON】：
{
  "finals": [
    {"name": "角色名", "line": "对这个结局中玩家的临别赠言（<=60字，符合人设：或欣慰、或遗憾、或嘲讽、或祝福）"}
  ],
  "history_note": "一句总评（<=50字）：玩家的选择与真实历史轨迹的对照感悟"
}"""


async def finale(
    case_id: str,
    choices: List[Dict[str, str]],
    ending_title: str,
    user_id: str = "default",
) -> Dict[str, Any]:
    """终幕：各角色对玩家的临别赠言 + 史评。"""
    case = load_case(case_id)
    choices_text = "；".join(
        f"{c.get('id', '?')}→{c.get('choice', '?')}" for c in choices
    )
    prompt = (
        f"故事：{case['title']}（{case['dossier']}）\n"
        f"玩家身份：故事中的年轻当事人。\n"
        f"玩家的选择路径：{choices_text}\n"
        f"玩家达成的结局：《{ending_title}》\n\n"
        f"角色名单：{'、'.join(r['name'] for r in case['roles'])}\n"
        f"真实史实（供对照）：{case['verdict_reference']}\n\n"
        "请生成每个角色对玩家的临别赠言（注意：赠言要体现该角色的立场与性格，"
        "对玩家既不必客气也不必苛责——像人对人说话），以及一句总评。"
    )
    response = await get_llm(
        current_usage().user_id if user_id == "default" else user_id, scene="court"
    ).async_think(
        messages=[
            {"role": "system", "content": _finale_system},
            {"role": "user", "content": prompt},
        ]
    )
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        data = {"finals": [], "history_note": "故事已落幕，星辰仍在运转。"}
    return data


_illustrate_prompt_template = (
    "16至17世纪欧洲铜版画风格插画，棕褐色单色调，细腻的排线阴影，古典构图，无文字无字母。"
    "画面主题：{subject}。{extra}"
)


async def illustrate(prompt: str, user_id: str = "default") -> Dict[str, Any]:
    """实时生成一张插画，返回 base64 data URL。失败返回 ok:false。"""
    import base64
    import requests as _req  # local import to avoid module load order issues

    # Re-read env (live)
    env_path = Path(__file__).resolve().parents[2] / ".env"
    cfg = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    api_key = cfg.get("IMG_API_KEY")
    base_url = cfg.get(
        "IMG_BASE_URL",
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
    )
    model = cfg.get("IMG_MODEL", "qwen-image-2.0")
    before_raw("image", model=model, provider="qwen")
    if not api_key:
        return {"ok": False, "error": "missing IMG_API_KEY"}
    payload = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {"size": "1664*928", "prompt_extend": True, "watermark": False},
    }
    try:
        r = _req.post(
            base_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=180,
        )
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:120]}"}
        content = r.json()["output"]["choices"][0]["message"]["content"]
        url = next(
            (i.get("image") for i in content if isinstance(i, dict) and i.get("image")),
            None,
        )
        if not url:
            return {"ok": False, "error": "no image url in response"}
        record_raw("image", model=model, provider="qwen")
        import urllib.request as _ur

        req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = _ur.urlopen(req, timeout=120).read()
        b64 = base64.b64encode(data).decode("ascii")
        return {"ok": True, "data_url": f"data:image/jpeg;base64,{b64}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


_consequence_system = """你是历史小说家兼史官。玩家在马嵬驿事件中扮演一个无名小人物并做了一系列选择。
请基于真实史实推演此人此后最可能的命运。要求：
- 结局叙述用第二人称（"你"），克制而有重量，像史书里突然为小人物开的一页
- 必须体现"个人选择 vs 历史结构"：他的选择改变了什么、没能改变什么
- 符合唐代历史逻辑（安史之乱、肃宗即位、收复两京等大事件为背景）
输出【只能是 JSON】：
{
  "ending": "命运推演，120-180字，第二人称，跨两到二十年",
  "history_note": "这个人的选择在大历史里改变了什么/没改变什么，50字内",
  "epilogue": "一句收束的金句，20字内"
}"""


async def consequence(
    role_desc: str,
    choices: List[str],
    user_id: str = "default",
) -> Dict[str, Any]:
    """代入模式：根据角色与选择推演历史结局。"""
    choices_text = "；".join(choices) if choices else "（未做选择）"
    prompt = (
        "马嵬驿之变（756年）：安史之乱中玄宗西逃，行至马嵬驿，禁军哗变杀杨国忠、"
        "逼死杨贵妃，随后玄宗入蜀、太子李亨北上灵武即位为肃宗。\n\n"
        f"玩家扮演的角色：{role_desc}\n"
        f"玩家做出的选择：{choices_text}\n\n"
        "请推演这个人物的命运。"
    )
    response = await get_llm(
        current_usage().user_id if user_id == "default" else user_id, scene="court"
    ).async_think(
        messages=[
            {"role": "system", "content": _consequence_system},
            {"role": "user", "content": prompt},
        ]
    )
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return {
            "ending": "后来的事，史书没有记。你活过了那一年，也活过了之后的许多年——只是再没有人问起马嵬驿。",
            "history_note": "个人的选择沉入了大历史的河床。",
            "epilogue": "无名者也有自己的一生。",
        }


_debrief_system = """你是历史教学法专家。一位学生刚以史官身份参与了一场马嵬驿多方对质，
现在请分析他的表现并生成学习总结。
输出【只能是 JSON】：
{
  "what_learned": ["史实层面收获一条", "方法层面收获一条", "视角层面收获一条"],
  "method_note": "针对该生提问方式的一句针对性点评（40字内）",
  "one_liner": "一句压轴金句（20字内）"
}"""


async def debrief(
    questions: List[str],
    verdict_text: str,
    user_id: str = "default",
) -> Dict[str, Any]:
    """圆桌模式：根据学生提问轨迹生成学习总结。"""
    q_text = "\n".join(f"- {q}" for q in questions[:12]) or "（学生主要旁观）"
    prompt = (
        "马嵬驿圆桌：唐玄宗、陈玄礼、高力士、太子李亨四方对质，人人只说对自己有利的真话。\n\n"
        f"该生（史官）的提问记录：\n{q_text}\n\n"
        f"该生的最终判决：{verdict_text}\n\n"
        "请生成学习总结（三条收获分别对应：史实、史料实证方法、立场与视角）。"
    )
    response = await get_llm(
        current_usage().user_id if user_id == "default" else user_id, scene="court"
    ).async_think(
        messages=[
            {"role": "system", "content": _debrief_system},
            {"role": "user", "content": prompt},
        ]
    )
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return {
            "what_learned": [
                "马嵬驿的史实脉络",
                "孤证不立，需交叉印证",
                "每份史料背后都有立场",
            ],
            "method_note": "多问了几句'你是怎么知道的'，已具史官雏形。",
            "one_liner": "读史前，先读写史的人。",
        }
