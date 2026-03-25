"""Base parser interface."""

from __future__ import annotations

from typing import Protocol

from src.models import Document


class DocumentParser(Protocol):
    def parse(self, raw_content: str, **kwargs) -> Document:
        ...
