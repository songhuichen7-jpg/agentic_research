"""
Phase 1 MVP — Full report generation via LangGraph.

Usage:
  python scripts/run_report.py "人形机器人"
  python scripts/run_report.py "低空经济"
"""

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import get_run, list_runs
from src.graph.workflow import run_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_report")


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "人形机器人"

    print(f"\n{'='*60}")
    print(f"  多模态行业研报 Agent — Phase 1 MVP")
    print(f"  行业主题: {topic}")
    print(f"{'='*60}\n")

    t0 = time.time()
    result = run_report(topic)
    elapsed = time.time() - t0

    # ── Print summary ────────────────────────────────────────
    status = result.get("status", "unknown")
    normalized = result.get("normalized_topic", topic)
    sections = result.get("drafted_sections", [])
    chart_assets = result.get("chart_assets", [])
    ok_charts = [a for a in chart_assets if a.status == "ok"]
    qc = result.get("qc_result")
    report_md = result.get("final_report_md", "")

    print(f"\n{'='*60}")
    print(f"  生成完毕")
    print(f"{'='*60}")
    print(f"  状态:        {status}")
    print(f"  耗时:        {elapsed:.1f} 秒")
    print(f"  规范化主题:  {normalized}")
    print(f"  章节数:      {len(sections)}")
    print(f"  图表数:      {len(ok_charts)} ok / {len(chart_assets)} total")
    if qc:
        print(f"  质检结果:    {qc.overall_status.value} — {qc.summary}")
        for sq in qc.sections:
            mark = "✓" if sq.status.value == "pass" else ("⚠" if sq.status.value == "warn" else "✗")
            issues_str = f" ({'; '.join(sq.issues)})" if sq.issues else ""
            print(f"    {mark} {sq.section_title}{issues_str}")
    print(f"  报告长度:    {len(report_md)} 字符")

    # DB history
    run_id = result.get("run_id", "")
    db_run = get_run(run_id) if run_id else None
    if db_run:
        print(f"  数据库记录:  run_id={db_run['run_id']}, elapsed={db_run['elapsed_sec']:.1f}s")

    # Token usage
    token_usage = result.get("token_usage", {})
    if token_usage:
        print(f"  Token 用量:")
        for role, stats in token_usage.items():
            total = stats.get("total_tokens", 0)
            calls = stats.get("calls", 0)
            print(f"    {role}: {total:,} tokens ({calls} calls)")

    from src.config.settings import REPORTS_DIR
    pdf_path = REPORTS_DIR / f"report_{run_id}.pdf"
    md_path = REPORTS_DIR / f"report_{run_id}.md"
    if pdf_path.exists():
        print(f"  PDF 报告:    {pdf_path}")
    if md_path.exists():
        print(f"  Markdown:    {md_path}")

    print(f"{'='*60}\n")

    # Print first 1500 chars of report
    print("── 报告预览 (前 1500 字) ──\n")
    print(report_md[:1500])
    if len(report_md) > 1500:
        print(f"\n... (共 {len(report_md)} 字符，完整报告见 data/reports/)\n")


if __name__ == "__main__":
    main()
