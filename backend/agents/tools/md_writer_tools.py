"""
MD 写回工具集 (md_writer_tools)

给「内部写回 Agent」用，解决两类任务的最末端落盘动作：

  - md_load_concept    读取已存在概念 md (参考同领域风格,辅助起草)
  - md_create_concept  按强 schema 创建一份新概念 md
                        (frontmatter + 老师领地 H1 + 空 Agent 领地)

约束严格踩在 ingest_okf 的解析规则上,任何不一致都会让后续 ingest 报错,
因此本文件里的字段名、类型、目录结构都要和 ingest_okf 同步,不要单方面发挥。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from agent_core.tool.base import BaseTool

logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================


# OKF 根目录,与 ingest_okf 默认值一致 (Path("knowledge"))
# 必须锚定到仓库根 (统一从 backend.config 读),避免 Agent 跑在不同 cwd 下时
# 写到 backend/knowledge/ 这种错误位置。
try:
    from config import KNOWLEDGE_ROOT as _CFG_KNOWLEDGE_ROOT  # type: ignore

    DEFAULT_KNOWLEDGE_ROOT = Path(_CFG_KNOWLEDGE_ROOT).resolve()
except Exception:  # pylint: disable=broad-except
    # 兜底: config 不可用时,基于本文件位置上溯到仓库根
    # backend/agents/tools/md_writer_tools.py → 上 3 级 = 仓库根
    DEFAULT_KNOWLEDGE_ROOT = (
        Path(__file__).resolve().parents[3] / "knowledge"
    ).resolve()

# 单段正文最少字数(防止 LLM 偷懒只写一句话)
_MIN_CONTENT_LEN = 50

# 单段正文最多字数(防止单段炸到不可读)
_MAX_CONTENT_LEN = 4000

# 概念 md 至少要写几个 H1 段(让概念页有最小完备性)
_MIN_SECTIONS = 3

# H1 标题最大字符数
_MAX_H1_LEN = 30


# 共性反馈白名单 H1(由飞轮维护,不能由建档 Agent 写)
# - 这里只用于"建档时给 Agent 兜底,提示不要预填这 4 个 H1"
# - 真正的写入由任务 1 的 facet 工具负责,本工具如检测到这 4 个 H1 直接拒绝
WHITELIST_AGENT_H1 = ("常见误解", "易错点", "有效讲法", "学习障碍")


# 允许 Agent 在 frontmatter 里写的关系字段(子集)
# 其它关系类型(generalizes/special_case_of/...) 由人工补,Agent 不开放。
_ALLOWED_RELATION_KEYS = ("prerequisites", "related")


# ============================================================
# 纯工具函数
# ============================================================


def _validate_subject(subject: str) -> Optional[str]:
    """校验 subject。返回错误信息,合法返回 None。"""
    if not subject or not subject.strip():
        return "subject 不能为空"
    if "/" in subject:
        return "subject 不能包含 '/'"
    return None


def _validate_slug(slug: str) -> Optional[str]:
    """校验 slug。返回错误信息,合法返回 None。"""
    if not slug or not slug.strip():
        return "slug 不能为空"
    if "/" in slug:
        return "slug 不能包含 '/'"
    # 推荐 kebab-case,但宽松一点,只禁止空白字符
    if re.search(r"\s", slug):
        return "slug 不能包含空白字符"
    return None


def _validate_h1(h1: str) -> Optional[str]:
    """校验单个 H1 标题。"""
    if not h1 or not h1.strip():
        return "H1 标题不能为空"
    if "/" in h1:
        return "H1 标题不能包含 '/'"
    if len(h1) > _MAX_H1_LEN:
        return f"H1 标题长度不能超过 {_MAX_H1_LEN} 字符"
    if h1 in WHITELIST_AGENT_H1:
        return (
            f"H1「{h1}」是飞轮共性反馈白名单,只能由飞轮维护,建档时不要预填,"
            "请改用其它 H1(如「直观理解」/「严格定义」/「典型例子」/「几何意义」)"
        )
    return None


def _resolve_concept_id_by_slug(slug: str) -> Optional[str]:
    """按 slug 查 KG 中是否存在 concept,返回 concept_id 或 None。

    用于 md_create_concept 校验 prerequisites/related 中的 slug 真实存在。
    """
    try:
        from kg.repositories import ConceptRepository
    except Exception:  # pylint: disable=broad-except
        return None
    try:
        c = ConceptRepository().get_by_slug(slug)
    except Exception:  # pylint: disable=broad-except
        logger.exception("get_by_slug 失败 slug=%s", slug)
        return None
    if not c or c.status != "approved":
        return None
    return c.id


def _build_frontmatter(
    *,
    slug: str,
    canonical_name: str,
    summary: str,
    subject: str,
    difficulty: int,
    aliases: list[str],
    tags: list[str],
    prerequisites: list[str],
    related: list[str],
) -> str:
    """拼一份 YAML frontmatter (含首尾 ---)。

    注意 ingest_okf 期待的字段名:
      slug / name / summary / subject / difficulty / aliases / tags
      + 关系字段 (prerequisites / related / ...)
    """
    fm: dict[str, Any] = {
        "slug": slug,
        "name": canonical_name,
        "summary": summary,
        "subject": subject,
        "difficulty": int(difficulty),
    }
    if aliases:
        fm["aliases"] = list(aliases)
    if tags:
        fm["tags"] = list(tags)
    if prerequisites:
        fm["prerequisites"] = list(prerequisites)
    if related:
        fm["related"] = list(related)

    body = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip("\n")
    return f"---\n{body}\n---\n"


def _build_md_text(
    *,
    frontmatter: str,
    sections: list[dict[str, str]],
) -> str:
    """拼整篇 md。

    格式:
      <frontmatter>

      # H1-1
      content-1

      # H1-2
      content-2
      ...
    """
    parts = [frontmatter.rstrip("\n"), ""]
    for sec in sections:
        h1 = sec["h1"].strip()
        content = sec["content"].strip()
        parts.append(f"# {h1}")
        parts.append("")
        parts.append(content)
        parts.append("")
    return "\n".join(parts).rstrip("\n") + "\n"


def _resolve_md_path(knowledge_root: Path, subject: str, slug: str) -> Path:
    """落盘路径: <root>/<subject>/<slug>.md"""
    return (knowledge_root / subject / f"{slug}.md").resolve()


def _ensure_within_root(knowledge_root: Path, target: Path) -> bool:
    """安全检查: target 必须在 knowledge_root 内,防止 subject/slug 含 .. 之类的注入。"""
    try:
        target.relative_to(knowledge_root)
        return True
    except ValueError:
        return False


# ============================================================
# md_load_concept
# ============================================================


class MdLoadConceptTool(BaseTool):
    name = "md_load_concept"
    description = (
        "读取一份已存在的概念 md 原文,用于建档时参考同领域已有概念的写作风格、"
        "frontmatter 结构、H1 划分等。"
        "可按 subject+slug 精确读取,或仅传 slug(由工具内部 KG 反查 subject 后定位)。"
        "返回 JSON: {found: bool, md_path?, content?, error?}"
    )
    parameters = {
        "type": "object",
        "properties": {
            "slug": {
                "type": "string",
                "description": "概念 slug,必填",
            },
            "subject": {
                "type": "string",
                "description": "学科目录名;不传则工具内部按 slug 查 KG 反查 subject",
            },
        },
        "required": ["slug"],
    }

    def __init__(self, knowledge_root: Optional[Path] = None) -> None:
        super().__init__()
        self._root = (knowledge_root or DEFAULT_KNOWLEDGE_ROOT).resolve()

    def run(self, slug: str = "", subject: str = "", **kwargs) -> str:
        slug = (slug or "").strip()
        subject = (subject or "").strip()

        err = _validate_slug(slug)
        if err:
            return json.dumps({"found": False, "error": err}, ensure_ascii=False)

        # subject 缺省 → 用 KG 反查
        if not subject:
            try:
                from kg.repositories import ConceptRepository

                c = ConceptRepository().get_by_slug(slug)
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("md_load_concept KG 反查失败 slug=%s", slug)
                return json.dumps(
                    {
                        "found": False,
                        "error": f"按 slug 反查 KG 异常: {exc}",
                    },
                    ensure_ascii=False,
                )
            if not c:
                return json.dumps(
                    {
                        "found": False,
                        "error": (
                            f"slug={slug!r} 在 KG 中找不到对应概念,"
                            "请显式提供 subject 或先核实 slug 是否正确"
                        ),
                    },
                    ensure_ascii=False,
                )
            subject = c.subject or ""

        err = _validate_subject(subject)
        if err:
            return json.dumps({"found": False, "error": err}, ensure_ascii=False)

        path = _resolve_md_path(self._root, subject, slug)
        if not _ensure_within_root(self._root, path):
            return json.dumps(
                {
                    "found": False,
                    "error": "subject/slug 包含非法路径成分",
                },
                ensure_ascii=False,
            )

        if not path.exists():
            return json.dumps(
                {
                    "found": False,
                    "error": f"md 文件不存在: {path.relative_to(self._root)}",
                },
                ensure_ascii=False,
            )

        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("md_load_concept 读取失败 path=%s", path)
            return json.dumps(
                {"found": False, "error": f"读取失败: {exc}"},
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "found": True,
                "md_path": str(path.relative_to(self._root)),
                "content": text,
            },
            ensure_ascii=False,
        )


# ============================================================
# md_create_concept
# ============================================================


class MdCreateConceptTool(BaseTool):
    name = "md_create_concept"
    description = (
        "【写回 Agent 专用】按强 schema 创建一份新的概念 md,"
        "落盘到 knowledge/<subject>/<slug>.md。"
        "工具会全量校验 frontmatter 与 sections,任一项不合格直接拒绝并返回错误码,"
        "不会落盘半成品。"
        ""
        "硬约束:"
        " 1) 目标文件必须不存在 (不允许覆盖)"
        " 2) subject/slug/H1 标题不能含 '/' 或空白"
        " 3) sections 至少 3 段,每段 H1 唯一,content 长度在 50-4000 字之间"
        " 4) H1 不能用飞轮共性反馈白名单 (常见误解/易错点/有效讲法/学习障碍)"
        " 5) prerequisites / related 中每个 slug 必须在 KG 中存在 approved concept"
        ""
        "返回 JSON: {ok: true, md_path, ...} 或 {ok: false, error_code, error, ...}"
    )
    parameters = {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "学科目录名,如 'math' / 'physics',不能含 '/'",
            },
            "slug": {
                "type": "string",
                "description": "概念 slug,kebab-case 风格,不能含 '/' 或空白",
            },
            "canonical_name": {
                "type": "string",
                "description": "概念中文/英文规范名,如「链式法则」",
            },
            "summary": {
                "type": "string",
                "description": "≤80 字一句话定义,会写入 frontmatter.summary",
                "maxLength": 200,
            },
            "difficulty": {
                "type": "integer",
                "description": "难度 0-5,0=入门,5=专家",
                "minimum": 0,
                "maximum": 5,
            },
            "aliases": {
                "type": "array",
                "description": "别名列表,每个元素是 str",
                "items": {"type": "string"},
            },
            "tags": {
                "type": "array",
                "description": "标签列表",
                "items": {"type": "string"},
            },
            "prerequisites": {
                "type": "array",
                "description": "前置概念 slug 列表,每个 slug 必须在 KG 中已有",
                "items": {"type": "string"},
            },
            "related": {
                "type": "array",
                "description": "相关概念 slug 列表,每个 slug 必须在 KG 中已有",
                "items": {"type": "string"},
            },
            "sections": {
                "type": "array",
                "description": (
                    "概念正文段落,每段一个 H1。至少 3 段,H1 不能重复,"
                    "H1 不能是共性反馈白名单。"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "h1": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["h1", "content"],
                },
            },
        },
        "required": [
            "subject",
            "slug",
            "canonical_name",
            "summary",
            "difficulty",
            "sections",
        ],
    }

    def __init__(self, knowledge_root: Optional[Path] = None) -> None:
        super().__init__()
        self._root = (knowledge_root or DEFAULT_KNOWLEDGE_ROOT).resolve()

    # --- helper ----------------------------------------------------

    @staticmethod
    def _err(code: str, msg: str, **extra: Any) -> str:
        payload = {"ok": False, "error_code": code, "error": msg}
        payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)

    def _validate_sections(
        self, sections: list[dict]
    ) -> Optional[tuple[str, str, dict]]:
        """校验 sections。返回 None=通过,否则 (code, msg, extra)。"""
        if not isinstance(sections, list):
            return ("invalid_sections", "sections 必须是数组", {})
        if len(sections) < _MIN_SECTIONS:
            return (
                "too_few_sections",
                f"sections 至少需要 {_MIN_SECTIONS} 段,当前 {len(sections)}",
                {"min": _MIN_SECTIONS},
            )

        seen: set[str] = set()
        for i, sec in enumerate(sections):
            if not isinstance(sec, dict):
                return (
                    "invalid_section_item",
                    f"第 {i} 段不是对象",
                    {"index": i},
                )
            h1 = (sec.get("h1") or "").strip()
            content = (sec.get("content") or "").strip()

            err = _validate_h1(h1)
            if err:
                return (
                    "invalid_h1",
                    f"第 {i} 段 H1 不合法: {err}",
                    {"index": i, "h1": h1},
                )
            if h1 in seen:
                return (
                    "duplicate_h1",
                    f"H1「{h1}」重复(第 {i} 段)",
                    {"index": i, "h1": h1},
                )
            seen.add(h1)

            if len(content) < _MIN_CONTENT_LEN:
                return (
                    "content_too_short",
                    (
                        f"第 {i} 段(H1={h1})content 长度 {len(content)} < "
                        f"{_MIN_CONTENT_LEN}"
                    ),
                    {"index": i, "h1": h1, "len": len(content)},
                )
            if len(content) > _MAX_CONTENT_LEN:
                return (
                    "content_too_long",
                    (
                        f"第 {i} 段(H1={h1})content 长度 {len(content)} > "
                        f"{_MAX_CONTENT_LEN}"
                    ),
                    {"index": i, "h1": h1, "len": len(content)},
                )
        return None

    def _validate_relation_slugs(
        self, slugs: list[str], rel_key: str
    ) -> Optional[tuple[str, str, dict]]:
        """校验关系字段中的每个 slug 都能在 KG 中找到。"""
        missing: list[str] = []
        for s in slugs:
            s = (s or "").strip()
            if not s:
                continue
            err = _validate_slug(s)
            if err:
                return (
                    "invalid_relation_slug",
                    f"{rel_key} 中 slug={s!r} 不合法: {err}",
                    {"rel": rel_key, "slug": s},
                )
            if not _resolve_concept_id_by_slug(s):
                missing.append(s)
        if missing:
            return (
                "relation_slug_not_found",
                (
                    f"{rel_key} 中以下 slug 在 KG 中找不到 approved concept: "
                    f"{missing} (请先建档或修正)"
                ),
                {"rel": rel_key, "missing": missing},
            )
        return None

    # --- main ------------------------------------------------------

    def run(
        self,
        subject: str = "",
        slug: str = "",
        canonical_name: str = "",
        summary: str = "",
        difficulty: int = 3,
        aliases: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        prerequisites: Optional[list[str]] = None,
        related: Optional[list[str]] = None,
        sections: Optional[list[dict]] = None,
        **kwargs,
    ) -> str:
        # ---------- 标量字段校验 ----------
        subject = (subject or "").strip()
        slug = (slug or "").strip()
        canonical_name = (canonical_name or "").strip()
        summary = (summary or "").strip()

        err = _validate_subject(subject)
        if err:
            return self._err("invalid_subject", err)

        err = _validate_slug(slug)
        if err:
            return self._err("invalid_slug", err)

        if not canonical_name:
            return self._err("invalid_canonical_name", "canonical_name 不能为空")

        if not summary:
            return self._err("invalid_summary", "summary 不能为空")
        if len(summary) > 200:
            return self._err(
                "summary_too_long",
                f"summary 长度 {len(summary)} > 200",
            )

        if not isinstance(difficulty, int) or not (0 <= difficulty <= 5):
            return self._err(
                "invalid_difficulty",
                f"difficulty={difficulty!r} 必须是 0-5 的整数",
            )

        # ---------- 列表字段规范化 ----------
        aliases = [a.strip() for a in (aliases or []) if a and a.strip()]
        tags = [t.strip() for t in (tags or []) if t and t.strip()]
        prerequisites = [s.strip() for s in (prerequisites or []) if s and s.strip()]
        related = [s.strip() for s in (related or []) if s and s.strip()]

        # ---------- sections 校验 ----------
        section_err = self._validate_sections(sections or [])
        if section_err:
            code, msg, extra = section_err
            return self._err(code, msg, **extra)

        # ---------- 关系 slug 存在性校验 ----------
        for rel_key, lst in (
            ("prerequisites", prerequisites),
            ("related", related),
        ):
            if not lst:
                continue
            rel_err = self._validate_relation_slugs(lst, rel_key)
            if rel_err:
                code, msg, extra = rel_err
                return self._err(code, msg, **extra)

        # ---------- 路径 + 防覆盖 ----------
        path = _resolve_md_path(self._root, subject, slug)
        if not _ensure_within_root(self._root, path):
            return self._err(
                "path_escape",
                "subject/slug 解析后越出 knowledge_root,拒绝写入",
            )
        if path.exists():
            return self._err(
                "file_already_exists",
                f"目标文件已存在: {path.relative_to(self._root)},不允许覆盖",
                md_path=str(path.relative_to(self._root)),
            )

        # ---------- 拼 md ----------
        try:
            fm = _build_frontmatter(
                slug=slug,
                canonical_name=canonical_name,
                summary=summary,
                subject=subject,
                difficulty=difficulty,
                aliases=aliases,
                tags=tags,
                prerequisites=prerequisites,
                related=related,
            )
            md_text = _build_md_text(frontmatter=fm, sections=sections or [])
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("md_create_concept 拼装失败")
            return self._err("assemble_failed", f"拼装 md 失败: {exc}")

        # ---------- 落盘(原子写) ----------
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(md_text, encoding="utf-8")
            tmp.replace(path)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("md_create_concept 写盘失败 path=%s", path)
            return self._err("write_failed", f"写盘失败: {exc}")

        return json.dumps(
            {
                "ok": True,
                "md_path": str(path.relative_to(self._root)),
                "abs_path": str(path),
                "bytes": len(md_text.encode("utf-8")),
                "section_count": len(sections or []),
                "next_step": (
                    "请管理员人工 review 此 md,确认无误后跑 "
                    "`conda run -n edu-agent python -m backend.ingest_okf "
                    "--incremental` 同步到 KG"
                ),
            },
            ensure_ascii=False,
        )


# ============================================================
# 任务 1: 共性反馈 facet section 写回
# ============================================================
#
# 设计要点(必读,不要凭直觉改):
#   1. ingest_okf 视角: 整个 H1 段 = 一条 facet (kind=H1 原文,content=整段)
#   2. 飞轮往回写的语义却是"条目级"的(对一条用户反馈做 add/merge/replace)
#   3. 因此本工具在 md 内部维持「段 = (可选引导文字 prologue) + 多条 bullet」的子结构
#      Agent 在 bullet 级做操作,ingest_okf 拿到的整段文本无感知。
#   4. 作用域只在 4 个飞轮白名单 H1: 常见误解/易错点/有效讲法/学习障碍
#      其它 H1 (老师领地) 由 md_create_concept 一次写死,不开放给本工具改。
#   5. action 语义:
#        add     → 在末尾追加一条新 bullet
#        merge   → 把 target_idx 那条 bullet 替换为 new_text
#                  (Agent 自己在 prompt 里把 A+B 融合好,工具层只负责落盘)
#        replace → 物理上同 merge,语义上"A 错→B 替"
#                  (保留区分用于审计日志,工具层不做差异化处理)
# ============================================================


# bullet 行检测: -, *, 1. 等都算
_BULLET_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.*)$")


def _strip_bullet_prefix(text: str) -> str:
    """剥掉用户提交文本里可能带的 '- ' / '* ' / '1. ' 前缀。"""
    text = (text or "").strip()
    m = _BULLET_LINE_RE.match(text)
    if m:
        return m.group(1).strip()
    return text


def _split_md_by_h1(text: str) -> tuple[str, list[tuple[str, str]]]:
    """把整篇 md 切成 (frontmatter_blob, [(h1, body)])。

    frontmatter_blob 包含开头的 ``---\\n...\\n---\\n`` 以及到第一个 H1 之前的
    所有内容(空行/简介段),原样保留,写回时拼回去。
    body 不含 H1 行本身,且首尾去多余空行,但保留段内空行。
    """
    h1_re = re.compile(r"^#\s+(.+)$", flags=re.MULTILINE)
    matches = list(h1_re.finditer(text))
    if not matches:
        return text, []

    head = text[: matches[0].start()]
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip("\n")
        sections.append((title, body))
    return head, sections


def _join_md(head: str, sections: list[tuple[str, str]]) -> str:
    """把 (head, [(h1, body)]) 拼回整篇 md。"""
    parts: list[str] = []
    head = head.rstrip("\n")
    if head:
        parts.append(head)
        parts.append("")  # head 与第一个 H1 间留空行
    for h1, body in sections:
        parts.append(f"# {h1}")
        parts.append("")
        body = body.strip("\n")
        if body:
            parts.append(body)
            parts.append("")
    return "\n".join(parts).rstrip("\n") + "\n"


def _parse_section_items(body: str) -> tuple[str, list[str]]:
    """把单段 body 解析为 (prologue, items)。

    规则:
      - 从顶端开始,**第一个** bullet 行之前的所有内容算作 prologue (引导文字)。
      - 之后逐行扫描:
          * 遇到新 bullet 行 → 起一个新 item
          * 遇到非 bullet 非空行 → 作为当前 item 的续行 (markdown 软换行也常见)
          * 空行 → 不结束 item,但保留为 item 内空行
      - 如果整段都没有 bullet,prologue = 整段,items = [] (允许工具用 add 给段内首次加 bullet)
    """
    if not body.strip():
        return "", []

    lines = body.split("\n")
    # 第一遍: 找第一个 bullet 行
    first_bullet_idx = -1
    for i, line in enumerate(lines):
        if _BULLET_LINE_RE.match(line):
            first_bullet_idx = i
            break

    if first_bullet_idx == -1:
        return body.strip("\n"), []

    prologue = "\n".join(lines[:first_bullet_idx]).strip("\n")

    items: list[str] = []
    cur: list[str] = []
    for line in lines[first_bullet_idx:]:
        m = _BULLET_LINE_RE.match(line)
        if m:
            if cur:
                items.append("\n".join(cur).rstrip())
                cur = []
            cur.append(m.group(1).rstrip())
        else:
            cur.append(line)
    if cur:
        # 跳过尾部纯空行
        while cur and not cur[-1].strip():
            cur.pop()
        if cur:
            items.append("\n".join(cur).rstrip())

    return prologue, items


def _render_section_body(prologue: str, items: list[str]) -> str:
    """把 (prologue, items) 渲染回段 body 文本。"""
    parts: list[str] = []
    prologue = prologue.strip("\n")
    if prologue:
        parts.append(prologue)
        parts.append("")  # prologue 与 bullet 列表间空一行
    for it in items:
        # 首行加 '- ',续行原样保留(让 markdown 用 4 空格表续行也行,我们不强制)
        first, *rest = it.split("\n")
        parts.append(f"- {first.strip()}")
        for r in rest:
            parts.append(r)
    return "\n".join(parts).rstrip("\n")


def _resolve_subject_for_slug(slug: str) -> Optional[str]:
    """缺 subject 时,按 slug 反查 KG 拿 subject。"""
    try:
        from kg.repositories import ConceptRepository

        c = ConceptRepository().get_by_slug(slug)
    except Exception:  # pylint: disable=broad-except
        logger.exception("_resolve_subject_for_slug 失败 slug=%s", slug)
        return None
    if not c:
        return None
    return c.subject or None


# ============================================================
# md_load_facet_section
# ============================================================


class MdLoadFacetSectionTool(BaseTool):
    name = "md_load_facet_section"
    description = (
        "【写回 Agent 专用 / 任务 1】读取概念 md 中某个共性反馈 H1 段的当前条目列表,"
        "供 Agent 决定 add/merge/replace 时使用。"
        "h1 必须是飞轮白名单之一: 常见误解 / 易错点 / 有效讲法 / 学习障碍。"
        "返回 JSON: {found, h1, prologue, items: [{idx, text}], md_path, "
        "section_exists} 或 {found:false, error}。"
        "section_exists=false 表示文件存在但还没有这个 H1 段(此时 add 操作会"
        "由 md_write_facet_section 自动建段)。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "概念 slug,必填"},
            "subject": {
                "type": "string",
                "description": "学科目录;不传则按 slug 查 KG 反推",
            },
            "h1": {
                "type": "string",
                "description": "段标题,必须是 常见误解/易错点/有效讲法/学习障碍 之一",
                "enum": list(WHITELIST_AGENT_H1),
            },
        },
        "required": ["slug", "h1"],
    }

    def __init__(self, knowledge_root: Optional[Path] = None) -> None:
        super().__init__()
        self._root = (knowledge_root or DEFAULT_KNOWLEDGE_ROOT).resolve()

    def run(self, slug: str = "", subject: str = "", h1: str = "", **kwargs) -> str:
        slug = (slug or "").strip()
        subject = (subject or "").strip()
        h1 = (h1 or "").strip()

        err = _validate_slug(slug)
        if err:
            return json.dumps({"found": False, "error": err}, ensure_ascii=False)
        if h1 not in WHITELIST_AGENT_H1:
            return json.dumps(
                {
                    "found": False,
                    "error": (
                        f"h1={h1!r} 不在白名单 {list(WHITELIST_AGENT_H1)} 内,"
                        "本工具只负责飞轮共性反馈段"
                    ),
                },
                ensure_ascii=False,
            )

        if not subject:
            subject = _resolve_subject_for_slug(slug) or ""
        err = _validate_subject(subject)
        if err:
            return json.dumps(
                {
                    "found": False,
                    "error": (
                        f"找不到 slug={slug!r} 对应的 subject,"
                        "请显式提供 subject 或先核实 slug"
                    ),
                },
                ensure_ascii=False,
            )

        path = _resolve_md_path(self._root, subject, slug)
        if not _ensure_within_root(self._root, path):
            return json.dumps(
                {"found": False, "error": "subject/slug 含非法路径成分"},
                ensure_ascii=False,
            )
        if not path.exists():
            return json.dumps(
                {
                    "found": False,
                    "error": f"md 文件不存在: {path.relative_to(self._root)}",
                },
                ensure_ascii=False,
            )

        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("md_load_facet_section 读取失败 path=%s", path)
            return json.dumps(
                {"found": False, "error": f"读取失败: {exc}"},
                ensure_ascii=False,
            )

        head, sections = _split_md_by_h1(text)
        del head
        target_body: Optional[str] = None
        for title, body in sections:
            if title == h1:
                target_body = body
                break

        md_rel = str(path.relative_to(self._root))
        if target_body is None:
            return json.dumps(
                {
                    "found": True,
                    "section_exists": False,
                    "h1": h1,
                    "prologue": "",
                    "items": [],
                    "md_path": md_rel,
                },
                ensure_ascii=False,
            )

        prologue, items = _parse_section_items(target_body)
        return json.dumps(
            {
                "found": True,
                "section_exists": True,
                "h1": h1,
                "prologue": prologue,
                "items": [{"idx": i, "text": t} for i, t in enumerate(items)],
                "md_path": md_rel,
            },
            ensure_ascii=False,
        )


# ============================================================
# md_write_facet_section
# ============================================================


_FACET_ACTIONS = ("add", "merge", "replace")


class MdWriteFacetSectionTool(BaseTool):
    name = "md_write_facet_section"
    description = (
        "【写回 Agent 专用 / 任务 1】对概念 md 的共性反馈 H1 段执行 "
        "add / merge / replace。"
        ""
        "action 语义:"
        " - add:     在段末追加一条 bullet (target_idx 必须为空)"
        " - merge:   用 new_text 替换 target_idx 那条 bullet (Agent 自行融合好)"
        " - replace: 同 merge 的物理动作,语义为「原条目错了,用 new_text 替换」"
        ""
        "硬约束:"
        " 1) h1 必须在白名单: 常见误解/易错点/有效讲法/学习障碍"
        " 2) merge/replace 必须给 target_idx 且在当前 items 范围内"
        "    建议先调用 md_load_facet_section 拿到 idx 再写"
        " 3) new_text 必须非空、≤500 字"
        " 4) 文件不存在/段不存在(对 add 例外,会自动建段) → 报错"
        " 5) 写盘原子(tmp + replace),不留半成品"
        ""
        "返回 JSON: {ok, action, h1, idx, before?, after, md_path} 或 "
        "{ok:false, error_code, error}"
    )
    parameters = {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "概念 slug"},
            "subject": {
                "type": "string",
                "description": "学科目录;不传则按 slug 反查 KG",
            },
            "h1": {
                "type": "string",
                "description": "段标题,必须是飞轮白名单之一",
                "enum": list(WHITELIST_AGENT_H1),
            },
            "action": {
                "type": "string",
                "description": "操作类型",
                "enum": list(_FACET_ACTIONS),
            },
            "new_text": {
                "type": "string",
                "description": ("新条目内容 (不要带 '- ' / '* ' 前缀,工具会自动渲染)"),
            },
            "target_idx": {
                "type": "integer",
                "description": (
                    "merge/replace 必填,指定要替换的 bullet 序号 "
                    "(由 md_load_facet_section 返回);add 时禁止填"
                ),
                "minimum": 0,
            },
        },
        "required": ["slug", "h1", "action", "new_text"],
    }

    def __init__(self, knowledge_root: Optional[Path] = None) -> None:
        super().__init__()
        self._root = (knowledge_root or DEFAULT_KNOWLEDGE_ROOT).resolve()

    @staticmethod
    def _err(code: str, msg: str, **extra: Any) -> str:
        payload = {"ok": False, "error_code": code, "error": msg}
        payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)

    def run(
        self,
        slug: str = "",
        subject: str = "",
        h1: str = "",
        action: str = "",
        new_text: str = "",
        target_idx: Optional[int] = None,
        **kwargs,
    ) -> str:
        slug = (slug or "").strip()
        subject = (subject or "").strip()
        h1 = (h1 or "").strip()
        action = (action or "").strip()
        new_text_raw = new_text or ""
        new_text_clean = _strip_bullet_prefix(new_text_raw)

        # ---------- 基础字段校验 ----------
        err = _validate_slug(slug)
        if err:
            return self._err("invalid_slug", err)
        if h1 not in WHITELIST_AGENT_H1:
            return self._err(
                "invalid_h1",
                f"h1={h1!r} 不在白名单 {list(WHITELIST_AGENT_H1)}",
            )
        if action not in _FACET_ACTIONS:
            return self._err(
                "invalid_action",
                f"action={action!r} 必须是 {list(_FACET_ACTIONS)} 之一",
            )
        if not new_text_clean:
            return self._err("invalid_new_text", "new_text 不能为空(剥前缀后)")
        if len(new_text_clean) > 500:
            return self._err(
                "new_text_too_long",
                f"new_text 长度 {len(new_text_clean)} > 500",
            )

        if action == "add":
            if target_idx is not None:
                return self._err(
                    "target_idx_not_allowed",
                    "action=add 不能指定 target_idx",
                )
        else:
            if target_idx is None or target_idx < 0:
                return self._err(
                    "target_idx_required",
                    f"action={action} 必须给非负 target_idx",
                )

        # ---------- 路径解析 ----------
        if not subject:
            subject = _resolve_subject_for_slug(slug) or ""
        err = _validate_subject(subject)
        if err:
            return self._err(
                "invalid_subject",
                f"找不到 slug={slug!r} 对应的 subject,请显式提供 subject",
            )

        path = _resolve_md_path(self._root, subject, slug)
        if not _ensure_within_root(self._root, path):
            return self._err("path_escape", "subject/slug 解析后越出 knowledge_root")
        if not path.exists():
            return self._err(
                "file_not_found",
                f"md 文件不存在: {path.relative_to(self._root)}",
                md_path=str(path.relative_to(self._root)),
            )

        # ---------- 读 + 切 ----------
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("md_write_facet_section 读取失败 path=%s", path)
            return self._err("read_failed", f"读取失败: {exc}")

        head, sections = _split_md_by_h1(text)
        if not sections:
            return self._err(
                "no_h1_in_md",
                "md 中没有任何 H1 段,文件结构异常,请人工核查",
            )

        # 找目标段
        target_pos = -1
        for i, (title, _body) in enumerate(sections):
            if title == h1:
                target_pos = i
                break

        # ---------- 改 items ----------
        before_text: Optional[str] = None
        if target_pos == -1:
            # 段不存在
            if action != "add":
                return self._err(
                    "section_not_found",
                    (f"段「{h1}」在 md 中不存在,action={action} 需要先有该段才能操作"),
                )
            prologue, items = "", []
        else:
            _, body = sections[target_pos]
            prologue, items = _parse_section_items(body)

        if action == "add":
            new_idx = len(items)
            items.append(new_text_clean)
        else:
            # merge / replace
            assert target_idx is not None  # for mypy
            if target_idx >= len(items):
                return self._err(
                    "target_idx_out_of_range",
                    (f"target_idx={target_idx} 越界,当前段共 {len(items)} 条"),
                    items_count=len(items),
                )
            before_text = items[target_idx]
            items[target_idx] = new_text_clean
            new_idx = target_idx

        new_body = _render_section_body(prologue, items)

        # ---------- 把新段塞回 sections ----------
        if target_pos == -1:
            # 新建段,追加到末尾(共性反馈段约定排序在末尾,符合现状)
            sections.append((h1, new_body))
        else:
            sections[target_pos] = (h1, new_body)

        new_md = _join_md(head, sections)

        # ---------- 原子写 ----------
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(new_md, encoding="utf-8")
            tmp.replace(path)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("md_write_facet_section 写盘失败 path=%s", path)
            return self._err("write_failed", f"写盘失败: {exc}")

        result: dict[str, Any] = {
            "ok": True,
            "action": action,
            "h1": h1,
            "idx": new_idx,
            "after": new_text_clean,
            "items_count": len(items),
            "md_path": str(path.relative_to(self._root)),
            "next_step": (
                "请人工 review 此次写回,确认无误后跑 "
                "`conda run -n edu-agent python -m backend.ingest_okf "
                "--incremental` 同步到 KG"
            ),
        }
        if before_text is not None:
            result["before"] = before_text
        return json.dumps(result, ensure_ascii=False)
