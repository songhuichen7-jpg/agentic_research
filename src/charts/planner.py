"""Chart Planner — extracts chartable data from drafted sections.

Two strategies:
  1. **LLM full-report scan**: concatenate all sections, one LLM call to
     extract 3-5 charts from the full picture.
  2. **Heuristic fallback**: regex-based extraction of common numeric patterns
     (year-market-size, share percentages, multi-entity comparison).
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from src.config.llm import get_writer_llm
from src.models import ChartSpec, ChartType, DraftedSection

logger = logging.getLogger(__name__)

_CHART_TYPE_MAP = {
    "line": ChartType.LINE,
    "bar": ChartType.BAR,
    "stacked_bar": ChartType.STACKED_BAR,
    "pie": ChartType.PIE,
    "table": ChartType.TABLE,
    "timeline": ChartType.TIMELINE,
}

# ── LLM prompt (full report) ─────────────────────────────

_FULL_PROMPT = """\
你是一位资深数据可视化专家。以下是完整行业研报，请识别**真实出现的数值数据**，生成 3-5 个高质量图表。

## 研究主题
{topic}

## 研报全文
{full_text}

## 严格要求

### 数据真实性（最重要）
1. **只提取原文中真实出现的具体数值**，禁止推断、估算、编造任何数字
2. 每个数据点必须能在原文中找到对应句子
3. **绝对禁止输出 y 值为 0 或全部接近 0 的图表**
4. **禁止把年份、序号、引用编号（如 c1 中的 1）当作数值**
5. 如果某类型数据不足，宁可不生成，也不要编造

### 图表类型选择
按优先级：
- **line（趋势图）**: 多个连续年份的市场规模/产值/销量，至少 3 个年份
- **bar（柱状图）**: 企业/区域/产品对比，至少 3 个数据点
- **pie（饼图）**: 市场份额占比，总和接近 100%，至少 3 项
- **stacked_bar（堆叠柱）**: 多年份 × 多类别
- **table（表格）**: 最后选项

### 输出规则
- **只输出 JSON 数组**，不要有其他文字
- 至少 3 个图表
- y 数组必须是纯数字 float
- 不同图表不要展示重复数据
- 标题要具体清晰（如"2019-2024年中国人形机器人市场规模趋势"）

```json
[
  {{
    "chart_type": "line",
    "title": "具体清晰的图表标题",
    "x": ["2019年", "2020年", "2021年", "2022年", "2023年"],
    "y": [12.5, 18.3, 25.7, 35.2, 48.9],
    "unit": "亿元",
    "caption": "一句话说明图表含义",
    "source_refs": ["c1"]
  }}
]
```
"""


def _parse_llm_json(raw: str) -> list[dict]:
    """Extract a JSON array from LLM output."""
    json_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1)
    else:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start != -1 and end > start:
            raw = raw[start:end]
    try:
        items = json.loads(raw)
        return items if isinstance(items, list) else []
    except json.JSONDecodeError:
        logger.warning("Unparseable chart JSON: %s", raw[:200])
        return []


def _validate_specs(items: list[dict]) -> list[ChartSpec]:
    """Validate and convert raw JSON items to ChartSpecs."""
    specs: list[ChartSpec] = []
    for item in items:
        ct = _CHART_TYPE_MAP.get(item.get("chart_type", ""), ChartType.BAR)
        x = item.get("x", [])
        y = item.get("y", [])

        if not x or not y or len(x) != len(y):
            continue
        try:
            y = [float(v) for v in y]
        except (ValueError, TypeError):
            continue
        if len(x) < 2 and ct in (ChartType.BAR, ChartType.LINE, ChartType.PIE, ChartType.STACKED_BAR):
            continue

        # Reject charts where all values are zero or near-zero (meaningless data)
        if ct in (ChartType.BAR, ChartType.LINE, ChartType.PIE, ChartType.STACKED_BAR, ChartType.KPI):
            if all(abs(v) < 0.001 for v in y):
                logger.warning("Rejecting chart '%s': all y-values are zero", item.get("title", ""))
                continue
            # Reject if too many zeros (> 50%)
            zero_count = sum(1 for v in y if abs(v) < 0.001)
            if zero_count > len(y) / 2:
                logger.warning("Rejecting chart '%s': %d/%d zero values", item.get("title", ""), zero_count, len(y))
                continue

        if ct == ChartType.PIE:
            s = sum(y)
            if s > 0 and (s < 50 or s > 200):
                logger.info("Pie '%s' sum=%g, may look odd", item.get("title", ""), s)

        specs.append(
            ChartSpec(
                chart_type=ct,
                title=item.get("title", ""),
                x=x,
                y=y,
                unit=item.get("unit", ""),
                caption=item.get("caption", ""),
                source_refs=item.get("source_refs", []),
            )
        )
    return specs


# ── Heuristic fallback ───────────────────────────────────

_RE_TREND = re.compile(
    r"(20[12]\d)\s*年[^，。]{0,15}?(?:规模|产值|需求量|市场|销售额|营收)"
    r"[^，。]{0,10}?(\d+(?:\.\d+)?)\s*(亿|万|百万|千)",
)

_RE_SHARE = re.compile(
    r"([^，。\d]{2,15}?)(?:占比|份额|市场占有率)[^，。]{0,5}?(\d+(?:\.\d+)?)%",
)

_RE_YEAR_EVENT = re.compile(
    r"(20[012]\d)\s*年[^，。\n]{0,40}?(?:发布|成立|突破|上市|推出|获批|首次|实现|达到|里程碑)",
)

_RE_IMPORTANT_TERMS = re.compile(r"[\u4e00-\u9fff]{2,6}")


def _heuristic_extract(full_text: str) -> list[ChartSpec]:
    """Regex-based extraction of common data patterns."""
    specs: list[ChartSpec] = []

    # 1. Year–market-size trend (line chart)
    trend_matches = _RE_TREND.findall(full_text)
    if len(trend_matches) >= 2:
        # Deduplicate by year
        year_data: dict[str, float] = {}
        unit_hint = ""
        for year, value, unit in trend_matches:
            year_data[year] = float(value)
            unit_hint = unit + "元"
        if len(year_data) >= 2:
            sorted_years = sorted(year_data.keys())
            specs.append(
                ChartSpec(
                    chart_type=ChartType.LINE,
                    title="市场规模趋势",
                    x=[f"{y}年" for y in sorted_years],
                    y=[year_data[y] for y in sorted_years],
                    unit=unit_hint,
                    caption="基于报告中提及的市场规模数据",
                )
            )

    # 2. Market share (pie chart)
    share_matches = _RE_SHARE.findall(full_text)
    if len(share_matches) >= 2:
        # Take top entries, deduplicate
        seen_names: set[str] = set()
        names: list[str] = []
        values: list[float] = []
        for name, pct in share_matches:
            name = name.strip()
            if name in seen_names or len(name) < 2:
                continue
            seen_names.add(name)
            names.append(name)
            values.append(float(pct))
            if len(names) >= 6:
                break
        if len(names) >= 2 and sum(values) > 0:
            specs.append(
                ChartSpec(
                    chart_type=ChartType.PIE,
                    title="市场份额分布",
                    x=names,
                    y=values,
                    unit="%",
                    caption="基于报告中提及的市场份额数据",
                )
            )

    if specs:
        logger.info("Heuristic extraction produced %d chart(s)", len(specs))
    return specs


def _heuristic_timeline(full_text: str) -> list[ChartSpec]:
    """Extract chronological events for a timeline."""
    matches = _RE_YEAR_EVENT.findall(full_text)
    if len(matches) < 3:
        return []

    # Deduplicate and sort
    events = sorted(set(matches))
    if len(events) < 3:
        return []

    return [
        ChartSpec(
            chart_type=ChartType.TIMELINE,
            title="产业发展时间线",
            x=[f"{y}年" for y in events],
            y=[0.0] * len(events),  # unused for timeline
            caption="报告中提及的关键时间节点",
        )
    ]


def _heuristic_wordcloud(full_text: str) -> list[ChartSpec]:
    """Extract top keywords for a word cloud."""
    # Remove common stop words
    stop_words = {
        "的",
        "在",
        "是",
        "和",
        "与",
        "及",
        "为",
        "等",
        "了",
        "也",
        "将",
        "从",
        "到",
        "对",
        "于",
        "其",
        "中",
        "有",
        "不",
        "已",
        "被",
        "个",
        "这",
        "之",
        "而",
        "或",
        "由",
        "所",
        "如",
        "但",
        "并",
        "更",
        "上",
        "下",
        "该",
        "以",
        "可以",
        "以及",
        "通过",
        "进行",
        "实现",
        "发展",
        "研究",
        "分析",
        "报告",
        "方面",
        "情况",
        "问题",
        "目前",
        "当前",
        "随着",
        "相关",
        "包括",
        "不仅",
        "因此",
        "同时",
        "进一步",
        "基于",
    }

    all_terms = _RE_IMPORTANT_TERMS.findall(full_text)
    from collections import Counter

    term_counts = Counter(t for t in all_terms if t not in stop_words and len(t) >= 2)

    # Take top 20
    top = term_counts.most_common(20)
    if len(top) < 5:
        return []

    labels = [t[0] for t in top]
    weights = [float(t[1]) for t in top]

    return [
        ChartSpec(
            chart_type=ChartType.WORDCLOUD,
            title="报告关键词",
            x=labels,
            y=weights,
            caption="全文高频关键词",
        )
    ]


def _heuristic_kpi(full_text: str) -> list[ChartSpec]:
    """Extract single key metrics as KPI cards."""
    matches = _RE_ANY_NUMBER.findall(full_text)
    if len(matches) < 2:
        return []

    seen: set[str] = set()
    labels: list[str] = []
    values: list[float] = []
    for label, val, unit in matches:
        label = label.strip()
        if label in seen or len(label) < 3:
            continue
        seen.add(label)
        labels.append(f"{label} ({unit}{'元' if unit not in ('%',) else ''})")
        values.append(float(val))
        if len(labels) >= 4:
            break

    if len(labels) < 1:
        return []

    return [
        ChartSpec(
            chart_type=ChartType.KPI,
            title="核心指标",
            x=labels,
            y=values,
            caption="报告中提及的核心数据指标",
        )
    ]


def _heuristic_chain(full_text: str) -> list[ChartSpec]:
    """Detect upstream/midstream/downstream chain structure."""
    chain_keywords = ["上游", "中游", "下游", "基础层", "技术层", "应用层", "芯片", "算法", "应用", "数据层", "平台层"]
    found = [kw for kw in chain_keywords if kw in full_text]
    if len(found) < 3:
        return []

    # Order them logically
    order_map = {
        "上游": 0,
        "基础层": 0,
        "芯片": 0,
        "数据层": 0,
        "中游": 1,
        "技术层": 1,
        "算法": 1,
        "平台层": 1,
        "下游": 2,
        "应用层": 2,
        "应用": 2,
    }
    found.sort(key=lambda k: order_map.get(k, 1))

    return [
        ChartSpec(
            chart_type=ChartType.CHAIN,
            title="产业链结构",
            x=found[:5],
            y=[0.0] * min(len(found), 5),
            caption="报告中识别的产业链环节",
        )
    ]


def _heuristic_matrix(full_text: str) -> list[ChartSpec]:
    """Detect comparison dimensions for a matrix."""
    dim_patterns = [r"(?:美国|中国|欧洲|日本|英国)", r"(?:优势|劣势|特点|现状)"]
    entity_matches = re.findall(dim_patterns[0], full_text)
    dim_matches = re.findall(dim_patterns[1], full_text)

    entities = list(dict.fromkeys(entity_matches))  # dedupe, keep order
    dims = list(dict.fromkeys(dim_matches))

    if len(entities) >= 2 and len(dims) >= 2:
        return [
            ChartSpec(
                chart_type=ChartType.MATRIX,
                title="多维对比",
                x=entities[:4],
                y=[float(i) for i in range(len(dims[:4]))],
                caption=f"{', '.join(dims[:3])}等维度对比",
            )
        ]

    return []


# ── Fallback summary table ───────────────────────────────

_RE_ANY_NUMBER = re.compile(
    r"([^，。\n]{3,20}?)(?:为|达|约|超过|突破|达到|是)[^，。\n]{0,5}"
    r"(\d+(?:\.\d+)?)\s*(亿|万|百万|千|%)",
)


def _fallback_summary_table(full_text: str) -> list[ChartSpec]:
    """When no charts can be generated, create a KPI summary table."""
    matches = _RE_ANY_NUMBER.findall(full_text)
    if len(matches) < 3:
        return []

    # Deduplicate and limit
    seen: set[str] = set()
    labels: list[str] = []
    values: list[float] = []
    units: list[str] = []

    for label, val, unit in matches:
        label = label.strip()
        if label in seen or len(label) < 2:
            continue
        seen.add(label)
        labels.append(label)
        values.append(float(val))
        units.append(unit)
        if len(labels) >= 8:
            break

    if len(labels) < 2:
        return []

    # Determine dominant unit
    from collections import Counter

    dominant_unit = Counter(units).most_common(1)[0][0] if units else ""

    return [
        ChartSpec(
            chart_type=ChartType.TABLE,
            title="关键数据摘要",
            x=labels,
            y=values,
            unit=dominant_unit + ("元" if dominant_unit not in ("%",) else ""),
            caption="报告中提及的关键数值指标",
        )
    ]


# ── Dedup ────────────────────────────────────────────────

# Core keywords that indicate the "same kind" of chart
_CHART_SEMANTICS = [
    {"规模", "产值", "需求量", "销售额", "营收", "市场规模", "产业规模"},
    {"份额", "占比", "占有率", "百分比"},
    {"增长", "增速", "增长率", "增速"},
    {"排名", "对比", "比较"},
]


def _chart_semantic_key(title: str, chart_type: ChartType) -> str:
    """Return a semantic key so charts about the same topic are grouped."""
    title_norm = re.sub(r"\s+", "", title)
    for group in _CHART_SEMANTICS:
        for kw in group:
            if kw in title_norm:
                return f"{chart_type.value}:{kw}"
    # Fallback: first 4 chars of normalised title
    return f"{chart_type.value}:{title_norm[:4]}"


def _data_overlap_ratio(a: list[str], b: list[str]) -> float:
    """Jaccard similarity of two x-label lists."""
    sa, sb = set(str(v) for v in a), set(str(v) for v in b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _deduplicate_charts(specs: list[ChartSpec]) -> list[ChartSpec]:
    if len(specs) <= 1:
        return specs

    unique: list[ChartSpec] = []
    meta: list[tuple[str, ChartType, list[str]]] = []  # (semantic_key, type, x)

    for spec in specs:
        sem_key = _chart_semantic_key(spec.title, spec.chart_type)
        is_dup = False

        for prev_key, prev_type, prev_x in meta:
            # Same chart type + same semantic group → duplicate
            if spec.chart_type == prev_type and sem_key == prev_key:
                logger.info("Dedup (semantic): '%s' ≈ '%s'", spec.title, prev_key)
                is_dup = True
                break

            # Same chart type + >50% data overlap → duplicate
            if spec.chart_type == prev_type and _data_overlap_ratio(spec.x, prev_x) > 0.5:
                logger.info("Dedup (overlap): '%s' x labels overlap with previous", spec.title)
                is_dup = True
                break

        if not is_dup:
            unique.append(spec)
            meta.append((sem_key, spec.chart_type, [str(v) for v in spec.x]))

    if len(unique) < len(specs):
        logger.info("Dedup: %d → %d charts", len(specs), len(unique))
    return unique


# ── Public API ───────────────────────────────────────────


def plan_charts(section: DraftedSection) -> list[ChartSpec]:
    """Legacy: plan charts from a single section (kept for backward compat)."""
    if not section.markdown.strip():
        return []
    llm = get_writer_llm(temperature=0.1)
    resp = llm.invoke(
        _FULL_PROMPT.format(
            topic="",
            full_text=section.markdown[:3000],
        )
    )
    return _validate_specs(_parse_llm_json(resp.content.strip()))


def plan_charts_for_sections(
    sections: list[DraftedSection],
    topic: str = "",
) -> list[ChartSpec]:
    """Plan high-quality charts combining real market data + LLM extraction.

    Strategy:
      1. **Real data first**: fetch up to 2 charts from AkShare (sector index, top holdings)
      2. **LLM extraction**: scan report text for numeric data, get up to 3 more charts
      3. **Max 4 charts total**, strictly validated
      4. No KPI/chain/matrix/wordcloud auto-adds (low quality)
    """
    if not sections:
        return []

    # ── 1. Real market data charts (AkShare) ─────────────
    specs: list[ChartSpec] = []
    if topic:
        try:
            from src.charts.real_data import fetch_real_data_charts
            real_charts = fetch_real_data_charts(topic)
            specs.extend(real_charts)
            logger.info("Real data charts: %d", len(real_charts))
        except Exception as e:
            logger.warning("Real data fetch failed: %s", e)

    # ── 2. Concatenate all markdown for LLM scan ─────────
    full_text_parts: list[str] = []
    for sec in sections:
        if sec.markdown.strip():
            full_text_parts.append(f"### {sec.title}\n{sec.markdown}")
    if not full_text_parts:
        return specs  # Return whatever real data we got

    full_text = "\n\n".join(full_text_parts)

    # ── 3. LLM extraction (at most 3 more charts, for a total of ~4) ──
    remaining = max(0, 4 - len(specs))
    if remaining > 0:
        topic_guess = topic or (sections[0].title if sections else "")
        try:
            llm = get_writer_llm(temperature=0.1)
            resp = llm.invoke(
                _FULL_PROMPT.format(
                    topic=topic_guess,
                    full_text=full_text[:10000],
                )
            )
            items = _parse_llm_json(resp.content.strip())
            llm_specs = _validate_specs(items)

            # Dedup against real data charts
            existing_titles = {re.sub(r"\s+", "", s.title).lower() for s in specs}
            for spec in llm_specs[:remaining]:
                norm = re.sub(r"\s+", "", spec.title).lower()
                if not any(norm == t or norm in t or t in norm for t in existing_titles):
                    specs.append(spec)
                    existing_titles.add(norm)
            logger.info("LLM chart planner produced %d valid chart(s)", len(llm_specs))
        except Exception as e:
            logger.warning("LLM chart planning failed: %s", e)

    # ── 4. Data heuristics fallback (only if still < 2) ──
    if len(specs) < 2:
        heuristic = _heuristic_extract(full_text)
        existing_titles = {re.sub(r"\s+", "", s.title).lower() for s in specs}
        for h in heuristic:
            if len(specs) >= 3:
                break
            norm = re.sub(r"\s+", "", h.title).lower()
            if not any(norm == t or norm in t or t in norm for t in existing_titles):
                specs.append(h)
                existing_titles.add(norm)
                logger.info("Added heuristic chart: %s", h.title)

    # ── 5. Hard cap at 4 charts ──────────────────────────
    specs = _deduplicate_charts(specs)[:4]
    logger.info("Final chart count: %d (real + LLM, max 4)", len(specs))
    return specs
