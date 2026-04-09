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
from src.analysis.frameworks import format_framework_for_writer
from src.config.llm import get_writer_llm
from src.models import Citation, DraftedSection, EvidenceChunk, SectionPlan
from src.retrieval.citation import build_citation_list, format_citations_for_prompt

logger = logging.getLogger(__name__)

_SECTION_PROMPT = """\
你是一位顶级券商的资深行业研究分析师，正在撰写一份面向机构投资者的行业深度研报。

## 研究主题
{topic}

## 本章节信息
- 章节标题：{section_title}
- 章节目标：{section_objective}

## 可引用的证据资料
以下是经过检索筛选的相关资料，每条资料前有引用编号 [cN]。你必须基于这些资料写作，禁止编造不存在的数据。

{evidence_block}

## 写作要求

### 篇幅与深度
- 本章节需要写出 **800-1500 字**的深度分析内容
- 必须包含具体的数据、数字、百分比，不要空泛的定性描述
- 如果资料中有具体数字（市场规模、增速、市占率等），必须引用并分析其含义

### 结构规范
请按以下结构组织内容（用 Markdown 三级标题 ### 分隔）：

1. **核心观点**（2-3 句话概括本章结论，开门见山）
2. **详细分析**（主体内容，要求：
   - 每个论点必须有数据支撑，用 [cN] 标注来源
   - 使用对比分析（同比、环比、国际对比、企业对比）
   - 提供因果逻辑链，不要只罗列事实
   - 如涉及市场规模，给出具体数字和计算逻辑
   - 如涉及竞争格局，给出 TOP3-5 企业的份额或对比）
3. **趋势与展望**（基于数据的前瞻判断，2-3 句）

### 写作风格
- 语言专业精炼，像券商研报而非新闻稿
- 多用数据说话，少用"行业快速发展""前景广阔"等空话
- 段落之间要有逻辑衔接

### 图表建议
在末尾用 JSON 列出适合图表化的数据（如果有具体数字的话），格式：
```chart_suggestions
["建议1: 具体描述什么数据做什么图（如：2019-2024 年市场规模柱状图）", ...]
```
{framework_guidance}
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

    evidence_count = len(evidence)
    # Deduplicate sources for tracking
    evidence_sources = list({c.title or c.url for c in evidence if c.title or c.url})

    if evidence_count == 0:
        logger.warning("Section '%s' has ZERO evidence — output will lack citations", section.title)

    citations = build_citation_list(evidence)
    evidence_block = format_citations_for_prompt(citations)

    if not evidence_block.strip():
        evidence_block = (
            "（暂无检索到的相关资料。请基于行业常识简要分析，"
            "但必须在每个段落开头用 **[数据不足]** 标注，明确告知读者本段缺乏数据支撑。）"
        )

    # Auto-compute metrics from evidence text
    all_evidence_text = "\n".join(c.chunk_text for c in evidence)
    computed = extract_and_compute(all_evidence_text)
    if computed:
        evidence_block += "\n\n## 自动计算的行业指标\n" + "\n".join(computed)

    framework_guidance = format_framework_for_writer(topic, section.title)

    prompt = _SECTION_PROMPT.format(
        topic=topic,
        section_title=section.title,
        section_objective=section.objective,
        evidence_block=evidence_block,
        framework_guidance=framework_guidance,
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
        evidence_count=evidence_count,
        evidence_sources=evidence_sources,
    )
