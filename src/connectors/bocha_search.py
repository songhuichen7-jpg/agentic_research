"""Bocha AI Web Search connector.

Uses the Bocha Search API (https://api.bochaai.com/v1/web-search) to find
recent web pages about a topic, then optionally fetches full-text content
and converts it into Documents for the evidence pool.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from src.config.settings import BOCHA_API_KEY, BOCHA_MAX_QUERIES_PER_TOPIC, BOCHA_SEARCH_URL, RAW_DIR
from src.models import Document, SourceType

logger = logging.getLogger(__name__)

_HEADERS_SEARCH = {
    "Authorization": f"Bearer {BOCHA_API_KEY}",
    "Content-Type": "application/json",
}

_HEADERS_FETCH = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36"
    ),
}


# ── Cache helpers ─────────────────────────────────────────────


def _cache_dir() -> Path:
    d = RAW_DIR / "bocha"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(query: str) -> Path:
    h = hashlib.md5(query.encode()).hexdigest()[:12]
    return _cache_dir() / f"{h}.json"


# ── Core search ──────────────────────────────────────────────


def bocha_web_search(
    query: str,
    count: int = 8,
    freshness: str = "oneYear",
    summary: bool = True,
) -> list[dict]:
    """Call Bocha Web Search API and return result items.

    Each item has: name, url, snippet, summary, datePublished, siteName.
    """
    if not BOCHA_API_KEY:
        logger.warning("BOCHA_API_KEY not set, skipping web search")
        return []

    cache = _cache_path(query)
    if cache.exists():
        logger.info("Bocha cache hit: %s", query[:40])
        return json.loads(cache.read_text("utf-8"))

    payload = {
        "query": query,
        "freshness": freshness,
        "summary": summary,
        "count": count,
    }

    try:
        resp = requests.post(
            BOCHA_SEARCH_URL,
            headers=_HEADERS_SEARCH,
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        raw = resp.json()
        # Bocha wraps the response in a "data" envelope
        data = raw.get("data", raw)
    except Exception as e:
        logger.warning("Bocha search failed for '%s': %s", query[:40], e)
        return []

    items = []
    for page in data.get("webPages", {}).get("value", []):
        items.append(
            {
                "name": page.get("name", ""),
                "url": page.get("url", ""),
                "snippet": page.get("snippet", ""),
                "summary": page.get("summary", ""),
                "datePublished": page.get("datePublished", ""),
                "siteName": page.get("siteName", ""),
            }
        )

    cache.write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")
    logger.info("Bocha search '%s' → %d results", query[:40], len(items))
    return items


def _fetch_page_text(url: str) -> str:
    """Fetch a web page and extract its main text content."""
    try:
        resp = requests.get(url, headers=_HEADERS_FETCH, timeout=15)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove noise
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try common content containers
        content = (
            soup.find("article")
            or soup.find("div", class_="content")
            or soup.find("div", class_="article")
            or soup.find("main")
            or soup.body
        )
        text = content.get_text(separator="\n", strip=True) if content else ""

        # Truncate very long pages
        if len(text) > 8000:
            text = text[:8000]
        return text
    except Exception as e:
        logger.debug("Page fetch failed for %s: %s", url, e)
        return ""


# ── Public connector class ───────────────────────────────────


class BochaSearchConnector:
    """SourceConnector for Bocha AI web search results."""

    def __init__(self, delay: float = 1.0, fetch_fulltext: bool = True):
        self.delay = delay
        self.fetch_fulltext = fetch_fulltext

    def search_and_fetch(
        self,
        queries: list[str],
        results_per_query: int = 5,
        *,
        emit_fn=None,
    ) -> list[Document]:
        """Run multiple search queries and convert results to Documents.

        Deduplicates by URL across queries.  Accepts optional *emit_fn*
        callable(detail: str) for granular progress.
        """
        seen_urls: set[str] = set()
        docs: list[Document] = []
        total_q = min(len(queries), BOCHA_MAX_QUERIES_PER_TOPIC)

        for i, q in enumerate(queries[:BOCHA_MAX_QUERIES_PER_TOPIC]):
            if i > 0:
                time.sleep(self.delay)
            if emit_fn:
                emit_fn(f'搜索 [{i + 1}/{total_q}] "{q[:30]}"')
            items = bocha_web_search(q, count=results_per_query)

            for item in items:
                url = item["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Use summary from search API; optionally enrich with full text
                text = item.get("summary", "") or item.get("snippet", "")
                if self.fetch_fulltext and len(text) < 300:
                    if emit_fn:
                        emit_fn(f"获取全文: {item['name'][:30]}")
                    fulltext = _fetch_page_text(url)
                    if fulltext and len(fulltext) > len(text):
                        text = fulltext

                if not text.strip():
                    continue

                pub_date = item.get("datePublished", "")
                if pub_date and "T" in pub_date:
                    pub_date = pub_date.split("T")[0]

                docs.append(
                    Document(
                        source_type=SourceType.NEWS,
                        source_name="bocha_web",
                        title=item["name"],
                        published_at=pub_date,
                        url=url,
                        content_text=text,
                        content_markdown=text,
                        meta={
                            "site_name": item.get("siteName", ""),
                            "snippet": item.get("snippet", ""),
                            "search_query": q,
                        },
                    )
                )

        logger.info("Bocha connector: %d queries → %d unique documents", len(queries), len(docs))
        if emit_fn:
            emit_fn(f"搜索完成，共 {len(docs)} 篇补充文档")
        return docs
