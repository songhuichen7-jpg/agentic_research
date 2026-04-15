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
你是一位顶级投行（中金/中信/高盛）的资深行业研究分析师，正在撰写面向机构投资者的行业深度研报。
读者是基金经理、投资委员会成员，他们只读有数据、有洞察的研报，对空话和套话零容忍。

## 研究主题
{topic}

## 本章节信息
- 章节标题：{section_title}
- 章节目标：{section_objective}

## 可引用的证据资料
以下是经过检索筛选的相关资料，每条资料前有引用编号 [cN]。你必须基于这些资料写作，禁止编造不存在的数据。

{evidence_block}

## 写作要求（必须严格遵守）

### 1. 数字密度（最重要）
- **每段文字必须至少包含 2 个具体数字**（金额、百分比、排名、时间等）
- **严禁使用以下模糊词汇**：较快、较高、显著、快速、巨大、广阔、强劲、不断、持续（不带数字）
- **必须具体到**：年份、季度、金额（亿元/万元）、百分比（精确到 0.1%）、公司名称、产品型号
- 示例：
  - ✗ "市场规模快速增长" → ✓ "市场规模从 2020 年的 850 亿元增至 2024 年的 1,560 亿元，CAGR 16.4%"
  - ✗ "头部企业市占率较高" → ✓ "TOP3 企业（A/B/C）合计市占率 42%（2024），较 2020 年的 28% 提升 14 pct"
  - ✗ "行业前景广阔" → ✓ "预计 2028 年市场规模达 3,200 亿元，对应 2024-2028 CAGR 19.8%"

### 2. 结构规范（3-4 个 ### 三级小节）
必须包含这些小节之一或组合：
- **### 核心观点**（3-4 句话，必须带数字的结论式陈述）
- **### 现状量化**（用数据描述当前市场规模、增速、结构）
- **### 竞争格局 / 驱动因素 / 产业链分析**（按章节目标选择）
- **### 趋势预判**（3-5 年前瞻，必须给出具体数字预测和时间点）

### 3. 分析深度
每个观点必须回答 **为什么** 和 **所以呢**：
- 不是"政策支持行业发展" → 而是"《XX发展规划》明确 2025 年渗透率目标 40%（当前 18%），政策直接拉动 XX 亿元需求 [c1]"
- 不是"竞争激烈" → 而是"TOP5 集中度从 2022 年的 58% 降至 2024 年的 49%，新进入者 12 家，头部企业价格战压缩毛利率 4.2 pct [c2]"

### 4. 篇幅：800-1500 字，宁精不滥
- 字数硬要求，但不要为了凑字数写废话
- 每句话要么有数据、要么有逻辑，否则删掉

### 5. 引用规范
- 每个数字后面必须有 [c1]、[c2] 引用标注
- 无引用的数字会被视为编造，严重违规

### 图表建议
**严格要求**：本章节所有正文结束后，必须用以下**精确格式**输出图表建议，禁止使用任何其他 JSON 对象形式（如 {{"图表建议": [...]}}）、禁止使用中文 key：

```chart_suggestions
["2019-2024 年市场规模柱状图", "主要企业市场份额饼图"]
```

- 必须用 ` ```chart_suggestions ` 作为代码块标签
- 数组元素为字符串，每个描述一个图表
- 即使没有合适的数据也必须输出 `[]`，不要省略
{framework_guidance}
只输出章节正文内容和最后的 chart_suggestions 代码块，不要重复章节标题。
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
    markdown = raw

    # 1. Try to extract from a proper fenced code block (```chart_suggestions or ```json)
    cs_match = re.search(
        r"```(?:chart_suggestions|json)?\s*(\[[^`]*?\])\s*```",
        markdown,
        re.DOTALL,
    )
    if cs_match:
        try:
            chart_suggestions = json.loads(cs_match.group(1))
        except json.JSONDecodeError:
            pass
        markdown = markdown[: cs_match.start()] + markdown[cs_match.end():]

    # 2. Try to extract from a JSON object with "图表建议" / "chart_suggestions" key
    obj_match = re.search(
        r'```(?:json)?\s*(\{[^`]*?(?:"图表建议"|"chart_suggestions")[^`]*?\})\s*```',
        markdown,
        re.DOTALL,
    )
    if obj_match:
        try:
            data = json.loads(obj_match.group(1))
            if isinstance(data, dict):
                for key in ("图表建议", "chart_suggestions"):
                    if key in data and isinstance(data[key], list):
                        chart_suggestions = data[key]
                        break
        except json.JSONDecodeError:
            pass
        markdown = markdown[: obj_match.start()] + markdown[obj_match.end():]

    # 3. Aggressive cleanup: remove bare JSON objects with 图表建议/chart_suggestions key
    #    (handles unfenced output like { "图表建议": [...] })
    markdown = re.sub(
        r'\{\s*"(?:图表建议|chart_suggestions)"\s*:\s*\[[\s\S]*?\]\s*\}',
        "",
        markdown,
    )

    # 4. Aggressive cleanup: remove bare chart_suggestions label + array
    markdown = re.sub(
        r"chart_suggestions\s*[\n\r]*\[[\s\S]*?(?:\]|$)",
        "",
        markdown,
        flags=re.IGNORECASE,
    )

    # 5. Remove "图表建议" heading/label followed by a list or JSON
    markdown = re.sub(
        r"(?:^|\n)\s*#{0,4}\s*图表建议[：:\s]*\n?\s*[\[\{][\s\S]*?[\]\}]",
        "",
        markdown,
    )

    # 6. Remove any stray triple-backtick fences with just "chart_suggestions" or "json" label
    markdown = re.sub(r"```(?:chart_suggestions|json)?\s*$", "", markdown, flags=re.MULTILINE)
    # 7. Remove trailing orphan code fences
    markdown = re.sub(r"\n\s*```\s*$", "", markdown)
    markdown = markdown.strip()

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
