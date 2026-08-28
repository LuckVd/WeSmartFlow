#!/usr/bin/env python3
"""
教材索引体验页（独立小服务，不影响 live_science 主服务 8767 端口）
================================================================
给用户一个可视化界面来体验 textbook_index 的效果：
  - 输入关键词 -> 展示命中的教材/章节/页码
  - 点击某条命中 -> 现场用 pdftotext 提取那几页原文给你看

这是"体验/验收"用途，不是给生成管线调用的正式接口（生成管线直接
import lookup.py 里的 find_chapter/get_page_text 函数即可，不需要走 HTTP）。
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from lookup import find_chapter, get_page_text, hit_range, _load_index  # noqa: E402

PORT = 8770

PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>课内知识索引 · 体验</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #14121c; color: #eee7f5; padding: 32px 24px 60px;
  }
  .wrap { max-width: 900px; margin: 0 auto; }
  h1 { font-size: 20px; font-weight: 500; margin: 0 0 6px; color: #f4eaff; }
  .sub { color: #9a8fb5; font-size: 13px; margin-bottom: 24px; }
  .search-box { display: flex; gap: 10px; margin-bottom: 8px; }
  input[type=text] {
    flex: 1; padding: 11px 14px; border-radius: 10px; border: 1px solid #3a3350;
    background: #1e1a2b; color: #f4eaff; font-size: 14px; outline: none;
  }
  input[type=text]:focus { border-color: #8a6fd8; }
  button {
    padding: 11px 20px; border-radius: 10px; border: none; cursor: pointer;
    background: #6c4fc9; color: #fff; font-size: 14px; font-weight: 500;
  }
  button:hover { background: #7c5fd9; }
  .stat { color: #7a6f95; font-size: 12px; margin-bottom: 18px; }
  .hit {
    background: #1e1a2b; border: 1px solid #2c2640; border-radius: 12px;
    padding: 14px 16px; margin-bottom: 10px; cursor: pointer; transition: border-color .15s;
  }
  .hit:hover { border-color: #6c4fc9; }
  .hit .tag {
    display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 5px;
    background: #2c2640; color: #b8a8e0; margin-right: 8px;
  }
  .hit .book { font-size: 13px; color: #9a8fb5; margin-top: 4px; }
  .hit .chapter { font-size: 15px; font-weight: 500; margin-top: 6px; color: #f4eaff; cursor: pointer; }
  .hit .chapter:hover { color: #cfc0ff; }
  .hit .page { color: #7a6f95; font-size: 12px; margin-top: 2px; }
  .seclist { margin-top: 10px; padding-top: 10px; border-top: 1px solid #2c2640; }
  .seclist .sec {
    display: inline-block; font-size: 12px; color: #b8a8e0; background: #241f38;
    padding: 4px 9px; border-radius: 6px; margin: 0 6px 6px 0;
  }
  .seclist .sec i { color: #6a6080; font-style: normal; margin-left: 4px; }
  .preview {
    display: none; margin-top: 10px; padding: 14px; background: #14111e;
    border-radius: 8px; border: 1px solid #2c2640; font-size: 13px; line-height: 1.8;
    white-space: pre-wrap; color: #d8cfe8; max-height: 480px; overflow-y: auto;
  }
  .empty { text-align: center; color: #6a6080; padding: 40px 0; font-size: 13px; }
  .examples { margin-top: 8px; }
  .examples span {
    display: inline-block; font-size: 12px; color: #8a7fb0; background: #221d33;
    padding: 4px 10px; border-radius: 6px; margin-right: 8px; margin-bottom: 6px;
    cursor: pointer; border: 1px solid #2c2640;
  }
  .examples span:hover { border-color: #6c4fc9; color: #cfc0ff; }
  .loading { color: #8a7fb0; font-size: 13px; padding: 20px 0; text-align: center; }
</style>
</head>
<body>
<div class="wrap">
  <h1>课内知识索引 · 体验</h1>
  <div class="sub">在人教系教材目录索引里搜关键词，点开看命中章节的真实课本原文</div>
  <div class="search-box">
    <input type="text" id="kw" placeholder="输入知识点关键词，如：万有引力、数列、遗传、有理数……" />
    <button onclick="doSearch()">搜索</button>
  </div>
  <div class="examples">
    <span onclick="quick('万有引力')">万有引力</span>
    <span onclick="quick('数列')">数列</span>
    <span onclick="quick('细胞')">细胞</span>
    <span onclick="quick('遗传')">遗传</span>
    <span onclick="quick('有理数')">有理数</span>
    <span onclick="quick('化学反应')">化学反应</span>
  </div>
  <div id="stat" class="stat"></div>
  <div id="results"></div>
</div>
<script>
function quick(kw){ document.getElementById('kw').value = kw; doSearch(); }
document.getElementById('kw').addEventListener('keydown', e => { if(e.key==='Enter') doSearch(); });

async function doSearch(){
  const kw = document.getElementById('kw').value.trim();
  if(!kw) return;
  document.getElementById('results').innerHTML = '<div class="loading">搜索中…</div>';
  const res = await fetch('/api/search?kw=' + encodeURIComponent(kw));
  const data = await res.json();
  render(data);
}

function render(data){
  const box = document.getElementById('results');
  document.getElementById('stat').textContent =
    `命中 ${data.hits.length} 处（已索引 ${data.total_books} 本人教系教材）`;
  if(data.hits.length === 0){
    box.innerHTML = '<div class="empty">没有命中，换个关键词试试</div>';
    return;
  }
  box.innerHTML = data.hits.map((h, i) => `
    <div class="hit">
      <span class="tag">${h.stage}</span><span class="tag">${h.subject}</span><span class="tag">${h.edition}</span>
      <div class="book">${h.title}</div>
      <div class="chapter" onclick="loadPreview(${i}, this)">${h.chapter_title}${h.chapter_title!==h.location ? ' › '+h.location : ''}</div>
      <div class="page">第 ${h.page}${h.end_page ? '-'+h.end_page : ''} 页（已校准页码偏移，点击展开原文）</div>
      ${h.sections.length ? `<div class="seclist">${h.sections.map(s =>
        `<span class="sec">${s.title} <i>p${s.page}${s.end_page?('-'+s.end_page):''}</i></span>`).join('')}</div>` : ''}
      <div class="preview" id="preview-${i}"></div>
    </div>
  `).join('');
  window._hits = data.hits;
}

async function loadPreview(i, el){
  const pv = document.getElementById('preview-' + i);
  const isShown = pv.style.display === 'block';
  document.querySelectorAll('.preview').forEach(p => p.style.display = 'none');
  if(isShown) return;
  pv.style.display = 'block';
  pv.textContent = '正在提取课本原文…';
  const h = window._hits[i];
  const endPage = h.end_page || (h.page + 3);
  const res = await fetch('/api/preview?path=' + encodeURIComponent(h.path) + '&page=' + h.page + '&end_page=' + endPage);
  const data = await res.json();
  pv.textContent = data.text || '（未能提取到文字，可能是纯图片扫描页）';
}

doSearch.kw = '';
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = PAGE_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/search":
            qs = parse_qs(parsed.query)
            kw = (qs.get("kw") or [""])[0].strip()
            hits = find_chapter(kw) if kw else []
            out = []
            for h in hits[:30]:
                loc = h["section"]["title"] if h["section"] else h["chapter"]["title"]
                start, end = hit_range(h)
                sections = h["chapter"].get("sections") or []
                out.append({
                    "stage": h["stage"], "subject": h["subject"], "edition": h["edition"],
                    "title": h["title"], "location": loc, "page": start, "end_page": end,
                    "path": h["path"], "chapter_title": h["chapter"]["title"],
                    "sections": [{"title": s["title"], "page": s["page"], "end_page": s.get("end_page")}
                                 for s in sections],
                })
            self._json({"hits": out, "total_books": len(_load_index())})
            return

        if parsed.path == "/api/preview":
            qs = parse_qs(parsed.query)
            path = (qs.get("path") or [""])[0]
            try:
                page = int((qs.get("page") or ["1"])[0])
            except ValueError:
                page = 1
            try:
                end_page = int((qs.get("end_page") or [str(page + 1)])[0])
            except ValueError:
                end_page = page + 1
            text = get_page_text(path, page, min(end_page, page + 20))
            self._json({"text": text[:6000]})
            return

        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    print(f"课内知识索引体验页 → http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
