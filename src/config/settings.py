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

BOCHA_API_KEY: str = os.getenv("bocha_API_KEY", "")
BOCHA_SEARCH_URL: str = "https://api.bochaai.com/v1/web-search"
BOCHA_MAX_QUERIES_PER_TOPIC: int = 6

# Writer model: strong at Chinese long-form generation
WRITER_MODEL: str = "xiaomi/mimo-v2-flash"

# Fast utility model: routing, classification, data extraction
UTILITY_MODEL: str = "google/gemini-3.1-flash-lite-preview"

# ── Rate limits ──────────────────────────────────────────────

EASTMONEY_REQUEST_DELAY: float = 5.0  # seconds between requests
AKSHARE_REQUEST_DELAY: float = 1.0

# ── HTTP (FastAPI) ───────────────────────────────────────────

# Comma-separated origins; use "*" for dev (allow all). Production: https://your.domain
CORS_ORIGINS: list[str] = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
] or ["*"]

# ── Retrieval ────────────────────────────────────────────────

CHUNK_MIN_LENGTH: int = 200
CHUNK_MAX_LENGTH: int = 1200
RETRIEVAL_TOP_K: int = 8
