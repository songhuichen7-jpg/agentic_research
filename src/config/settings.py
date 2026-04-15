"""Centralised configuration loaded from environment / .env file."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ── Load .env ────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")

# ── Paths ────────────────────────────────────────────────────

DATA_DIR = _PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PARSED_DIR = DATA_DIR / "parsed"
EVIDENCE_DIR = DATA_DIR / "evidence"
CHARTS_DIR = DATA_DIR / "charts"
REPORTS_DIR = DATA_DIR / "reports"
DB_PATH = _PROJECT_ROOT / "db" / "app.db"
CACHE_DIR = _PROJECT_ROOT / "cache"

# ── LLM Provider (OpenAI-compatible) ─────────────────────────

# Supports OpenRouter, 小爱 (Xiaoai), or any OpenAI-compatible endpoint.
# Set OPENROUTER_API_KEY in .env (the name is kept for backward compat).
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://xiaoai.plus/v1")

# ── Bocha Search ─────────────────────────────────────────────

BOCHA_API_KEY: str = os.getenv("BOCHA_API_KEY", "")
BOCHA_SEARCH_URL: str = "https://api.bochaai.com/v1/web-search"
BOCHA_MAX_QUERIES_PER_TOPIC: int = 6

# Writer model: strong at Chinese long-form generation
WRITER_MODEL: str = os.getenv("WRITER_MODEL", "gpt-4o")

# Fast utility model: routing, classification, data extraction
UTILITY_MODEL: str = os.getenv("UTILITY_MODEL", "gpt-4o")

# ── Rate limits ──────────────────────────────────────────────

EASTMONEY_REQUEST_DELAY: float = 5.0  # seconds between requests
AKSHARE_REQUEST_DELAY: float = 1.0

# ── HTTP (FastAPI) ───────────────────────────────────────────

# Comma-separated origins. Unset = same-origin only (safe default).
# Dev: CORS_ORIGINS=*    Production: CORS_ORIGINS=https://your.domain
_cors_raw = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS: list[str] = [o.strip() for o in _cors_raw.split(",") if o.strip()] if _cors_raw else []

# ── Retrieval ────────────────────────────────────────────────

CHUNK_MIN_LENGTH: int = 200
CHUNK_MAX_LENGTH: int = 1200
RETRIEVAL_TOP_K: int = 8

# Embedding model for vector store (OpenAI-compatible API)
# Set to "" to use Chroma's local default (all-MiniLM-L6-v2)
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
