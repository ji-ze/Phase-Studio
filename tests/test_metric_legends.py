"""Regression tests for Workflow-metrics legend determinism.

Plain Python test (no pytest dependency; run with
`python tests/test_metric_legends.py`), following this project's usual
checks-list-plus-exit-code convention.

Motivated by a real Jana2020 Phase Recycling run in which the Superflip,
SharpED, Superflip-validation and SharpED-validation tabs plotted series but
showed no legend, and a legend then appeared by itself a cycle or two later.

Root cause: the legend was created only when MORE THAN ONE series happened to
carry finite values in that render pass (`plotted > 1`). On early cycles that
is routinely false on a multi-metric tab -- Map correlation needs a previous
cycle, the reference-dependent metrics need a reference -- so the legend
disappeared until some later cycle populated a second series.

The rule is now driven by the tab's DEFINITION (how many labelled series it
can ever plot), not by transient data availability, so it is stable across
cycles, tab switches and re-renders. A genuinely single-series tab (Powder
repartitioning, Intensity correction) still omits its legend, because its
y-axis label already names the one plotted metric.

These tests walk the real lifecycle: no data -> cycle 1 -> cycle 2 -> tab
switch -> forced re-render -> completion, checking the legend after each step.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []

# Tabs that define more than one labelled series: these must always show a
# legend as soon as at least one of them plots.
MULTI_SERIES_TABS = {
    "superflip": "Superflip",
    "deblur": "SharpED",
    "superflip_omit": "Superflip validation",
    "deblur_omit": "SharpED validation",
}
# Tabs that define exactly one series: the y-axis label already names it.
SINGLE_SERIES_TABS = {
    "powder_repartition": "Powder repartitioning",
    "intensity_correction": "Intensity correction",
}


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def legend_labels(win, key):
    """Labels currently shown in a metric tab's legend (empty when none)."""
    figure = win.metrics_figures[key]
    if not figure.legends:
        return []
    return [text.get_text() for text in figure.legends[0].get_texts()]


def plotted_labels(win, key):
    """Labels of the artists actually drawn in this tab."""
    ax = win.metrics_axes.get(key)
    if ax is None:
        return []
    _handles, labels = ax.get_legend_handles_labels()
    return list(labels)


def make_result(appmod, tmp, cycle, *, sparse):
    """One CycleResult. `sparse` mimics the real first cycle, where the
    cross-cycle and reference-dependent metrics are not available yet."""

    def f(path):
        p = tmp / path
        p.write_text("dummy", encoding="utf-8")
        return p

    common = dict(
        cycle=cycle,
        model_source="superflip",
        model_in=None,
        model_metric=None,
        superflip_map=f("sf%d.xplor" % cycle),
        superflip_edma_cif=f("sf%d.cif" % cycle),
        deblur_map=f("db%d.xplor" % cycle),
        deblur_edma_cif=f("db%d.cif" % cycle),
    )
    if sparse:
        # Exactly one finite series per multi-metric tab -- the shape that
        # used to suppress the legend entirely.
        return appmod.CycleResult(
            superflip_metric=None,
            deblur_metric=None,
            superflip_ref_match=None,
            superflip_recall=None,
            superflip_precision=None,
            superflip_heavy_atom_count=9,
            deblur_recall=None,
            deblur_precision=None,
            deblur_heavy_atom_count=11,
            recycle_map_correlation=None,
            omit_superflip_correlation=0.61,
            omit_superflip_rfree=None,
            omit_deblur_correlation=0.71,
            omit_deblur_rfree=None,
            powder_repartition_avg_change_percent=4.0,
            intensity_correction_avg_change_percent=3.0,
            **common
        )
    return appmod.CycleResult(
        superflip_metric=0.50 - cycle * 0.01,
        deblur_metric=0.40 - cycle * 0.01,
        superflip_ref_match=0.80 + cycle * 0.01,
        superflip_recall=0.40,
        superflip_precision=0.50,
        superflip_heavy_atom_count=9,
        deblur_recall=0.50,
        deblur_precision=0.60,
        deblur_heavy_atom_count=11,
        recycle_map_correlation=0.80 + cycle * 0.005,
        omit_superflip_correlation=0.60,
        omit_superflip_rfree=0.35,
        omit_deblur_correlation=0.70,
        omit_deblur_rfree=0.30,
        powder_repartition_avg_change_percent=4.0 - cycle * 0.1,
        intensity_correction_avg_change_percent=3.0 - cycle * 0.1,
        **common
    )


def assert_tab_state(win, stage):
    """Every multi-series tab that plotted anything must show a matching
    legend; every single-series tab must not."""
    for key, title in MULTI_SERIES_TABS.items():
        drawn = plotted_labels(win, key)
        shown = legend_labels(win, key)
        if not drawn:
            check(
                "%s: %s plots nothing, so no legend is required" % (stage, title),
                shown == [],
            )
            continue
        check(
            "%s: %s shows a legend (%d series plotted)" % (stage, title, len(drawn)),
            bool(shown),
        )
        check(
            "%s: %s legend matches the plotted series exactly" % (stage, title),
            shown == drawn,
        )
        check(
            "%s: %s legend has no duplicate entries" % (stage, title),
            len(shown) == len(set(shown)),
        )
        check(
            "%s: %s legend has no empty placeholder entries" % (stage, title),
            all(str(label).strip() for label in shown),
        )
    for key, title in SINGLE_SERIES_TABS.items():
        check(
            "%s: %s (single metric) correctly omits its legend" % (stage, title),
            legend_labels(win, key) == [],
        )


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)
    import phase_studio.app as appmod

    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    win = appmod.IterativeSuperflipPipelineQtGUI()
    tmp = Path(tempfile.mkdtemp())

    # ---- no data -----------------------------------------------------
    win.results = []
    win._update_plot()
    no_data_legends = [k for k in MULTI_SERIES_TABS if legend_labels(win, k)]
    check("no data: no tab shows a legend", no_data_legends == [])

    # ---- first cycle: the shape that used to lose the legend ---------
    win.results = [make_result(appmod, tmp, 1, sparse=True)]
    win._update_plot()
    for key, title in MULTI_SERIES_TABS.items():
        check(
            "first cycle: %s plots exactly one series (the regression shape)" % title,
            len(plotted_labels(win, key)) == 1,
        )
    assert_tab_state(win, "first cycle")

    # ---- second cycle: more series become finite ---------------------
    win.results.append(make_result(appmod, tmp, 2, sparse=False))
    win._update_plot()
    for key, title in MULTI_SERIES_TABS.items():
        check(
            "second cycle: %s now plots several series" % title,
            len(plotted_labels(win, key)) > 1,
        )
    assert_tab_state(win, "second cycle")

    # ---- axes reset / re-render (what a tab switch triggers) ---------
    first_cycle_legends = {k: legend_labels(win, k) for k in MULTI_SERIES_TABS}
    for key in list(MULTI_SERIES_TABS) + list(SINGLE_SERIES_TABS):
        win._replay_metrics_tab(key)
    assert_tab_state(win, "after re-render")
    check(
        "re-render is stable: legend labels are unchanged",
        all(legend_labels(win, k) == first_cycle_legends[k] for k in MULTI_SERIES_TABS),
    )

    # ---- explicit tab switch through the real signal path ------------
    for index, key in enumerate(win._metrics_tab_keys):
        win.metrics_tabs.setCurrentIndex(index)
        win._on_metrics_tab_changed(index)
    assert_tab_state(win, "after tab switch")

    # ---- view reset (axes.clear() + full rebuild) --------------------
    for key in MULTI_SERIES_TABS:
        win._reset_metrics_view(key)
    assert_tab_state(win, "after view reset")

    # ---- completion: further cycles, run finished --------------------
    for cycle in (3, 4, 5):
        win.results.append(make_result(appmod, tmp, cycle, sparse=False))
        win._update_plot()
        assert_tab_state(win, "cycle %d" % cycle)
    win._set_run_status("Complete")
    win._update_plot()
    assert_tab_state(win, "completion")

    # ---- the legend must survive figure.clear() in every pass --------
    check(
        "legend is rebuilt after every figure.clear() (still present at completion)",
        all(bool(legend_labels(win, k)) for k in MULTI_SERIES_TABS),
    )

    # ---- colors / markers / line styles are untouched ----------------
    ax = win.metrics_axes["superflip"]
    styles = [(line.get_color(), line.get_marker(), line.get_linestyle()) for line in ax.get_lines()]
    check(
        "plot styling preserved: every series keeps a distinct colour/marker/style",
        len(set(styles)) == len(styles) and len(styles) > 1,
    )

    # =====================================================================
    # The reserved legend band must actually fit the labels it shows.
    #
    # It used to be a flat 112 px, narrower than the legend the validation
    # tabs draw ("Omit map correlation" needs ~133 px), so the longest labels
    # were clipped at the canvas edge.
    # =====================================================================
    win.resize(1500, 950)
    win.show()
    app.processEvents()
    win.results = [make_result(appmod, tmp, cycle, sparse=False) for cycle in (1, 2, 3)]
    win._update_plot()
    app.processEvents()

    def laid_out(key):
        """Lay out and draw one tab, returning (figure, legend, renderer).

        The tab is selected first: _layout_metrics_figure budgets in canvas
        widget pixels while positioning the legend in figure-fraction
        coordinates, so the two only describe the same geometry once Qt has
        actually sized the canvas and matplotlib has resized the figure to
        match. Measuring an unsized canvas would compare the legend against a
        figure that is not the one on screen.
        """
        win.metrics_tabs.setCurrentIndex(win._metrics_tab_keys.index(key))
        app.processEvents()
        figure = win.metrics_figures[key]
        canvas = win.metrics_canvases[key]
        win._layout_metrics_figure(key)
        canvas.draw()
        legend = figure.legends[0] if figure.legends else None
        return figure, legend, figure.canvas.get_renderer()

    seen_labels = set()
    for key, title in MULTI_SERIES_TABS.items():
        figure, legend, renderer = laid_out(key)
        check("%s: has a legend to measure" % title, legend is not None)
        if legend is None:
            continue
        figure_right = figure.get_window_extent().x1
        # Guard the measurement itself: if the canvas widget and the figure
        # disagree on width, the numbers below describe a layout that is not
        # what the user sees, and the clipping check would be meaningless.
        check(
            "%s: the measured canvas matches the on-screen figure width" % title,
            abs(win.metrics_canvases[key].width() - figure_right) <= 1.0,
        )
        legend_box = legend.get_window_extent(renderer)
        check(
            "%s: the whole legend fits inside the canvas (right edge %.0f of %.0f px)"
            % (title, legend_box.x1, figure_right),
            legend_box.x1 <= figure_right,
        )
        # Every individual label, not just the legend box as a whole.
        for text in legend.get_texts():
            label = text.get_text()
            seen_labels.add(label)
            check(
                "%s: legend label %r is not clipped" % (title, label),
                text.get_window_extent(renderer).x1 <= figure_right,
            )
        # The reserved band must be at least as wide as the legend needs.
        reserved = min(
            win.METRICS_LEGEND_MAX_WIDTH_PX,
            max(win.METRICS_LEGEND_MIN_WIDTH_PX, win._metrics_legend_width_pixels(figure)),
        )
        check(
            "%s: the reserved band covers the measured legend width" % title,
            reserved >= legend_box.width,
        )

    # The specific labels called out as the longest in the current metric set.
    for label in ("Reference match", "Heavy atoms found", "Omit map correlation", "R_free"):
        check("legend label %r was actually exercised above" % label, label in seen_labels)

    # ---- clamp bounds ------------------------------------------------
    check(
        "the legend band never shrinks below the previous fixed width",
        win.METRICS_LEGEND_MIN_WIDTH_PX == 112.0,
    )
    check(
        "the legend band is capped in the intended 180-200 px range",
        180.0 <= win.METRICS_LEGEND_MAX_WIDTH_PX <= 200.0,
    )
    check(
        "the clamp is ordered min < max",
        win.METRICS_LEGEND_MIN_WIDTH_PX < win.METRICS_LEGEND_MAX_WIDTH_PX,
    )

    # ---- a pathological label cannot eat the plot --------------------
    long_label = "An absurdly long metric label that should never be allowed " * 3
    win._render_metrics_tab(
        "superflip",
        [
            (long_label, [r.superflip_heavy_atom_count for r in win.results], True, "#001170", "o", "-"),
            ("Recall", [r.superflip_recall for r in win.results], True, "#2264b8", "^", "-"),
        ],
    )
    figure, legend, _renderer = laid_out("superflip")
    measured = win._metrics_legend_width_pixels(figure)
    clamped = min(win.METRICS_LEGEND_MAX_WIDTH_PX, max(win.METRICS_LEGEND_MIN_WIDTH_PX, measured))
    check("pathological label: raw measurement exceeds the cap", measured > win.METRICS_LEGEND_MAX_WIDTH_PX)
    check("pathological label: the reserved band is clamped to the cap",
          clamped == win.METRICS_LEGEND_MAX_WIDTH_PX)
    axes_box = win.metrics_axes["superflip"].get_window_extent()
    check("pathological label: the plot keeps most of the canvas",
          axes_box.width >= figure.get_window_extent().x1 * 0.5)

    # ---- no legend means no reserved band ----------------------------
    win._replay_metrics_tab("superflip")
    legend_figure, _legend, _r = laid_out("superflip")
    legend_axes_right = win.metrics_axes["superflip"].get_window_extent().x1
    plain_figure, plain_legend, _r2 = laid_out("powder_repartition")
    plain_axes = win.metrics_axes["powder_repartition"].get_window_extent()
    check("a single-series tab reserves no legend band", plain_legend is None)
    check(
        "a single-series tab uses the width a legend band would have cost",
        (plain_axes.x1 / plain_figure.get_window_extent().x1)
        > (legend_axes_right / legend_figure.get_window_extent().x1),
    )

    failures = [name for name, ok in results_log if not ok]
    print()
    if failures:
        print(str(len(failures)) + " of " + str(len(results_log)) + " checks FAILED:")
        for name in failures:
            print("  - " + name)
        return 1
    print("All " + str(len(results_log)) + " checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
