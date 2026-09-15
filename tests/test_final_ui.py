"""Focused 1.0.9 wording, remediation, and scalable-geometry checks."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QToolButton, QGroupBox
    from phase_studio import app as appmod
    from phase_studio.error_reporting import build_error_report, build_validation_report
    from phase_studio.ui_style import apply_phase_studio_style

    qt_app = QApplication.instance() or QApplication([sys.argv[0]])
    apply_phase_studio_style(qt_app)
    checks = []

    def check(name, condition):
        checks.append((name, bool(condition)))
        print(("PASS" if condition else "FAIL") + " - " + name)

    with patch.object(appmod.IterativeSuperflipPipelineQtGUI, "load_settings"), \
         patch.object(appmod.IterativeSuperflipPipelineQtGUI, "save_settings"), \
         patch.object(appmod.IterativeSuperflipPipelineQtGUI, "refresh_sharped_models"):
        win = appmod.IterativeSuperflipPipelineQtGUI()

    visible = []
    for widget_type in (QLabel, QPushButton, QToolButton):
        for widget in win.findChildren(widget_type):
            visible.extend((widget.text(), widget.toolTip()))
    visible.extend(group.title() for group in win.findChildren(QGroupBox))
    for tabs in (win.basic_tabs, win.advanced_tabs):
        visible.extend(tabs.tabText(index) for index in range(tabs.count()))
    check("no visible main-window string says pipeline",
          all("pipeline" not in text.casefold() for text in visible))
    check("metadata source uses Jana2020 .inflip",
          win.inputs["metadata_source"].itemText(0) == "Jana2020 .inflip")
    check("canonical phase/amplitude HKL notation is shared",
          appmod.format_reflection_data_mode(appmod.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA)
          == "h k l · F · phase · σ(F)")
    check("initial log matches the no-input state",
          win.log_text.toPlainText() == "Ready. Select an input to begin.")

    with tempfile.NamedTemporaryFile(suffix=".inflip") as selected:
        win._set_widget_value_from_string(win.inputs["jana_inflip"], selected.name)
        win._sync_idle_ready_log()
        check("loaded input changes the idle log without adding a line",
              win.log_text.toPlainText() == "Ready. Review the settings and run phasing.")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        stale_inflip = temp / "remembered.inflip"
        stale_inflip.write_text("title remembered inactive input\n", encoding="utf-8")
        external_hkl = temp / "external.hkl"
        external_hkl.write_text("1 0 0 10 1\n", encoding="utf-8")
        reference_cif = temp / "reference.cif"
        reference_cif.write_text(
            "data_ref\n_cell_length_a 10\n_cell_length_b 10\n_cell_length_c 10\n"
            "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
            "_space_group_name_H-M_alt 'P 1'\n_chemical_formula_sum 'C 1'\n",
            encoding="utf-8",
        )
        win._set_widget_value_from_string(win.inputs["jana_inflip"], str(stale_inflip))
        win._set_widget_value_from_string(
            win.inputs["input_source_mode"], appmod.INPUT_MODE_LABELS[appmod.INPUT_MODE_EXTERNAL],
        )
        win._set_widget_value_from_string(win.inputs["hkl"], str(external_hkl))
        win._set_widget_value_from_string(win.inputs["reference_cif"], str(reference_cif))
        win._set_widget_value_from_string(
            win.inputs["metadata_source"], appmod.METADATA_SOURCE_LABELS[appmod.METADATA_SOURCE_INFLIP],
        )
        win._sync_metadata_source_widgets()
        check("External HKL mode rejects an inactive Jana2020 metadata source",
              win._metadata_source_value() == appmod.METADATA_SOURCE_REFERENCE)
        external_cfg = win.get_config()
        check("External HKL mode omits a remembered inactive .inflip from RunConfig",
              external_cfg.jana_inflip is None)
        check("standalone RunConfig never enables Jana2020 handoff",
              not external_cfg.jana_return_to_jana)

    inflip = build_error_report(RuntimeError("invalid .inflip"), subsystem="Jana2020")
    check("Jana handoff action names its destination",
          [action.label for action in win._error_actions(inflip)] == ["Open Input settings"])
    edma = build_validation_report(["Phase Studio could not find a working EDMA executable."])
    check("single EDMA preflight is requirement-specific",
          edma.title == "EDMA setup required" and
          [action.label for action in win._error_actions(edma)] == ["Set up EDMA"])
    sharped = build_validation_report(["A SharpED API token is required for the selected workflow."])
    check("SharpED preflight routes directly to the API token",
          [action.label for action in win._error_actions(sharped)] == ["Update API token"])
    unavailable = build_error_report(
        RuntimeError("connection refused"), subsystem="SharpED", operation="Upload map"
    )
    check("SharpED connectivity guidance does not direct users to edit the server URL",
          "try again" in unavailable.guidance
          and "temporarily unavailable" in unavailable.guidance
          and "server URL" not in unavailable.guidance)

    splash = appmod.PhaseStudioSplash()
    check("splash progress is determinate", splash.progress.minimum() == 0 and splash.progress.maximum() == 100)
    splash.set_status("Finalizing workspace…")
    check("splash uses one continuous determinate fill", splash.progress.value() == 86)
    check("main actions retain high-DPI-safe minimum height",
          min(win.run_btn.minimumSizeHint().height(), win.continue_btn.minimumSizeHint().height(),
              win.stop_now_btn.minimumSizeHint().height()) >= 30)
    splash.close()
    win.timer.stop()
    win.close()
    failed = [name for name, ok in checks if not ok]
    if failed:
        print(f"\n{len(failed)} check(s) FAILED: " + ", ".join(failed))
        return 1
    print(f"\nAll {len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
