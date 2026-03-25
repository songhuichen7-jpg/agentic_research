"""Section Writer — generates one report chapter from evidence.

Flow (design doc §6.6):
  1. Receive section objective + retrieved evidence
  2. Generate draft with inline citation markers [c1], [c2] …
  3. Output: markdown text + citation list + chart suggestions
"""

from __future__ import annotations

import json
import logging
import re

from src.analysis.calculator import extract_and_compute
from src.config.llm import get_writer_llm
from src.models import Citation, DraftedSection, EvidenceChunk, SectionPlan
from src.retrieval.citation import build_citation_list, format_citations_for_prompt

logger = logging.getLogger(__name__)

_SECTION_PROMPT = """\
你是一位专业的行业研究分析师，正在撰写一份行业研报的某个章节。

## 研究主题
{topic}

## 本章节信息
- 章节标题：{section_title}
- 章节目标：{section_objective}

## 可引用的证据资料
以下是经过检索筛选的相关资料，每条资料前有引用编号 [cN]。你必须基于这些资料写作，禁止编造不存在的数据。

{evidence_block}

## 写作要求
1. 围绕章节目标，写出 400-800 字的分析内容
2. 每个核心观点或数据必须用 [cN] 标注来源
3. 包含以下结构：
   - 核心观点（1-2 句总结）
   - 详细分析（数据支撑的展开论述）
   - 风险与限制（如有）
4. 在末尾用 JSON 列出适合图表化的数据建议（如果有的话），格式如下：
   ```chart_suggestions
   ["建议1: 描述什么数据适合做什么图", ...]
   ```
5. 使用 Markdown 格式，语言专业但不晦涩

只输出章节正文内容和图表建议，不要重复章节标题。
"""

# How often to emit a streaming detail event (every N chars)
_STREAM_EMIT_INTERVAL = 80


def write_section(
    topic: str,
    section: SectionPlan,
    evidence: list[EvidenceChunk],
    *,
    run_id: str = "",
    node: str = "write_sections",
) -> DraftedSection:
    """Write a single report section based on retrieved evidence.

    When *run_id* is provided, uses LLM streaming and emits detail events
    so the frontend can display token-level progress.
    """
    from src.telemetry.run_events import emit_node_detail

    citations = build_citation_list(evidence)
    evidence_block = format_citations_for_prompt(citations)

    if not evidence_block.strip():
        evidence_block = "（暂无检索到的相关资料，请基于行业常识简要分析，并注明缺乏数据支撑。）"

    # Auto-compute metrics from evidence text
    all_evidence_text = "\n".join(c.chunk_text for c in evidence)
    computed = extract_and_compute(all_evidence_text)
    if computed:
        evidence_block += "\n\n## 自动计算的行业指标\n" + "\n".join(computed)

    prompt = _SECTION_PROMPT.format(
        topic=topic,
        section_title=section.title,
        section_objective=section.objective,
        evidence_block=evidence_block,
    )

    llm = get_writer_llm(temperature=0.3)

    if run_id:
        # ── Streaming mode ────────────────────────────────────
        emit_node_detail(run_id, node, f"开始写作「{section.title}」({len(evidence)} 条证据)")
        chunks: list[str] = []
        buf = ""
        emitted_len = 0
        try:
            for chunk in llm.stream(prompt):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                if not token:
                    continue
                chunks.append(token)
                buf += token
                # Emit buffered tokens periodically so SSE isn't flooded
                if len(buf) - emitted_len >= _STREAM_EMIT_INTERVAL:
                    snippet = buf[emitted_len:]
                    emit_node_detail(run_id, node, f"「{section.title}」{snippet}")
                    emitted_len = len(buf)
        except Exception as e:
            logger.error("Streaming failed for section '%s': %s", section.title, e)
            # Fallback to non-streaming invoke
            resp = llm.invoke(prompt)
            raw = resp.content.strip()
        else:
            # Flush remaining buffer
            if emitted_len < len(buf):
                emit_node_detail(run_id, node, f"「{section.title}」{buf[emitted_len:]}")
            raw = "".join(chunks)
            emit_node_detail(run_id, node, f"「{section.title}」写作完成 ({len(raw)} 字)")
    else:
        # ── Non-streaming mode (backward compatible) ──────────
        resp = llm.invoke(prompt)
        raw = resp.content.strip()

    # Extract chart suggestions if present
    chart_suggestions: list[str] = []
    cs_match = re.search(r"```chart_suggestions\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if cs_match:
        try:
            chart_suggestions = json.loads(cs_match.group(1))
        except json.JSONDecodeError:
            pass
        markdown = raw[: cs_match.start()].strip()
    else:
        markdown = raw

    # Clean up any leftover code fences
    markdown = re.sub(r"```json\s*\[.*?\]\s*```", "", markdown, flags=re.DOTALL).strip()

    return DraftedSection(
        section_id=section.section_id,
        title=section.title,
        markdown=markdown,
        citations=citations,
        chart_suggestions=chart_suggestions,
        order=section.order,
    )
