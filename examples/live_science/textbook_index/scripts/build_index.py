#!/usr/bin/env python3
"""
教材索引构建器（知识之境 · 课内知识库）
=========================================
背景：用户在本地下载了国家中小学智慧教育平台的教材 PDF（31GB / 330 本，覆盖小学-高中
四大学科多个版本）。直接把整本 PDF 甚至整个目录丢给生成管线是不可行的——文件太大太多，
LLM 单次上下文塞不下，也没必要（生成一幕历史剧情只需要"这段历史对应课本哪一节、那一节
讲了什么"，不需要整本书）。

方案：只建"章节目录索引"，不做全文 OCR/全文入库。
  - 索引内容：每本书的 章/节 标题 + 起始页码（从目录页文本解析，人教系教材目录格式统一）
  - 索引不含教材原文全文（避免版权/体量问题），只有目录结构本身
  - 生成管线要用某一节的具体内容时，再用 extract_pages() 按需从 PDF 提取那几页文本
    （教材原文的引用应保持简短、指向性使用，而非整段照搬）

提取引擎：pymupdf（fitz），不用 pdftotext。原因：
  1. pymupdf 是 Python 库直接调用，不依赖外部 poppler 二进制，也不受 NFD/NFC 文件名
     编码问题影响（真实测试过 pdftotext 遇 NFD 路径直接报 "No such file or directory"，
     必须先用 glob 转换路径；pymupdf 用 Python str 路径可以直接打开，内部走的是不同的
     文件系统调用层，不受这个 macOS 特有问题困扰）。
  2. pymupdf 能识别真实字体名（如 E-BX9 白斜体），配合 fzsp_font_fix.py 的还原表，可以
     解决数学教材"犃犫犮狓狔"这类方正书版斜体乱码问题（pdftotext 做不到，它只能按 Unicode
     码位输出，不知道这层私有字体映射）。

已知限制：
  - 方正书版数学斜体乱码：已用 fzsp_font_fix.py 的映射表解决（a-z、A-V 全部真实验证，
    W/X/Y/Z 因未在样本教材出现，按同一字体区连续码位推断，置信度略低）。
  - macOS 下这批文件名是 Unicode NFD 分解形式，用 glob 匹配获取真实路径（pymupdf 虽然
    不受 NFD 问题困扰，但 manifest.csv 里记录的路径仍是 NFC，需要转换才能找到文件）。
  - 数学/物理教材的公式如果整体是图片（截图排版），文字层提取不到，只能提取到公式周围
    的文字说明。

用法：
  python3 build_index.py                  # 构建默认范围（人教系全学段全学科）的索引
  python3 build_index.py --scope all      # 构建全部 330 本（包括非人教版本）
"""
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

import fitz  # pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fzsp_font_fix import restore_fz_italic  # noqa: E402

MANIFEST = Path("/Users/shipeng/Desktop/国家中小学智慧教育平台教材/download_manifest.csv")
ROOT = Path("/Users/shipeng/Desktop/国家中小学智慧教育平台教材")
OUT_DIR = Path(__file__).resolve().parent.parent / "index_data"
OUT_DIR.mkdir(exist_ok=True)

# 目录页里的章/节标题行格式——实测抽样发现至少两大类排版结构：
#   A类（单行）："第一章 集合与常用逻辑用语 ………………………… １"（标题+分隔符+页码同一行）
#   B类（跨行）："第1 章  走近细胞\n1\n"（标题独占一行，下一行是纯页码，可能还带一行省略号）
# pdftotext -layout 时代主要遇到 A 类；换用 pymupdf 后发现同样多的书是 B 类，
# 必须两类都支持，否则会漏掉一大批教材的目录结构
FULLWIDTH_DIGITS = "０１２３４５６７８９"
HALFWIDTH_DIGITS = "0123456789"
_DIGIT_MAP = str.maketrans(FULLWIDTH_DIGITS, HALFWIDTH_DIGITS)

CHAPTER_RE = re.compile(
    r'^第([一二三四五六七八九十0-9０-９]+)\s*[章单元]{1,2}\s*(.+?)[…\.·\s]{2,}([0-9０-９]{1,4})\s*$'
)
CHAPTER_HEAD_RE = re.compile(r'^第([一二三四五六七八九十0-9０-９]+)\s*[章单元]{1,2}\s*(.+?)\s*[…\.·]*\s*$')
# 教材子节编号至少有 5 种不同格式（实测抽样发现，之前只覆盖了前3种，导致化学/生物/部分
# 初中数学教材的子节全部没被索引到——用户反馈"内容比教材少了很多"的真实根因）：
#   ①数学系："1.1 集合的概念…………… 2"      （两级阿拉伯数字，点号分隔）
#   ②物理系："2. 万有引力定律          49"     （单级阿拉伯数字+点）
#   ③化学系（节）："第一节  物质的分类及转化   6"（中文数字"第X节"）
#   ④生物系："第1节  细胞是生命活动的基本单位. ...2"（阿拉伯数字"第X节"，连接符可以是点号）
#   ⑤化学系（课题）："课题1 物质的变化和性质   8"（"课题N"，人教版化学教材专用）
#   ⑥数学系（三级编号）："1.1.2 集合的基本关系……10"（B版数学教材用"章.节.小节"三级编号，
#     比A版的两级编号多一级；正则必须先试三级再试两级，否则"1.1.2"会被两级模式误吞成
#     "1.1"+标题里带着残余的".2"）
SECTION_RE_VARIANTS = [
    re.compile(r'^([0-9０-９]{1,2}[．\.][0-9０-９]{1,2}[．\.][0-9０-９]{1,2})\s*(.+?)[…\.·\s]{2,}([0-9０-９]{1,4})\s*$'),
    re.compile(r'^([0-9０-９]{1,2}[．\.][0-9０-９]{1,2})\s*(.+?)[…\.·\s]{2,}([0-9０-９]{1,4})\s*$'),
    re.compile(r'^([0-9０-９]{1,2})[．\.]\s*(.+?)[…\.·\s]{2,}([0-9０-９]{1,4})\s*$'),
    re.compile(r'^第([一二三四五六七八九十0-9０-９]{1,3})\s*节\s*(.+?)[…\.·\s]{2,}([0-9０-９]{1,4})\s*$'),
    re.compile(r'^课题([0-9０-９]{1,2})\s*(.+?)[…\.·\s]{2,}([0-9０-９]{1,4})\s*$'),
]
SECTION_HEAD_RE_VARIANTS = [
    re.compile(r'^([0-9０-９]{1,2}[．\.][0-9０-９]{1,2}[．\.][0-9０-９]{1,2})\s*(.+?)\s*[…\.·]*\s*$'),
    re.compile(r'^([0-9０-９]{1,2}[．\.][0-9０-９]{1,2})\s*(.+?)\s*[…\.·]*\s*$'),
    re.compile(r'^第([一二三四五六七八九十0-9０-９]{1,3})\s*节\s*(.+?)\s*[…\.·]*\s*$'),
    re.compile(r'^课题([0-9０-９]{1,2})\s*(.+?)\s*[…\.·]*\s*$'),
]
PURE_PAGE_RE = re.compile(r'^([0-9０-９]{1,4})$')


def to_halfwidth(s: str) -> str:
    return s.translate(_DIGIT_MAP)


def real_path(p: str) -> Path:
    """CSV 里的 path 列是 NFC 编码字符串，但磁盘上文件名是 NFD 分解形式，直接用会找不到文件。
    用 glob 通过目录+文件名(NFC)重新匹配磁盘上的真实(NFD)路径。"""
    pp = Path(p)
    parent = pp.parent
    name = pp.name
    if not parent.exists():
        # 尝试逐级用 NFD 匹配父目录
        parts = pp.relative_to(ROOT).parts if str(pp).startswith(str(ROOT)) else pp.parts
        cur = ROOT if str(pp).startswith(str(ROOT)) else Path("/")
        for part in parts[:-1]:
            part_nfd = unicodedata.normalize("NFD", part)
            matches = [c for c in cur.iterdir() if c.is_dir() and unicodedata.normalize("NFD", c.name) == part_nfd]
            if not matches:
                matches = [c for c in cur.iterdir() if c.is_dir() and c.name == part]
            if not matches:
                return pp
            cur = matches[0]
        parent = cur
    name_nfd = unicodedata.normalize("NFD", name)
    for f in parent.iterdir():
        if f.is_file() and unicodedata.normalize("NFD", f.name) == name_nfd:
            return f
        if f.is_file() and f.name == name:
            return f
    return pp


def pdftotext_range(path: Path, first: int, last: int, clean: bool = True) -> str:
    """用 pymupdf 提取指定页码范围的文字（页码是 1-based，兼容原 pdftotext -f/-l 语义）。
    clean=True 时会调用 restore_fz_italic() 清洗方正书版斜体乱码（数学教材公式变量），
    对非数学教材文本无副作用（还原表里的字符本来就不会出现在正常汉字文本中）。"""
    try:
        doc = fitz.open(str(path))
    except Exception:
        return ""
    parts = []
    for pgno in range(first - 1, min(last, doc.page_count)):
        if pgno < 0:
            continue
        parts.append(doc[pgno].get_text())
    doc.close()
    text = "\n".join(parts)
    return restore_fz_italic(text) if clean else text


def parse_toc(text: str):
    """从目录页文本里解析出章/节结构。兼容三类排版：
    A类单行："第一章 标题………页码"；B类跨行："第一章 标题\n页码\n（可能还有省略号行）"；
    B'类（章标题无独立页码）："第一章 标题\n1.1 子节标题\n页码\n"——实测踩过：部分教材
    （如人教版初中数学九年级）章标题本身不带页码，直接紧跟第一个子节，章的 start_page
    要用第一个子节的页码回填，不能因为"下一行不是纯页码"就放弃匹配整个章节。"""
    chapters = []
    cur_chapter = None
    lines = [to_halfwidth(l).strip() for l in text.split("\n")]
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line:
            i += 1
            continue
        # A类：章标题+分隔符+页码同一行
        m = CHAPTER_RE.match(line)
        if m:
            cur_chapter = {
                "chapter_no": m.group(1),
                "title": m.group(2).strip().replace("　", " "),
                "start_page": int(m.group(3)),
                "sections": [],
            }
            chapters.append(cur_chapter)
            i += 1
            continue
        # B类：章标题独占一行，下一行（跳过空行）是纯页码
        m = CHAPTER_HEAD_RE.match(line)
        if m and m.group(2).strip():
            j = i + 1
            while j < n and not lines[j]:
                j += 1
            pm = PURE_PAGE_RE.match(lines[j]) if j < n else None
            if pm:
                cur_chapter = {
                    "chapter_no": m.group(1),
                    "title": m.group(2).strip().replace("　", " "),
                    "start_page": int(to_halfwidth(pm.group(1))),
                    "sections": [],
                }
                chapters.append(cur_chapter)
                i = j + 1
                continue
            # B'类：章标题无独立页码，start_page 先占位为 None，
            # 等下面解析出第一个 section 后再回填（见 section 解析分支末尾）
            cur_chapter = {
                "chapter_no": m.group(1),
                "title": m.group(2).strip().replace("　", " "),
                "start_page": None,
                "sections": [],
            }
            chapters.append(cur_chapter)
            i += 1
            continue
        # A类：节标题+分隔符+页码同一行
        matched_section = False
        for pat in SECTION_RE_VARIANTS:
            m = pat.match(line)
            if m and cur_chapter is not None:
                cur_chapter["sections"].append({
                    "section_no": m.group(1),
                    "title": m.group(2).strip().replace("　", " "),
                    "page": int(m.group(3)),
                })
                if cur_chapter["start_page"] is None:
                    cur_chapter["start_page"] = int(m.group(3))
                matched_section = True
                break
        if matched_section:
            i += 1
            continue
        # B类：节标题独占一行，下一行是纯页码
        for pat in SECTION_HEAD_RE_VARIANTS:
            m = pat.match(line)
            if m and m.group(2).strip() and cur_chapter is not None:
                j = i + 1
                while j < n and not lines[j]:
                    j += 1
                if j < n:
                    pm = PURE_PAGE_RE.match(lines[j])
                    if pm:
                        page = int(to_halfwidth(pm.group(1)))
                        cur_chapter["sections"].append({
                            "section_no": m.group(1),
                            "title": m.group(2).strip().replace("　", " "),
                            "page": page,
                        })
                        if cur_chapter["start_page"] is None:
                            cur_chapter["start_page"] = page
                        i = j + 1
                        matched_section = True
                        break
        if matched_section:
            continue
        i += 1
    # 过滤掉 start_page 始终没能回填的章（B'类匹配到了章标题但后面一个 section 都没解析出来，
    # 说明这一章其实是格式误判，不是真实章节，不能带着 start_page=None 混进最终结果）
    return [c for c in chapters if c["start_page"] is not None]


def parse_toc_columnar(path: Path, first_page: int = 1, last_page: int = 20):
    """C类目录兜底：有些教材目录版式是"标题列 + 页码列"分栏排版，pymupdf 的 blocks
    输出会把两列完全拆散、集中放在一起（不相邻），A/B 类的"同行"或"相邻行"匹配规则
    都失效。实测发现这类版式有两种子情况，顺序还会反：
      C1（物理必修二）：页码列先出现，标题列紧随其后 "1\\n2\\n6\\n...\\n第五章 抛体运动\\n1.曲线运动\\n..."
      C2（物理必修一）：标题列先出现，页码列紧随其后，且章标题常与第一个子节标题
                        合并在同一个 block 里，如 "第一章 运动的描述\\n1.质点 参考系"
    用 blocks 模式找出最长的连续纯数字 block 序列（页码列），再看页码列前面还是
    后面有等长的"看起来像标题"的 block 序列，两种顺序都尝试。"""
    try:
        doc = fitz.open(str(path))
    except Exception:
        return []
    chapters = []
    for pgno in range(first_page - 1, min(last_page, doc.page_count)):
        raw_blocks = [restore_fz_italic(b[4]).strip() for b in doc[pgno].get_text("blocks")]
        raw_blocks = [b for b in raw_blocks if b]
        # 找到最长的连续纯数字block序列（页码列）——注意block内部可能有多行数字
        # 叠在一起被pymupdf合并成一个多行block，所以先展开成"每行都是纯数字"的判定
        def is_pure_page_block(b):
            lines = [to_halfwidth(x).strip() for x in b.split("\n") if x.strip()]
            return bool(lines) and all(PURE_PAGE_RE.match(x) for x in lines)

        best_start, best_len = -1, 0
        cur_start, cur_len = -1, 0
        for idx, b in enumerate(raw_blocks):
            if is_pure_page_block(b):
                if cur_len == 0:
                    cur_start = idx
                cur_len += 1
                if cur_len > best_len:
                    best_len, best_start = cur_len, cur_start
            else:
                cur_len = 0
        if best_len < 3:
            continue
        page_blocks = raw_blocks[best_start:best_start + best_len]
        pages = []
        for pb in page_blocks:
            pages.extend(int(to_halfwidth(x)) for x in pb.split("\n") if x.strip())
        # 标题列：先试"页码列之后"（C1），拿不到足够数量再试"页码列之前"（C2）
        title_blocks = raw_blocks[best_start + best_len:best_start + best_len + len(pages)]
        if len(title_blocks) < len(pages) * 0.6:
            title_blocks = raw_blocks[max(0, best_start - len(pages)):best_start]
        if len(title_blocks) < 3:
            continue
        # 把标题block按行拆开（C2会出现"第一章 xx\n1.子节"这种合并block，要拆成两条）
        title_lines = []
        for tb in title_blocks:
            for ln in tb.split("\n"):
                ln = ln.strip()
                if ln:
                    title_lines.append(ln)
        if len(title_lines) < len(pages) * 0.6:
            continue
        pi = 0
        for tl in title_lines:
            if pi >= len(pages):
                break
            m = re.match(r'^第([一二三四五六七八九十0-9０-９]+)\s*章[\s\u2003]*(.*)$', tl)
            if m:
                cur = {"chapter_no": m.group(1), "title": m.group(2).strip(), "start_page": pages[pi], "sections": []}
                chapters.append(cur)
                pi += 1
                continue
            m2 = re.match(r'^([0-9０-９]{1,2})[\.．:：]\s*(.+)$', tl)
            if m2 and chapters:
                chapters[-1]["sections"].append({
                    "section_no": m2.group(1), "title": m2.group(2).strip(), "page": pages[pi],
                })
                pi += 1
        if chapters and sum(len(c["sections"]) for c in chapters) > 0:
            doc.close()
            return chapters
        chapters = []
    doc.close()
    return []


def calibrate_offset(path: Path, chapters: list, max_probe: int = 15) -> int:
    """目录里印刷的页码，和 PDF 实际页序（pdftotext -f/-l 用的页号）之间往往有偏移——
    实测踩过：教材前面有封面/扉页/编者寄语等未计入印刷页码的页，导致目录写"第43页"
    但真实内容在 PDF 第48页（偏移+5）。不校准会导致 get_page_text() 提取到完全不相关
    的内容（曾用"万有引力"章节测试，印刷页43页提取出来的却是另一章"离心运动"的内容）。
    做法：拿目录第一章的"第X章"+标题，在印刷页码附近范围内搜索该组合字样真正出现的
    PDF 页。踩过两次假阳性坑：①目录列表里子节标题的残缺片段可能提前误命中（如"1. 曲线
    运动"导致"抛体运动"单独被命中）②有些书封面/扉页会把"第X章 标题"整行复现一次作为
    装饰（如封面下方印着"第五章 抛体运动 1"），这行后面紧跟的是印刷页码数字，不是正文
    内容——真正的章节正文页，标题后面接的应该是叙述性文字（长度可观、不是纯数字）。
    用这条规则过滤掉两类假阳性：标题命中后，看紧跟的一段文本是否为"纯数字+空白"（是则
    跳过，继续往后探测）。"""
    if not chapters:
        return 0
    first = chapters[0]
    target_page = first["start_page"]
    chapter_word = "第%s章" % first["chapter_no"]
    for offset in range(0, max_probe + 1):
        p = target_page + offset
        text = pdftotext_range(path, p, p)
        idx_chapter = text.find(chapter_word)
        if idx_chapter == -1:
            continue
        rest = text[idx_chapter + len(chapter_word):idx_chapter + len(chapter_word) + 60]
        if first["title"][:4] not in rest:
            continue
        # 排除"标题后紧跟目录列表格式（省略号+页码，或另起一行紧跟数字/编号）"的假阳性——
        # 真正的正文标题页，标题后面接的是叙述性长句；目录页则标题后紧跟省略号串
        # （"………………… １"）或换行后紧跟下一个编号子项（"４．１ ..."）。
        # 用"标题后 8 个字符内出现省略号/全角数字/换行+数字编号"作为目录特征判定。
        after_title = rest[rest.find(first["title"][:4]) + 4:]
        probe_window = after_title[:10]
        looks_like_toc = (
            "…" in probe_window or "．" in probe_window.lstrip(" \n\t\x0c")[:2]
            or probe_window.lstrip(" \t\x0c")[:1].isdigit()
            or probe_window.lstrip(" \t\x0c")[:1] in FULLWIDTH_DIGITS
        )
        if looks_like_toc:
            continue
        return offset
    return None  # 校准失败，页码可能不可靠


def _slice_after_toc_marker(text: str) -> str:
    """有些教材封面/扉页会把"第X章 标题"整行复现一次做装饰（实测踩过：B版数学必修一
    封面残留了"第五章 抛体运动"——这是模板复用出错，混入了物理教材的封面文字），出现在
    真正的"目录"二字之前。如果不先定位真正的目录起点，这类装饰文字会被误判成第一章，
    把真实的第一章挤掉（去重时按 chapter_no 覆盖，真章节反而被丢弃）。
    用"目录"独占一整行（前后是换行）的位置作为解析起点——不能用"最早出现的'目录'字样"，
    因为前言常有"通过本书的目录……"这种句子提前包含"目录"二字，会把前言正文误判成目录页
    （实测踩过：B版数学必修一前言最后一句"目录与每章的'本章导语'……"）。
    找不到独占一行的"目录"时，退化为原文本不做截断。"""
    m = re.search(r'(?:^|\n)\s*目\s{0,3}录\s*(?:\n|$)', text)
    return text[m.end():] if m else text


def build_one(path: Path, meta: dict, toc_scan_pages: int = 12):
    text = pdftotext_range(path, 1, toc_scan_pages)
    chapters = parse_toc(_slice_after_toc_marker(text))
    if not chapters and toc_scan_pages < 20:
        # 目录靠后（如有较长的编者寄语），扩大扫描范围重试一次
        text = pdftotext_range(path, 1, 20)
        chapters = parse_toc(_slice_after_toc_marker(text))
    if not chapters:
        # 极少数教材"目录"二字排版在目录列表末尾而非开头（实测踩过：人教版生物七年级下册，
        # 整页目录列表印在前面，标题"目 录"反而印在这页最后一行）——_slice_after_toc_marker
        # 会把真正的目录内容切掉。这种情况下退回不做切割，直接在原始扫描范围内解析。
        chapters = parse_toc(text)
    if not chapters or sum(len(c["sections"]) for c in chapters) == 0:
        # A/B 类都失败，或解析出章但一节都没有（很可能是 C 类"页码列+标题列"分栏
        # 排版，如实测的物理必修二），改用 blocks 模式的列对齐兜底解析
        columnar = parse_toc_columnar(path, 1, 20)
        if columnar and sum(len(c["sections"]) for c in columnar) > sum(len(c["sections"]) for c in chapters):
            chapters = columnar
    # 去重：扫描范围内如果目录本身超过一页、或某些书章节标题在目录之外的地方
    # （如章首页装饰）又被 parse_toc 误采一次，会出现同名章节重复——按 chapter_no
    # 去重，保留 sections 更多的那个（更完整的目录条目）
    dedup = {}
    for ch in chapters:
        key = ch["chapter_no"]
        if key not in dedup or len(ch["sections"]) > len(dedup[key]["sections"]):
            dedup[key] = ch
    chapters = list(dedup.values())
    offset = calibrate_offset(path, chapters) if chapters else 0
    if offset:
        for ch in chapters:
            ch["start_page"] += offset
            for sec in ch.get("sections", []):
                sec["page"] += offset
    # 补充 end_page：用"下一章的 start_page - 1"推算本章覆盖到哪一页；章内的
    # sections 同理用"下一节的 page - 1"推算，最后一节延伸到本章 end_page。
    # 有了范围才能一次性把整章/整节内容取全，而不是只看到开头一两段
    # （用户反馈"内容比教材少了很多"，根因之一就是之前只有 start_page，
    # lookup.py 调用方不知道该往后取几页，只能拍脑袋取1-2页）。
    for i, ch in enumerate(chapters):
        ch["end_page"] = chapters[i + 1]["start_page"] - 1 if i + 1 < len(chapters) else None
        secs = ch.get("sections", [])
        for j, sec in enumerate(secs):
            if j + 1 < len(secs):
                sec["end_page"] = secs[j + 1]["page"] - 1
            else:
                sec["end_page"] = ch["end_page"]
    return {
        "stage": meta["stage"],
        "subject": meta["subject"],
        "edition": meta["edition"],
        "grade": meta["grade"],
        "title": meta["title"],
        "path": str(path),
        "chapter_count": len(chapters),
        "page_offset": offset,
        "page_offset_calibrated": offset is not None,
        "chapters": chapters,
    }


def main():
    scope = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] == "--scope" else None
    full_scope = len(sys.argv) > 2 and sys.argv[2] == "all"

    with open(MANIFEST, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["status"] == "ok"]

    if not full_scope:
        rows = [r for r in rows if "人教" in r["edition"]]

    print(f"待索引册数: {len(rows)}")
    results = []
    failed = []
    for i, r in enumerate(rows):
        p = real_path(r["path"])
        if not p.exists():
            failed.append((r["title"], "文件不存在: %s" % p))
            continue
        try:
            entry = build_one(p, r)
            results.append(entry)
            if not entry["chapter_count"]:
                status = "无目录"
            elif not entry["page_offset_calibrated"]:
                status = "OK(%d章)但页码校准失败" % entry["chapter_count"]
            else:
                status = "OK(%d章,offset=%d)" % (entry["chapter_count"], entry["page_offset"])
        except Exception as e:
            failed.append((r["title"], str(e)))
            status = "FAIL: %s" % e
        print(f"[{i+1}/{len(rows)}] {r['stage']}/{r['subject']}/{r['grade']} {r['title'][:30]} -> {status}")

    out_file = OUT_DIR / ("index_all.json" if full_scope else "index_renjiao.json")
    out_file.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n索引已写入: {out_file}")
    print(f"成功: {len(results)} | 失败: {len(failed)}")
    no_toc = [r["title"] for r in results if r["chapter_count"] == 0]
    if no_toc:
        print(f"\n未解析出目录结构的书（{len(no_toc)}本，需要人工检查目录格式）：")
        for t in no_toc[:20]:
            print("  -", t)
    if failed:
        print("\n失败详情：")
        for t, e in failed[:20]:
            print("  -", t, "|", e)


if __name__ == "__main__":
    main()
