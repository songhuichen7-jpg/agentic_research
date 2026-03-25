"""Report Assembler — merges sections, charts, and citations into a final report.

Design doc §6.9: cover page, abstract, chapters, references.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from src.config.settings import REPORTS_DIR
from src.models import ChartAsset, Citation, DraftedSection

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


def assemble_report(
    topic: str,
    normalized_topic: str,
    sections: list[DraftedSection],
    chart_assets: list[ChartAsset],
    run_id: str = "",
) -> str:
    """Assemble the final Markdown report.

    Returns the full Markdown string and writes it to data/reports/.
    """
    sections_sorted = sorted(sections, key=lambda s: s.order)
    all_citations = _deduplicate_citations(sections_sorted)

    # Build chart lookup: chart_id → asset
    chart_map: dict[str, ChartAsset] = {}
    for asset in chart_assets:
        if asset.status == "ok" and asset.file_path:
            chart_map[asset.chart_id] = asset

    parts: list[str] = []

    # ── Cover page ───────────────────────────────────────────
    parts.append(f"# {normalized_topic}\n")
    parts.append(f"> 生成日期: {datetime.now().strftime('%Y-%m-%d')}")
    parts.append(f"> 研究主题: {topic}")
    if run_id:
        parts.append(f"> 运行编号: {run_id}")
    parts.append("")
    parts.append("---\n")

    # ── Table of contents ────────────────────────────────────
    parts.append("## 目录\n")
    for i, sec in enumerate(sections_sorted, 1):
        parts.append(f"{i}. [{sec.title}](#{_slug(sec.title)})")
    parts.append(f"{len(sections_sorted) + 1}. [参考资料](#参考资料)")
    parts.append("")
    parts.append("---\n")

    # ── Sections ─────────────────────────────────────────────
    chart_counter = 0
    placed_chart_ids: set[str] = set()

    for sec in sections_sorted:
        parts.append(f"## {sec.title}\n")
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
            parts.append(f"*图{chart_counter}: {asset.spec.title if asset.spec else ''}*\n")

        parts.append("")

    # ── References ───────────────────────────────────────────
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

    # ── Disclaimer ───────────────────────────────────────────
    parts.append("---\n")
    parts.append("*本报告由 AI 自动生成，数据和结论仅供参考，不构成投资建议。*\n")

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
