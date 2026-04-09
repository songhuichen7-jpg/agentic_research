"""Query Planner node — turns a user topic into a structured research plan.

Responsibilities (design doc §6.1):
  - Rewrite the industry topic into a researchable task
  - Generate a standardised research outline
  - Constrain report scope and time window
"""

from __future__ import annotations

import json
import logging
import re

from src.analysis.frameworks import format_frameworks_for_planner
from src.config.llm import get_writer_llm
from src.models import SectionPlan

logger = logging.getLogger(__name__)

_PLAN_PROMPT = """\
你是一位顶级券商的资深行业研究分析师（10 年以上经验）。请为以下行业主题制定一份**机构级**研究报告的写作计划。

行业主题：{topic}

## 要求

1. 将主题规范化为一个专业研究标题（格式：「XX行业深度研究：XX趋势与投资机会（2024-2028）」）
2. 列出 6-8 个研究子任务（task_list），确保覆盖以下维度：
   - 行业定义与产业链梳理
   - 市场规模与增速（历史 + 预测）
   - 驱动因素与政策环境
   - 竞争格局与主要玩家
   - 技术趋势或商业模式创新
   - 风险因素与投资建议
3. 设计 6-8 个报告章节（sections），遵循标准研报结构：
   - 第一章：行业概览与定义（产业链、上下游关系）
   - 第二章：市场规模与增长（TAM/SAM、历史数据、未来预测）
   - 第三章：驱动力分析（政策、技术、需求端）
   - 第四章：竞争格局（市场份额、头部企业对比、护城河）
   - 第五章：产业链与价值链分析
   - 第六章：风险与挑战
   - 第七章：投资建议与展望
   你可以根据具体行业调整章节，但不得少于 6 章。

## 分析框架
{frameworks}

严格按以下 JSON 格式输出，不要有任何其他文字：
```json
{{
  "normalized_topic": "规范化研究标题",
  "task_list": ["任务1", "任务2", ...],
  "sections": [
    {{"title": "章节标题", "objective": "该章节需要回答的核心问题，要具体，如：量化市场规模、对比 TOP5 企业份额"}},
    ...
  ]
}}
```
"""


def plan_report(topic: str) -> dict:
    """Call the writer LLM to generate a research plan.

    Returns dict with keys: normalized_topic, task_list, sections (list of SectionPlan).
    """
    llm = get_writer_llm(temperature=0.2)
    frameworks_text = format_frameworks_for_planner(topic)
    resp = llm.invoke(_PLAN_PROMPT.format(topic=topic, frameworks=frameworks_text))
    content = resp.content.strip()

    # Extract JSON from possible markdown fence
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if json_match:
        content = json_match.group(1)
    else:
        # Try to find raw JSON object
        brace_start = content.find("{")
        brace_end = content.rfind("}") + 1
        if brace_start != -1 and brace_end > brace_start:
            content = content[brace_start:brace_end]

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.error("Failed to parse planner JSON: %s", content[:300])
        raise ValueError(f"Planner LLM returned unparseable response: {content[:200]}")

    sections = []
    for i, sec in enumerate(data.get("sections", [])):
        sections.append(SectionPlan(
            title=sec.get("title", f"章节{i+1}"),
            objective=sec.get("objective", ""),
            order=i,
        ))

    return {
        "normalized_topic": data.get("normalized_topic", topic),
        "task_list": data.get("task_list", []),
        "section_plans": sections,
    }
