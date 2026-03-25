"""PDF export — converts the final Markdown report to a styled PDF.

Pipeline: Markdown → HTML (via markdown lib) → PDF (via WeasyPrint).
Image paths in the markdown are resolved to absolute paths for embedding.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.assembly.html_template import REPORT_HTML_TEMPLATE
from src.config.settings import CHARTS_DIR, REPORTS_DIR

logger = logging.getLogger(__name__)


def _md_to_html_body(md_text: str, run_id: str = "") -> str:
    """Lightweight Markdown → HTML conversion sufficient for our report structure."""
    lines = md_text.splitlines()
    html_parts: list[str] = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # Headings (add id for TOC anchor links)
        if stripped.startswith("# ") and not stripped.startswith("## "):
            text = stripped[2:]
            html_parts.append(f'<h1 id="{text}">{_inline(text)}</h1>')
            continue
        if stripped.startswith("## "):
            text = stripped[3:]
            html_parts.append(f'<h2 id="{text}">{_inline(text)}</h2>')
            continue
        if stripped.startswith("### "):
            text = stripped[4:]
            html_parts.append(f'<h3 id="{text}">{_inline(text)}</h3>')
            continue

        # Blockquotes
        if stripped.startswith("> "):
            html_parts.append(f"<blockquote>{_inline(stripped[2:])}</blockquote>")
            continue

        # Horizontal rules
        if stripped in ("---", "***", "___"):
            html_parts.append("<hr>")
            continue

        # Images — resolve chart paths to absolute file:// URIs
        img_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if img_match:
            alt, src = img_match.group(1), img_match.group(2)
            abs_path = _resolve_image_path(src, run_id)
            html_parts.append(f'<img src="{abs_path}" alt="{alt}">')
            continue

        # Emphasis line (italic caption)
        if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            html_parts.append(f"<p><em>{_inline(stripped[1:-1])}</em></p>")
            continue

        # Ordered list items
        ol_match = re.match(r"^(\d+)\.\s+(.+)", stripped)
        if ol_match:
            if not in_list:
                html_parts.append("<ol>")
                in_list = True
            html_parts.append(f"<li>{_inline(ol_match.group(2))}</li>")
            continue

        # Unordered list items
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{_inline(stripped[2:])}</li>")
            continue

        # Close list if we're leaving list context
        if in_list and not stripped:
            html_parts.append("</ol>" if any("<ol>" in p for p in html_parts[-20:]) else "</ul>")
            in_list = False

        # Regular paragraph
        if stripped:
            html_parts.append(f"<p>{_inline(stripped)}</p>")

    if in_list:
        html_parts.append("</ol>" if any("<ol>" in p for p in html_parts[-20:]) else "</ul>")

    return "\n".join(html_parts)


def _inline(text: str) -> str:
    """Convert inline markdown: bold, italic, links, code."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _resolve_image_path(src: str, run_id: str) -> str:
    """Resolve a relative chart image path to an absolute file:// URI."""
    if src.startswith(("http://", "https://", "file://")):
        return src

    # Try: charts/<filename>
    if src.startswith("charts/"):
        filename = src[7:]
        # With run_id subdirectory
        abs_path = CHARTS_DIR / run_id / filename
        if abs_path.exists():
            return f"file://{abs_path}"
        # Without run_id
        abs_path = CHARTS_DIR / filename
        if abs_path.exists():
            return f"file://{abs_path}"

    # Try absolute
    p = Path(src)
    if p.exists():
        return f"file://{p.resolve()}"

    return src


def export_pdf(
    markdown_text: str,
    output_path: str | Path | None = None,
    run_id: str = "",
    title: str = "",
) -> Path:
    """Convert a Markdown report to PDF using WeasyPrint."""
    from weasyprint import HTML

    if not title:
        # Extract from first h1
        m = re.search(r"^# (.+)$", markdown_text, re.MULTILINE)
        title = m.group(1) if m else "行业研究报告"

    short_title = title[:30] + "..." if len(title) > 30 else title
    body_html = _md_to_html_body(markdown_text, run_id)
    full_html = REPORT_HTML_TEMPLATE.format(title=title, short_title=short_title, body=body_html)

    if not output_path:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = REPORTS_DIR / f"report_{run_id or 'output'}.pdf"
    output_path = Path(output_path)

    html_doc = HTML(string=full_html)
    html_doc.write_pdf(str(output_path))

    logger.info("PDF exported: %s (%.1f KB)", output_path, output_path.stat().st_size / 1024)
    return output_path
