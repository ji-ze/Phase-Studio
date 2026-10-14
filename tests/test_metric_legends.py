"""Profile-aware workflow metric tabs and legend regression tests."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

checks = []


def check(name, condition):
    checks.append((name, bool(condition)))
    print(("PASS" if condition else "FAIL") + " - " + name)


def main():
    from PySide6.QtWidgets import QApplication
    from phase_studio import app as appmod
    from phase_studio.map_quality import MapQualityMetrics, PROFILE_DEFINITIONS

    app = QApplication.instance() or QApplication([sys.argv[0]])
    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    win = appmod.IterativeSuperflipPipelineQtGUI()
    tmp = Path(tempfile.mkdtemp())
    map_path = tmp / "result.xplor"
    cif_path = tmp / "result.cif"
    map_path.write_text("map", encoding="utf-8")
    cif_path.write_text("model", encoding="utf-8")
    quality_sf = MapQualityMetrics(
        reference_f05=0.71, reference_rmsd=0.34, reference_phase_agreement=0.81,
        amplitude_rf=0.21, amplitude_cc=0.82, r_free=0.29, cc_free=0.73,
        omit_map_correlation=0.68, triplet_c3=0.61,
    )
    quality_sharped = MapQualityMetrics(
        reference_f05=0.78, reference_rmsd=0.28, reference_phase_agreement=0.85,
        amplitude_rf=0.17, amplitude_cc=0.88, r_free=0.25, cc_free=0.79,
        omit_map_correlation=0.74, triplet_c3=0.67,
    )

    def result(profile, cycle=1):
        return appmod.CycleResult(
            cycle=cycle, model_source="superflip", model_in=None, model_metric=None,
            superflip_map=map_path, superflip_edma_cif=cif_path, superflip_metric=None,
            deblur_map=map_path, deblur_edma_cif=cif_path, deblur_metric=None,
            validation_profile=profile.value,
            superflip_quality=quality_sf, deblur_quality=quality_sharped,
        )

    # A restored 4th tab (the historical Map Feedback change diagnostic) is
    # always built alongside the 3 profile-aware tabs, but stays hidden
    # until Map Feedback intensity correction is enabled -- see the
    # dedicated visibility checks below.
    check("exactly four metric tabs exist (3 profile-aware + 1 restored diagnostic)", win.metrics_tabs.count() == 4)
    check(
        "the four internal metric keys are stable",
        win._metrics_tab_keys == ["quality_0", "quality_1", "quality_2", "map_feedback_change"],
    )
    check("the Map Feedback change tab starts hidden", not win.metrics_tabs.isTabVisible(3))
    for profile, definition in PROFILE_DEFINITIONS.items():
        win.results = [result(profile)]
        win._update_plot()
        expected = [metric.label for metric in definition.primary_metrics]
        shown = [win.metrics_tabs.tabText(i) for i in range(3)]
        check(f"{profile.value}: plotted metric set follows the authoritative profile", shown == expected)
        check(f"{profile.value}: Map Feedback change tab remains hidden with intensity correction off", not win.metrics_tabs.isTabVisible(3))
        check(
            f"{profile.value}: assessment label follows the profile",
            win.assessment_label.text() == f"Assessment: {definition.assessment_label}",
        )
        for index, metric in enumerate(definition.primary_metrics):
            key = f"quality_{index}"
            labels = win.metrics_axes[key].get_legend_handles_labels()[1]
            legend = win.metrics_figures[key].legends[0] if win.metrics_figures[key].legends else None
            shown_labels = [] if legend is None else [text.get_text() for text in legend.get_texts()]
            check(f"{profile.value}/{metric.key}: both sources are plotted", labels == ["Superflip", "SharpED"])
            check(f"{profile.value}/{metric.key}: legend matches plotted sources", shown_labels == labels)
            direction = "Higher is better." if metric.higher_is_better else "Lower is better."
            check(f"{profile.value}/{metric.key}: direction tooltip is explicit", direction in win.metrics_tabs.tabToolTip(index))

    # Enabling Map Feedback intensity correction shows the restored 4th tab
    # with the cycle-level diagnostic; the 3 profile tabs and the
    # recommendation-relevant data are untouched.
    feedback_result = result(next(iter(PROFILE_DEFINITIONS)))
    feedback_result.intensity_correction_avg_change_percent = -2.5
    win.results = [feedback_result]
    win.inputs["map_feedback_intensity_enabled"].setChecked(True)
    win._update_plot()
    check("Map Feedback change tab becomes visible once intensity correction is enabled", win.metrics_tabs.isTabVisible(3))
    check("Map Feedback change tab title", win.metrics_tabs.tabText(3) == "Map Feedback change (%)")
    feedback_hover = win._metrics_hover_series.get("map_feedback_change", [])
    check(
        "Map Feedback change tab plots the cycle-level diagnostic, not a Superflip/SharpED pair",
        len(feedback_hover) == 1 and feedback_hover[0][0] == "Map Feedback change (%)"
        and feedback_hover[0][2] == [-2.5],
    )
    win.inputs["map_feedback_intensity_enabled"].setChecked(False)
    win._sync_map_feedback_widgets()
    check("Map Feedback change tab hides again once intensity correction is disabled", not win.metrics_tabs.isTabVisible(3))

    win.results = []
    win._update_plot()
    check("empty tabs do not fabricate legends", all(not win.metrics_figures[key].legends for key in win._metrics_tab_keys))
    win.timer.stop()
    win.close()
    failures = [name for name, ok in checks if not ok]
    print()
    if failures:
        print(f"{len(failures)} of {len(checks)} checks FAILED:")
        for failure in failures:
            print("  - " + failure)
        return 1
    print(f"All {len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
