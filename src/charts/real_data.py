"""Real data fetcher — uses AkShare + LLM to pull actual market data for charts.

Strategy:
  1. Fetch all SW (申万) level-1 industry list (31 industries)
  2. Ask LLM to map user topic → best matching SW industry
  3. Fetch the sector's historical index (monthly) for the past 2-3 years
  4. Fetch SW industry PE/PB ratios — generate cross-industry comparison

Uses only endpoints verified to work from the deployment environment.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

from src.config.llm import get_utility_llm
from src.models import ChartSpec, ChartType

logger = logging.getLogger(__name__)


def _get_sw_industries() -> pd.DataFrame | None:
    """Get the 31 SW level-1 industries with PE/PB data."""
    try:
        df = ak.sw_index_first_info()
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        logger.warning("Failed to fetch SW industry list: %s", e)
        return None


_MAP_PROMPT = """\
用户要研究的行业主题：{topic}

以下是可用的申万一级行业列表（31 个）：
{industry_list}

请从上述列表中选出与用户主题**最相关的 1-2 个**申万行业名称。只返回 JSON，不要其他文字：

{{"primary": "行业名称1", "secondary": "行业名称2 或 null"}}

规则：
- primary 是主要相关行业，secondary 是次要相关（可为 null）
- 必须从列表中精确选择，不要自己编造
- 示例：用户问"人形机器人" → primary="机械设备"（因为机器人属于机械设备）
- 示例：用户问"AI 大模型" → primary="计算机"
- 示例：用户问"低空经济" → primary="国防军工"（航空装备归军工）, secondary="交通运输"
"""


def _llm_map_topic_to_sector(topic: str, industries: list[str]) -> tuple[str | None, str | None]:
    """Use LLM to map user topic to 1-2 SW industries."""
    try:
        llm = get_utility_llm(temperature=0)
        prompt = _MAP_PROMPT.format(topic=topic, industry_list="、".join(industries))
        resp = llm.invoke(prompt)
        raw = resp.content.strip()
        # Extract JSON
        m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if not m:
            return None, None
        data = json.loads(m.group(0))
        primary = data.get("primary")
        secondary = data.get("secondary")
        if primary == "null":
            primary = None
        if secondary == "null":
            secondary = None
        # Validate they're in the list
        if primary and primary not in industries:
            primary = None
        if secondary and secondary not in industries:
            secondary = None
        logger.info("Topic '%s' → primary=%s, secondary=%s", topic, primary, secondary)
        return primary, secondary
    except Exception as e:
        logger.warning("LLM mapping failed: %s", e)
        return None, None


def _fetch_industry_index_trend(sector_code: str, sector_name: str) -> ChartSpec | None:
    """Fetch monthly index trend for a SW sector (past 3 years)."""
    try:
        df = ak.index_hist_sw(symbol=sector_code, period="day")
        if df is None or df.empty:
            return None

        # Parse date column
        df = df.copy()
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
        df = df.dropna(subset=["日期"]).sort_values("日期")

        # Last 3 years only
        cutoff = datetime.now() - timedelta(days=365 * 3)
        df = df[df["日期"] >= cutoff]

        if len(df) < 24:
            return None

        # Resample to monthly (take last day of month)
        df = df.set_index("日期")
        monthly = df["收盘"].resample("ME").last().dropna().tail(30)

        if len(monthly) < 6:
            return None

        x_labels = [d.strftime("%Y-%m") for d in monthly.index]
        y_values = [round(float(v), 2) for v in monthly.values]

        return ChartSpec(
            chart_type=ChartType.LINE,
            title=f"{sector_name}行业指数走势（近{len(monthly)}个月）",
            x=x_labels,
            y=y_values,
            unit="点",
            caption="数据来源：申万行业指数（AkShare）",
            source_refs=[],
        )
    except Exception as e:
        logger.error("Failed to fetch index trend for %s: %s", sector_code, e)
        return None


def _build_pe_comparison_chart(df: pd.DataFrame, primary_name: str) -> ChartSpec | None:
    """Build a chart comparing the target sector's PE vs other top industries."""
    try:
        if df is None or df.empty:
            return None

        # Keep relevant columns, drop rows with missing PE
        df = df[["行业名称", "TTM(滚动)市盈率"]].copy()
        df["TTM(滚动)市盈率"] = pd.to_numeric(df["TTM(滚动)市盈率"], errors="coerce")
        df = df.dropna(subset=["TTM(滚动)市盈率"])

        if len(df) < 5:
            return None

        # Sort by PE ascending, take top-10 including primary
        df_sorted = df.sort_values("TTM(滚动)市盈率", ascending=True)

        # Ensure primary is in the selection
        primary_row = df[df["行业名称"] == primary_name]
        top_10 = df_sorted.head(10)
        if not primary_row.empty and primary_name not in top_10["行业名称"].tolist():
            top_10 = pd.concat([top_10, primary_row]).drop_duplicates().head(10)

        top_10 = top_10.sort_values("TTM(滚动)市盈率", ascending=True)

        x_labels = top_10["行业名称"].tolist()
        y_values = [round(float(v), 2) for v in top_10["TTM(滚动)市盈率"].tolist()]

        return ChartSpec(
            chart_type=ChartType.BAR,
            title="申万一级行业 TTM 市盈率对比",
            x=x_labels,
            y=y_values,
            unit="倍",
            caption="数据来源：申万行业指数（AkShare），按 TTM 市盈率升序",
            source_refs=[],
        )
    except Exception as e:
        logger.error("PE comparison chart failed: %s", e)
        return None


def fetch_real_data_charts(topic: str) -> list[ChartSpec]:
    """Main entry — fetch up to 2 real-data charts for the given topic.

    Returns a list of ChartSpecs grounded in actual market data from AkShare.
    """
    if not topic:
        return []

    # Step 1: Get SW industry list
    df_industries = _get_sw_industries()
    if df_industries is None or df_industries.empty:
        logger.warning("Cannot fetch SW industry list, skipping real data charts")
        return []

    industry_names = df_industries["行业名称"].tolist()
    name_to_code = dict(zip(df_industries["行业名称"], df_industries["行业代码"]))

    # Step 2: LLM maps topic to sector
    primary, _secondary = _llm_map_topic_to_sector(topic, industry_names)
    if not primary:
        logger.info("LLM could not map topic '%s' to any SW sector", topic)
        return []

    specs: list[ChartSpec] = []

    # Step 3: Chart 1 — primary sector's index trend
    primary_code = name_to_code.get(primary, "")
    if primary_code:
        # Strip ".SI" suffix if present
        code_clean = primary_code.split(".")[0] if "." in primary_code else primary_code
        trend = _fetch_industry_index_trend(code_clean, primary)
        if trend:
            specs.append(trend)
            logger.info("Added real trend chart: %s (%d points)", trend.title, len(trend.x))
            time.sleep(0.5)

    # Step 4: Chart 2 — PE comparison across industries
    pe_chart = _build_pe_comparison_chart(df_industries, primary)
    if pe_chart:
        specs.append(pe_chart)
        logger.info("Added real PE chart: %s (%d points)", pe_chart.title, len(pe_chart.x))

    return specs
