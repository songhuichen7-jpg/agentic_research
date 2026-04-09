"""Report Reviser — handles multi-turn revision of generated reports.

Single LLM call: revise the report AND output a change summary.
Intent detection via keyword matching (fast, no extra LLM call).
Research path only when user explicitly requests new data.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.config.llm import get_writer_llm
from src.config.settings import BOCHA_API_KEY, REPORTS_DIR
from src.connectors.bocha_search import BochaSearchConnector

logger = logging.getLogger(__name__)

# Keywords that trigger the research (search + rewrite) path
_RESEARCH_KEYWORDS = re.compile(
    r"补充|搜索|查找|最新|新增数据|更新数据|添加数据|新的资料|查一下|找一下|加入.*数据"
)

_REVISE_PROMPT = """\
你是专业的行业研究分析师。用户已经有一份行业研报，现在要求你修改它。

## 当前研报全文
{report}

## 用户修改要求
{message}
{extra_context}
## 输出要求
请按以下格式输出，严格遵守分隔符：

===SUMMARY===
用 2-4 个要点说明你做了哪些修改，每行一个，用 "- " 开头。

===REPORT===
输出修改后的完整研报（Markdown 格式，包含未修改的部分）。
只修改需要改的部分，保留已有引用标记 [c1] 等。
"""


def _needs_research(message: str) -> bool:
    """Check if the user message requests new data (keyword-based, no LLM call)."""
    return bool(_RESEARCH_KEYWORDS.search(message))


def _search_new_evidence(topic: str, message: str) -> str:
    """Search for supplementary evidence via Bocha."""
    if not BOCHA_API_KEY:
        logger.warning("BOCHA_API_KEY not set, skipping research for revision")
        return ""

    # Build simple queries from topic + message keywords
    queries = [
        f"{topic} {message[:20]}",
        topic,
    ]
    try:
        bocha = BochaSearchConnector(delay=0.5, fetch_fulltext=True)
        docs = bocha.search_and_fetch(queries, results_per_query=3)
    except Exception as e:
        logger.warning("Bocha search failed during revision: %s", e)
        return ""

    if not docs:
        return ""

    parts = []
    for i, doc in enumerate(docs[:5], 1):
        text = doc.content_text[:600] if doc.content_text else ""
        if text:
            parts.append(f"[新资料{i}] {doc.title}\n{text}")
    return "\n\n".join(parts)


def _parse_response(raw: str) -> tuple[str, str]:
    """Parse LLM response into (summary, revised_report)."""
    # Try to split on markers
    if "===REPORT===" in raw:
        parts = raw.split("===REPORT===", 1)
        report = parts[1].strip()
        summary_part = parts[0]
        if "===SUMMARY===" in summary_part:
            summary = summary_part.split("===SUMMARY===", 1)[1].strip()
        else:
            summary = summary_part.strip()
    else:
        # No markers — treat the whole thing as the report
        report = raw.strip()
        summary = ""

    # Clean up markdown fences
    for fence in ("```markdown", "```md", "```"):
        if report.startswith(fence):
            report = report[len(fence):].strip()
    if report.endswith("```"):
        report = report[:-3].strip()

    return summary, report


def revise_report(
    run_id: str,
    message: str,
    topic: str = "",
) -> dict:
    """Revise an existing report based on user instruction.

    Returns {"summary": str, "intent": str, "success": bool, "error"?: str}.
    """
    report_path = REPORTS_DIR / f"report_{run_id}.md"
    if not report_path.exists():
        return {"summary": "", "intent": "edit", "success": False, "error": "报告文件不存在"}

    current_report = report_path.read_text(encoding="utf-8")

    # Save current version as backup before overwriting
    existing_versions = sorted(report_path.parent.glob(f"report_{run_id}_v*.md"))
    next_v = len(existing_versions) + 1
    backup_path = report_path.parent / f"report_{run_id}_v{next_v}.md"
    backup_path.write_text(current_report, encoding="utf-8")
    logger.info("Backed up v%d: %s", next_v, backup_path.name)

    # Determine intent via keywords (instant, no LLM call)
    intent = "research" if _needs_research(message) else "edit"
    logger.info("Revision intent=%s for: %s", intent, message[:60])

    # If research: search for new evidence
    extra_context = ""
    if intent == "research":
        evidence_text = _search_new_evidence(topic or "行业研报", message)
        if evidence_text:
            extra_context = f"\n## 新搜索到的补充资料（请整合到研报中）\n{evidence_text}\n"
        else:
            # No new data found — fall back to edit
            extra_context = "\n（注意：未能搜索到新的补充资料，请基于已有内容尽力修改。）\n"
            intent = "edit"

    # Single LLM call: revise + summarize
    prompt = _REVISE_PROMPT.format(
        report=current_report,
        message=message,
        extra_context=extra_context,
    )

    llm = get_writer_llm(temperature=0.3)
    resp = llm.invoke(prompt)
    raw = resp.content.strip()

    summary, revised = _parse_response(raw)

    if not revised or len(revised) < 100:
        logger.error("Revision produced empty or too-short output (%d chars)", len(revised))
        return {"summary": "", "intent": intent, "success": False, "error": "修改结果异常，请重试"}

    # Fallback summary if LLM didn't provide one
    if not summary:
        summary = f"- 已根据要求「{message[:50]}」修改研报"

    # Save revised report
    report_path.write_text(revised, encoding="utf-8")
    logger.info("Report revised (intent=%s, run_id=%s): %d → %d chars", intent, run_id, len(current_report), len(revised))

    return {
        "summary": summary,
        "intent": intent,
        "old_version": next_v,
        "new_version": next_v + 1,
        "success": True,
    }
