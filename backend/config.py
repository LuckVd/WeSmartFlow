"""
WeSmartFlow 后端配置
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# 加载仓库根目录的 .env（统一来源，模板见 backend/.env.example）
_root_env = Path(__file__).parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env)


# 项目根目录（支持通过环境变量 ROOT_DIR 配置，默认为 backend/ 的父目录）
ROOT_DIR = Path(os.getenv("ROOT_DIR", str(Path(__file__).parent.parent)))

# 数据目录
DATA_DIR = ROOT_DIR / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
UPLOADS_DIR = DOCUMENTS_DIR / "uploads"
CARDS_DIR = DOCUMENTS_DIR / "cards"
COURSES_DIR = DOCUMENTS_DIR / "courses"
VIZ_DIR = DOCUMENTS_DIR / "viz"
SESSIONS_DIR = DATA_DIR / "sessions"

# OKF 知识库根目录（概念 md 落盘根，由 ingest_okf 同步到 KG）
# 必须锚定到仓库根，避免进程 cwd 漂移导致 md 写到 backend/knowledge/ 这种错误位置。
# 子目录由写回工具按 subject 自行 mkdir，此处不预创建。
KNOWLEDGE_ROOT = Path(os.getenv("KNOWLEDGE_ROOT", str(ROOT_DIR / "knowledge")))

# 默认指向 SimplePlus-BeamerTheme 主题目录
TEX_TEMPLATE_DIR = Path(
    os.getenv("TEX_TEMPLATE_DIR", str(Path(__file__).parent / "SimplePlus-BeamerTheme"))
)

# 日志目录
LOG_DIR = DATA_DIR / "logs"

# SQLite 数据库
DB_PATH = DATA_DIR / "wesmartflow.db"

# JWT 配置
JWT_SECRET = os.getenv("JWT_SECRET", "wesmartflow-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "72"))

# Admin 审核台账号（明文，单人后台用）
# 必须在 .env 配置；未配置则 admin 登录直接 503。
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
# admin token 单独的过期时间（更短）
ADMIN_TOKEN_EXPIRE_HOURS = int(os.getenv("ADMIN_TOKEN_EXPIRE_HOURS", "12"))

# 免费额度配置（每用户总量，使用平台公共 Key 时生效）
# 注意：额度按实际 API 调用次数计数（一次对话可能触发多次 LLM 调用）
# 10¥ ≈ $1.37 预算，按 6:3:1 分配
FREE_LLM_TOTAL = int(os.getenv("FREE_LLM_TOTAL", "100"))  # LLM 调用总次数
FREE_SEARCH_TOTAL = int(os.getenv("FREE_SEARCH_TOTAL", "30"))  # 搜索总次数
FREE_IMAGE_TOTAL = int(os.getenv("FREE_IMAGE_TOTAL", "15"))  # 图片生成总次数

# SMTP 邮件配置（用于邮箱验证码登录）
SMTP_HOST = os.getenv("SMTP_HOST", "")  # SMTP 服务器地址，如 smtp.qq.com
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # SMTP 端口，SSL 通常为 465
SMTP_USER = os.getenv("SMTP_USER", "")  # 发件邮箱地址
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # SMTP 授权码（非邮箱密码）
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "WeSmartFlow")  # 发件人显示名称

# 微信小程序配置（扫码登录）
WECHAT_MP_APPID = os.getenv("WECHAT_MP_APPID", "")  # 小程序 AppID
WECHAT_MP_SECRET = os.getenv("WECHAT_MP_SECRET", "")  # 小程序 AppSecret

# ── weclaw 微信通道（多租户：每个用户扫码绑定自己的 bot）──────────────
# 接收消息只能靠 clawbridge 长轮询（无 webhook）；本项目用 async httpx 协程池实现，
# 每个已启用的 bot 一个长轮询协程（≈ 一条 idle 长连接），由 ChannelManager 统一调度。
WECLAW_ENABLED = os.getenv("WECLAW_ENABLED", "false").lower() in {"1", "true", "yes"}
WECLAW_BASE_URL = os.getenv("WECLAW_BASE_URL", "https://clawbridge.weixin.qq.com")
WECLAW_CDN_BASE_URL = os.getenv(
    "WECLAW_CDN_BASE_URL", "https://novac2c.cdn.weixin.qq.com/c2c"
)
WECLAW_LONG_POLL_TIMEOUT_MS = int(os.getenv("WECLAW_LONG_POLL_TIMEOUT_MS", "35000"))
# 对外可访问的基础 URL，用于拼卡片 / PDF 链接（微信 webview 打开），末尾不带斜杠。
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
# 卡片渲染成图片（Playwright 无头 Chromium）：html/quiz/viz 卡片截图后作为图片发到微信。
WECLAW_RENDER_CARDS = os.getenv("WECLAW_RENDER_CARDS", "true").lower() in {
    "1",
    "true",
    "yes",
}
WECLAW_RENDER_WIDTH = int(os.getenv("WECLAW_RENDER_WIDTH", "480"))  # 截图视口宽度(px)
WECLAW_RENDER_TIMEOUT_MS = int(os.getenv("WECLAW_RENDER_TIMEOUT_MS", "15000"))
# EduViz 沙箱 SDK 源文件（用于后端复刻 viz 沙箱做截图）
EDUVIZ_SDK_PATH = (
    ROOT_DIR / "frontend" / "src" / "components" / "EduViz" / "eduviz-sdk.js"
)

# GitHub OAuth 配置
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")

# 服务配置
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8080"))
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:5174,http://localhost:5173"
).split(",")

# 文件上传限制
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100"))
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}

# 确保数据目录存在
for _dir in [
    DATA_DIR,
    DOCUMENTS_DIR,
    UPLOADS_DIR,
    CARDS_DIR,
    COURSES_DIR,
    VIZ_DIR,
    SESSIONS_DIR,
    LOG_DIR,
]:
    _dir.mkdir(parents=True, exist_ok=True)

TTS_MODEL = os.getenv(
    "TTS_MODEL", "cosyvoice-v1"
)  # 角色语音模型（v1 默认；v2 需开通对应权限）
