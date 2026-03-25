"""
Sprint 2 end-to-end verification.

Full pipeline:
  1. Fetch research reports (EastMoney)
  2. Chunk documents → build Evidence Store (Chroma)
  3. Build BM25 index → hybrid retrieval
  4. Query Planner → generate section plans
  5. Section Writer → write one chapter with citations
"""

import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import EVIDENCE_DIR
from src.connectors.eastmoney import EastMoneyConnector
from src.evidence.store import EvidenceStore
from src.graph.nodes.planner import plan_report
from src.retrieval.citation import format_reference_list
from src.retrieval.retriever import HybridRetriever
from src.writers.section_writer import write_section

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("verify_sprint2")


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "人形机器人"

    print(f"\n{'='*60}")
    print(f"  Sprint 2 端到端验证")
    print(f"  行业主题: {topic}")
    print(f"{'='*60}\n")

    # ── Step 1: Fetch documents ──────────────────────────────
    print("[1/5] 抓取行业研报...")
    em = EastMoneyConnector(delay=2.0, max_pages=1, years_ago=2)
    docs = em.search_and_fetch(topic, max_reports=5)
    print(f"      获取 {len(docs)} 篇研报\n")

    for i, d in enumerate(docs):
        print(f"      {i+1}. {d.title} ({len(d.content_text)} chars)")

    # ── Step 2: Build Evidence Store ─────────────────────────
    print(f"\n[2/5] 构建证据池 (chunking + Chroma)...")

    # Use a fresh store for this verification run
    store_dir = EVIDENCE_DIR / "chroma_sprint2_verify"
    if store_dir.exists():
        shutil.rmtree(store_dir)

    store = EvidenceStore(persist_dir=store_dir)
    chunks = store.ingest_documents(docs)
    print(f"      文档分 chunk: {len(chunks)} 个")
    print(f"      Chroma 已存储: {store.count()} 个向量\n")

    if chunks:
        sample = chunks[0]
        print(f"      示例 chunk (来自「{sample.title}」):")
        print(f"      {sample.chunk_text[:120]}...\n")

    # ── Step 3: Hybrid retrieval ─────────────────────────────
    print("[3/5] 混合检索测试...")
    retriever = HybridRetriever(store)
    retriever.build_bm25_index(chunks)

    test_query = f"{topic}市场规模与增长趋势"
    results = retriever.retrieve(test_query, top_k=5)
    print(f"      查询: 「{test_query}」")
    print(f"      返回 {len(results)} 个相关 chunk:\n")

    for i, c in enumerate(results):
        preview = c.chunk_text[:80].replace('\n', ' ')
        print(f"      {i+1}. [{c.source_name}] {c.title}")
        print(f"         {preview}...")

    # ── Step 4: Query Planner ────────────────────────────────
    print(f"\n[4/5] 研究计划生成 (LLM)...")
    plan = plan_report(topic)
    print(f"      规范化主题: {plan['normalized_topic']}")
    print(f"      子任务数: {len(plan['task_list'])}")
    print(f"      章节数: {len(plan['section_plans'])}\n")

    for t in plan["task_list"]:
        print(f"      · {t}")

    print()
    for s in plan["section_plans"]:
        print(f"      [{s.order}] {s.title}")
        print(f"          {s.objective}")

    # ── Step 5: Write one section ────────────────────────────
    if plan["section_plans"]:
        target_section = plan["section_plans"][0]
        print(f"\n[5/5] 章节写作测试: 「{target_section.title}」")

        section_query = f"{plan['normalized_topic']} {target_section.title} {target_section.objective}"
        evidence = retriever.retrieve(section_query, top_k=6)
        print(f"      检索到 {len(evidence)} 条证据")

        drafted = write_section(
            topic=plan["normalized_topic"],
            section=target_section,
            evidence=evidence,
        )

        print(f"      章节字数: {len(drafted.markdown)}")
        print(f"      引用数: {len(drafted.citations)}")
        print(f"      图表建议: {len(drafted.chart_suggestions)} 条\n")

        print("      ── 章节内容预览 ──")
        print(f"      ## {drafted.title}\n")
        # Print first 600 chars
        preview_lines = drafted.markdown[:600]
        for line in preview_lines.splitlines():
            print(f"      {line}")
        if len(drafted.markdown) > 600:
            print(f"      ... (共 {len(drafted.markdown)} 字)")

        if drafted.chart_suggestions:
            print(f"\n      ── 图表建议 ──")
            for cs in drafted.chart_suggestions:
                print(f"      · {cs}")

        print(f"\n      ── 参考资料 ──")
        refs = format_reference_list(drafted.citations)
        for line in refs.splitlines()[:5]:
            print(f"      {line}")

    # ── Summary ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  Sprint 2 验证结果总结")
    print(f"{'='*60}")
    print(f"  行业主题:        {topic}")
    print(f"  研报抓取:        {len(docs)} 篇")
    print(f"  证据 chunks:     {len(chunks)} 个")
    print(f"  混合检索:        {'✓ 正常' if results else '✗ 异常'}")
    print(f"  研究计划:        {len(plan['section_plans'])} 个章节")
    print(f"  章节写作:        {'✓ 正常' if plan['section_plans'] else '✗ 跳过'}")
    print(f"  Sprint 2 状态:   {'✓ 全部通过' if results and plan['section_plans'] else '⚠ 部分通过'}")
    print(f"{'='*60}\n")

    # Cleanup
    if store_dir.exists():
        shutil.rmtree(store_dir)


if __name__ == "__main__":
    main()
