"""LangGraph workflow — orchestrates the full report generation pipeline.

Design doc §7:
  Start → Normalize Topic → Plan Tasks → Collect Documents
  → Build Evidence Store → Plan Sections
  → [For each section: Retrieve → Write → Plan Charts → Render Charts]
  → Assemble Report → Quality Check → Export
"""

from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime
from typing import Any, TypedDict

from src.assembly.assembler import assemble_report
from src.assembly.pdf_export import export_pdf
from src.charts.planner import plan_charts, plan_charts_for_sections
from src.charts.renderer import render_charts
from src.config.llm import get_token_usage, reset_token_usage
from src.config.settings import CHARTS_DIR, EVIDENCE_DIR
from src.connectors.bocha_search import BochaSearchConnector
from src.connectors.eastmoney import EastMoneyConnector
from src.db import init_db, insert_document, insert_run, update_run
from src.evidence.store import EvidenceStore
from src.graph.nodes.planner import plan_report
from src.models import (
    ChartAsset,
    ChartSpec,
    DraftedSection,
    EvidenceChunk,
    Document,
    QualityResult,
    SectionPlan,
)
from src.parsers.pdf_parser import parse_pdf_url
from src.quality.checker import check_report
from src.retrieval.retriever import HybridRetriever
from src.graph.run_control import RunCancelled, begin_run, end_run, is_cancelled
from src.telemetry.run_events import (
    RunEventBus,
    emit_node_detail,
    emit_node_end,
    emit_node_error,
    emit_node_start,
    emit_pipeline_cancelled,
    emit_pipeline_end,
    emit_pipeline_error,
    emit_pipeline_start,
)
from src.writers.section_writer import write_section

logger = logging.getLogger(__name__)


# ── State definition ─────────────────────────────────────────


class WorkflowState(TypedDict, total=False):
    user_query: str
    normalized_topic: str
    task_list: list[str]
    documents: list[Document]
    evidence_chunks: list[EvidenceChunk]
    section_plans: list[SectionPlan]
    drafted_sections: list[DraftedSection]
    chart_specs: list[ChartSpec]
    chart_assets: list[ChartAsset]
    final_report_md: str
    qc_result: QualityResult
    run_id: str
    status: str
    error: str


# ── Node functions ───────────────────────────────────────────


def node_collect_documents(state: WorkflowState) -> dict:
    """Fetch research reports from EastMoney, with optional PDF enrichment.

    Resilient: individual fetch/parse failures are logged and skipped.
    """
    topic = state["user_query"]
    run_id = state.get("run_id", "")
    emit_node_start(run_id, "collect_documents")
    logger.info("=== Node: Collect Documents (%s) ===", topic)

    try:
        try:
            em = EastMoneyConnector(delay=2.0, max_pages=1, years_ago=2)
            emit_node_detail(run_id, "collect_documents", "正在搜索东方财富行业研报…")
            docs = em.search_and_fetch(
                topic,
                max_reports=8,
                emit_fn=lambda d: emit_node_detail(run_id, "collect_documents", d),
            )
        except Exception as e:
            logger.error("EastMoney connector failed, continuing with empty docs: %s", e)
            docs = []

        # Try to enrich with PDF full-text for docs that have pdf_url
        pdf_count = 0
        for doc in docs:
            if is_cancelled(run_id):
                raise RunCancelled()
            try:
                pdf_url = doc.meta.get("pdf_url")
                if pdf_url and len(doc.content_text) < 500:
                    logger.info("Attempting PDF enrichment for: %s", doc.title)
                    emit_node_detail(run_id, "collect_documents", f"PDF 解析: {doc.title[:30]}")
                    pdf_doc = parse_pdf_url(pdf_url, title=doc.title, source_name="eastmoney_pdf")
                    if pdf_doc and len(pdf_doc.content_text) > len(doc.content_text):
                        doc.content_text = pdf_doc.content_text
                        doc.content_markdown = pdf_doc.content_markdown
                        doc.meta["pdf_parsed"] = True
                        pdf_count += 1
            except Exception as e:
                logger.warning("PDF enrichment failed for '%s': %s", doc.title, e)

        # Record documents in DB
        for doc in docs:
            try:
                insert_document(
                    doc.doc_id, doc.source_name, doc.title, doc.url, doc.published_at, len(doc.content_text), run_id
                )
            except Exception as e:
                logger.warning("DB insert failed for doc '%s': %s", doc.title, e)

        logger.info("Collected %d documents (%d PDF-enriched)", len(docs), pdf_count)
        emit_node_end(run_id, "collect_documents", detail=f"{len(docs)} 篇，PDF 增强 {pdf_count}")
        return {"documents": docs}
    except Exception as e:
        emit_node_error(run_id, "collect_documents", str(e))
        raise


def node_plan(state: WorkflowState) -> dict:
    """Generate research plan with LLM."""
    topic = state["user_query"]
    run_id = state.get("run_id", "")
    emit_node_start(run_id, "plan")
    logger.info("=== Node: Plan Report (%s) ===", topic)

    try:
        emit_node_detail(run_id, "plan", "LLM 正在生成研究大纲…")
        plan = plan_report(topic)
        nsec = len(plan.get("section_plans", []))
        emit_node_end(run_id, "plan", detail=f"{nsec} 个章节")
        return {
            "normalized_topic": plan["normalized_topic"],
            "task_list": plan["task_list"],
            "section_plans": plan["section_plans"],
        }
    except Exception as e:
        emit_node_error(run_id, "plan", str(e))
        raise


def _build_search_queries(raw_topic: str, sections: list[SectionPlan]) -> list[str]:
    """Build concise search queries from topic + section titles.

    Long queries return zero results from search APIs, so we truncate
    section titles and ensure query diversity.
    """
    queries = [raw_topic]
    for sec in sections[:4]:
        # Truncate long titles to first 15 chars to keep queries concise
        title_short = sec.title[:15].rstrip("，。、：")
        q = f"{raw_topic} {title_short}"
        if q not in queries:
            queries.append(q)
    # Add a broad industry query as fallback
    fallback = f"{raw_topic} 行业分析 市场规模"
    if fallback not in queries:
        queries.append(fallback)
    return queries


def node_web_search(state: WorkflowState) -> dict:
    """Supplement documents with Bocha web search results based on the plan."""
    run_id = state.get("run_id", "")
    emit_node_start(run_id, "web_search")
    logger.info("=== Node: Web Search (Bocha) ===")

    topic = state.get("normalized_topic", state["user_query"])
    sections = state.get("section_plans", [])
    existing_docs = state.get("documents", [])

    try:
        raw_topic = state["user_query"]
        queries = _build_search_queries(raw_topic, sections)
        logger.info("Web search queries: %s", [q[:40] for q in queries])

        try:
            bocha = BochaSearchConnector(delay=1.0, fetch_fulltext=True)
            web_docs = bocha.search_and_fetch(
                queries,
                results_per_query=8,
                emit_fn=lambda d: emit_node_detail(run_id, "web_search", d),
            )
        except Exception as e:
            logger.error("Web search failed, continuing without: %s", e)
            web_docs = []

        # Record in DB
        for doc in web_docs:
            try:
                insert_document(
                    doc.doc_id, doc.source_name, doc.title, doc.url, doc.published_at, len(doc.content_text), run_id
                )
            except Exception as e:
                logger.warning("DB insert failed for web doc '%s': %s", doc.title[:30], e)

        merged = existing_docs + web_docs
        logger.info("Web search added %d documents (total: %d)", len(web_docs), len(merged))
        emit_node_end(run_id, "web_search", detail=f"博查 +{len(web_docs)}，合计 {len(merged)} 篇")
        return {"documents": merged}
    except Exception as e:
        emit_node_error(run_id, "web_search", str(e))
        raise


def node_build_evidence(state: WorkflowState) -> dict:
    """Chunk documents and build the evidence store.

    Includes data quality validation: logs warnings for low document/chunk
    counts and filters out documents with empty content before chunking.
    """
    run_id = state.get("run_id", "default")
    emit_node_start(run_id, "build_evidence")
    logger.info("=== Node: Build Evidence Store ===")

    try:
        raw_docs = state.get("documents", [])

        # ── Data validation: filter out empty-content documents ──
        valid_docs = [d for d in raw_docs if d.content_text and len(d.content_text.strip()) >= 50]
        skipped = len(raw_docs) - len(valid_docs)
        if skipped > 0:
            logger.warning(
                "Filtered out %d/%d documents with insufficient content (<50 chars)",
                skipped, len(raw_docs),
            )
            emit_node_detail(
                run_id, "build_evidence",
                f"过滤掉 {skipped} 篇无效文档（内容过短），剩余 {len(valid_docs)} 篇",
            )

        if not valid_docs:
            msg = f"无有效文档可供分析（共 {len(raw_docs)} 篇文档全部内容为空）"
            logger.error(msg)
            emit_node_error(run_id, "build_evidence", msg)
            raise RuntimeError(msg)

        store_dir = EVIDENCE_DIR / f"chroma_{run_id}"
        if store_dir.exists():
            shutil.rmtree(store_dir)

        emit_node_detail(run_id, "build_evidence", f"正在分块 {len(valid_docs)} 篇文档…")
        store = EvidenceStore(persist_dir=store_dir)
        chunks = store.ingest_documents(valid_docs)
        logger.info("Evidence store: %d chunks from %d documents", len(chunks), len(valid_docs))

        # ── Data sufficiency check ──
        if len(chunks) < 5:
            logger.warning(
                "Low evidence: only %d chunks from %d documents — report quality may be poor",
                len(chunks), len(valid_docs),
            )
            emit_node_detail(
                run_id, "build_evidence",
                f"警告：仅产生 {len(chunks)} 个证据块，数据量偏少，报告质量可能受限",
            )

        emit_node_detail(run_id, "build_evidence", f"构建 BM25 索引 ({len(chunks)} chunks)")
        _RUNTIME_CACHE["store"] = store
        retriever = HybridRetriever(store)
        retriever.build_bm25_index(chunks)
        _RUNTIME_CACHE["retriever"] = retriever

        emit_node_end(run_id, "build_evidence", detail=f"{len(chunks)} chunks（来自 {len(valid_docs)} 篇文档）")
        return {"evidence_chunks": chunks}
    except Exception as e:
        emit_node_error(run_id, "build_evidence", str(e))
        raise


def node_write_sections(state: WorkflowState) -> dict:
    """Write all sections in parallel with evidence retrieval.

    Uses ThreadPoolExecutor to call LLM for all sections concurrently.
    Resilient: individual section failures produce a stub instead of aborting.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    run_id = state.get("run_id", "")
    emit_node_start(run_id, "write_sections")
    logger.info("=== Node: Write Sections (parallel) ===")

    try:
        retriever: HybridRetriever = _RUNTIME_CACHE["retriever"]
        topic = state.get("normalized_topic", state["user_query"])
        sections = state.get("section_plans", [])
        total = len(sections)

        completed_count = 0
        completed_lock = threading.Lock()

        def write_one(idx_sec):
            idx, sec = idx_sec
            if is_cancelled(run_id):
                raise RunCancelled()
            try:
                query = f"{topic} {sec.title} {sec.objective}"
                evidence = retriever.retrieve(query, top_k=10)
                draft = write_section(topic, sec, evidence, run_id=run_id, node="write_sections")
                return idx, draft
            except Exception as e:
                logger.error("Section '%s' failed: %s — inserting stub", sec.title, e)
                return idx, DraftedSection(
                    section_id=sec.section_id,
                    title=sec.title,
                    markdown=f"*（本章节生成失败：{e}）*",
                    order=sec.order,
                    evidence_count=0,
                )

        # Run all sections concurrently (max 6 workers to avoid rate limits)
        results: dict[int, DraftedSection] = {}
        max_workers = min(total, 6)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(write_one, (i, sec)): i for i, sec in enumerate(sections)}
            for fut in as_completed(futures):
                if is_cancelled(run_id):
                    raise RunCancelled()
                idx, draft = fut.result()
                results[idx] = draft
                with completed_lock:
                    completed_count += 1
                    n = completed_count
                logger.info("[Section %d/%d done] %s", n, total, draft.title)
                emit_node_detail(
                    run_id, "write_sections",
                    f"[{n}/{total}] 完成「{draft.title}」",
                )

        # Restore original order
        drafted = [results[i] for i in range(total)]

        no_evidence = [d.title for d in drafted if d.evidence_count == 0]
        if no_evidence:
            logger.warning("Sections with ZERO evidence: %s", no_evidence)
            emit_node_detail(
                run_id, "write_sections",
                f"警告：{len(no_evidence)} 个章节无证据支撑：{', '.join(no_evidence)}",
            )

        emit_node_end(run_id, "write_sections", detail=f"{len(drafted)} 节（并行）")
        return {"drafted_sections": drafted}
    except Exception as e:
        emit_node_error(run_id, "write_sections", str(e))
        raise


def node_plan_and_render_charts(state: WorkflowState) -> dict:
    """Plan charts from drafted sections, then render them.

    Resilient: individual chart plan/render failures are logged and skipped.
    """
    run_id = state.get("run_id", "default")
    emit_node_start(run_id, "charts")
    logger.info("=== Node: Plan & Render Charts ===")

    try:
        sections = state.get("drafted_sections", [])
        topic = state.get("normalized_topic") or state.get("user_query", "")
        emit_node_detail(run_id, "charts", f"正在从 {len(sections)} 个章节中规划图表…")

        # Full-report aggregation: real data (AkShare) + LLM extraction
        all_specs = plan_charts_for_sections(sections, topic=topic)

        logger.info("Chart planner produced %d specs total", len(all_specs))

        if not all_specs:
            emit_node_detail(run_id, "charts", "未发现可图表化的数据")
            emit_node_end(run_id, "charts", detail="0 张图表")
            return {"chart_specs": [], "chart_assets": []}

        emit_node_detail(run_id, "charts", f"正在渲染 {len(all_specs)} 张图表…")
        chart_dir = CHARTS_DIR / run_id
        try:
            assets = render_charts(all_specs, output_dir=chart_dir)
        except Exception as e:
            logger.error("Chart rendering batch failed: %s", e)
            assets = []

        ok = sum(1 for a in assets if a.status == "ok")
        logger.info("Rendered %d/%d charts successfully", ok, len(assets))
        emit_node_end(run_id, "charts", detail=f"{ok} 张图表")
        return {"chart_specs": all_specs, "chart_assets": assets}
    except Exception as e:
        emit_node_error(run_id, "charts", str(e))
        raise


def node_assemble(state: WorkflowState) -> dict:
    """Assemble the final report."""
    run_id = state.get("run_id", "")
    emit_node_start(run_id, "assemble")
    logger.info("=== Node: Assemble Report ===")

    try:
        report_md = assemble_report(
            topic=state["user_query"],
            normalized_topic=state.get("normalized_topic", state["user_query"]),
            sections=state.get("drafted_sections", []),
            chart_assets=state.get("chart_assets", []),
            run_id=state.get("run_id", ""),
        )
        emit_node_end(run_id, "assemble", detail=f"{len(report_md)} 字符")
        return {"final_report_md": report_md}
    except Exception as e:
        emit_node_error(run_id, "assemble", str(e))
        raise


def node_quality_check(state: WorkflowState) -> dict:
    """Run quality checks."""
    run_id = state.get("run_id", "")
    emit_node_start(run_id, "quality_check")
    logger.info("=== Node: Quality Check ===")

    try:
        qc = check_report(
            sections=state.get("drafted_sections", []),
            chart_assets=state.get("chart_assets", []),
        )
        emit_node_end(run_id, "quality_check", detail=qc.overall_status.value)
        return {"qc_result": qc}
    except Exception as e:
        emit_node_error(run_id, "quality_check", str(e))
        raise


def node_export_pdf(state: WorkflowState) -> dict:
    """Export the final report as PDF."""
    run_id = state.get("run_id", "")
    emit_node_start(run_id, "export_pdf")
    logger.info("=== Node: Export PDF ===")

    report_md = state.get("final_report_md", "")
    if not report_md:
        logger.warning("No report markdown to export")
        emit_node_end(run_id, "export_pdf", detail="跳过（无 Markdown）")
        return {"status": "completed"}

    try:
        pdf_path = export_pdf(report_md, run_id=run_id)
        logger.info("PDF exported: %s", pdf_path)
        emit_node_end(run_id, "export_pdf", detail=str(pdf_path.name))
    except Exception as e:
        logger.error("PDF export failed: %s", e)
        emit_node_end(run_id, "export_pdf", detail=f"导出失败（已忽略）: {e}")

    return {"status": "completed"}


# ── Runtime cache for non-serialisable objects ───────────────
_RUNTIME_CACHE: dict[str, Any] = {}


# ── Build the graph ──────────────────────────────────────────


def build_graph():
    """Build and return the LangGraph StateGraph."""
    from langgraph.graph import StateGraph, END

    graph = StateGraph(WorkflowState)

    graph.add_node("collect_documents", node_collect_documents)
    graph.add_node("plan", node_plan)
    graph.add_node("web_search", node_web_search)
    graph.add_node("build_evidence", node_build_evidence)
    graph.add_node("write_sections", node_write_sections)
    graph.add_node("charts", node_plan_and_render_charts)
    graph.add_node("assemble", node_assemble)
    graph.add_node("quality_check", node_quality_check)
    graph.add_node("export_pdf", node_export_pdf)

    graph.set_entry_point("collect_documents")
    graph.add_edge("collect_documents", "plan")
    graph.add_edge("plan", "web_search")
    graph.add_edge("web_search", "build_evidence")
    graph.add_edge("build_evidence", "write_sections")
    graph.add_edge("write_sections", "charts")
    graph.add_edge("charts", "assemble")
    graph.add_edge("assemble", "quality_check")
    graph.add_edge("quality_check", "export_pdf")
    graph.add_edge("export_pdf", END)

    return graph.compile()


# ── Convenience runner ───────────────────────────────────────


def run_report(topic: str, run_id: str | None = None) -> WorkflowState:
    """Run the full report generation pipeline for a given topic."""
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    logger.info("Starting report generation: topic='%s', run_id='%s'", topic, run_id)
    _RUNTIME_CACHE.clear()
    reset_token_usage()

    # DB tracking
    init_db()
    insert_run(run_id, topic)
    t0 = time.time()

    RunEventBus.reset_run(run_id)
    begin_run(run_id)

    graph = build_graph()
    initial_state: WorkflowState = {
        "user_query": topic,
        "run_id": run_id,
        "status": "running",
    }

    try:
        emit_pipeline_start(run_id)
        result: WorkflowState | None = None
        for state in graph.stream(initial_state, stream_mode="values"):
            result = state
            if is_cancelled(run_id):
                raise RunCancelled()

        if result is None:
            raise RuntimeError("Graph produced no state")

        elapsed = time.time() - t0

        qc = result.get("qc_result")
        token_usage = get_token_usage()
        update_run(
            run_id,
            normalized=result.get("normalized_topic", ""),
            status="completed",
            sections=len(result.get("drafted_sections", [])),
            charts=sum(1 for a in result.get("chart_assets", []) if a.status == "ok"),
            report_chars=len(result.get("final_report_md", "")),
            qc_status=qc.overall_status.value if qc else "",
            elapsed_sec=elapsed,
            token_usage=token_usage,
        )
        emit_pipeline_end(run_id, detail=f"耗时 {elapsed:.1f}s")
        logger.info("Report generation complete in %.1fs: status=%s", elapsed, result.get("status"))
        logger.info("Token usage: %s", token_usage)
        result["token_usage"] = token_usage
        return result

    except RunCancelled as e:
        elapsed = time.time() - t0
        token_usage = get_token_usage()
        msg = e.message
        emit_pipeline_cancelled(run_id, msg)
        update_run(
            run_id,
            status="cancelled",
            error=msg,
            elapsed_sec=elapsed,
            token_usage=token_usage,
        )
        logger.warning("Report generation cancelled after %.1fs: %s", elapsed, msg)
        return result if result is not None else initial_state

    except Exception as e:
        elapsed = time.time() - t0
        token_usage = get_token_usage()
        emit_pipeline_error(run_id, str(e))
        update_run(run_id, status="failed", error=str(e), elapsed_sec=elapsed, token_usage=token_usage)
        logger.error("Report generation failed after %.1fs: %s", elapsed, e)
        raise
    finally:
        end_run(run_id)
