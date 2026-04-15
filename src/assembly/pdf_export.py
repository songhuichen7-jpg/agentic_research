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
    """Lightweight Markdown → HTML conversion with table support and raw-HTML passthrough."""
    lines = md_text.splitlines()
    html_parts: list[str] = []
    in_list = False
    in_ol = False
    i = 0
    n = len(lines)

    # Track whether we're currently inside a raw HTML block (e.g. cover page)
    in_raw_html = False
    raw_html_tag: str | None = None

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ── Raw HTML blocks (passthrough) ────────────────────
        # Detect opening block-level tags like <div class="...">
        if not in_raw_html and re.match(r"^<(div|section|figure)\b", stripped):
            in_raw_html = True
            raw_html_tag = re.match(r"^<(\w+)", stripped).group(1)  # type: ignore
            html_parts.append(line)
            i += 1
            continue

        if in_raw_html:
            html_parts.append(line)
            # Close when we see matching end tag (shallow: assumes no nesting)
            if raw_html_tag and f"</{raw_html_tag}>" in stripped:
                in_raw_html = False
                raw_html_tag = None
            i += 1
            continue

        # ── Tables (GFM pipe tables) ─────────────────────────
        if "|" in stripped and i + 1 < n and re.match(r"^\s*\|?[-:\s|]+\|[-:\s|]+", lines[i + 1]):
            table_lines = [lines[i]]
            i += 1  # skip header
            separator = lines[i]
            table_lines.append(separator)
            i += 1
            while i < n and "|" in lines[i].strip():
                table_lines.append(lines[i])
                i += 1
            html_parts.append(_render_table(table_lines))
            continue

        # ── Headings (add id for TOC anchor links) ───────────
        if stripped.startswith("# ") and not stripped.startswith("## "):
            text = stripped[2:]
            html_parts.append(f'<h1 id="{text}">{_inline(text)}</h1>')
            i += 1
            continue
        if stripped.startswith("## "):
            text = stripped[3:]
            html_parts.append(f'<h2 id="{text}">{_inline(text)}</h2>')
            i += 1
            continue
        if stripped.startswith("### "):
            text = stripped[4:]
            html_parts.append(f'<h3 id="{text}">{_inline(text)}</h3>')
            i += 1
            continue
        if stripped.startswith("#### "):
            text = stripped[5:]
            html_parts.append(f'<h4 id="{text}">{_inline(text)}</h4>')
            i += 1
            continue

        # ── Blockquotes (support multi-line) ─────────────────
        if stripped.startswith(">"):
            bq_lines = []
            while i < n and lines[i].strip().startswith(">"):
                content = lines[i].strip()[1:].lstrip()
                bq_lines.append(_inline(content))
                i += 1
            html_parts.append("<blockquote>" + "<br>".join(bq_lines) + "</blockquote>")
            continue

        # ── Horizontal rules ─────────────────────────────────
        if stripped in ("---", "***", "___"):
            html_parts.append("<hr>")
            i += 1
            continue

        # ── Images — resolve chart paths to absolute file:// URIs ──
        img_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if img_match:
            alt, src = img_match.group(1), img_match.group(2)
            abs_path = _resolve_image_path(src, run_id)
            html_parts.append(f'<img src="{abs_path}" alt="{alt}">')
            i += 1
            continue

        # ── Emphasis line (italic caption) ───────────────────
        if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            html_parts.append(f"<p><em>{_inline(stripped[1:-1])}</em></p>")
            i += 1
            continue

        # ── Ordered list items ───────────────────────────────
        ol_match = re.match(r"^(\d+)\.\s+(.+)", stripped)
        if ol_match:
            if not in_list:
                html_parts.append("<ol>")
                in_list = True
                in_ol = True
            html_parts.append(f"<li>{_inline(ol_match.group(2))}</li>")
            i += 1
            continue

        # ── Unordered list items ─────────────────────────────
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
                in_ol = False
            html_parts.append(f"<li>{_inline(stripped[2:])}</li>")
            i += 1
            continue

        # ── Close list if we're leaving list context ─────────
        if in_list and not stripped:
            html_parts.append("</ol>" if in_ol else "</ul>")
            in_list = False
            in_ol = False
            i += 1
            continue

        # ── Regular paragraph ────────────────────────────────
        if stripped:
            html_parts.append(f"<p>{_inline(stripped)}</p>")
        i += 1

    if in_list:
        html_parts.append("</ol>" if in_ol else "</ul>")

    return "\n".join(html_parts)


def _render_table(lines: list[str]) -> str:
    """Render GFM pipe table lines as HTML."""
    def split_row(row: str) -> list[str]:
        row = row.strip()
        if row.startswith("|"):
            row = row[1:]
        if row.endswith("|"):
            row = row[:-1]
        return [c.strip() for c in row.split("|")]

    if len(lines) < 2:
        return ""

    header = split_row(lines[0])
    rows = [split_row(ln) for ln in lines[2:] if ln.strip()]

    out = ["<table>", "<thead><tr>"]
    for cell in header:
        out.append(f"<th>{_inline(cell)}</th>")
    out.append("</tr></thead>")

    out.append("<tbody>")
    for row in rows:
        out.append("<tr>")
        for cell in row:
            out.append(f"<td>{_inline(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody>")
    out.append("</table>")
    return "\n".join(out)


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
