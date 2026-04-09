"""Chart Renderer — premium Matplotlib rendering from ChartSpec."""

from __future__ import annotations

import logging
import platform
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from matplotlib.patches import FancyBboxPatch

from src.config.settings import CHARTS_DIR
from src.models import ChartAsset, ChartSpec, ChartType

logger = logging.getLogger(__name__)

# ── Font setup ────────────────────────────────────────────


def _setup_chinese_font() -> None:
    system = platform.system()
    candidates = []
    if system == "Darwin":
        candidates = ["PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS"]
    elif system == "Linux":
        candidates = ["WenQuanYi Micro Hei", "Noto Sans CJK SC", "SimHei"]
    else:
        candidates = ["SimHei", "Microsoft YaHei"]
    from matplotlib.font_manager import fontManager

    available = {f.name for f in fontManager.ttflist}
    for font in candidates:
        if font in available:
            plt.rcParams["font.sans-serif"] = [font, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            logger.info("Using Chinese font: %s", font)
            return
    logger.warning("No CJK font found")
    plt.rcParams["axes.unicode_minus"] = False


_setup_chinese_font()

# ── Style constants ──────────────────────────────────────

# Premium palette — muted, professional tones (inspired by McKinsey / Goldman reports)
_PALETTE = [
    "#2563EB",  # royal blue
    "#0EA5E9",  # sky
    "#6366F1",  # indigo
    "#8B5CF6",  # violet
    "#0D9488",  # teal
    "#059669",  # emerald
    "#D97706",  # amber
    "#DC2626",  # red (for contrast)
]

_PALETTE_LIGHT = [
    "#DBEAFE",  # blue-100
    "#E0F2FE",  # sky-100
    "#E0E7FF",  # indigo-100
    "#EDE9FE",  # violet-100
    "#CCFBF1",  # teal-100
    "#D1FAE5",  # emerald-100
    "#FEF3C7",  # amber-100
    "#FEE2E2",  # red-100
]

_LIGHT_BG = "#FFFFFF"
_GRID_COLOR = "#F1F5F9"
_TEXT_COLOR = "#0F172A"
_TEXT_MUTED = "#94A3B8"
_SPINE_COLOR = "#E2E8F0"

_DPI = 220
_FIG_W = 11
_FIG_H = 6.5


# ── Helpers ──────────────────────────────────────────────


def _apply_base_style(ax: plt.Axes) -> None:
    """Clean, premium axes style."""
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=_TEXT_MUTED, labelsize=9, length=0, pad=8)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.grid(axis="y", color=_GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)


def _value_labels(ax: plt.Axes, bars_or_points, values: list[float], fmt: str = "{:g}") -> None:
    """Add value labels above bars/points."""
    for obj, val in zip(bars_or_points, values):
        if hasattr(obj, "get_x"):  # bar
            x = obj.get_x() + obj.get_width() / 2
            y = obj.get_height()
        else:  # point / tuple
            x, y = obj
        label = fmt.format(val)
        ax.annotate(
            label,
            (x, y),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=8.5,
            fontweight="600",
            color=_TEXT_COLOR,
        )


# ── Renderers ────────────────────────────────────────────


def _render_bar(spec: ChartSpec, ax: plt.Axes) -> None:
    n = len(spec.x)
    x = np.arange(n)
    width = min(0.55, 0.75 - 0.025 * n)

    # Use single color for uniform look, vary shade only when many bars
    if n <= 6:
        colors = [_PALETTE[0]] * n
    else:
        colors = [_PALETTE[i % len(_PALETTE)] for i in range(n)]

    bars = ax.bar(x, spec.y, color=colors, width=width, zorder=3, alpha=0.88,
                  edgecolor="none", linewidth=0)

    # Subtle shadow bars behind
    ax.bar(x + 0.02, spec.y, color="#00000008", width=width, zorder=2)

    ax.set_xticks(x)
    ax.set_xticklabels(spec.x, rotation=30 if n > 5 else 0,
                       ha="right" if n > 5 else "center", fontsize=9)
    _value_labels(ax, bars, spec.y)

    ymax = max(spec.y) if spec.y else 1
    ax.set_ylim(0, ymax * 1.25)


def _render_line(spec: ChartSpec, ax: plt.Axes) -> None:
    n = len(spec.x)
    x = np.arange(n)
    y = np.array(spec.y)
    color = _PALETTE[0]
    color_light = _PALETTE_LIGHT[0]

    # Gradient area fill
    ax.fill_between(x, y, alpha=0.12, color=color_light, zorder=2)

    # Main line
    ax.plot(
        x, y,
        color=color,
        linewidth=2.8,
        marker="o",
        markersize=8,
        markerfacecolor="white",
        markeredgecolor=color,
        markeredgewidth=2.5,
        zorder=3,
        solid_capstyle="round",
    )

    _value_labels(ax, zip(x, y), spec.y)

    ax.set_xticks(x)
    ax.set_xticklabels(spec.x, rotation=30 if n > 5 else 0,
                       ha="right" if n > 5 else "center", fontsize=9)

    ymin, ymax = min(spec.y), max(spec.y)
    margin = (ymax - ymin) * 0.18 if ymax != ymin else ymax * 0.25
    ax.set_ylim(max(0, ymin - margin), ymax + margin)


def _render_pie(spec: ChartSpec, ax: plt.Axes) -> None:
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(spec.y))]
    total = sum(spec.y)

    wedges, texts, autotexts = ax.pie(
        spec.y,
        labels=None,
        autopct=lambda p: f"{p:.1f}%" if p >= 4 else "",
        colors=colors,
        startangle=90,
        pctdistance=0.78,
        wedgeprops=dict(width=0.38, edgecolor="white", linewidth=2.5),
    )

    for t in autotexts:
        t.set_fontsize(8)
        t.set_fontweight("600")
        t.set_color(_TEXT_COLOR)

    # Clean legend on the right
    labels = [f"{name}  {val:g}" for name, val in zip(spec.x, spec.y)]
    legend = ax.legend(
        wedges, labels, loc="center left", bbox_to_anchor=(1.02, 0.5),
        fontsize=9, frameon=False, handlelength=1.2, handleheight=1.2,
        labelspacing=1.0,
    )
    for text in legend.get_texts():
        text.set_color(_TEXT_COLOR)

    # Center label
    ax.text(0, 0, f"总计\n{total:g}", ha="center", va="center",
            fontsize=12, fontweight="700", color=_TEXT_COLOR)


def _render_stacked_bar(spec: ChartSpec, ax: plt.Axes) -> None:
    if not spec.y_series:
        _render_bar(spec, ax)
        return

    n = len(spec.x)
    x = np.arange(n)
    bottom = np.zeros(n)

    for i, (label, values) in enumerate(spec.y_series.items()):
        color = _PALETTE[i % len(_PALETTE)]
        ax.bar(
            x,
            values,
            bottom=bottom,
            label=label,
            color=color,
            width=0.6,
            edgecolor="white",
            linewidth=0.5,
            alpha=0.9,
            zorder=3,
        )
        bottom += np.array(values)

    ax.set_xticks(x)
    ax.set_xticklabels(spec.x, rotation=30 if n > 5 else 0, ha="right" if n > 5 else "center")
    ax.legend(fontsize=9, frameon=False, loc="upper left")
    ax.set_ylim(0, max(bottom) * 1.15)


def _render_table(spec: ChartSpec, ax: plt.Axes) -> None:
    """Render data as a clean table."""
    ax.axis("off")
    n = len(spec.x)
    cell_text = [[spec.x[i], f"{spec.y[i]:g}"] for i in range(n)]

    table = ax.table(
        cellText=cell_text,
        colLabels=["项目", spec.unit or "数值"],
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.6)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(_GRID_COLOR)
        if row == 0:
            cell.set_facecolor("#F3F4F6")
            cell.set_text_props(fontweight="bold", color=_TEXT_COLOR)
        else:
            cell.set_facecolor("white")
            cell.set_text_props(color=_TEXT_COLOR)


def _render_timeline(spec: ChartSpec, ax: plt.Axes) -> None:
    """Render a horizontal timeline with events."""
    n = len(spec.x)
    if n < 2:
        ax.text(0.5, 0.5, "数据不足", ha="center", va="center", transform=ax.transAxes)
        return

    y_pos = 0.5
    x_positions = np.linspace(0.1, 0.9, n)

    # Horizontal line
    ax.plot([0.05, 0.95], [y_pos, y_pos], color=_SPINE_COLOR, linewidth=2, zorder=1)

    for i, (xpos, label) in enumerate(zip(x_positions, spec.x)):
        color = _PALETTE[i % len(_PALETTE)]
        # Dot on timeline
        ax.plot(xpos, y_pos, "o", color=color, markersize=12, zorder=3, markeredgecolor="white", markeredgewidth=2)
        # Label above/below alternating
        offset = 0.15 if i % 2 == 0 else -0.15
        va = "bottom" if i % 2 == 0 else "top"
        ax.annotate(
            label,
            (xpos, y_pos),
            xytext=(0, offset * (1 if i % 2 == 0 else -1)),
            textcoords=("offset points", "data"),
            ha="center",
            va=va,
            fontsize=9,
            fontweight="600",
            color=_TEXT_COLOR,
            arrowprops=dict(arrowstyle="-", color=_SPINE_COLOR, lw=0.8),
        )

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")


def _render_wordcloud(spec: ChartSpec, ax: plt.Axes) -> None:
    """Render keywords as sized text (word cloud style, no external lib)."""
    if not spec.x:
        return

    weights = spec.y if spec.y else [1.0] * len(spec.x)
    max_w = max(weights) if weights else 1

    # Layout: place words in a roughly centered grid
    n = len(spec.x)
    cols = min(4, n)
    rows = (n + cols - 1) // cols

    for i, (word, w) in enumerate(zip(spec.x, weights)):
        row, col = divmod(i, cols)
        x = 0.15 + col * (0.7 / max(cols - 1, 1))
        y = 0.85 - row * (0.7 / max(rows - 1, 1))
        size = 10 + (w / max_w) * 22
        color = _PALETTE[i % len(_PALETTE)]
        alpha = 0.6 + (w / max_w) * 0.4
        ax.text(
            x,
            y,
            word,
            fontsize=size,
            fontweight="bold",
            color=color,
            ha="center",
            va="center",
            alpha=alpha,
            transform=ax.transAxes,
        )

    ax.axis("off")


def _render_kpi(spec: ChartSpec, ax: plt.Axes) -> None:
    """Render key metrics as large number cards."""
    ax.axis("off")
    n = len(spec.x)
    if n == 0:
        return

    cols = min(n, 3)
    rows = (n + cols - 1) // cols

    for i, (label, value) in enumerate(zip(spec.x, spec.y)):
        row, col = divmod(i, cols)
        cx = (col + 0.5) / cols
        cy = 0.65 - row * 0.45

        # Big number
        ax.text(
            cx,
            cy + 0.08,
            f"{value:g}",
            fontsize=28,
            fontweight="bold",
            color=_PALETTE[i % len(_PALETTE)],
            ha="center",
            va="center",
            transform=ax.transAxes,
        )

        # Label below
        ax.text(
            cx,
            cy - 0.08,
            label,
            fontsize=9,
            color=_TEXT_MUTED,
            ha="center",
            va="center",
            transform=ax.transAxes,
            wrap=True,
        )


def _render_chain(spec: ChartSpec, ax: plt.Axes) -> None:
    """Render an industry chain flow diagram."""
    ax.axis("off")
    n = len(spec.x)
    if n == 0:
        return

    x_positions = np.linspace(0.08, 0.92, n)
    box_w = min(0.22, 0.8 / n)

    for i, (xpos, label) in enumerate(zip(x_positions, spec.x)):
        color = _PALETTE[i % len(_PALETTE)]
        # Rounded rectangle
        box = FancyBboxPatch(
            (xpos - box_w / 2, 0.35),
            box_w,
            0.3,
            boxstyle="round,pad=0.02",
            facecolor=color,
            alpha=0.15,
            edgecolor=color,
            linewidth=2,
        )
        ax.add_patch(box)
        ax.text(xpos, 0.5, label, ha="center", va="center", fontsize=11, fontweight="bold", color=color)

        # Arrow to next
        if i < n - 1:
            ax.annotate(
                "",
                xy=(x_positions[i + 1] - box_w / 2 - 0.01, 0.5),
                xytext=(xpos + box_w / 2 + 0.01, 0.5),
                arrowprops=dict(arrowstyle="->", color=_SPINE_COLOR, lw=2, connectionstyle="arc3,rad=0"),
            )

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)


def _render_matrix(spec: ChartSpec, ax: plt.Axes) -> None:
    """Render a comparison matrix with colored cells."""
    ax.axis("off")

    entities = spec.x
    dims = ["优势", "劣势", "现状", "趋势"][: max(2, len(spec.y))]
    rows_n, cols_n = len(dims), len(entities)

    # Generate qualitative cell content from spec caption/context
    cell_colors = []
    for r in range(rows_n):
        row_colors = []
        for c in range(cols_n):
            # Alternate colors for visual distinction
            idx = (r * cols_n + c) % len(_PALETTE)
            row_colors.append(_PALETTE[idx] + "18")  # very light
        cell_colors.append(row_colors)

    table = ax.table(
        cellText=[["—"] * cols_n for _ in range(rows_n)],
        rowLabels=dims,
        colLabels=entities,
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2.0)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(_GRID_COLOR)
        if row == 0:
            cell.set_facecolor("#F3F4F6")
            cell.set_text_props(fontweight="bold", color=_TEXT_COLOR)
        elif col == -1:
            cell.set_facecolor("#F9FAFB")
            cell.set_text_props(fontweight="600", color=_TEXT_COLOR)
        else:
            cell.set_facecolor("white")


_RENDERERS = {
    ChartType.BAR: _render_bar,
    ChartType.LINE: _render_line,
    ChartType.PIE: _render_pie,
    ChartType.STACKED_BAR: _render_stacked_bar,
    ChartType.TABLE: _render_table,
    ChartType.TIMELINE: _render_timeline,
    ChartType.WORDCLOUD: _render_wordcloud,
    ChartType.KPI: _render_kpi,
    ChartType.CHAIN: _render_chain,
    ChartType.MATRIX: _render_matrix,
}


# ── Public API ───────────────────────────────────────────


def render_chart(spec: ChartSpec, output_dir: str | Path | None = None) -> ChartAsset:
    output_dir = Path(output_dir or CHARTS_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"{spec.chart_id}.png"

    if spec.chart_type in (ChartType.BAR, ChartType.LINE, ChartType.PIE, ChartType.STACKED_BAR):
        if len(spec.x) < 2:
            return ChartAsset(
                chart_id=spec.chart_id, file_path="", spec=spec, status="error: insufficient data (< 2 points)"
            )

    # Non-data chart types need at least 1 label
    if spec.chart_type in (ChartType.TIMELINE, ChartType.WORDCLOUD, ChartType.KPI, ChartType.CHAIN):
        if len(spec.x) < 1:
            return ChartAsset(chart_id=spec.chart_id, file_path="", spec=spec, status="error: no data")

    try:
        # Adjust figure size for different chart types
        if spec.chart_type == ChartType.PIE:
            w, h = _FIG_W + 1.5, _FIG_H
        elif spec.chart_type == ChartType.TIMELINE:
            w, h = _FIG_W, 3.5
        elif spec.chart_type == ChartType.WORDCLOUD:
            w, h = _FIG_W, 5
        elif spec.chart_type == ChartType.KPI:
            n_kpi = max(len(spec.x), 1)
            w, h = min(n_kpi * 3.5, _FIG_W + 2), 3
        elif spec.chart_type == ChartType.CHAIN:
            w, h = _FIG_W, 3.5
        elif spec.chart_type == ChartType.MATRIX:
            w, h = _FIG_W, 4
        else:
            w, h = _FIG_W, _FIG_H

        fig, ax = plt.subplots(figsize=(w, h), dpi=_DPI)
        fig.patch.set_facecolor(_LIGHT_BG)
        ax.set_facecolor(_LIGHT_BG)

        renderer = _RENDERERS.get(spec.chart_type, _render_bar)
        renderer(spec, ax)
        _apply_base_style(ax)

        # Title — bold, left-aligned
        ax.set_title(spec.title, fontsize=14, fontweight="700", color=_TEXT_COLOR, pad=20, loc="left")

        # Unit label (top-left, subtle)
        data_chart_types = (ChartType.BAR, ChartType.LINE, ChartType.STACKED_BAR)
        if spec.unit and spec.chart_type in data_chart_types:
            ax.set_ylabel(spec.unit, fontsize=9, color=_TEXT_MUTED, labelpad=10)

        # Footer — caption + source
        footer_parts = []
        if spec.caption:
            footer_parts.append(spec.caption)
        if spec.source_refs:
            footer_parts.append(f"数据来源: {', '.join(spec.source_refs)}")
        if footer_parts:
            fig.text(0.03, 0.01, "  |  ".join(footer_parts), ha="left",
                     fontsize=7.5, color=_TEXT_MUTED, style="italic")

        fig.tight_layout(rect=[0, 0.035, 1, 0.97])
        fig.savefig(file_path, dpi=_DPI, bbox_inches="tight",
                    facecolor=fig.get_facecolor(), pad_inches=0.3)
        plt.close(fig)

        logger.info("Rendered: %s → %s", spec.title, file_path.name)
        return ChartAsset(chart_id=spec.chart_id, file_path=str(file_path), spec=spec, status="ok")

    except Exception as e:
        logger.error("Chart render failed for '%s': %s", spec.title, e)
        plt.close("all")
        return ChartAsset(chart_id=spec.chart_id, file_path="", spec=spec, status=f"error: {e}")


def render_charts(specs: list[ChartSpec], output_dir: str | Path | None = None) -> list[ChartAsset]:
    return [render_chart(s, output_dir) for s in specs]
