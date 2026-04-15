"""Executive Summary generator — creates investment highlights + key metrics table.

Produces the opening section of a professional institutional research report:
  1. Investment thesis (1 paragraph)
  2. 4-6 investment highlights (bullet points with data)
  3. Key metrics table (8-12 key numbers)
  4. Investment rating + target window
"""

from __future__ import annotations

import json
import logging
import re

from src.config.llm import get_writer_llm
from src.models import DraftedSection

logger = logging.getLogger(__name__)


_SUMMARY_PROMPT = """\
你是一位资深行业研究分析师，正在为一份完整的行业深度研报撰写**开篇执行摘要**（Executive Summary）。
这是全篇最关键的部分，读者可能只看这一页，所以必须高度浓缩、数据密集。

## 研究主题
{topic}

## 完整研报内容（所有章节）
{full_text}

## 任务

从研报内容中提炼出一份专业的开篇摘要，包含四个部分：

### 1. 核心观点（thesis）
一段 80-120 字的总结，概括本行业的核心投资逻辑。必须包含：
- 市场当前规模（具体数字）
- 未来增长预期（具体 CAGR 或增速）
- 主要驱动因素（1-2 个）

### 2. 投资要点（highlights）
4-6 条关键发现，每条格式：
- **[一句话核心结论]**：具体数据/案例支撑（20-40 字）
- 必须带数字，禁止"快速增长""广阔前景"这种空话
- 每条都要锚定原文数据

### 3. 核心指标表（metrics）
从研报中提取 8-12 个最关键的量化指标，格式：
- 指标名 | 数值 | 单位/说明
- 优先提取：市场规模、同比增速、CAGR、TOP3/TOP5 集中度、头部企业市占率、
  关键技术渗透率、核心客户结构、政策目标数字、价格水平等
- 每个必须是具体数字，禁止"较高""增长迅速"等定性描述

### 4. 投资建议（rating）
- rating: 必须是 "强烈推荐" / "推荐" / "中性" / "回避" 之一
- time_window: 建议关注时间窗口（如 "6-12个月" / "2024-2026"）
- key_assumption: 一句话说明该评级依赖的最关键假设

## 输出格式

**严格输出以下 JSON 对象（不要代码块包装，不要其他文字）：**

{{
  "thesis": "核心观点文本...",
  "highlights": [
    "**核心结论1**: 具体数据支撑",
    "**核心结论2**: 具体数据支撑",
    "..."
  ],
  "metrics": [
    {{"name": "市场规模", "value": "1500", "unit": "亿元 (2024)"}},
    {{"name": "CAGR", "value": "23.4", "unit": "% (2024-2028E)"}},
    "..."
  ],
  "rating": "推荐",
  "time_window": "6-12个月",
  "key_assumption": "依赖政策持续支持和核心技术突破"
}}
"""


def _parse_json(raw: str) -> dict | None:
    """Extract a JSON object from LLM output."""
    raw = raw.strip()
    # Strip code fences
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw)
    if m:
        raw = m.group(1)
    else:
        # Find first { ... matching }
        start = raw.find("{")
        if start == -1:
            return None
        # Naive brace matching
        depth = 0
        end = start
        for i, ch in enumerate(raw[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        raw = raw[start:end]

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse executive summary JSON: %s", e)
        return None


def generate_executive_summary(topic: str, sections: list[DraftedSection]) -> dict | None:
    """Generate an executive summary dict from drafted sections.

    Returns a dict with keys: thesis, highlights, metrics, rating, time_window, key_assumption.
    Returns None if generation fails.
    """
    if not sections:
        return None

    # Build full text (cap to avoid exceeding context)
    parts: list[str] = []
    for sec in sections:
        if sec.markdown.strip():
            parts.append(f"### {sec.title}\n{sec.markdown}")
    if not parts:
        return None
    full_text = "\n\n".join(parts)[:15000]  # ~ 15k chars

    llm = get_writer_llm(temperature=0.2)
    try:
        resp = llm.invoke(_SUMMARY_PROMPT.format(topic=topic, full_text=full_text))
    except Exception as e:
        logger.error("Executive summary LLM call failed: %s", e)
        return None

    data = _parse_json(resp.content)
    if not data or not isinstance(data, dict):
        logger.warning("Executive summary returned invalid JSON")
        return None

    # Validate shape
    required = ("thesis", "highlights", "metrics", "rating")
    if not all(k in data for k in required):
        logger.warning("Executive summary missing keys: %s", set(required) - set(data.keys()))
        return None

    logger.info(
        "Executive summary generated: rating=%s, %d highlights, %d metrics",
        data.get("rating"),
        len(data.get("highlights", [])),
        len(data.get("metrics", [])),
    )
    return data


def format_executive_summary_markdown(summary: dict, topic: str) -> str:
    """Format an executive summary dict as Markdown for insertion into the report."""
    lines: list[str] = []

    # Rating badge at the very top
    rating = summary.get("rating", "中性")
    rating_map = {
        "强烈推荐": "★★★ 强烈推荐",
        "推荐": "★★ 推荐",
        "中性": "★ 中性",
        "回避": "✕ 回避",
    }
    rating_display = rating_map.get(rating, f"★ {rating}")

    lines.append("## 执行摘要")
    lines.append("")

    # Rating + time window
    time_window = summary.get("time_window", "")
    assumption = summary.get("key_assumption", "")
    lines.append(f"> **投资评级**: {rating_display}　　**时间窗口**: {time_window}")
    if assumption:
        lines.append(f">")
        lines.append(f"> **关键假设**: {assumption}")
    lines.append("")

    # Thesis
    thesis = summary.get("thesis", "")
    if thesis:
        lines.append("### 核心观点")
        lines.append("")
        lines.append(thesis)
        lines.append("")

    # Investment highlights
    highlights = summary.get("highlights", [])
    if highlights:
        lines.append("### 投资要点")
        lines.append("")
        for h in highlights:
            if isinstance(h, str):
                lines.append(f"- {h}")
        lines.append("")

    # Key metrics table
    metrics = summary.get("metrics", [])
    if metrics and isinstance(metrics, list):
        lines.append("### 核心指标")
        lines.append("")
        lines.append("| 指标 | 数值 | 单位/说明 |")
        lines.append("|------|-----:|-----------|")
        for m in metrics:
            if isinstance(m, dict):
                name = str(m.get("name", ""))
                value = str(m.get("value", ""))
                unit = str(m.get("unit", ""))
                if name and value:
                    lines.append(f"| {name} | **{value}** | {unit} |")
        lines.append("")

    return "\n".join(lines)
