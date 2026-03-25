"""Citation management — binds evidence chunks to traceable references."""

from __future__ import annotations

from src.models import Citation, EvidenceChunk


def make_citation(chunk: EvidenceChunk, citation_index: int) -> Citation:
    """Create a Citation from an EvidenceChunk with a human-readable id."""
    return Citation(
        citation_id=f"c{citation_index}",
        doc_id=chunk.doc_id,
        title=chunk.title,
        published_at=chunk.published_at,
        source_name=chunk.source_name,
        url=chunk.url,
        chunk_text=chunk.chunk_text[:500],
    )


def build_citation_list(chunks: list[EvidenceChunk]) -> list[Citation]:
    """Build a citation list from retrieved chunks (1-indexed)."""
    return [make_citation(c, i + 1) for i, c in enumerate(chunks)]


def format_citations_for_prompt(citations: list[Citation]) -> str:
    """Format citations as context block for LLM prompts."""
    lines: list[str] = []
    for c in citations:
        header = f"[{c.citation_id}] {c.title}"
        if c.published_at:
            header += f" ({c.published_at})"
        if c.source_name:
            header += f" — {c.source_name}"
        lines.append(header)
        lines.append(c.chunk_text)
        lines.append("")
    return "\n".join(lines)


def format_reference_list(citations: list[Citation]) -> str:
    """Format citations as a numbered reference list for the final report."""
    lines: list[str] = []
    for c in citations:
        entry = f"[{c.citation_id}] {c.title}"
        if c.published_at:
            entry += f", {c.published_at}"
        if c.source_name:
            entry += f", {c.source_name}"
        if c.url:
            entry += f", {c.url}"
        lines.append(entry)
    return "\n".join(lines)
