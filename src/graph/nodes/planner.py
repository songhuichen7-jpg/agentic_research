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

from src.config.llm import get_writer_llm
from src.models import SectionPlan

logger = logging.getLogger(__name__)

_PLAN_PROMPT = """\
你是一位资深行业研究分析师。用户希望你为以下行业主题制定一份研究报告的写作计划。

行业主题：{topic}

请你完成以下任务：
1. 将主题规范化为一个明确的研究标题（包含行业名称、研究范围、截止年份）
2. 列出 5-7 个研究子任务（task_list），覆盖行业全景
3. 列出 4-6 个报告章节（sections），每个章节给出标题和一句话目标

严格按以下 JSON 格式输出，不要有任何其他文字：
```json
{{
  "normalized_topic": "规范化研究标题",
  "task_list": ["任务1", "任务2", ...],
  "sections": [
    {{"title": "章节标题", "objective": "一句话说明该章节要回答什么问题"}},
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
    resp = llm.invoke(_PLAN_PROMPT.format(topic=topic))
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
