"""
系统设置路由
GET  /api/settings               → 返回所有配置项（敏感字段脱敏）
POST /api/settings               → 批量保存配置项
POST /api/settings/test          → 测试当前 LLM 配置是否可用
POST /api/settings/test-tavily   → 测试 Tavily API Key 是否可用
POST /api/settings/test-image    → 测试图像生成 API 是否可用
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database import get_all_settings, set_settings_batch, get_setting
from dependencies import get_current_user
from utils.log_safe import safe_log
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 敏感字段：返回给前端时脱敏
_SENSITIVE_KEYS = {"llm_api_key", "tavily_api_key", "img_api_key"}


def _mask(key: str, value: str) -> str:
    """敏感字段只返回前4位 + *** 或空字符串。"""
    if key not in _SENSITIVE_KEYS or not value:
        return value
    return value[:4] + "***" if len(value) > 4 else "***"


class SettingsSaveRequest(BaseModel):
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    tavily_api_key: str | None = None
    img_api_key: str | None = None
    img_base_url: str | None = None
    img_model: str | None = None


@router.get("/features")
def get_features(user_id: str = Depends(get_current_user)):
    """查询各功能当前是否可用（issue #62/#103）。

    返回示例:
    {"llm": true, "search": false, "image": true, "tts": true}

    判定规则：用户自配 key 或环境变量配置了平台 key 即视为可用；
    未配置的功能前端应禁用入口并标注原因，而不是点击后报错。
    """
    import os

    def _has(user_key_name: str, env_key_name: str) -> bool:
        return bool(get_setting(user_id, user_key_name) or os.getenv(env_key_name, ""))

    return {
        "llm": _has("llm_api_key", "LLM_API_KEY"),
        "search": _has("tavily_api_key", "TAVILY_API_KEY"),
        "image": _has("img_api_key", "IMG_API_KEY"),
    }


@router.get("")
def get_settings(user_id: str = Depends(get_current_user)):
    """返回当前用户的所有配置项，敏感字段脱敏。"""
    raw = get_all_settings(user_id)
    return {k: _mask(k, v) for k, v in raw.items()}


@router.post("")
def save_settings(body: SettingsSaveRequest, user_id: str = Depends(get_current_user)):
    """批量保存当前用户的配置项，None 字段跳过（不覆盖）。"""
    updates: dict[str, str] = {}
    for key, value in body.model_dump().items():
        if value is not None:
            updates[key] = value
    if updates:
        set_settings_batch(user_id, updates)
    return {"ok": True, "updated": list(updates.keys())}


@router.post("/test")
def test_llm(user_id: str = Depends(get_current_user)):
    """测试当前 LLM 配置是否可用（发送一条最小请求）。"""
    try:
        from services.llm_factory import get_llm

        llm = get_llm(user_id, scene="system")
        resp = llm.think(
            [{"role": "user", "content": "reply with the single word: ok"}],
            config={"max_tokens": 10},
        )
        # 检查 finish_reason / is_error，避免把错误内容当成成功回复
        if resp.finish_reason == "error" or getattr(resp, "is_error", False):
            error_msg = (
                resp.metadata.get("error_message", resp.content)
                if resp.metadata
                else resp.content
            )
            return {"ok": False, "error": error_msg}
        return {"ok": True, "reply": resp.content.strip()}
    except Exception as e:  # pylint: disable=broad-except
        logger.exception("LLM 测试异常 (user=%s), error: %s", safe_log(user_id), str(e))
        return {"ok": False, "error": "LLM 测试失败"}


@router.post("/test-image")
def test_image_gen(user_id: str = Depends(get_current_user)):
    """测试图像生成 API 是否可用（真正生成一张图片并返回 base64 供前端展示）。

    走 services/image_factory 工厂，确保测试链路与实际生成链路完全一致
    （额度拦截 + 记账同步生效）。
    """
    try:
        import base64
        import os
        import tempfile
        from pathlib import Path

        from agent_core.tool.imagegen.base import ImageGenError
        from database import get_setting
        from services.image_factory import get_image_gen

        # 前置校验：在调工厂前给出更友好的错误
        base_url = get_setting(user_id, "img_base_url") or os.getenv("IMG_BASE_URL", "")
        api_key = get_setting(user_id, "img_api_key") or os.getenv("IMG_API_KEY", "")
        if not base_url:
            return {"ok": False, "error": "未配置图像生成 Base URL"}
        if not api_key:
            return {"ok": False, "error": "未配置图像生成 API Key"}

        # 工厂产出已带额度检查 hook 的客户端
        client = get_image_gen(user_id, scene="media")
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                image_path = client.generate(
                    prompt="A beautiful sunset over a calm ocean",
                    output_dir=tmp_dir,
                    size="512*512",
                    timeout=120,
                )
            except ImageGenError as e:
                return {"ok": False, "error": str(e)}

            path = Path(image_path)
            if not path.exists():
                return {"ok": False, "error": f"图片文件不存在: {path}"}

            image_b64 = base64.b64encode(path.read_bytes()).decode("utf-8")

        return {
            "ok": True,
            "reply": "图像生成成功，API 配置正确",
            "image": f"data:image/png;base64,{image_b64}",
        }

    except Exception as e:  # pylint: disable=broad-except
        logger.exception(
            "图像生成测试异常 (user=%s), error: %s", safe_log(user_id), str(e)
        )
        return {"ok": False, "error": "图像生成测试失败"}


@router.post("/test-tavily")
def test_tavily(user_id: str = Depends(get_current_user)):
    """测试 Tavily API Key 是否可用（发送一条最小搜索请求）。

    走 services/search_factory 工厂，测试链路与实际搜索链路一致
    （额度拦截 + 记账同步生效）。
    """
    try:
        from agent_core.tool.search.base import SearchError
        from services.search_factory import get_search_client

        # 工厂产出已带额度检查 hook 的客户端
        client = get_search_client(user_id, scene="search")
        try:
            result = client.search("test", max_results=1)
        except SearchError as e:
            return {"ok": False, "error": str(e)}
        return {
            "ok": True,
            "reply": f"连接成功，返回 {len(result.results)} 条结果",
        }
    except Exception as e:  # pylint: disable=broad-except
        logger.exception(
            "Tavily API 测试异常 (user=%s), error: %s", safe_log(user_id), str(e)
        )
        return {"ok": False, "error": "Tavily API 测试失败"}
