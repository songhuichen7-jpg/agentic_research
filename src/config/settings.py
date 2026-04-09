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

# ── OpenRouter ───────────────────────────────────────────────

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

# ── Bocha Search ─────────────────────────────────────────────

BOCHA_API_KEY: str = os.getenv("BOCHA_API_KEY", "")
BOCHA_SEARCH_URL: str = "https://api.bochaai.com/v1/web-search"
BOCHA_MAX_QUERIES_PER_TOPIC: int = 6

# Writer model: strong at Chinese long-form generation
WRITER_MODEL: str = "deepseek/deepseek-v3.2"

# Fast utility model: routing, classification, data extraction
UTILITY_MODEL: str = "google/gemini-3-flash-preview"

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
