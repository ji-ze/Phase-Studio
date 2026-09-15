"""Workflow-metrics Qt/Matplotlib presentation.

Scientific metric definitions and values remain authoritative in map_quality;
this module only lays out and renders the completed values supplied by the GUI.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np
from matplotlib.ticker import MaxNLocator

from phase_studio.map_quality import profile_definition

def robust_detail_range(values: Sequence[Optional[float]], min_points: int = 4) -> Optional[Tuple[float, float]]:
    """Display-only robust y-range covering the main body of ``values`` (a
    padded IQR fence around the median), for a "Detail" viewport that stays
    readable when one extreme outlier would otherwise dominate the full
    autoscaled range. Never modifies, discards or recalculates any stored
    metric value -- points outside the returned range are simply outside the
    current viewport, exactly like an ordinary zoom. Returns None when there
    are too few finite points for a robust range to mean anything."""
    finite = np.asarray(
        [float(v) for v in values if v is not None and np.isfinite(float(v))], dtype=float
    )
    if finite.size < min_points:
        return None
    q1, q3 = np.percentile(finite, [25, 75])
    iqr = q3 - q1
    pad = iqr * 1.5 if iqr > 1e-9 else max(abs(float(np.median(finite))), 1.0) * 0.1
    lo, hi = q1 - pad, q3 + pad
    if hi - lo < 1e-9:
        hi = lo + max(abs(lo), 1.0) * 0.05
    return (float(lo), float(hi))


def metrics_legend_width_pixels(self, figure) -> float:
    """Width in device pixels the figure's legend needs to render whole.

    Measured from the legend itself (handles, handle/text padding and the
    label text), which is what Matplotlib will actually draw, rather than
    guessed from a character count. Falls back to an estimate only if no
    renderer is available yet; either way the caller clamps the result.
    """
    if not figure.legends:
        return 0.0
    legend = figure.legends[0]
    try:
        renderer = figure.canvas.get_renderer()
    except Exception:
        renderer = None
    if renderer is not None:
        try:
            measured = float(legend.get_window_extent(renderer).width)
            if math.isfinite(measured) and measured > 0.0:
                return measured + self.METRICS_LEGEND_TEXT_PADDING_PX
        except Exception:
            pass
    # No renderer yet (first layout before any draw): approximate from the
    # longest label at the legend's own font size, plus its handle column.
    try:
        labels = [text.get_text() for text in legend.get_texts()]
        font_pixels = float(legend.prop.get_size_in_points()) * figure.dpi / 72.0
        longest = max((len(label) for label in labels), default=0)
        handle_pixels = 1.8 * font_pixels
        return longest * 0.55 * font_pixels + handle_pixels + self.METRICS_LEGEND_TEXT_PADDING_PX
    except Exception:
        return self.METRICS_LEGEND_MIN_WIDTH_PX


def layout_metrics_figure(self, key: str) -> None:
    figure = self.metrics_figures[key]
    canvas = self.metrics_canvases[key]
    width = max(1.0, float(canvas.width()))
    height = max(1.0, float(canvas.height()))
    has_data = bool(self.results)
    # A single-series tab (e.g. Powder repartitioning) omits its legend
    # entirely -- the y-axis label already names the one plotted metric
    # -- so it should reclaim the margin a legend would otherwise cost,
    # rather than leaving a wide empty band on the right.
    has_legend = has_data and bool(figure.legends)
    legend_gap_pixels = 8.0
    left_pixels = 86.0 if has_data else 70.0
    left = min(0.18, max(0.07, left_pixels / width))
    bottom = min(0.22, max(0.12, 34.0 / height))
    if has_data:
        top = 1.0 - min(0.08, max(0.035, 10.0 / height))
        if has_legend:
            # Reserve a compact, content-aware band for the vertical
            # legend. Keeping this budget pixel based avoids wasting plot
            # width on large canvases; measuring it means the longest
            # label is no longer clipped, and the clamp keeps a
            # pathological label from eating the plot. The 0.32 fraction
            # below is a second, canvas-relative safety net on narrow
            # canvases.
            legend_width_pixels = min(
                self.METRICS_LEGEND_MAX_WIDTH_PX,
                max(
                    self.METRICS_LEGEND_MIN_WIDTH_PX,
                    self._metrics_legend_width_pixels(figure),
                ),
            )
            outer_right_pixels = 8.0
            right = 1.0 - min(
                0.32,
                (legend_width_pixels + legend_gap_pixels + outer_right_pixels) / width,
            )
        else:
            right = 1.0 - min(0.04, max(0.02, 18.0 / width))
    else:
        right = 1.0 - min(0.04, max(0.02, 18.0 / width))
        top = 1.0 - min(0.16, max(0.07, 22.0 / height))
    figure.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
    if has_legend:
        legend_left = right + (legend_gap_pixels / width)
        legend_center_y = (bottom + top) / 2.0
        figure.legends[0].set_bbox_to_anchor(
            (legend_left, legend_center_y),
            transform=figure.transFigure,
        )


def render_metrics_tab(
    self,
    key: str,
    series: List[Tuple[str, List[Optional[float]], bool, str, str, str]],
    *,
    raw: bool = False,
    raw_ylabel: str = "",
) -> None:
    """Render one convergence tab. By default, each series is rescaled to a
    shared 0-1 "Best/Worst" score so metrics with unrelated units (RMSD,
    recall, reference match, ...) can be compared on one axis. Pass raw=True
    for a tab with a single metric already in one meaningful unit (for
    example a percentage), where that rescaling would hide whether the
    actual value is trending down/up and should instead be plotted as-is.

    Visualization only: the values plotted/shown here (and in hover
    tooltips) are exactly the stored CycleResult metrics or, for
    non-raw tabs, a display-only 0-1 rescaling of them for a shared axis
    -- nothing here recomputes or alters a scientific value."""
    self._metrics_last_render_args[key] = {"series": series, "raw": raw, "raw_ylabel": raw_ylabel}
    interaction = self.metrics_interactions.get(key)
    if interaction is not None:
        interaction.notify_redraw_start()
    figure = self.metrics_figures[key]
    canvas = self.metrics_canvases[key]
    figure.clear()
    ax = figure.add_subplot(111)
    self.metrics_axes[key] = ax
    figure.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    cycles = [r.cycle for r in self.results]
    if not cycles:
        self._metrics_hover_series[key] = []
        status = str(getattr(self, "_run_status", "READY")).upper()
        if status in {"RUNNING", "STOPPING"}:
            empty_message = "Workflow is running · waiting for workflow metrics…"
        elif status in {"ERROR", "CANCELLED", "STOPPED"}:
            empty_message = "No workflow metrics available."
        else:
            empty_message = "Run phasing to display workflow metrics."
        ax.set_axis_off()
        ax.text(
            0.5,
            0.50,
            empty_message,
            ha="center",
            va="center",
            color="#7183a6",
            fontsize=8.5,
            transform=ax.transAxes,
        )
        self._layout_metrics_figure(key)
        canvas.draw_idle()
        return

    ax.set_title("")
    ax.set_xlabel("")
    figure.text(0.5, 0.018, "Cycle", ha="center", va="bottom", color="#14204a", fontsize=8.5)
    detail_ylim: Optional[Tuple[float, float]] = None
    if raw:
        all_finite = [
            float(v)
            for _label, values, *_rest in series
            for v in values
            if v is not None and np.isfinite(float(v))
        ]
        if all_finite:
            lo = min(0.0, min(all_finite))
            hi = max(all_finite)
            pad = max(1e-9, (hi - lo) * 0.08)
            full_ylim = (lo - pad, hi + pad)
            candidate_detail = robust_detail_range(all_finite)
            if candidate_detail is not None:
                full_span = full_ylim[1] - full_ylim[0]
                detail_span = candidate_detail[1] - candidate_detail[0]
                # Only offer Detail when it would actually narrow the
                # view meaningfully -- otherwise it's the same as Full
                # range and just adds a confusing extra control.
                if full_span > 0 and detail_span < full_span * 0.92:
                    detail_ylim = candidate_detail
        else:
            full_ylim = (0.0, 1.0)
        ax.set_ylabel(raw_ylabel, fontsize=7.5, color="#001170")
    else:
        full_ylim = (-0.04, 1.04)
        # Intermediate ticks stay at their numeric positions (0.25/0.5/0.75)
        # so the horizontal gridlines remain useful, but only the two
        # semantic endpoints get a label -- "Worst 0.00"/"Best 1.00" read
        # as redundant once the axis is understood as a quality scale.
        ax.set_yticks([0.0, 0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels(["Worst", "", "", "", "Best"])
        ax.set_ylabel("Normalized score", fontsize=7.5, color="#001170")
    try:
        cycles_to_run = max(1, self._spin_value("cycles"))
    except Exception:
        cycles_to_run = max(cycles) if cycles else 1
    max_completed = max(cycles) if cycles else 0
    run_status = str(getattr(self, "_run_status", "READY")).upper()
    if run_status in {"RUNNING", "STOPPING"}:
        # Live run: fit the currently populated cycles plus a little
        # right-side headroom for the next point, rather than jumping
        # straight to the full planned cycle count -- 12 of 50 planned
        # cycles otherwise compresses all the active data into the left
        # ~24% of the plot. Headroom grows with progress so the viewport
        # doesn't visibly jump every single cycle, and is capped at the
        # planned total.
        headroom = max(2, round(max_completed * 0.1))
        x_max = min(cycles_to_run, max(max_completed + headroom, 1))
    else:
        # Not currently running (finished, stopped early, or not yet
        # started): fit the data that actually exists instead of
        # stretching out to a planned count that will never be reached
        # for a run stopped before completion.
        x_max = max_completed if cycles else cycles_to_run
    full_xlim = (0.75, float(x_max) + 0.25)
    if interaction is not None and interaction.user_modified:
        # A manual zoom/pan may no longer align with one-tick-per-cycle;
        # let Matplotlib choose sensible ticks for whatever is visible.
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=10, min_n_ticks=2))
    elif x_max <= 30:
        ax.set_xticks(list(range(1, x_max + 1)))
    else:
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=12, min_n_ticks=2))
    ax.grid(True, axis="y", color="#cbd7ea", linewidth=0.6, alpha=0.64)
    ax.grid(True, axis="x", color="#cbd7ea", linewidth=0.5, alpha=0.42)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#001170")
    ax.spines["bottom"].set_color("#001170")
    ax.tick_params(colors="#001170")
    ax.title.set_color("#001170")
    ax.xaxis.label.set_color("#001170")
    ax.yaxis.label.set_color("#001170")

    def best_score(values: Sequence[Optional[float]], higher_is_better: bool) -> List[float]:
        arr = np.asarray([np.nan if v is None else float(v) for v in values], dtype=float)
        finite = np.isfinite(arr)
        out = np.full_like(arr, np.nan, dtype=float)
        if not np.any(finite):
            return out.tolist()
        lo = float(np.nanmin(arr[finite]))
        hi = float(np.nanmax(arr[finite]))
        if abs(hi - lo) < 1e-12:
            out[finite] = 1.0
        else:
            scaled = (arr[finite] - lo) / (hi - lo)
            out[finite] = scaled if higher_is_better else 1.0 - scaled
        return out.tolist()

    plotted = 0
    hover_series: List[Tuple[str, List[int], List[Optional[float]], List[Optional[float]], str]] = []
    for label, values, higher_is_better, color, marker, linestyle in series:
        if raw:
            y = [np.nan if v is None else float(v) for v in values]
        else:
            y = best_score(values, higher_is_better)
        finite_mask = np.isfinite(np.asarray(y, dtype=float))
        if not np.any(finite_mask):
            continue
        plotted += 1
        ax.plot(
            cycles,
            y,
            color=color,
            marker=marker,
            linestyle=linestyle,
            linewidth=2.1,
            markersize=5.5,
            markeredgecolor="#ffffff",
            markeredgewidth=0.8,
            label=label,
        )
        # No persistent "latest cycle" ring: the line ending already shows
        # the newest point, and a permanent hollow-circle overlay reads as
        # a leftover hover state even when the pointer isn't over it. Only
        # an actual hover (MetricsPlotInteraction) emphasizes a marker now.
        unit = "%" if ("%" in label or ("%" in raw_ylabel and raw)) else ""
        hover_series.append((label, list(cycles), list(y), list(values), unit))
    self._metrics_hover_series[key] = hover_series
    # Whether this tab shows a legend is decided by the tab's DEFINITION
    # (how many labelled series it can ever plot), never by how many of
    # them happen to carry finite values right now. Keying it off the
    # live count made the legend flicker in and out between cycles: on
    # cycle 1 several multi-metric tabs have exactly one finite series
    # (Map correlation needs a previous cycle, reference-dependent
    # metrics need a reference, ...), so `plotted > 1` was False and the
    # legend silently vanished until a later cycle happened to populate
    # a second series.
    #
    # A genuinely single-series tab (Powder repartitioning, Intensity
    # correction) still omits its legend: its y-axis label already names
    # the one plotted metric, so a one-item legend would just repeat it
    # while costing horizontal space.
    #
    # Built here, AFTER every artist for this pass has been added, and
    # after figure.clear() above discarded the previous pass's legend --
    # so the legend always matches the artists actually on screen, with
    # one entry per plotted series and no stale or placeholder entries.
    if plotted >= 1 and len(series) > 1:
        handles, labels = ax.get_legend_handles_labels()
        figure.legend(
            handles,
            labels,
            loc="center left",
            bbox_to_anchor=(0.82, 0.5),
            ncol=1,
            frameon=False,
            fontsize=7.2,
            handlelength=1.4,
            labelspacing=0.28,
            handletextpad=0.4,
            borderaxespad=0.0,
        )
    elif not plotted:
        ax.text(
            0.5,
            0.5,
            "No finite metrics yet",
            ha="center",
            va="center",
            color="#7183a6",
            transform=ax.transAxes,
        )

    view_mode = "full"
    if interaction is not None:
        view_mode = interaction.apply_limits(ax, full_xlim, full_ylim, detail_ylim)
    else:
        ax.set_xlim(*full_xlim)
        ax.set_ylim(*full_ylim)

    if view_mode == "detail":
        ylo, yhi = ax.get_ylim()
        clipped = sum(
            1
            for _label, values, *_rest in series
            for v in values
            if v is not None and np.isfinite(float(v)) and not (ylo <= float(v) <= yhi)
        )
        if clipped:
            noun = "point" if clipped == 1 else "points"
            ax.text(
                0.02,
                0.965,
                f"{clipped} {noun} outside detail range · Full range to view",
                ha="left",
                va="top",
                color="#52658b",
                fontsize=7.0,
                style="italic",
                transform=ax.transAxes,
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#ffffff", edgecolor="none", alpha=0.82),
            )

    self._layout_metrics_figure(key)
    canvas.draw_idle()


def update_metrics_plot(self) -> None:
    definition = profile_definition(self._active_validation_profile())
    if hasattr(self, "assessment_label"):
        self.assessment_label.setText(f"Assessment: {definition.assessment_label}")
        self.assessment_label.setToolTip(definition.description)
    for index, metric in enumerate(definition.primary_metrics):
        key = f"quality_{index}"
        self.metrics_tabs.setTabText(index, metric.label)
        direction = "Higher is better." if metric.higher_is_better else "Lower is better."
        self.metrics_tabs.setTabToolTip(index, f"{metric.label}. {direction}")
        superflip_values = [
            None if result.superflip_quality is None else result.superflip_quality.value(metric.key)
            for result in self.results
        ]
        sharped_values = [
            None if result.deblur_quality is None else result.deblur_quality.value(metric.key)
            for result in self.results
        ]
        series = [
            ("Superflip", superflip_values, metric.higher_is_better, "#001170", "o", "-"),
            ("SharpED", sharped_values, metric.higher_is_better, "#44b7ff", "^", "--"),
        ]
        self._render_metrics_tab(key, series, raw=True, raw_ylabel=metric.label)
