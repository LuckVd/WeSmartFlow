"""
文档路由（上传 + 提取节点 + 节点挂接 + 文件读取）。

本层只负责：
  - 接收 HTTP / form 参数
  - 调用 DocumentService 执行业务
  - 把 Service 抛出的业务异常翻译成 HTTPException

文件读取走两个统一端点：
  - GET /api/documents/{doc_id}/raw           — 主资源
  - GET /api/documents/{doc_id}/asset/{sub}   — 同目录伴生文件
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    BackgroundTasks,
    Body,
)
from fastapi.responses import FileResponse

from models.document import DocumentSchema, DocumentBrief
from services import DocumentService
from services.document_service import (
    DocumentNotFound,
    DocumentNotReady,
    InvalidUpload,
    NodeAlreadyLinked,
    NodeNotFound,
)
from services.document_resolver import (
    AssetPathInvalid,
    DocumentNotFound as ResolverNotFound,
    resolve_asset,
    resolve_main,
)
from utils.web_auth import COOKIE_NAME, get_user_from_request_flexible
from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


# ── MIME / 响应辅助 ──────────────────────────────────────────────────

_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".tex": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
}


def _infer_mime(path: Path) -> str:
    return _MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _file_response(
    abs_path: Path,
    *,
    query_token: str | None = None,
    download_filename: str | None = None,
) -> FileResponse:
    """统一的文件响应：自动推断 MIME，可选写 Cookie / Content-Disposition。"""
    headers: dict[str, str] = {}
    if query_token:
        # iframe / web-view 首次以 ?token= 打开主资源后，子资源请求由 cookie 兜底
        headers["Set-Cookie"] = (
            f"{COOKIE_NAME}={query_token}; Path=/; HttpOnly; SameSite=Lax"
        )
    return FileResponse(
        path=abs_path,
        media_type=_infer_mime(abs_path),
        filename=download_filename,
        headers=headers,
    )


# ── 文档列表 / 详情 / 上传 / 删除 / 节点挂接 ─────────────────────────


@router.get("", response_model=list[DocumentBrief])
def list_documents(user_id: str = Depends(get_current_user)):
    return DocumentService().list_documents(user_id)


def _extract_guide_json(text: str) -> dict:
    """从 LLM 返回文本中健壮地抽取学习建议 JSON。

    容错：markdown 代码块包裹、单引号 key/value、尾逗号、字段缺引号。
    全部失败时返回 {}。
    """
    import json as _json
    import re as _re

    # 1) 剥 markdown 代码块
    m_code = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, _re.DOTALL)
    if m_code:
        text = m_code.group(1)
    # 2) 直接找最外层大括号
    m = _re.search(r"\{.*\}", text, _re.DOTALL)
    if not m:
        return {}
    raw = m.group(0)
    # 3) 依次尝试：原样 / 单引号转双引号 / 去尾逗号
    candidates = [raw]
    candidates.append(raw.replace("'", '"'))
    candidates.append(_re.sub(r",\s*([}\]])", r"\1", raw))
    candidates.append(_re.sub(r",\s*([}\]])", r"\1", raw.replace("'", '"')))
    for cand in candidates:
        try:
            obj = _json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


@router.get("/{doc_id}/study-guide")
async def get_study_guide(doc_id: str, user_id: str = Depends(get_current_user)):
    """返回已生成的学习建议（issue #1 系列：上传后先告诉用户怎么学）。"""
    try:
        doc = DocumentService()._assert_doc_owner(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="文档不存在") from None
    guide_path = Path(doc.get_file_path()).parent / "study_guide.json"
    if not guide_path.exists():
        return {"generated": False}
    import json as _json

    return {"generated": True, "guide": _json.loads(guide_path.read_text("utf-8"))}


@router.post("/{doc_id}/study-guide")
async def generate_study_guide(doc_id: str, user_id: str = Depends(get_current_user)):
    """生成学习建议：适合什么基础 / 先看哪几节 / 哪里难（一次性 LLM 调用）。"""
    try:
        doc = DocumentService()._assert_doc_owner(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="文档不存在") from None
    guide_path = Path(doc.get_file_path()).parent / "study_guide.json"
    if guide_path.exists():
        import json as _json

        return {"generated": True, "guide": _json.loads(guide_path.read_text("utf-8"))}

    # 读文档内容前 6000 字（够 LLM 判断基础/顺序/难点）
    try:
        content = DocumentService().get_content(user_id, doc_id).get("content", "")
    except Exception as e:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=f"文档内容读取失败: {e}") from e
    if not content or len(content.strip()) < 50:
        raise HTTPException(status_code=400, detail="文档内容为空，无法生成学习建议")

    from services.llm_factory import get_llm

    # 学习规划是用户触发的操作：走用户额度（拦截 + 记账）
    llm = get_llm(user_id, scene="chat")
    prompt = (
        "根据以下资料内容，输出一份简短的学习建议，"
        "帮助用户决定怎么学这份材料。只能是 JSON：\n"
        '{"basics": "适合什么基础的读者（50字内）", '
        '"order": "建议的阅读/学习顺序（80字内）", '
        '"difficulties": "可能的难点提示（80字内）", '
        '"estimated": "预计学习时长（20字内）"}\n\n'
        f"资料内容：\n{content[:6000]}"
    )
    try:
        resp = llm.think(
            messages=[
                {"role": "system", "content": "你是学习规划助手，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ]
        )
        text = getattr(resp, "content", "") or ""
        guide = _extract_guide_json(text)
    except Exception as e:  # pylint: disable=broad-except
        raise HTTPException(status_code=502, detail=f"学习建议生成失败: {e}") from e

    if not guide.get("basics"):
        raise HTTPException(
            status_code=502, detail="学习建议生成失败：模型未返回有效内容"
        )

    import json as _json

    guide_path.write_text(_json.dumps(guide, ensure_ascii=False, indent=2), "utf-8")
    return {"generated": True, "guide": guide}


@router.get("/{doc_id}", response_model=DocumentSchema)
def get_document(doc_id: str, user_id: str = Depends(get_current_user)):
    try:
        return DocumentService().get_document(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")


@router.post("/upload", response_model=DocumentSchema, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """上传文档（单文件），后台自动触发提取。"""
    content = await file.read()
    try:
        return await DocumentService().upload(
            user_id=user_id,
            filename=file.filename,
            content=content,
            background_tasks=background_tasks,
        )
    except InvalidUpload as e:
        raise HTTPException(400, str(e))


@router.post("/{doc_id}/extract")
async def trigger_extract(
    doc_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
):
    """手动触发（重新）提取。"""
    try:
        return DocumentService().trigger_extract(user_id, doc_id, background_tasks)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")


@router.get("/{doc_id}/content")
async def get_document_content(doc_id: str, user_id: str = Depends(get_current_user)):
    """获取文档内容（支持分段获取）。"""
    try:
        return DocumentService().get_content(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except DocumentNotReady:
        raise HTTPException(400, "文档尚未处理完成")


# ── 文件读取（核心两个接口） ──────────────────────────────────────────


@router.api_route("/{doc_id}/raw", methods=["GET", "HEAD"])
async def get_document_raw(doc_id: str, request: Request):
    """读取文档主资源。

    URL 参数：
      - ``token`` — 可选；为 iframe / web-view 兜底鉴权。命中后会写同域 cookie。
      - ``download=1`` — 强制 ``Content-Disposition: attachment``，触发浏览器下载。
    """
    user_id, query_token = get_user_from_request_flexible(request)
    try:
        rf = resolve_main(doc_id, user_id)
    except ResolverNotFound:
        raise HTTPException(404, "文件不存在")

    download = request.query_params.get("download") in {"1", "true", "yes"}
    return _file_response(
        rf.abs_path,
        query_token=query_token,
        download_filename=rf.doc.file_name if download else None,
    )


@router.api_route("/{doc_id}/asset/{sub_path:path}", methods=["GET", "HEAD"])
async def get_document_asset(doc_id: str, sub_path: str, request: Request):
    """读取文档主资源同目录下的伴生文件。

    例如 HTML 卡片 ``card.html`` 内嵌图片：
      ``/api/documents/{doc_id}/asset/images/cover.png``

    沉浸式课程章节音频帧：
      ``/api/documents/{audio_doc_id}/asset/frame_001.wav``
    """
    user_id, query_token = get_user_from_request_flexible(request)
    try:
        rf = resolve_asset(doc_id, sub_path, user_id)
    except (ResolverNotFound, AssetPathInvalid):
        raise HTTPException(404, "文件不存在")
    return _file_response(rf.abs_path, query_token=query_token)


# ── 删除 / 节点挂接 ──────────────────────────────────────────────────


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, user_id: str = Depends(get_current_user)):
    try:
        DocumentService().delete(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/{doc_id}/nodes")
async def get_document_nodes(doc_id: str, user_id: str = Depends(get_current_user)):
    """获取文档关联的知识节点。"""
    try:
        return DocumentService().list_document_nodes(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")


@router.get("/nodes/{node_id}/documents")
async def get_node_documents(node_id: str, user_id: str = Depends(get_current_user)):
    """获取知识节点关联的文档。"""
    try:
        return DocumentService().list_node_documents(user_id, node_id)
    except NodeNotFound:
        raise HTTPException(404, "知识节点不存在")


@router.get("/{doc_id}/summary")
async def get_document_summary(doc_id: str, user_id: str = Depends(get_current_user)):
    """获取文档摘要信息。"""
    try:
        return DocumentService().get_summary(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except DocumentNotReady:
        raise HTTPException(400, "文档尚未处理完成")


@router.post("/{doc_id}/add_node")
async def add_node_to_document(
    doc_id: str,
    node_id: str = Body(..., embed=True),
    user_id: str = Depends(get_current_user),
):
    """为文档手动添加现有节点。"""
    try:
        return DocumentService().add_node(user_id, doc_id, node_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except NodeNotFound:
        raise HTTPException(404, "节点不存在")
    except NodeAlreadyLinked:
        raise HTTPException(400, "节点已关联到该文档")
