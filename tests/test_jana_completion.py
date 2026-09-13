"""Shared Jana2020/standalone profile-aware result-selection tests."""
import dataclasses
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []

CIF = """data_test
_cell_length_a 10.0
_cell_length_b 10.0
_cell_length_c 10.0
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
_space_group_name_H-M_alt 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C 0.10 0.10 0.10
O1 O 0.50 0.40 0.35
"""


def check(name, condition):
    results_log.append((name, bool(condition)))
    print(("PASS" if condition else "FAIL") + " - " + name)


def make_run_config(appmod, tmp, inflip):
    import gemmi
    metadata = appmod.CrystalMetadata(
        cell=gemmi.UnitCell(10, 10, 10, 90, 90, 90),
        spacegroup=gemmi.SpaceGroup("P 1"), spacegroup_hm="P 1",
        composition="C 2", source="test", source_path=inflip,
    )
    values = {}
    for field in dataclasses.fields(appmod.RunConfig):
        text_type = field.type if isinstance(field.type, str) else str(field.type)
        if field.name == "crystal_metadata":
            values[field.name] = metadata
        elif field.name == "jana_inflip":
            values[field.name] = inflip
        elif field.name == "work_dir":
            values[field.name] = tmp
        elif text_type.startswith("Optional"):
            values[field.name] = None
        elif text_type == "Path":
            values[field.name] = tmp / "placeholder"
        elif text_type == "bool":
            values[field.name] = False
        elif text_type == "int":
            values[field.name] = 1
        elif text_type == "float":
            values[field.name] = 0.0
        else:
            values[field.name] = ""
    values["cycles"] = 5
    values["jana_return_to_jana"] = True
    return appmod.RunConfig(**values)


def build_window(appmod, source="deblurred", launch_mode="phase_recycling", cycles=3, sharped_maps=True):
    """Build a completed-result fixture shared with workflow-state tests."""
    from phase_studio.map_quality import MapQualityMetrics, ValidationProfile
    import gemmi

    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    win = appmod.IterativeSuperflipPipelineQtGUI()
    tmp = Path(tempfile.mkdtemp())

    def model(name):
        path = tmp / name
        path.write_text(CIF, encoding="utf-8")
        return path

    def map_file(name):
        path = tmp / name
        path.write_text("real existing map", encoding="utf-8")
        return path

    cycle_results = []
    for cycle in range(1, cycles + 1):
        sf_quality = MapQualityMetrics(
            reference_f05=0.60 + cycle * 0.01, reference_rmsd=0.40,
            reference_phase_agreement=0.70, amplitude_rf=0.25,
            amplitude_cc=0.75, r_free=0.32, cc_free=0.70,
            omit_map_correlation=0.65, triplet_c3=0.55,
            n_measured_reflections=100, n_work_reflections=95, n_free_reflections=5,
        )
        sharped_quality = MapQualityMetrics(
            reference_f05=0.70 + cycle * 0.01, reference_rmsd=0.30,
            reference_phase_agreement=0.80, amplitude_rf=0.20,
            amplitude_cc=0.82, r_free=0.27, cc_free=0.77,
            omit_map_correlation=0.72, triplet_c3=0.62,
            n_measured_reflections=100, n_work_reflections=95, n_free_reflections=5,
        )
        cycle_results.append(appmod.CycleResult(
            cycle=cycle, model_source="superflip", model_in=None, model_metric=None,
            superflip_map=map_file(f"sf{cycle}.xplor"),
            superflip_edma_cif=model(f"sf{cycle}.cif"), superflip_metric=0.4,
            deblur_map=(map_file(f"db{cycle}.xplor") if sharped_maps else tmp / f"missing{cycle}.xplor"),
            deblur_edma_cif=model(f"db{cycle}.cif"), deblur_metric=0.3,
            validation_profile=ValidationProfile.REFERENCE_AND_HOLDOUT.value,
            superflip_quality=sf_quality,
            deblur_quality=(sharped_quality if sharped_maps else None),
        ))
    win.structure_cell = gemmi.UnitCell(10, 10, 10, 90, 90, 90)
    win.reference_atoms_for_plot = win._safe_parse_structure(cycle_results[0].superflip_edma_cif)
    inflip = model("job.inflip")
    win.last_run_config = make_run_config(appmod, tmp, inflip)
    win.jana_wizard_context = appmod.JanaWizardContext(
        launched_from_jana_wizard=launch_mode in {"phase_recycling", "full_configuration"},
        launch_mode=launch_mode,
        wizard_map_source=source,
    )
    return win, cycle_results


def run_to_completion(win, cycle_results, app):
    from PySide6.QtCore import QCoreApplication
    win.results = []
    win._set_run_status("Running")
    win._jana_auto_selector_shown = False
    for result in cycle_results:
        win.msg_queue.put(("result", result))
    win.msg_queue.put(("done", len(cycle_results)))
    win._poll_queue()
    QCoreApplication.processEvents()


def main():
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLabel, QPushButton, QTableWidget
    from phase_studio import app as appmod
    from phase_studio.map_quality import PROFILE_DEFINITIONS, ValidationProfile

    app = QApplication.instance() or QApplication([sys.argv[0]])
    opened = []

    def reject_dialog(dialog):
        opened.append(dialog)
        return QDialog.Rejected

    QDialog.exec = reject_dialog

    for launch_mode in ("phase_recycling", "full_configuration"):
        opened.clear()
        win, cycle_results = build_window(appmod, launch_mode=launch_mode)
        run_to_completion(win, cycle_results, app)
        check(f"{launch_mode}: completion is COMPLETE", win._run_status == "COMPLETE")
        check(f"{launch_mode}: selector opens automatically once", len(opened) == 1)
        check(f"{launch_mode}: Jana action has current wording", win.jana_action_btn.text() == "Pass to Jana2020")
        check(f"{launch_mode}: Jana action remains enabled", win.jana_action_btn.isEnabled())
        check(f"{launch_mode}: shared dialog has Jana context", opened and opened[0].property("resultContext") == "JANA2020")

    # The same dialog's columns are driven by each authoritative profile.
    win, cycle_results = build_window(appmod, launch_mode="phase_recycling", cycles=1)
    win.results = cycle_results
    for profile, definition in PROFILE_DEFINITIONS.items():
        win.results[0].validation_profile = profile.value
        opened.clear()
        win.open_result_selector("jana")
        table = opened[-1].findChild(QTableWidget)
        headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
        expected = ["Recommended", "Cycle", "Source"] + [metric.arrow_label for metric in definition.primary_metrics]
        check(f"{profile.value}: selector columns follow profile", headers == expected)
        labels = [label.text() for label in opened[-1].findChildren(QLabel)]
        check(f"{profile.value}: selector summary names assessment", definition.assessment_label in labels)
        check(f"{profile.value}: obsolete Selection score is absent", "Selection score" not in " ".join(headers + labels))

    # Standalone completion stays quiet; its visible action opens this same component.
    opened.clear()
    standalone, standalone_results = build_window(appmod, launch_mode="standalone")
    run_to_completion(standalone, standalone_results, app)
    check("standalone: selector does not auto-open", opened == [])
    check("standalone: save action is visible", not standalone.jana_action_btn.isHidden())
    check("standalone: save action is enabled", standalone.jana_action_btn.isEnabled())
    check("standalone: save action wording", standalone.jana_action_btn.text() == "Save map and model")
    standalone._on_jana_action_clicked()
    check("standalone: button opens shared selector", len(opened) == 1 and opened[0].property("resultContext") == "STANDALONE")

    # Map-only candidates remain selectable and are labelled honestly.
    map_only, map_only_results = build_window(appmod, launch_mode="standalone", cycles=1)
    missing_model = Path(map_only_results[0].deblur_edma_cif).with_name("missing-model.cif")
    map_only_results[0].deblur_edma_cif = missing_model
    map_only.results = map_only_results
    opened.clear()
    map_only.open_result_selector("standalone")
    map_only_dialog = opened[-1]
    map_only_table = map_only_dialog.findChild(QTableWidget)
    source_values = [map_only_table.item(row, 2).text() for row in range(map_only_table.rowCount())]
    primary_button = map_only_dialog.findChild(QPushButton, "primaryButton")
    check("map-only candidate is identified in its row", any("map only" in value for value in source_values))
    check("map-only selection uses honest save wording", primary_button is not None and primary_button.text() == "Save available result")

    # Identical candidates produce the same recommendation in both contexts.
    jana, jana_results = build_window(appmod, launch_mode="phase_recycling")
    jana.results = jana_results
    jana.open_result_selector("jana")
    standalone.results = jana_results
    standalone.open_result_selector("standalone")
    check(
        "Jana and standalone recommend the same cycle/source",
        jana.result_recommendation.recommended_candidate == standalone.result_recommendation.recommended_candidate,
    )

    # Standalone export copies the selected canonical files without changing
    # or recomputing their contents.
    export_dir = Path(tempfile.mkdtemp()) / "export"
    original_directory_picker = QFileDialog.getExistingDirectory
    try:
        QFileDialog.getExistingDirectory = lambda *_args, **_kwargs: str(export_dir)
        candidate = standalone._result_candidates()[0]
        original_map = Path(candidate.map_path).read_bytes()
        original_model = Path(candidate.structure_path).read_bytes()
        check("standalone export succeeds", standalone._export_selected_candidate(candidate))
        check("standalone export copies the selected real map", (export_dir / Path(candidate.map_path).name).read_bytes() == original_map)
        check("standalone export copies the selected real model", (export_dir / Path(candidate.structure_path).name).read_bytes() == original_model)
    finally:
        QFileDialog.getExistingDirectory = original_directory_picker

    # Accepted Jana selection delegates the selected existing CycleResult and
    # source to the established handoff implementation.
    handed_off = []
    original_handoff = appmod.perform_jana_handoff
    original_thread = appmod.threading.Thread

    class ImmediateThread:
        def __init__(self, target, daemon=True):
            self.target = target

        def start(self):
            self.target()

    try:
        appmod.perform_jana_handoff = lambda cfg, result, source, log=None: handed_off.append((result, source))
        appmod.threading.Thread = ImmediateThread
        QDialog.exec = lambda _dialog: QDialog.Accepted
        jana.open_result_selector("jana")
        selected = jana.result_recommendation.selected_candidate
        check("Jana accepted selection invokes existing handoff once", len(handed_off) == 1)
        check("Jana handoff uses selected source", handed_off and selected is not None and handed_off[0][1] == selected.source)
        check("Jana handoff uses selected real result files", handed_off and Path(handed_off[0][0].deblur_map if handed_off[0][1] != "superflip" else handed_off[0][0].superflip_map) == Path(selected.map_path))
    finally:
        appmod.perform_jana_handoff = original_handoff
        appmod.threading.Thread = original_thread
        QDialog.exec = reject_dialog

    # CSV and human report share the same profile and contain every diagnostic.
    report_dir = Path(tempfile.mkdtemp())
    appmod.write_metrics_csv(report_dir / "metrics.csv", jana_results[:1])
    csv_lines = (report_dir / "metrics.csv").read_text(encoding="utf-8").splitlines()
    check("metrics CSV writes one row per cycle/source", len(csv_lines) == 3)
    check("metrics CSV contains all stable quality columns", all(column in csv_lines[0].split(",") for column in appmod.QUALITY_CSV_COLUMNS))
    for profile, definition in PROFILE_DEFINITIONS.items():
        jana_results[0].validation_profile = profile.value
        report_path = report_dir / f"{profile.value}.txt"
        appmod.write_map_quality_report(report_path, jana_results[:1])
        report_text = report_path.read_text(encoding="utf-8")
        check(f"{profile.value}: report records assessment", f"Assessment: {definition.assessment_label}" in report_text)
        check(f"{profile.value}: report records all three criteria", all(metric.label in report_text for metric in definition.primary_metrics))
        check(f"{profile.value}: report includes all computed diagnostics", "All computed metrics:" in report_text and "amplitude_rf:" in report_text)

    # A graceful stop with valid results also auto-opens in Jana context.
    opened.clear()
    stopped, stopped_results = build_window(appmod, launch_mode="phase_recycling")
    stopped.results = stopped_results[:2]
    stopped._set_run_status("Running")
    stopped._jana_auto_selector_shown = False
    stopped._finish_stopped_run(2)
    app.processEvents()
    check("graceful stop: selector opens automatically", len(opened) == 1)

    for window in (win, standalone, map_only, jana, stopped):
        window.timer.stop()
        window.close()
    failures = [name for name, ok in results_log if not ok]
    print()
    if failures:
        print(f"{len(failures)} of {len(results_log)} checks FAILED:")
        for failure in failures:
            print("  - " + failure)
        return 1
    print(f"All {len(results_log)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
