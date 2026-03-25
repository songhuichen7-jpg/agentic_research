"""Chinese-aware document chunker.

Splits documents into chunks of 200-1200 characters, respecting paragraph
and sentence boundaries. Table-like content is chunked separately.
"""

from __future__ import annotations

import re
import uuid
from typing import Sequence

from src.config.settings import CHUNK_MAX_LENGTH, CHUNK_MIN_LENGTH
from src.models import Document, EvidenceChunk

_PARAGRAPH_SEP = re.compile(r"\n{2,}")
_SENTENCE_END = re.compile(r"(?<=[。！？；\n])")

# Heuristic: a line with ≥2 pipes or ≥3 consecutive numbers/separators is table-ish
_TABLE_LINE = re.compile(r"(\|.*\|)|((\d[\d,.%]+\s*){3,})")


def _is_table_block(text: str) -> bool:
    lines = text.strip().splitlines()
    if len(lines) < 2:
        return False
    table_lines = sum(1 for l in lines if _TABLE_LINE.search(l))
    return table_lines / len(lines) > 0.5


def _split_sentences(text: str) -> list[str]:
    """Split Chinese text at sentence-ending punctuation."""
    parts = _SENTENCE_END.split(text)
    return [p for p in parts if p.strip()]


def chunk_text(text: str, min_len: int = CHUNK_MIN_LENGTH, max_len: int = CHUNK_MAX_LENGTH) -> list[str]:
    """Split *text* into chunks between *min_len* and *max_len* characters."""
    paragraphs = _PARAGRAPH_SEP.split(text.strip())
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 1 <= max_len:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current.strip())
            if len(para) <= max_len:
                current = para
            else:
                # Paragraph too long — split by sentences
                sentences = _split_sentences(para)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= max_len:
                        current = f"{current}{sent}" if current else sent
                    else:
                        if current:
                            chunks.append(current.strip())
                        current = sent

    if current.strip():
        chunks.append(current.strip())

    # Merge tiny trailing chunks into previous
    merged: list[str] = []
    for c in chunks:
        if merged and len(c) < min_len and len(merged[-1]) + len(c) + 1 <= max_len:
            merged[-1] = f"{merged[-1]}\n\n{c}"
        else:
            merged.append(c)

    return merged


def chunk_document(doc: Document) -> list[EvidenceChunk]:
    """Split a Document into EvidenceChunk objects."""
    text = doc.content_text or doc.content_markdown
    if not text.strip():
        return []

    # Separate table blocks from prose
    paragraphs = _PARAGRAPH_SEP.split(text.strip())
    table_parts: list[str] = []
    prose_parts: list[str] = []

    for para in paragraphs:
        if _is_table_block(para):
            table_parts.append(para.strip())
        else:
            prose_parts.append(para.strip())

    chunks: list[EvidenceChunk] = []

    # Chunk prose
    prose_text = "\n\n".join(prose_parts)
    if prose_text.strip():
        for i, ct in enumerate(chunk_text(prose_text)):
            chunks.append(EvidenceChunk(
                doc_id=doc.doc_id,
                title=doc.title,
                source_name=doc.source_name,
                published_at=doc.published_at,
                url=doc.url,
                chunk_text=ct,
                chunk_index=i,
                is_table=False,
            ))

    # Each table block as its own chunk
    offset = len(chunks)
    for j, tb in enumerate(table_parts):
        chunks.append(EvidenceChunk(
            doc_id=doc.doc_id,
            title=doc.title,
            source_name=doc.source_name,
            published_at=doc.published_at,
            url=doc.url,
            chunk_text=tb,
            chunk_index=offset + j,
            is_table=True,
        ))

    return chunks


def chunk_documents(docs: Sequence[Document]) -> list[EvidenceChunk]:
    """Chunk multiple documents."""
    all_chunks: list[EvidenceChunk] = []
    for doc in docs:
        all_chunks.extend(chunk_document(doc))
    return all_chunks
