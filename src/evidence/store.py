"""Evidence Store — manages the chunk pool backed by Chroma vector DB.

Responsibilities:
  - Ingest Documents → chunk → embed → store in Chroma
  - Provide vector-search interface for the retrieval layer
  - Persist to disk so repeated runs reuse embeddings
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config.settings import EVIDENCE_DIR
from src.evidence.chunker import chunk_documents
from src.models import Document, EvidenceChunk

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "evidence_chunks"


class EvidenceStore:
    """Thin wrapper around a Chroma collection of EvidenceChunks."""

    def __init__(self, persist_dir: str | Path | None = None):
        persist_dir = str(persist_dir or EVIDENCE_DIR / "chroma")
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._chunks_by_id: dict[str, EvidenceChunk] = {}

    # ── Ingest ───────────────────────────────────────────────

    def ingest_documents(self, docs: Sequence[Document]) -> list[EvidenceChunk]:
        """Chunk documents and add to the vector store.

        Uses Chroma's built-in default embedding function (all-MiniLM-L6-v2)
        which is good enough for a first pass and avoids external API calls.
        """
        chunks = chunk_documents(docs)
        if not chunks:
            logger.warning("No chunks produced from %d documents", len(docs))
            return []

        # Deduplicate against already-stored ids
        existing_ids = set(self._collection.get()["ids"])
        new_chunks = [c for c in chunks if c.chunk_id not in existing_ids]

        if not new_chunks:
            logger.info("All %d chunks already in store, skipping", len(chunks))
            for c in chunks:
                self._chunks_by_id[c.chunk_id] = c
            return chunks

        self._collection.add(
            ids=[c.chunk_id for c in new_chunks],
            documents=[c.chunk_text for c in new_chunks],
            metadatas=[{
                "doc_id": c.doc_id,
                "title": c.title,
                "source_name": c.source_name,
                "published_at": c.published_at,
                "url": c.url,
                "is_table": str(c.is_table),
            } for c in new_chunks],
        )

        for c in chunks:
            self._chunks_by_id[c.chunk_id] = c

        logger.info("Ingested %d new chunks (total %d) from %d documents",
                     len(new_chunks), self._collection.count(), len(docs))
        return chunks

    # ── Query ────────────────────────────────────────────────

    def query(self, text: str, top_k: int = 8, where: dict | None = None) -> list[EvidenceChunk]:
        """Vector similarity search. Returns EvidenceChunk objects."""
        kwargs: dict = {"query_texts": [text], "n_results": min(top_k, self._collection.count() or 1)}
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        chunks: list[EvidenceChunk] = []
        if not results["ids"] or not results["ids"][0]:
            return chunks

        for cid, doc_text, meta in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
        ):
            if cid in self._chunks_by_id:
                chunks.append(self._chunks_by_id[cid])
            else:
                chunks.append(EvidenceChunk(
                    chunk_id=cid,
                    doc_id=meta.get("doc_id", ""),
                    title=meta.get("title", ""),
                    source_name=meta.get("source_name", ""),
                    published_at=meta.get("published_at", ""),
                    url=meta.get("url", ""),
                    chunk_text=doc_text,
                    is_table=meta.get("is_table", "False") == "True",
                ))
        return chunks

    # ── Utilities ────────────────────────────────────────────

    def count(self) -> int:
        return self._collection.count()

    def get_chunk(self, chunk_id: str) -> EvidenceChunk | None:
        return self._chunks_by_id.get(chunk_id)

    def all_chunks(self) -> list[EvidenceChunk]:
        return list(self._chunks_by_id.values())
