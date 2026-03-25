"""Base protocol for all data source connectors."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.models import Document


@runtime_checkable
class SourceConnector(Protocol):
    """Every data-source adapter must implement these three methods."""

    def search(self, topic: str, **kwargs: Any) -> list[dict]:
        """Return a list of raw result dicts matching *topic*."""
        ...

    def fetch(self, item_id: str | None = None, url: str | None = None) -> dict:
        """Fetch a single item by id or url and return its raw dict."""
        ...

    def normalize(self, raw: dict) -> Document:
        """Convert a raw dict into a unified Document."""
        ...
