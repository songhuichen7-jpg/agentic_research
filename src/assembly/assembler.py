"""Report Assembler — merges sections, charts, citations into an institutional-style report.

Structure:
  1. Cover page (professional layout with title, date, rating)
  2. Table of contents
  3. Executive summary (thesis, highlights, key metrics table, rating)
  4. Main sections (with embedded charts)
  5. References
  6. Disclaimer
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from src.config.settings import REPORTS_DIR
from src.models import ChartAsset, Citation, DraftedSection
from src.writers.executive_summary import (
    format_executive_summary_markdown,
    generate_executive_summary,
)

logger = logging.getLogger(__name__)


def _deduplicate_citations(sections: list[DraftedSection]) -> list[Citation]:
    """Collect all citations across sections, deduplicate by doc_id."""
    seen: dict[str, Citation] = {}
    for sec in sections:
        for c in sec.citations:
            key = c.doc_id or c.citation_id
            if key not in seen:
                seen[key] = c
    return list(seen.values())


def _build_cover_html(normalized_topic: str, topic: str, run_id: str, rating: str = "") -> str:
    """Build the HTML cover page block (inserted as raw HTML in the Markdown)."""
    date_str = datetime.now().strftime("%Y年%m月%d日")
    date_short = datetime.now().strftime("%Y.%m")

    rating_display = rating if rating else "深度研究"

    return f"""<div class="cover">
  <div class="cover__brand">
    <div class="cover__brand-name">RESEARCH · 研究报告</div>
    <div class="cover__brand-tag">INSTITUTIONAL RESEARCH<br>行业深度研究</div>
  </div>
  <div class="cover__title-block">
    <div class="cover__label">INDUSTRY DEEP DIVE · 行业深度</div>
    <h1 class="cover__main-title">{normalized_topic}</h1>
    <div class="cover__rule"></div>
    <div class="cover__subtitle">{topic} · {date_short}</div>
  </div>
  <div class="cover__meta">
    <div class="cover__meta-item">
      <div class="cover__meta-label">报告日期</div>
      <div class="cover__meta-value">{date_str}</div>
    </div>
    <div class="cover__meta-item">
      <div class="cover__meta-label">研究类型</div>
      <div class="cover__meta-value">{rating_display}</div>
    </div>
    <div class="cover__meta-item">
      <div class="cover__meta-label">报告编号</div>
      <div class="cover__meta-value">{run_id or "—"}</div>
    </div>
  </div>
</div>
"""


def assemble_report(
    topic: str,
    normalized_topic: str,
    sections: list[DraftedSection],
    chart_assets: list[ChartAsset],
    run_id: str = "",
) -> str:
    """Assemble the final Markdown report with institutional research format.

    Returns the full Markdown string and writes it to data/reports/.
    """
    sections_sorted = sorted(sections, key=lambda s: s.order)
    all_citations = _deduplicate_citations(sections_sorted)

    # Build chart lookup: chart_id → asset
    chart_map: dict[str, ChartAsset] = {}
    for asset in chart_assets:
        if asset.status == "ok" and asset.file_path:
            chart_map[asset.chart_id] = asset

    # Generate executive summary (can be None if LLM fails)
    exec_summary = generate_executive_summary(normalized_topic or topic, sections_sorted)

    parts: list[str] = []

    # ── 1. Cover page (HTML block — rendered only in PDF) ───
    rating = exec_summary.get("rating", "") if exec_summary else ""
    cover_html = _build_cover_html(normalized_topic, topic, run_id, rating)
    parts.append(cover_html)

    # ── 2. Table of contents ────────────────────────────────
    parts.append("## 目录\n")
    toc_items: list[str] = []
    if exec_summary:
        toc_items.append("执行摘要")
    for sec in sections_sorted:
        toc_items.append(sec.title)
    toc_items.append("参考资料")

    for title in toc_items:
        parts.append(f"1. [{title}](#{_slug(title)})")
    parts.append("")
    parts.append("---\n")

    # ── 3. Executive summary ────────────────────────────────
    if exec_summary:
        parts.append(format_executive_summary_markdown(exec_summary, normalized_topic))
        parts.append("")
        parts.append("---\n")
    else:
        logger.warning("No executive summary generated — skipping")

    # ── 4. Main sections with embedded charts ──────────────
    chart_counter = 0
    placed_chart_ids: set[str] = set()

    for sec in sections_sorted:
        parts.append(f"## {sec.title}\n")
        if sec.evidence_count == 0:
            parts.append("> **注意**：本章节缺乏数据来源支撑，内容仅供参考。\n")
        parts.append(sec.markdown)
        parts.append("")

        # Insert charts belonging to this section (by source_ref match)
        sec_charts = [
            a
            for a in chart_assets
            if a.status == "ok"
            and a.spec
            and a.chart_id not in placed_chart_ids
            and any(ref in [c.citation_id for c in sec.citations] for ref in (a.spec.source_refs or []))
        ]

        # If no source_ref match, take the first unplaced chart
        if not sec_charts:
            unplaced = [a for a in chart_assets if a.status == "ok" and a.chart_id not in placed_chart_ids]
            if unplaced:
                sec_charts = [unplaced[0]]

        for asset in sec_charts:
            placed_chart_ids.add(asset.chart_id)
            chart_counter += 1
            rel_path = Path(asset.file_path).name
            caption = asset.spec.caption if asset.spec else ""
            parts.append(f"![图{chart_counter}: {caption}](charts/{rel_path})")
            parts.append(f"*图 {chart_counter}　{asset.spec.title if asset.spec else ''}*\n")

        parts.append("")

    # ── 5. References ───────────────────────────────────────
    parts.append("---\n")
    parts.append("## 参考资料\n")
    if all_citations:
        for i, c in enumerate(all_citations, 1):
            entry = f"{i}. {c.title}"
            if c.published_at:
                entry += f", {c.published_at}"
            if c.source_name:
                entry += f", {c.source_name}"
            if c.url:
                entry += f", [{c.url}]({c.url})"
            parts.append(entry)
    else:
        parts.append("*暂无参考资料*")
    parts.append("")

    # ── 6. Disclaimer ───────────────────────────────────────
    parts.append("---\n")
    parts.append(
        '<div class="disclaimer">'
        "本报告由 AI 系统基于公开信息自动生成，所涉及数据、观点及结论仅供参考，"
        "不构成任何投资建议。投资有风险，决策需谨慎。"
        "报告使用者应自行判断并承担相应责任。"
        "</div>\n"
    )

    report_md = "\n".join(parts)

    # Write to file
    out_dir = REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"report_{run_id or datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path = out_dir / filename
    out_path.write_text(report_md, encoding="utf-8")
    logger.info("Report written to %s (%d chars)", out_path, len(report_md))

    return report_md


def _slug(text: str) -> str:
    """Simple slug for markdown anchor links."""
    return text.lower().replace(" ", "-").replace("　", "-")
