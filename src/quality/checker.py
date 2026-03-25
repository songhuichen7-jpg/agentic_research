"""Quality Gate — automated checks before final report output.

Design doc §6.10: structure, citation, chart, duplication, time consistency.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.models import ChartAsset, DraftedSection, QCStatus, QualityResult, SectionQC

logger = logging.getLogger(__name__)


def check_report(
    sections: list[DraftedSection],
    chart_assets: list[ChartAsset],
    min_sections: int = 4,
    min_charts: int = 3,
) -> QualityResult:
    """Run quality checks and return a QualityResult."""
    section_qcs: list[SectionQC] = []
    issues_global: list[str] = []

    # ── 1. Structure completeness ────────────────────────────
    if len(sections) < min_sections:
        issues_global.append(f"章节数不足: {len(sections)}/{min_sections}")

    # ── 2. Per-section checks ────────────────────────────────
    for sec in sections:
        issues: list[str] = []

        # Empty content
        if len(sec.markdown.strip()) < 100:
            issues.append("章节内容过短（<100字）")

        # Citation check
        citation_refs = re.findall(r"\[c\d+\]", sec.markdown)
        if not citation_refs and not sec.citations:
            issues.append("缺少数据引用")

        # Duplication / fluff heuristic: repeated sentences
        sentences = [s.strip() for s in re.split(r"[。！？]", sec.markdown) if len(s.strip()) > 10]
        if sentences:
            unique = set(sentences)
            if len(unique) < len(sentences) * 0.7:
                issues.append("存在重复语句")

        status = QCStatus.PASS
        if issues:
            status = QCStatus.WARN if len(issues) <= 1 else QCStatus.FAIL

        section_qcs.append(SectionQC(
            section_title=sec.title,
            status=status,
            issues=issues,
        ))

    # ── 3. Chart asset check ─────────────────────────────────
    ok_charts = [a for a in chart_assets if a.status == "ok"]
    failed_charts = [a for a in chart_assets if a.status != "ok"]
    if len(ok_charts) < min_charts:
        issues_global.append(f"图表数不足: {len(ok_charts)}/{min_charts}")
    if failed_charts:
        issues_global.append(f"{len(failed_charts)} 张图表渲染失败")

    for asset in ok_charts:
        if asset.file_path and not Path(asset.file_path).exists():
            issues_global.append(f"图表文件不存在: {asset.file_path}")

    # ── Overall ──────────────────────────────────────────────
    any_fail = any(sq.status == QCStatus.FAIL for sq in section_qcs)
    any_warn = any(sq.status == QCStatus.WARN for sq in section_qcs) or issues_global

    if any_fail:
        overall = QCStatus.FAIL
    elif any_warn:
        overall = QCStatus.WARN
    else:
        overall = QCStatus.PASS

    summary_parts = [f"章节: {len(sections)}", f"图表: {len(ok_charts)}"]
    if issues_global:
        summary_parts.append(f"全局问题: {'; '.join(issues_global)}")

    result = QualityResult(
        overall_status=overall,
        sections=section_qcs,
        summary=" | ".join(summary_parts),
    )

    logger.info("QC result: %s — %s", overall.value, result.summary)
    return result
