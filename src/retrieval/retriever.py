"""Hybrid retriever: BM25 coarse recall + Chroma vector re-rank.

Retrieval strategy (from design doc §6.5):
  1. Metadata pre-filter (time range, source type)
  2. BM25 keyword recall (jieba tokenised)
  3. Vector similarity search (Chroma)
  4. Content deduplication (similarity threshold)
  5. Merge & deduplicate, return top-K
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Sequence

import jieba
from rank_bm25 import BM25Okapi

from src.evidence.store import EvidenceStore
from src.models import EvidenceChunk

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Combines BM25 keyword search with Chroma vector search."""

    def __init__(
        self,
        store: EvidenceStore,
        bm25_weight: float = 0.4,
        vector_weight: float = 0.6,
        dedup_threshold: float = 0.85,
    ):
        self._store = store
        self._bm25_weight = bm25_weight
        self._vector_weight = vector_weight
        self._dedup_threshold = dedup_threshold
        self._bm25: BM25Okapi | None = None
        self._bm25_chunks: list[EvidenceChunk] = []

    def build_bm25_index(self, chunks: Sequence[EvidenceChunk] | None = None) -> None:
        """Build (or rebuild) the BM25 index from the evidence store."""
        self._bm25_chunks = list(chunks) if chunks else self._store.all_chunks()
        if not self._bm25_chunks:
            logger.warning("No chunks available for BM25 index")
            return
        tokenised = [list(jieba.cut(c.chunk_text)) for c in self._bm25_chunks]
        self._bm25 = BM25Okapi(tokenised)
        logger.info("BM25 index built with %d chunks", len(self._bm25_chunks))

    def _bm25_search(self, query: str, top_k: int) -> list[tuple[EvidenceChunk, float]]:
        if self._bm25 is None or not self._bm25_chunks:
            return []
        tokens = list(jieba.cut(query))
        scores = self._bm25.get_scores(tokens)
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [(self._bm25_chunks[i], float(s)) for i, s in indexed if s > 0]

    def _vector_search(self, query: str, top_k: int, where: dict | None = None) -> list[EvidenceChunk]:
        return self._store.query(query, top_k=top_k, where=where)

    def _deduplicate(self, chunks: list[EvidenceChunk]) -> list[EvidenceChunk]:
        """Remove near-duplicate chunks based on text similarity."""
        if not chunks or self._dedup_threshold >= 1.0:
            return chunks

        result: list[EvidenceChunk] = []
        for chunk in chunks:
            is_dup = False
            snippet = chunk.chunk_text[:300]
            for kept in result:
                ratio = SequenceMatcher(None, snippet, kept.chunk_text[:300]).ratio()
                if ratio >= self._dedup_threshold:
                    is_dup = True
                    break
            if not is_dup:
                result.append(chunk)
        if len(result) < len(chunks):
            logger.info("Dedup removed %d/%d chunks", len(chunks) - len(result), len(chunks))
        return result

    def retrieve(
        self,
        query: str,
        top_k: int = 8,
        source_filter: str | None = None,
        date_from: str | None = None,
    ) -> list[EvidenceChunk]:
        """Run hybrid retrieval with optional metadata filtering."""
        fetch_k = top_k * 2

        # Metadata filter for Chroma
        where: dict | None = None
        conditions: list[dict] = []
        if source_filter:
            conditions.append({"source_name": {"$eq": source_filter}})
        if date_from:
            conditions.append({"published_at": {"$gte": date_from}})
        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}

        # BM25 (operates on full index; filter afterward)
        bm25_results = self._bm25_search(query, fetch_k)
        if source_filter or date_from:
            bm25_results = [
                (c, s) for c, s in bm25_results
                if (not source_filter or c.source_name == source_filter)
                and (not date_from or c.published_at >= date_from)
            ]
        bm25_max = max((s for _, s in bm25_results), default=1.0) or 1.0

        # Vector
        vector_results = self._vector_search(query, fetch_k, where=where)

        # Score fusion (normalised)
        scores: dict[str, float] = {}
        chunk_map: dict[str, EvidenceChunk] = {}

        for rank, (chunk, raw_score) in enumerate(bm25_results):
            norm = raw_score / bm25_max
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + self._bm25_weight * norm
            chunk_map[chunk.chunk_id] = chunk

        for rank, chunk in enumerate(vector_results):
            norm = 1.0 - rank / max(len(vector_results), 1)
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + self._vector_weight * norm
            chunk_map[chunk.chunk_id] = chunk

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        merged = [chunk_map[cid] for cid, _ in ranked]

        # Deduplicate
        deduped = self._deduplicate(merged)[:top_k]

        logger.info("Hybrid retrieval for '%s': BM25=%d, Vector=%d → dedup → %d",
                     query[:40], len(bm25_results), len(vector_results), len(deduped))
        return deduped
