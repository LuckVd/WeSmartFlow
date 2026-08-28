#!/usr/bin/env python3
"""
教材索引查询工具（知识之境 · 课内知识库）
=========================================
供 server.py 的生成管线调用：给定学科+关键词，找到对应的课本章节位置，
再按需提取那几页的原文文本作为"课内知识参照"，拼进 GEN_PROMPT。

不做的事：不把整本教材全文塞给 LLM，不做全文 embedding 检索（30 本书的
目录规模，关键词匹配已经够用，没必要上向量数据库）。

用法示例：
    from lookup import find_chapter, get_page_text

    # 1. 找到"数列"这个关键词命中的所有章节
    hits = find_chapter("数列")
    for h in hits:
        print(h["title"], h["subject"], h["chapter"]["title"], h["chapter"]["start_page"])

    # 2. 取某一章节对应页码范围的原文（用于填进生成 prompt 的"课内知识参照"）
    text = get_page_text(hits[0]["path"], hits[0]["chapter"]["start_page"],
                          hits[0]["chapter"]["start_page"] + 2)
"""
import json
import sys
from pathlib import Path

import fitz  # pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fzsp_font_fix import restore_fz_italic  # noqa: E402

INDEX_FILE = Path(__file__).resolve().parent.parent / "index_data" / "index_renjiao.json"

_CACHE = None


def _load_index():
    global _CACHE
    if _CACHE is None:
        _CACHE = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return _CACHE


def find_chapter(keyword: str, subject: str = None, stage: str = None):
    """按关键词在所有已索引教材的章/节标题里搜索，返回命中列表。
    每条命中包含：book 元信息 + 命中的具体 chapter（含 sections 供进一步定位）+
    命中的具体 section（若关键词命中的是子节标题，page/end_page 会更精确地
    指向那一节，而不是整章的开头——之前只返回整章 start_page，导致提取内容
    永远停留在章节开篇一两段，看不到关键词真正所在的那部分内容）。"""
    results = []
    for book in _load_index():
        if subject and book["subject"] != subject:
            continue
        if stage and book["stage"] != stage:
            continue
        for ch in book.get("chapters", []):
            hay = ch["title"]
            hit_section = None
            for sec in ch.get("sections", []):
                if keyword in sec["title"]:
                    hit_section = sec
                    break
            if keyword in hay or hit_section:
                results.append({
                    "stage": book["stage"], "subject": book["subject"],
                    "edition": book["edition"], "grade": book["grade"],
                    "title": book["title"], "path": book["path"],
                    "chapter": ch, "section": hit_section,
                })
    return results


def hit_range(hit: dict):
    """从 find_chapter 的一条命中结果里，取出应该提取的页码范围（起止页）。
    命中的是子节就用子节范围（更精确），否则用整章范围。"""
    node = hit["section"] or hit["chapter"]
    start = node.get("page") or node.get("start_page")
    end = node.get("end_page") or start + 3  # 没有 end_page（如最后一章）时兜底取3页
    return start, end


def get_page_text(pdf_path: str, first_page: int, last_page: int) -> str:
    """提取指定页码范围的原文（供拼进生成 prompt 时引用，应保持简短摘引，不要整段照搬）。
    用 pymupdf 提取 + restore_fz_italic 还原方正书版斜体乱码（数学教材公式变量
    如"犃犫犮狓狔"会被还原成正常的"ABCabxy"，对非数学教材文本无副作用）。"""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return ""
    parts = []
    for pgno in range(first_page - 1, min(last_page, doc.page_count)):
        if pgno < 0:
            continue
        parts.append(doc[pgno].get_text())
    doc.close()
    return restore_fz_italic("\n".join(parts))


if __name__ == "__main__":
    import sys
    kw = sys.argv[1] if len(sys.argv) > 1 else "函数"
    hits = find_chapter(kw)
    print(f"关键词「{kw}」命中 {len(hits)} 处：")
    for h in hits[:10]:
        loc = h["section"]["title"] if h["section"] else h["chapter"]["title"]
        start, end = hit_range(h)
        print(f"  [{h['stage']}/{h['subject']}/{h['grade']}] {h['title'][:20]} -> {loc} (第{start}-{end}页)")
