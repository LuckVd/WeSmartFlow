"""live_science（知识之境）API 适配器，挂在 WeSmartFlow 主后端。

复用 live_science/server.py 的全部能力（零依赖 http.server 版的核心函数），
只把 HTTP 层从 `http.server` 换成 FastAPI，接入主后端的 /api 命名空间。

路由前缀：/api/demo/live-science
"""

from __future__ import annotations

import sys
import threading
import uuid
from pathlib import Path

_LIVE_DIR = Path(__file__).resolve().parent
if str(_LIVE_DIR) not in sys.path:
    sys.path.insert(0, str(_LIVE_DIR))

from fastapi import APIRouter, Response, Depends, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import server  # noqa: E402  # 复用 CFG / call_llm / call_tts* / JOBS / run_generate / ROOT

from services.external_usage import demo_usage, current_usage, UsageThread
from services.credit_quota import CreditsExceeded, assert_available

router = APIRouter(prefix="/api/demo/live-science", tags=["live-science"], dependencies=[Depends(demo_usage("live-science"))])
JOB_OWNERS = {}



class LLMRequest(BaseModel):
    messages: list = Field(min_length=1)


class TTSRequest(BaseModel):
    input: str = Field(min_length=1)
    voice: str = ""
    instruct: str = ""
    speed: float = 1.0


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=1)
    audience: str = "high"


@router.get("/health")
def health():
    return {
        "ok": True,
        "llm": bool(server.CFG["LLM_API_KEY"] and server.CFG["LLM_BASE_URL"] and server.CFG["LLM_MODEL"]),
        "tts": bool(server.CFG["DASHSCOPE_API_KEY"] or server.CFG["TTS_BASE_URL"]),
        "tts_backend": "dashscope" if server.CFG["DASHSCOPE_API_KEY"] else ("openai" if server.CFG["TTS_BASE_URL"] else "browser"),
        "image": bool(server.CFG["IMG_API_KEY"] or server.CFG["DASHSCOPE_API_KEY"]),
        "model": server.CFG["LLM_MODEL"],
    }


@router.get("/chapters")
def chapters():
    import json as _json

    result = []
    ch_dir = server.ROOT / "chapters"
    if ch_dir.is_dir():
        for d in sorted(ch_dir.iterdir()):
            if not d.is_dir() or not (d / "index.html").exists():
                continue
            meta = {"slug": d.name, "title": d.name, "subtitle": "", "cover": "prologue.png"}
            sj = d / "story.js"
            if sj.exists():
                try:
                    txt = sj.read_text(encoding="utf-8")
                    full = _json.loads(
                        txt[txt.index("{", txt.index("=")) : txt.rstrip().rstrip(";").rindex("}") + 1]
                    )
                    m2 = full.get("META") or {}
                    if m2:
                        meta.update(m2)
                except Exception:
                    pass
            assets = d / "assets"
            if assets.is_dir() and not (assets / meta["cover"]).exists():
                imgs = sorted(p.name for p in assets.glob("*.png"))
                if imgs:
                    meta["cover"] = imgs[0]
            meta["badge"] = "AI 生成"
            result.append(meta)
    return {"ok": True, "chapters": result}


@router.post("/llm")
def llm(req: LLMRequest):
    try:
        text = server.call_llm(req.messages)
        return {"ok": True, "text": text}
    except CreditsExceeded:
        raise
    except Exception as e:  # 代理失败统一回 ok:false，前端降级
        return {"ok": False, "error": str(e)}


@router.post("/tts")
def tts(req: TTSRequest):
    try:
        text = (req.input or "")[:600]
        voice = req.voice
        instruct = req.instruct or ""
        if server.CFG["DASHSCOPE_API_KEY"]:
            audio, ctype = server.call_tts_dashscope(voice, text, instruct)
        elif server.CFG["TTS_BASE_URL"]:
            audio, ctype = server.call_tts(voice, text, req.speed)
        else:
            return {"ok": False, "error": "TTS 未配置（.env 缺少 DASHSCOPE_API_KEY 或 TTS_BASE_URL）"}
        return Response(content=audio, media_type=ctype)
    except CreditsExceeded:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/generate")
def generate(req: GenerateRequest):
    try:
        topic = (req.topic or "").strip()
        audience = (req.audience or "high").strip()
        if not topic:
            return {"ok": False, "error": "missing topic"}
        if not (server.CFG["LLM_API_KEY"] and server.CFG["LLM_BASE_URL"]):
            return {"ok": False, "error": "LLM 未配置，无法生成"}
        assert_available(current_usage().user_id, platform_key=True)
        job_id = uuid.uuid4().hex[:8]
        JOB_OWNERS[job_id] = current_usage().user_id
        server.JOBS[job_id] = {"stage": "queued", "message": "排队中……"}
        UsageThread(target=server.run_generate, args=(job_id, topic, audience), daemon=True).start()
        return {"ok": True, "job": job_id}
    except CreditsExceeded:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/generate/status")
def generate_status(job: str = ""):
    if JOB_OWNERS.get(job) != current_usage().user_id:
        raise HTTPException(404, "任务不存在")
    return server.JOBS.get(job) or {"stage": "unknown", "message": "任务不存在"}
