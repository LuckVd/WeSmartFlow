"""
SmartSearch 数据模型

所有源 adapter 的返回结果统一为 SearchResult，
Router 的决策输出为 SearchPlan。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    """单条搜索结果（所有源统一格式）"""

    title: str
    content: str  # 摘要/正文片段（≤500 字）
    url: str
    source_id: str  # 来自哪个源 adapter（如 "tavily", "duckduckgo", "arxiv"）
    score: float = 0.5  # 原始相关度（源给的）
    credibility: float = 0.5  # 来源可信度（Filter 层打的）
    timestamp: Optional[str] = None  # 内容发布时间（ISO 格式，可为 None）
    modality: str = "text"  # text / image / video
    language: str = "unknown"  # zh / en / unknown
    metadata: dict = field(default_factory=dict)  # 源特有字段（如 arXiv 作者）

    # Filter 阶段填充
    is_duplicate: bool = False  # 是否被标记为重复
    verification_status: str = "unverified"  # verified / unverified / disputed
    final_score: float = 0.0  # 最终综合分（用于排序）


@dataclass
class SearchPlan:
    """Router 输出的检索计划"""

    sources: list[str]  # 要调用哪些源 ID
    sub_queries: dict[str, str]  # 每个源的定制 query
    complexity: str = "medium"  # simple / medium / complex
    expected_count: int = 10  # 期望总返回条数
    reason: str = ""  # Router 的决策理由（调试用）


@dataclass
class SmartSearchResult:
    """SmartSearch 最终输出"""

    query: str  # 原始用户 query
    results: list[SearchResult]  # 筛选排序后的 top-k
    plan: SearchPlan  # 路由计划（可溯源）
    total_raw: int = 0  # 筛选前原始条数
    total_filtered: int = 0  # 筛选后条数
    latency_ms: int = 0  # 总耗时
    errors: list[str] = field(default_factory=list)  # 各源错误信息

    def to_markdown(self) -> str:
        """转成结构化 Markdown（喂给 Agent 用）— 文本/图片/视频分组展示"""
        lines = []
        lines.append(f"## 搜索结果：「{self.query}」")
        lines.append(
            f"*检索 {len(self.plan.sources)} 个源，"
            f"召回 {self.total_raw} 条，筛选后 {self.total_filtered} 条，"
            f"耗时 {self.latency_ms}ms*\n"
        )

        text_results = [r for r in self.results if r.modality == "text"]
        image_results = [r for r in self.results if r.modality == "image"]
        video_results = [r for r in self.results if r.modality == "video"]

        # ── 文本 ──────────────────────────────────────────────────────
        if text_results:
            lines.append("### 📄 文本资料")
            for i, r in enumerate(text_results, 1):
                stars = "⭐" * max(1, min(5, int(r.credibility * 5)))
                vmark = {"verified": "✅", "disputed": "⚠️"}.get(
                    r.verification_status, ""
                )
                lines.append(f"\n**[{i}] {r.title}** {vmark}")
                lines.append(
                    f"来源: `{r.source_id}` | 可信度: {stars} | 语言: {r.language}"
                )
                if r.timestamp:
                    lines.append(f"时间: {r.timestamp}")
                lines.append(f"\n{r.content}\n")
                if r.url:
                    lines.append(f"🔗 {r.url}")

        # ── 图片 ──────────────────────────────────────────────────────
        if image_results:
            lines.append("\n### 🖼 相关图片")
            for r in image_results:
                thumb = r.metadata.get("thumb_url") or r.url
                page = r.metadata.get("page_url") or r.url
                license_ = r.metadata.get("license", "")
                desc = r.content.replace("[图片] ", "").strip()
                lines.append(f"\n- **{r.title}**")
                if desc:
                    lines.append(f"  {desc[:200]}")
                lines.append(f"  🖼 图片: {thumb}")
                if page and page != thumb:
                    lines.append(f"  🔗 页面: {page}")
                if license_:
                    lines.append(f"  📋 许可: {license_}")

        # ── 视频 ──────────────────────────────────────────────────────
        if video_results:
            lines.append("\n### 🎬 相关视频")
            for r in video_results:
                thumb = r.metadata.get("thumbnail", "")
                embed = r.metadata.get("embed_url", "")
                channel = r.metadata.get("channel", "")
                desc = r.content.replace("[视频] ", "").strip()
                lines.append(f"\n- **{r.title}**")
                if channel:
                    lines.append(f"  频道: {channel}")
                if desc:
                    lines.append(f"  {desc[:200]}")
                lines.append(f"  🎬 播放: {r.url}")
                if embed:
                    lines.append(f"  🔗 嵌入: {embed}")
                if thumb:
                    lines.append(f"  🖼 封面: {thumb}")

        # ── 汇总表 ────────────────────────────────────────────────────
        if self.results:
            lines.append("\n---")
            lines.append("| # | 标题 | 来源 | 模态 | 可信度 |")
            lines.append("|---|---|---|---|---|")
            modal_icon = {"text": "📄", "image": "🖼", "video": "🎬"}
            for i, r in enumerate(self.results, 1):
                icon = modal_icon.get(r.modality, "📄")
                lines.append(
                    f"| {i} | {r.title[:35]} | {r.source_id} | "
                    f"{icon} {r.modality} | {r.credibility:.0%} |"
                )

        if self.errors:
            lines.append("\n---\n⚠️ 部分源失败：" + "; ".join(self.errors))

        return "\n".join(lines)

    def to_agent_text(self) -> str:
        """精简版（给 Agent context 用，控制 token 消耗）"""
        text_results = [r for r in self.results if r.modality == "text"]
        image_results = [r for r in self.results if r.modality == "image"]
        video_results = [r for r in self.results if r.modality == "video"]

        lines = [
            f"【多源搜索结果】共 {self.total_filtered} 条 | "
            f"文本:{len(text_results)} 图片:{len(image_results)} 视频:{len(video_results)} | "
            f"{self.latency_ms}ms\n"
        ]

        # 文本（最多 6 条）
        for i, r in enumerate(text_results[:6], 1):
            vmark = {"verified": "[多源验证]", "disputed": "[有争议]"}.get(
                r.verification_status, ""
            )
            lines.append(
                f"[文本{i}] {r.title} {vmark}\n"
                f"    {r.content[:300]}\n"
                f"    来源:{r.source_id} | 可信:{r.credibility:.0%} | {r.url}"
            )

        # 图片（最多 3 条）
        if image_results:
            lines.append("\n【相关图片】")
            for r in image_results[:3]:
                thumb = r.metadata.get("thumb_url") or r.url
                desc = r.content.replace("[图片] ", "")[:100]
                lines.append(f"🖼 {r.title}: {desc}\n   图片URL: {thumb}")

        # 视频（最多 3 条）
        if video_results:
            lines.append("\n【相关视频】")
            for r in video_results[:3]:
                channel = r.metadata.get("channel", "")
                desc = r.content.replace("[视频] ", "")[:100]
                lines.append(
                    f"🎬 {r.title}"
                    + (f" | {channel}" if channel else "")
                    + f"\n   {desc}\n   {r.url}"
                )

        return "\n\n".join(lines)
