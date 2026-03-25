"""PDF parser — converts PDF files to Markdown text using PyMuPDF.

Supports:
  - Direct file path parsing
  - URL download + parsing (for EastMoney PDF links)
  - Table structure preservation via PyMuPDF's built-in extraction
"""

from __future__ import annotations

import hashlib
import logging
import re
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import requests

from src.config.settings import RAW_DIR
from src.models import Document, SourceType

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36"
    ),
}


def _download_pdf(url: str) -> Path | None:
    """Download a PDF to a local cache directory."""
    cache_dir = RAW_DIR / "pdf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    local_path = cache_dir / f"{h}.pdf"

    if local_path.exists():
        logger.info("PDF cache hit: %s", local_path.name)
        return local_path

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=30, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type and not url.endswith(".pdf"):
            logger.warning("URL does not appear to be PDF: %s (Content-Type: %s)", url, content_type)

        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info("Downloaded PDF: %s → %s", url, local_path.name)
        return local_path
    except Exception as e:
        logger.warning("PDF download failed for %s: %s", url, e)
        return None


def pdf_to_markdown(pdf_path: str | Path) -> str:
    """Extract text from a PDF file and convert to Markdown."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        logger.warning("PDF file not found: %s", pdf_path)
        return ""

    doc = fitz.open(str(pdf_path))
    parts: list[str] = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        # Extract text blocks with position info for structure detection
        text = page.get_text("text")
        if not text.strip():
            continue

        # Try to extract tables
        tables = page.find_tables()
        table_texts: set[str] = set()
        if tables and tables.tables:
            for table in tables.tables:
                md_table = _table_to_markdown(table)
                if md_table:
                    parts.append(md_table)
                    # Track table cell text to avoid duplication
                    for row in table.extract():
                        for cell in row:
                            if cell:
                                table_texts.add(cell.strip())

        # Add non-table text
        lines = text.splitlines()
        page_text: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in table_texts:
                continue
            # Heuristic heading detection: short bold-like lines
            if len(stripped) < 50 and not stripped.endswith(("。", "；", "，", "、")):
                page_text.append(f"\n### {stripped}\n")
            else:
                page_text.append(stripped)

        if page_text:
            parts.append("\n".join(page_text))

    doc.close()

    result = "\n\n".join(parts)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _table_to_markdown(table) -> str:
    """Convert a PyMuPDF table to Markdown format."""
    rows = table.extract()
    if not rows or len(rows) < 2:
        return ""

    md_rows: list[str] = []
    for i, row in enumerate(rows):
        cells = [str(c).strip() if c else "" for c in row]
        md_rows.append("| " + " | ".join(cells) + " |")
        if i == 0:
            md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")

    return "\n".join(md_rows)


def parse_pdf_url(url: str, title: str = "", source_name: str = "") -> Document | None:
    """Download and parse a PDF from URL into a Document."""
    local_path = _download_pdf(url)
    if not local_path:
        return None

    content = pdf_to_markdown(local_path)
    if not content:
        logger.warning("No text extracted from PDF: %s", url)
        return None

    return Document(
        source_type=SourceType.PDF,
        source_name=source_name or "pdf",
        title=title or local_path.stem,
        url=url,
        content_markdown=content,
        content_text=content,
        meta={"local_path": str(local_path), "pages": _count_pages(local_path)},
    )


def parse_pdf_file(path: str | Path, title: str = "", source_name: str = "") -> Document | None:
    """Parse a local PDF file into a Document."""
    path = Path(path)
    content = pdf_to_markdown(path)
    if not content:
        return None

    return Document(
        source_type=SourceType.PDF,
        source_name=source_name or "pdf",
        title=title or path.stem,
        content_markdown=content,
        content_text=content,
        meta={"local_path": str(path), "pages": _count_pages(path)},
    )


def _count_pages(path: Path) -> int:
    try:
        doc = fitz.open(str(path))
        n = len(doc)
        doc.close()
        return n
    except Exception:
        return 0
