"""Automated financial/industry data calculations.

Provides pure functions for common industry analysis metrics
that can be injected into section writing context.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def cagr(start_value: float, end_value: float, years: int) -> float | None:
    """Compound Annual Growth Rate."""
    if start_value <= 0 or end_value <= 0 or years <= 0:
        return None
    return (end_value / start_value) ** (1 / years) - 1


def yoy_growth(current: float, previous: float) -> float | None:
    """Year-over-year growth rate."""
    if previous == 0:
        return None
    return (current - previous) / previous


def market_share(part: float, total: float) -> float | None:
    """Market share as a ratio (0-1)."""
    if total <= 0:
        return None
    return part / total


def format_pct(value: float | None, decimals: int = 1) -> str:
    """Format a ratio as percentage string."""
    if value is None:
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def extract_and_compute(text: str) -> list[str]:
    """Scan text for common numerical patterns and compute derived metrics.

    Returns a list of human-readable computation results that can be
    appended to section evidence context.
    """
    results: list[str] = []

    # Pattern: "从X增长到Y，历时N年" → CAGR
    growth_pat = re.compile(
        r"从\s*([\d,.]+)\s*(万?亿?[元台部]?)\s*"
        r"(?:增长|增加|上升)(?:到|至)\s*([\d,.]+)\s*(万?亿?[元台部]?)\s*"
        r".*?(\d+)\s*年"
    )
    for m in growth_pat.finditer(text):
        try:
            start = float(m.group(1).replace(",", ""))
            end = float(m.group(3).replace(",", ""))
            years = int(m.group(5))
            unit = m.group(2) or m.group(4)
            rate = cagr(start, end, years)
            if rate is not None:
                results.append(
                    f"[自动计算] {start}{unit} → {end}{unit}，{years}年CAGR为{format_pct(rate)}"
                )
        except (ValueError, ZeroDivisionError):
            pass

    # Pattern: "2023年X，2024年Y" → YoY
    yoy_pat = re.compile(
        r"(\d{4})\s*年[^，。]*?([\d,.]+)\s*(万?亿?[元台部%]?)"
        r"[，,]\s*(\d{4})\s*年[^，。]*?([\d,.]+)\s*(万?亿?[元台部%]?)"
    )
    for m in yoy_pat.finditer(text):
        try:
            y1, v1 = int(m.group(1)), float(m.group(2).replace(",", ""))
            y2, v2 = int(m.group(4)), float(m.group(5).replace(",", ""))
            unit = m.group(3) or m.group(6)
            if y2 == y1 + 1 and v1 > 0:
                rate = yoy_growth(v2, v1)
                if rate is not None:
                    results.append(
                        f"[自动计算] {y1}年{v1}{unit} → {y2}年{v2}{unit}，同比增长{format_pct(rate)}"
                    )
        except (ValueError, ZeroDivisionError):
            pass

    # Pattern: "X占Y的Z%" or "X市场份额为Z%"
    share_pat = re.compile(r"([\d,.]+)\s*(万?亿?[元台部]?)\s*.*?占.*?([\d,.]+)\s*(万?亿?[元台部]?)")
    for m in share_pat.finditer(text):
        try:
            part = float(m.group(1).replace(",", ""))
            total = float(m.group(3).replace(",", ""))
            unit = m.group(2)
            share = market_share(part, total)
            if share is not None and 0 < share < 1:
                results.append(
                    f"[自动计算] {part}{unit} / {total}{unit} = 市场份额{format_pct(share)}"
                )
        except (ValueError, ZeroDivisionError):
            pass

    if results:
        logger.info("Auto-computed %d metrics from text", len(results))
    return results
