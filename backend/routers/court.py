"""历史法庭 demo 路由。

认证：demo 阶段不做 JWT 校验（游客可玩），统一用 default 用户的 LLM 配置。
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from court.service import interrogate as svc_interrogate
from court.service import (
    load_case,
    verdict as svc_verdict,
    finale as svc_finale,
    illustrate as svc_illustrate,
)
from court.service import consequence as svc_consequence, debrief as svc_debrief
import time
from court import forge as forge_mod
from court.tts import synthesize

router = APIRouter(prefix="/api/court", tags=["court"])


class InterrogateRequest(BaseModel):
    case_id: str = "mawei"
    question: str
    transcript: List[Dict[str, Any]] = []
    evidence_shown: bool = False


class VerdictRequest(BaseModel):
    case_id: str = "mawei"
    responsibility: Optional[Dict[str, int]] = None
    conclusion: str = ""
    evidence_used: Optional[List[str]] = None


class FinaleRequest(BaseModel):
    case_id: str = "copernicus"
    choices: List[Dict[str, str]] = []
    ending_title: str = ""


@router.get("/case/{case_id}")
def get_case(case_id: str):
    """返回案件包：卷宗、人物（不含秘密档案）、开场剧本、推荐质询。"""
    case = load_case(case_id)
    public_roles = [
        {
            "id": r["id"],
            "name": r["name"],
            "title": r["title"],
            "portrait": f"/court/{case_id}/{r['id']}.png",
        }
        for r in case["roles"]
    ]
    return {
        "case_id": case["case_id"],
        "title": case["title"],
        "year": case["year"],
        "dossier": case["dossier"],
        "roles": public_roles,
        "physical_evidence": {
            "id": case["physical_evidence"]["id"],
            "name": case["physical_evidence"]["name"],
            "desc": case["physical_evidence"]["desc"],
            "unlock_hint": case["physical_evidence"]["unlock_hint"],
        },
        "opening_script": [
            {"role": t["role"], "line": t["line"]} for t in case["opening_script"]
        ],
        "suggested_questions": case["suggested_questions"],
    }


@router.post("/interrogate")
async def interrogate(req: InterrogateRequest):
    """史官质询：Director 编排角色回应。"""
    return await svc_interrogate(
        case_id=req.case_id,
        question=req.question,
        transcript=req.transcript,
        evidence_shown=req.evidence_shown,
    )


@router.post("/verdict")
async def verdict(req: VerdictRequest):
    """判决：群反应 + 李白评诗 + 史书对照。"""
    return await svc_verdict(
        case_id=req.case_id,
        responsibility=req.responsibility,
        evidence_used=req.evidence_used,
        conclusion=req.conclusion,
    )


@router.post("/finale")
async def finale(req: FinaleRequest):
    """终幕：各角色临别赠言 + 史评（叙事模式）。"""
    return await svc_finale(
        case_id=req.case_id,
        choices=req.choices,
        ending_title=req.ending_title,
    )


class IllustrateRequest(BaseModel):
    prompt: str


class TTSRequest(BaseModel):
    text: str
    voice: str = "n"


class ForgeRequest(BaseModel):
    topic: str


class ConsequenceRequest(BaseModel):
    role_desc: str
    choices: List[str] = []


class DebriefRequest(BaseModel):
    questions: List[str] = []
    verdict_text: str = ""


@router.post("/illustrate")
async def illustrate(req: IllustrateRequest):
    """实时生图（结局插画）。返回 base64 data URL 或 ok:false。"""
    return await svc_illustrate(prompt=req.prompt)


@router.post("/consequence")
async def consequence(req: ConsequenceRequest):
    """代入模式：根据角色与选择推演历史结局。"""
    return await svc_consequence(role_desc=req.role_desc, choices=req.choices)


@router.post("/debrief")
async def debrief(req: DebriefRequest):
    """圆桌模式：根据提问轨迹生成学习总结。"""
    return await svc_debrief(questions=req.questions, verdict_text=req.verdict_text)


@router.post("/tts")
def tts(req: TTSRequest):
    """情感语音合成（CosyVoice）。失败时前端回退浏览器 TTS。"""
    return synthesize(req.text, req.voice)


class PostsRequest(BaseModel):
    message: str = ""


class ReactRequest(BaseModel):
    title: str = ""
    pivot: str = ""
    choice: str = ""


class DisambiguateRequest(BaseModel):
    topic: str = ""


class LearnRequest(BaseModel):
    role_name: str = ""
    post_text: str = ""


@router.post("/forge/{case_id}/learn")
async def forge_learn(case_id: str, req: LearnRequest):
    """帖子史实对照卡：围观 → 用史实校验立场（学习层）。"""
    data = await forge_mod.learn_card(case_id, req.role_name, req.post_text)
    return data


@router.get("/assets/{case_id}/{key}")
def court_asset(case_id: str, key: str):
    """案件插画：统一从后端出图（任何部署形态路径都对，替代静态相对路径）。"""
    import re as _re
    from fastapi.responses import FileResponse

    if not _re.fullmatch(r"[\w\u4e00-\u9fff.-]+", case_id) or not _re.fullmatch(
        r"[\w-]+", key
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="bad path")
    path = forge_mod.ASSET_DIR / f"{case_id}_{key}.jpg"
    if not path.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="image not ready")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/forge/disambiguate")
async def forge_disambiguate(req: DisambiguateRequest):
    """开卷前：3 个关键设定反问（Synthetic World 式·带推荐选项·10s 自动采用）。"""
    if not req.topic.strip():
        return {"error": "empty topic"}
    data = await forge_mod.disambiguate(req.topic.strip())
    return {"questions": data.get("questions", [])}


@router.post("/forge")
async def forge(req: ForgeRequest):
    """命题造案 v2：极小首屏（~8s 同步返回），人设/剧本/图片全部后台并行。"""
    from court.service import load_case

    topic = req.topic.strip()[:60]
    if not topic:
        return {"error": "empty topic"}
    t0 = time.time()
    core = await forge_mod.forge_stage1a(topic)
    print(f"[forge] 阶段1a耗时 {time.time() - t0:.1f}s")
    case_id = forge_mod.start_forge(topic)
    forge_mod.save_case(case_id, core)
    forge_mod.start_background(case_id, topic, core)
    case = load_case(case_id)
    return {
        "case_id": case_id,
        "package": case,
        "stage": forge_mod.FORGE_TASKS[case_id]["stage"],
    }


@router.post("/forge/{case_id}/react")
async def forge_react(case_id: str, req: ReactRequest):
    """推演第二幕：众人对你抉择的当庭反应。"""
    reactions = await forge_mod.whatif_reactions(
        case_id, req.title, req.pivot, req.choice
    )
    return {"reactions": reactions}


@router.post("/forge/{case_id}/posts")
async def forge_posts(case_id: str, req: PostsRequest):
    """社区动态：生成一批帖子；message 非空 = 用户推剧情（角色不一定听）。
    all=全部历史帖（含后台预热的首批），前端首次渲染用。"""
    posts = await forge_mod.forge_posts(case_id, req.message or None)
    all_posts = forge_mod.FORGE_POSTS.get(case_id, [])
    return {"new": posts, "all": all_posts, "all_count": len(all_posts)}


@router.get("/forge/{case_id}/status")
def forge_status(case_id: str):
    """轮询：阶段(2=作剧本 2.5=作画 3=全部就绪 -1=失败) + 已就绪图片 + 最新案件包。"""
    from court.service import load_case

    task = forge_mod.FORGE_TASKS.get(case_id)
    try:
        case = load_case(case_id)
    except FileNotFoundError:
        case = {}
    # 无论内存 task 是否存在，都扫描磁盘已落盘的图（cover/f1-f6/w1-w2…）
    # ——与内存 images 取并集：磁盘有就是真有（防止"内存记了有但磁盘没"
    #  和"磁盘有但内存没记录"两种错位，前者因旧 ASSET_DIR bug，后者因进程重启）
    disk_images = sorted(
        p.name[len(case_id) + 1 : -4]
        for p in forge_mod.ASSET_DIR.glob(f"{case_id}_*.jpg")
    )
    if task is None and case:
        if len(disk_images) >= 4 and case.get("frames"):
            stage = 3
        elif case.get("frames"):
            stage = 2.5
        else:
            stage = 2
        task = {"stage": stage, "images": disk_images, "error": ""}
    task = task or {"stage": 0, "images": [], "error": "unknown case"}
    # 合并：内存 + 磁盘（去重保序）
    merged = list(dict.fromkeys(list(task.get("images", [])) + disk_images))
    task["images"] = merged
    return {
        "stage": task.get("stage"),
        "images": task.get("images", []),
        "error": task.get("error", ""),
        "package": case,
    }
