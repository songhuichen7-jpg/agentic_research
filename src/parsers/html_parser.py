"""HTML → clean Markdown/text parser."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.models import Document, SourceType


def html_to_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_markdown(html: str) -> str:
    """Lightweight HTML → Markdown conversion (headings, lists, paragraphs)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    lines: list[str] = []
    for el in soup.descendants:
        if el.name and el.name in ("h1", "h2", "h3", "h4"):
            level = int(el.name[1])
            lines.append(f"\n{'#' * level} {el.get_text(strip=True)}\n")
        elif el.name == "p":
            text = el.get_text(strip=True)
            if text:
                lines.append(f"\n{text}\n")
        elif el.name == "li":
            lines.append(f"- {el.get_text(strip=True)}")
        elif el.name == "table":
            lines.append(_table_to_markdown(el))

    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _table_to_markdown(table_tag) -> str:
    """Convert an HTML <table> into a Markdown table."""
    rows = table_tag.find_all("tr")
    if not rows:
        return ""
    md_rows: list[str] = []
    for i, row in enumerate(rows):
        cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
        md_rows.append("| " + " | ".join(cells) + " |")
        if i == 0:
            md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return "\n".join(md_rows)


def parse_html_document(html: str, title: str = "", url: str = "", source_name: str = "") -> Document:
    """Parse raw HTML into a Document."""
    return Document(
        source_type=SourceType.OTHER,
        source_name=source_name,
        title=title,
        url=url,
        content_markdown=html_to_markdown(html),
        content_text=html_to_text(html),
    )
