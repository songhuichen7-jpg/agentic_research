"""Core data models for the research report agent system."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now().isoformat()


# ── Source types ──────────────────────────────────────────────


class SourceType(str, Enum):
    INDUSTRY_REPORT = "industry_report"
    COMPANY_REPORT = "company_report"
    MACRO_REPORT = "macro_report"
    STRUCTURED_DATA = "structured_data"
    NEWS = "news"
    POLICY = "policy"
    PDF = "pdf"
    OTHER = "other"


# ── Unified document ─────────────────────────────────────────


class Document(BaseModel):
    doc_id: str = Field(default_factory=_uuid)
    source_type: SourceType = SourceType.OTHER
    source_name: str = ""
    title: str = ""
    published_at: str = ""
    url: str = ""
    content_markdown: str = ""
    content_text: str = ""
    attachments: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    fetched_at: str = Field(default_factory=_now)


# ── Evidence chunk ───────────────────────────────────────────


class EvidenceChunk(BaseModel):
    chunk_id: str = Field(default_factory=_uuid)
    doc_id: str = ""
    title: str = ""
    source_name: str = ""
    published_at: str = ""
    url: str = ""
    chunk_text: str = ""
    chunk_index: int = 0
    is_table: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)


# ── Citation ─────────────────────────────────────────────────


class Citation(BaseModel):
    citation_id: str = Field(default_factory=_uuid)
    doc_id: str = ""
    title: str = ""
    published_at: str = ""
    source_name: str = ""
    url: str = ""
    chunk_text: str = ""


# ── Chart spec ───────────────────────────────────────────────


class ChartType(str, Enum):
    LINE = "line"
    BAR = "bar"
    STACKED_BAR = "stacked_bar"
    PIE = "pie"
    TABLE = "table"
    TIMELINE = "timeline"
    WORDCLOUD = "wordcloud"
    KPI = "kpi"
    CHAIN = "chain"
    MATRIX = "matrix"


class ChartSpec(BaseModel):
    chart_id: str = Field(default_factory=_uuid)
    chart_type: ChartType = ChartType.BAR
    title: str = ""
    x: list[str] = Field(default_factory=list)
    y: list[float] = Field(default_factory=list)
    y_series: dict[str, list[float]] = Field(default_factory=dict)
    unit: str = ""
    caption: str = ""
    source_refs: list[str] = Field(default_factory=list)


class ChartAsset(BaseModel):
    chart_id: str = ""
    file_path: str = ""
    spec: ChartSpec | None = None
    status: str = "pending"


# ── Section ──────────────────────────────────────────────────


class SectionPlan(BaseModel):
    section_id: str = Field(default_factory=_uuid)
    title: str = ""
    objective: str = ""
    order: int = 0


class DraftedSection(BaseModel):
    section_id: str = ""
    title: str = ""
    markdown: str = ""
    citations: list[Citation] = Field(default_factory=list)
    chart_suggestions: list[str] = Field(default_factory=list)
    order: int = 0


# ── Quality check ────────────────────────────────────────────


class QCStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class SectionQC(BaseModel):
    section_title: str = ""
    status: QCStatus = QCStatus.PASS
    issues: list[str] = Field(default_factory=list)


class QualityResult(BaseModel):
    overall_status: QCStatus = QCStatus.PASS
    sections: list[SectionQC] = Field(default_factory=list)
    summary: str = ""


# ── LangGraph state ──────────────────────────────────────────


class ReportState(BaseModel):
    """Top-level state flowing through the LangGraph workflow."""

    user_query: str = ""
    normalized_topic: str = ""
    task_list: list[str] = Field(default_factory=list)
    expected_sections: list[str] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    evidence_chunks: list[EvidenceChunk] = Field(default_factory=list)
    section_plans: list[SectionPlan] = Field(default_factory=list)
    drafted_sections: list[DraftedSection] = Field(default_factory=list)
    chart_specs: list[ChartSpec] = Field(default_factory=list)
    chart_assets: list[ChartAsset] = Field(default_factory=list)
    final_report_md: str = ""
    qc_result: QualityResult | None = None
    run_id: str = Field(default_factory=_uuid)
    started_at: str = Field(default_factory=_now)
    status: str = "pending"
    error: str = ""
