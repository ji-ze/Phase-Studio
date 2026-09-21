"""Shared Jana2020/standalone profile-aware result-selection tests."""
import csv
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
    # cfg.run_sharped gates whether the SharpED result-selection tab is shown
    # at all (a disabled SharpED run still leaves a placeholder deblur_map
    # copied from Superflip); this fixture's sharped_maps flag already
    # encodes "SharpED genuinely produced distinct results", so it drives
    # run_sharped too instead of leaving it at make_run_config's blanket
    # bool default of False.
    win.last_run_config.run_sharped = sharped_maps
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
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLabel, QPushButton, QTableWidget, QWidget
    from phase_studio import app as appmod
    from phase_studio.map_quality import PROFILE_DEFINITIONS, ValidationProfile
    from phase_studio.result_selection import result_selection_metric_columns

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
        dialog = opened[-1]
        table = dialog._views[dialog.active_source].table
        headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
        columns = result_selection_metric_columns(definition)
        expected = ["Recommended", "Cycle"] + [column[0] for column in columns]
        check(f"{profile.value}: selector columns follow profile", headers == expected)
        check(f"{profile.value}: selector has no Source column", "Source" not in headers)
        check(
            f"{profile.value}: selector exposes full metric names",
            all(table.horizontalHeaderItem(index + 2).toolTip() == column[1]
                for index, column in enumerate(columns)),
        )
        check(
            f"{profile.value}: selector exposes accessible metric descriptions",
            all(table.horizontalHeaderItem(index + 2).data(Qt.AccessibleDescriptionRole) == column[1]
                for index, column in enumerate(columns)),
        )
        labels = [label.text() for label in dialog.findChildren(QLabel)]
        check(f"{profile.value}: selector summary names assessment", definition.assessment_label in labels)
        check(f"{profile.value}: obsolete Selection score is absent", "Selection score" not in " ".join(headers + labels))

    # Candidate-count geometry uses the same dialog at small and large run
    # sizes. Six to eight rows are reserved; larger result sets scroll inside
    # the table while the dialog footer remains outside that viewport.
    count_window, count_results = build_window(
        appmod, launch_mode="standalone", cycles=30,
    )
    count_window.results = count_results
    # Superflip-only slice: isolates the shared table-geometry logic
    # (_build_candidate_table) from the source split -- SharpED stays hidden
    # throughout so the one visible table's row count is exactly n.
    all_candidates = [c for c in count_window._result_candidates() if c.source == "superflip"]
    original_candidates = count_window._result_candidates
    for candidate_count in (1, 2, 4, 10, 30):
        count_window._result_candidates = lambda n=candidate_count: all_candidates[:n]
        opened.clear()
        count_window.open_result_selector("standalone")
        dialog = opened[-1]
        check(f"{candidate_count} candidates: SharpED tab hidden, no source ambiguity", dialog.active_source == "superflip")
        table = dialog._views["superflip"].table
        dialog.resize(1280, 760)
        dialog.show()
        app.processEvents()
        check(f"{candidate_count} candidates: exact row count", table.rowCount() == candidate_count)
        check(
            f"{candidate_count} candidates: table viewport is capped at eight rows",
            table.maximumHeight() <= table.horizontalHeader().sizeHint().height()
            + 8 * table.verticalHeader().defaultSectionSize() + 2 * table.frameWidth(),
        )
        check(
            f"{candidate_count} candidates: no horizontal table scrollbar",
            table.horizontalScrollBar().maximum() == 0,
        )
        if candidate_count >= 10:
            check(
                f"{candidate_count} candidates: table scrolls vertically",
                table.verticalScrollBar().maximum() > 0,
            )
        dialog.close()
    count_window._result_candidates = original_candidates
    count_window.timer.stop()
    count_window.close()

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
    # The SharpED result is the map-only one in this fixture; switch there
    # explicitly rather than depending on the initial-source default.
    map_only_dialog._apply_source("deblurred")
    map_only_table = map_only_dialog._views["deblurred"].table
    cycle_values = [map_only_table.item(row, 1).text() for row in range(map_only_table.rowCount())]
    primary_button = map_only_dialog.findChild(QPushButton, "primaryButton")
    check("map-only candidate is identified in its row", any("map only" in value for value in cycle_values))
    check("map-only selection uses honest save wording", primary_button is not None and primary_button.text() == "Save available result")

    # --- Source split: independent tables, recommendations, selection, and
    # source-appropriate validation warnings. ---
    from phase_studio.result_selection import result_warning_callout_text

    split_window, split_results = build_window(appmod, launch_mode="standalone", cycles=4)
    split_window.results = split_results
    opened.clear()
    split_window.open_result_selector("standalone")
    split_dialog = opened[-1]
    # isVisible() reflects real on-screen visibility (ancestor chain
    # included), unlike a bare setVisible() call on an unshown dialog.
    split_dialog.show()
    app.processEvents()
    check("split: both source tabs available", set(split_dialog._views.keys()) == {"superflip", "deblurred"})
    check(
        "split: switch buttons exist, are checkable and exclusive",
        split_dialog._superflip_btn is not None and split_dialog._sharped_btn is not None
        and split_dialog._superflip_btn.isCheckable() and split_dialog._sharped_btn.isCheckable(),
    )
    check("split: two independent tables exist", len(split_dialog.findChildren(QTableWidget)) == 2)
    check(
        "split: row counts match each source independently",
        split_dialog._views["superflip"].table.rowCount() == 4
        and split_dialog._views["deblurred"].table.rowCount() == 4,
    )
    # This fixture's reference_f05 rises with cycle for both sources, so the
    # independent per-source recommendation is cycle 4 in both -- computed
    # separately (no SharpED bonus, no cross-source competition).
    check(
        "split: independent recommendations computed per source",
        split_dialog._views["superflip"].recommendation.recommended_candidate.cycle == 4
        and split_dialog._views["deblurred"].recommendation.recommended_candidate.cycle == 4,
    )

    # Selection persistence: Superflip -> SharpED -> Superflip must not lose
    # or overwrite either source's own selection.
    split_dialog._apply_source("superflip")
    split_dialog._views["superflip"].table.selectRow(0)
    app.processEvents()
    split_dialog._apply_source("deblurred")
    split_dialog._views["deblurred"].table.selectRow(1)
    app.processEvents()
    split_dialog._apply_source("superflip")
    check(
        "split: switching sources preserves each source's own selection",
        split_dialog._views["superflip"].selected.cycle == 1
        and split_dialog._views["deblurred"].selected.cycle == 2,
    )
    check(
        "split: final action uses the currently active source's selection",
        split_dialog.selected_candidate == split_dialog._views["superflip"].selected,
    )

    # Warnings: pure-function coverage of all four combinations, plus the
    # live dialog reflecting the same text for its active source.
    check("split: no warning for plain Superflip with Map Feedback off", result_warning_callout_text("superflip", False) is None)
    sharped_only_warning = result_warning_callout_text("deblurred", False)
    check("split: SharpED always warns", sharped_only_warning is not None and "neural-network" in sharped_only_warning)
    superflip_mf_warning = result_warning_callout_text("superflip", True)
    check("split: Superflip warns when Map Feedback is on", superflip_mf_warning is not None and "Map Feedback" in superflip_mf_warning)
    combined_warning = result_warning_callout_text("deblurred", True)
    check(
        "split: SharpED + Map Feedback uses one combined warning",
        combined_warning is not None and "neural-network" in combined_warning and "Map Feedback" in combined_warning,
    )
    check("split: live callout hidden for plain Superflip with Map Feedback off", not split_dialog._warning_callout.isVisible())
    split_dialog._apply_source("deblurred")
    check("split: live callout visible for SharpED", split_dialog._warning_callout.isVisible())
    split_dialog.close()

    # Map Feedback intensity correction on: 4th column appears in both
    # tables (cycle-level value, same figure in both source tables), with
    # "—" for cycles where it was never computed.
    mf_window, mf_results = build_window(appmod, launch_mode="standalone", cycles=2)
    mf_results[1].intensity_correction_avg_change_percent = -3.25
    mf_window.results = mf_results
    mf_window.last_run_config.map_feedback_intensity_enabled = True
    opened.clear()
    mf_window.open_result_selector("standalone")
    mf_dialog = opened[-1]
    mf_dialog._apply_source("superflip")
    check(
        "split: Map Feedback column appears when intensity correction is enabled",
        "Map Feedback Δ (%)" in [
            mf_dialog._views["superflip"].table.horizontalHeaderItem(i).text()
            for i in range(mf_dialog._views["superflip"].table.columnCount())
        ],
    )
    feedback_column = mf_dialog._views["superflip"].table.columnCount() - 1
    feedback_cell_values = [
        mf_dialog._views["superflip"].table.item(row, feedback_column).text()
        for row in range(mf_dialog._views["superflip"].table.rowCount())
    ]
    check("split: Map Feedback value renders for the cycle it was computed on", "-3.2%" in feedback_cell_values)
    check("split: Map Feedback shows an em dash where unavailable", "—" in feedback_cell_values)
    check(
        "split: Map Feedback column absent when intensity correction is off",
        "Map Feedback Δ (%)" not in [
            split_dialog._views["superflip"].table.horizontalHeaderItem(i).text()
            for i in range(split_dialog._views["superflip"].table.columnCount())
        ],
    )

    # Only one source available: the switch bar disappears and the dialog
    # opens directly on the available source, without an empty misleading
    # table for the missing one.
    superflip_only, superflip_only_results = build_window(
        appmod, launch_mode="standalone", cycles=2, sharped_maps=False,
    )
    superflip_only.results = superflip_only_results
    opened.clear()
    superflip_only.open_result_selector("standalone")
    superflip_only_dialog = opened[-1]
    check("split: SharpED-only-missing hides the switch bar", superflip_only_dialog._superflip_btn is None)
    check("split: SharpED-only-missing opens directly on Superflip", superflip_only_dialog.active_source == "superflip")
    check("split: SharpED-only-missing has no SharpED view at all", "deblurred" not in superflip_only_dialog._views)

    # cfg.run_sharped=False must hide the SharpED tab even when a real-looking
    # deblurred candidate technically exists (the pipeline's own copy of the
    # Superflip map when SharpED was disabled) -- this is the trap a naive
    # "candidates non-empty" check would miss.
    disabled_sharped, disabled_sharped_results = build_window(appmod, launch_mode="standalone", cycles=2)
    disabled_sharped.results = disabled_sharped_results
    disabled_sharped.last_run_config.run_sharped = False
    opened.clear()
    disabled_sharped.open_result_selector("standalone")
    disabled_sharped_dialog = opened[-1]
    check(
        "split: run_sharped=False hides SharpED even with a populated deblurred candidate",
        "deblurred" not in disabled_sharped_dialog._views
        and disabled_sharped_dialog._superflip_btn is None
        and disabled_sharped_dialog.active_source == "superflip",
    )

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

    # A row change updates both the explicit selection returned to the caller
    # and the lazily rendered preview, without changing the recommendation.
    selector = opened[-1]
    selector._apply_source("superflip")
    selector_table = selector._views["superflip"].table
    selector_table.selectRow(0)
    app.processEvents()
    manual_candidate = standalone._result_candidates()[0]
    check(
        "manual override selects the requested cycle/source",
        selector.selected_candidate == manual_candidate,
    )
    preview_canvas = selector.findChild(QWidget, "resultPreviewCanvas")
    preview_titles = [text.get_text() for text in preview_canvas.figure.texts]
    check(
        "preview selection updates to the manually selected result",
        manual_candidate.label in preview_titles,
    )
    recommendation_markers = [
        selector_table.item(row, 0).text() for row in range(selector_table.rowCount())
    ]
    check(
        "manual selection leaves the automatic recommendation marker unchanged",
        recommendation_markers.count("★ Recommended") == 1
        and recommendation_markers[selector_table.currentRow()] != "★ Recommended",
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

    # The Wizard-to-full-GUI handoff is a stable compatibility surface. Pin
    # its complete value mapping, including override precedence and feedback
    # settings, before deleting any historical selector code.
    from phase_studio import jana_superflip as jana_superflip
    handoff_dir = Path(tempfile.mkdtemp())
    handoff_inflip = handoff_dir / "job.inflip"
    handoff_inflip.write_text("title guard\n", encoding="utf-8")
    handoff_options = jana_superflip.JanaRunOptions(
        action="edit", cycles=4, next_cycle_modelfile="superflip_xplor",
        api_token="secret-token", server_url="https://jana.fzu.cz", model="default",
        elements="C N O", outres=0.25, input_mode=jana_superflip.INPUT_MODE_EXTERNAL,
        hkl_override="override.hkl", reference_override="override.cif",
        first_cycle_modelfile="seed.xplor", compute_omit_maps=True,
        compute_omit_rfree=True, enable_missing_completion=True, missing_start_cycle=2,
        missing_max_added_percent=7.5, enable_intensity_correction=True,
        intensity_start_cycle=3, intensity_damping=0.4, intensity_sigma_threshold=1.5,
        enable_powder_repartition=True, powder_start_cycle=2, powder_wavelength=0.71073,
        powder_separation_factor=0.3, powder_map_ratio_mix=0.8,
    )
    handoff = jana_superflip.build_jana_handoff_import(
        handoff_inflip,
        handoff_options,
        {"perform_algorithm": "AAR", "reflection_data_mode": "intensity"},
    )
    expected_handoff_values = {
        "perform_algorithm": "AAR",
        "reflection_data_mode": "intensity",
        "input_source_mode": "External HKL + CIF reference",
        "jana_inflip": str(handoff_inflip.resolve()),
        "work_dir": str((handoff_dir / "phase_studio_full_run_job").resolve()),
        "superflip_exe": str(jana_superflip.DEFAULT_JANA_SUPERFLIP),
        "edma_exe": str(jana_superflip.DEFAULT_JANA_EDMA),
        "cycles": "4", "run_sharped": "true",
        "sharped_base_url": "https://jana.fzu.cz", "sharped_api_token": "secret-token",
        "sharped_model": "default", "sharped_elements": "C N O", "sharped_outres": "0.25",
        "modelfile_source": "deblurred_xplor", "map_export_format": "jana",
        "hkl": str((handoff_dir / "override.hkl").resolve()),
        "compute_omit_maps": "true", "compute_omit_rfree": "true",
        "map_feedback_missing_enabled": "true", "map_feedback_missing_from_cycle": "2",
        "map_feedback_missing_percent_limit": "7.5",
        "map_feedback_intensity_enabled": "true", "map_feedback_intensity_from_cycle": "3",
        "map_feedback_intensity_damping": "0.4",
        "map_feedback_intensity_max_i_over_sigma": "1.5",
        "redistribute_overlaps": "true", "powder_redistribution_from_cycle": "2",
        "powder_wavelength": "0.71073", "powder_separation_factor": "0.3",
        "powder_redistribution_mix": "0.8",
        "first_cycle_modelfile": str((handoff_dir / "seed.xplor").resolve()),
        "reference_cif": str((handoff_dir / "override.cif").resolve()),
        "referencefile_mode": "reference_cif",
    }
    check("Jana handoff exports the exact pinned full-GUI value mapping",
          handoff.values == expected_handoff_values)
    handoff_log = jana_superflip.jana_handoff_log_lines(
        handoff, handoff_inflip, expected_handoff_values,
    )
    check("Jana handoff provenance records exact input, mode, sources and imported count",
          handoff_log[:7] == [
              "[Jana2020] Job received",
              "  Input: job.inflip",
              f"  Working directory: {(handoff_dir / 'phase_studio_full_run_job').resolve()}",
              "  Mode: External HKL + CIF reference",
              f"  Reflections: {(handoff_dir / 'override.hkl').resolve()}",
              f"  Reference: {(handoff_dir / 'override.cif').resolve()}",
              "[Input] 2 compatible .inflip settings imported",
          ])
    check("Jana handoff provenance never exposes the API token",
          all("secret-token" not in line for line in handoff_log))

    # CSV and human report share the same profile and contain every diagnostic.
    report_dir = Path(tempfile.mkdtemp())
    appmod.write_metrics_csv(report_dir / "metrics.csv", jana_results[:1])
    csv_lines = (report_dir / "metrics.csv").read_text(encoding="utf-8").splitlines()
    check("metrics CSV writes one row per cycle/source", len(csv_lines) == 3)
    check("metrics CSV contains all stable quality columns", all(column in csv_lines[0].split(",") for column in appmod.QUALITY_CSV_COLUMNS))
    expected_csv_header = "cycle,source,validation_profile,map_path,structure_path,reference_f05,reference_precision,reference_recall,reference_tp,reference_fp,reference_rmsd,reference_phase_agreement,amplitude_rf,amplitude_cc,amplitude_scale,r_work,r_free,cc_work,cc_free,omit_map_correlation,triplet_c3,entropy_normalized,map_concentration,standardized_peakiness,negative_density_mass,n_measured_reflections,n_work_reflections,n_free_reflections,n_triplets,unavailable_reason,model_source,model_in,model_rmsd_A,superflip_map,superflip_edma_cif,superflip_rmsd_A,deblur_map,deblur_edma_cif,deblur_rmsd_A,superflip_saved_run,superflip_rvalue,superflip_peaks,superflip_symm,superflip_derived_sg,superflip_ref_match,superflip_fom,superflip_success_rate_percent,superflip_mean_cycles,recycle_map_correlation,omit_superflip_correlation,omit_superflip_rfree,omit_deblur_correlation,omit_deblur_rfree,superflip_recall,superflip_precision,superflip_heavy_atom_count,deblur_recall,deblur_precision,deblur_heavy_atom_count,powder_repartition_avg_change_percent,intensity_correction_avg_change_percent"
    check("metrics CSV schema and column order match the pinned 1.0.9 contract",
          csv_lines[0] == expected_csv_header)
    with (report_dir / "metrics.csv").open(encoding="utf-8", newline="") as csv_stream:
        csv_rows = list(csv.DictReader(csv_stream))
    check("metrics CSV representative Superflip values match the golden row",
          {key: csv_rows[0][key] for key in (
              "cycle", "source", "validation_profile", "reference_f05",
              "reference_rmsd", "amplitude_rf", "amplitude_cc", "r_free",
              "cc_free", "n_measured_reflections", "n_work_reflections",
              "n_free_reflections", "model_source", "superflip_rmsd_A",
          )} == {
              "cycle": "1", "source": "superflip",
              "validation_profile": "reference_and_holdout", "reference_f05": "0.61",
              "reference_rmsd": "0.4", "amplitude_rf": "0.25", "amplitude_cc": "0.75",
              "r_free": "0.32", "cc_free": "0.7", "n_measured_reflections": "100",
              "n_work_reflections": "95", "n_free_reflections": "5",
              "model_source": "superflip", "superflip_rmsd_A": "0.4",
          })
    for profile, definition in PROFILE_DEFINITIONS.items():
        jana_results[0].validation_profile = profile.value
        report_path = report_dir / f"{profile.value}.txt"
        appmod.write_map_quality_report(report_path, jana_results[:1])
        report_text = report_path.read_text(encoding="utf-8")
        check(f"{profile.value}: report records assessment", f"Assessment: {definition.assessment_label}" in report_text)
        check(f"{profile.value}: report records all three criteria", all(metric.label in report_text for metric in definition.primary_metrics))
        check(f"{profile.value}: report includes all computed diagnostics", "All computed metrics:" in report_text and "amplitude_rf:" in report_text)
        if profile is ValidationProfile.REFERENCE_AND_HOLDOUT:
            check("map-quality report representative candidate rows match the golden content",
                  "1 | Superflip | 0.61 | 0.32 | 0.65" in report_text and
                  "1 | SharpED | 0.71 | 0.27 | 0.72" in report_text)

    # A graceful stop with valid results also auto-opens in Jana context.
    opened.clear()
    stopped, stopped_results = build_window(appmod, launch_mode="phase_recycling")
    stopped.results = stopped_results[:2]
    stopped._set_run_status("Running")
    stopped._jana_auto_selector_shown = False
    stopped._finish_stopped_run(2)
    app.processEvents()
    check("graceful stop: selector opens automatically", len(opened) == 1)

    # Exercise the two lightweight Jana wrapper workflows through their real
    # orchestration, replacing only the external Superflip/SharpED processes.
    # This pins the original .inflip restoration and the exact final-map path
    # passed to Jana without depending on a network token or test installation.
    wrapper_dir = Path(tempfile.mkdtemp())
    wrapper_bin = wrapper_dir / "bin"
    (wrapper_bin / "deblurrer").mkdir(parents=True)
    wrapper_exe = wrapper_bin / "superflip_original.exe"
    wrapper_exe.write_bytes(b"test executable")
    wrapper_inflip = wrapper_dir / "wrapper-job.inflip"
    wrapper_text = (
        "title Jana context guard\n"
        "outputfile wrapper-job.m81 wrapper-job.m80\n"
        "cell 10 10 10 90 90 90\n"
        "spacegroup P1\n"
        "# Keywords for charge flipping\n"
        "perform CF\n"
        "fbegin\n0 0 1 10 1\nfend\n"
    )
    wrapper_inflip.write_text(wrapper_text, encoding="utf-8")
    wrapper_calls = []
    deblur_calls = []
    original_cwd = Path.cwd()
    original_application_dir = jana_superflip.application_dir
    original_resolve = jana_superflip.resolve_original_superflip
    original_run_process = jana_superflip.run_process
    original_deblur = jana_superflip.deblur_with_sharped

    def fake_wrapper_process(cmd, cwd, log):
        wrapper_calls.append((tuple(map(str, cmd)), Path(cwd)))
        if len(wrapper_calls) == 1:
            (wrapper_dir / "wrapper-job.xplor").write_bytes(b"scientific superflip map")
        return 0

    def fake_wrapper_deblur(input_map, output_map, options, log):
        deblur_calls.append((Path(input_map), Path(output_map)))
        Path(output_map).write_bytes(b"scientific sharped map")

    try:
        os.chdir(wrapper_dir)
        jana_superflip.application_dir = lambda: wrapper_bin
        jana_superflip.resolve_original_superflip = lambda _directory: wrapper_exe
        jana_superflip.run_process = fake_wrapper_process
        jana_superflip.deblur_with_sharped = fake_wrapper_deblur

        wrapper_calls.clear()
        superflip_only = jana_superflip.JanaRunOptions(
            action="run", next_cycle_modelfile="none",
        )
        code = jana_superflip.run_jana_superflip(
            [wrapper_inflip.name], superflip_only, lambda _line: None,
        )
        check("Superflip only: wrapper returns the original Superflip exit code", code == 0)
        check("Superflip only: original Jana .inflip is passed exactly once",
              len(wrapper_calls) == 1 and wrapper_calls[0][0] == (str(wrapper_exe), wrapper_inflip.name))
        check("Superflip only: original Jana working directory is preserved",
              wrapper_calls[0][1] == wrapper_dir)
        check("Superflip only: original .inflip content remains byte-identical",
              wrapper_inflip.read_text(encoding="utf-8") == wrapper_text)
        check("Superflip only: no SharpED or second handoff recomputation occurs",
              deblur_calls == [] and len(wrapper_calls) == 1)

        wrapper_calls.clear()
        deblur_calls.clear()
        sharped_single = jana_superflip.JanaRunOptions(
            action="run", next_cycle_modelfile="deblurred_xplor",
            api_token="test-token", server_url="https://example.invalid",
        )
        code = jana_superflip.run_jana_superflip(
            [wrapper_inflip.name], sharped_single, lambda _line: None,
        )
        calc_m80 = wrapper_bin / "deblurrer" / "calc_m80.inflip"
        calc_text = calc_m80.read_text(encoding="utf-8")
        check("Superflip + SharpED: wrapper completes one scientific and one final Jana call",
              code == 0 and len(wrapper_calls) == 2)
        check("Superflip + SharpED: SharpED consumes the current Superflip map once",
              deblur_calls == [(wrapper_dir / "wrapper-job.xplor", wrapper_dir / "wrapper-job-deb.xplor")])
        check("Superflip + SharpED: final Jana handoff uses the actual SharpED map",
              'modelfile "wrapper-job-deb.xplor"' in calc_text
              and (wrapper_dir / "wrapper-job-deb.xplor").read_bytes() == b"scientific sharped map")
        check("Superflip + SharpED: final Jana command uses calc_m80 in the original context",
              wrapper_calls[1] == ((str(wrapper_exe), str(calc_m80)), wrapper_dir))
        check("Superflip + SharpED: original .inflip content is restored byte-for-byte",
              wrapper_inflip.read_text(encoding="utf-8") == wrapper_text)
        check("Superflip + SharpED: calc_m80 preserves the original Jana header",
              "title Jana context guard" in calc_text and "cell 10 10 10 90 90 90" in calc_text)
    finally:
        os.chdir(original_cwd)
        jana_superflip.application_dir = original_application_dir
        jana_superflip.resolve_original_superflip = original_resolve
        jana_superflip.run_process = original_run_process
        jana_superflip.deblur_with_sharped = original_deblur

    # Run the GUI selector through the real filesystem handoff. The external
    # Superflip invocation is captured, while copying and calc_m80 generation
    # remain production code. This covers Phase recycling, Full configuration,
    # graceful stop, and an explicit non-recommended candidate override.
    original_run_command = appmod.run_command
    original_handoff_thread = appmod.threading.Thread
    gui_handoff_calls = []

    def fake_run_command(cmd, cwd, **kwargs):
        gui_handoff_calls.append((tuple(map(str, cmd)), Path(cwd), kwargs))
        return 0

    def configure_real_handoff(window, results):
        inflip_path = Path(window.last_run_config.jana_inflip)
        inflip_path.write_text(wrapper_text.replace("wrapper-job", "job"), encoding="utf-8")
        executable = inflip_path.parent / "jana-bin" / "superflip_original.exe"
        (executable.parent / "deblurrer").mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test executable")
        window.last_run_config.superflip_exe = str(executable)
        preview = inflip_path.parent / "preview-only.xplor"
        preview.write_bytes(b"preview data must never be handed off")
        return inflip_path, executable, preview

    def accept_candidate(predicate):
        """Switch to whichever source tab actually holds the matching
        candidate, then select it there -- mirroring how a user would
        operate the split dialog (switch tab, then pick a row) and
        confirming the final action uses whatever is active at click time."""
        def execute(dialog):
            for source, view in dialog._views.items():
                match = next((c for c in view.ordered if predicate(c)), None)
                if match is None:
                    continue
                button = dialog._superflip_btn if source == "superflip" else dialog._sharped_btn
                if button is not None:
                    button.setChecked(True)
                else:
                    dialog._apply_source(source)
                view.table.selectRow(view.ordered.index(match))
                app.processEvents()
                break
            return QDialog.Accepted
        return execute

    gui_windows = []
    try:
        appmod.run_command = fake_run_command
        appmod.threading.Thread = ImmediateThread

        # Phase recycling: accept the automatic recommendation after successful
        # completion and verify the selected cycle/source's canonical files.
        recycling, recycling_results = build_window(appmod, launch_mode="phase_recycling")
        gui_windows.append(recycling)
        recycling.results = recycling_results
        recycling_inflip, recycling_exe, recycling_preview = configure_real_handoff(recycling, recycling_results)
        gui_handoff_calls.clear()
        QDialog.exec = lambda _dialog: QDialog.Accepted
        recycling.open_result_selector("jana")
        recycling_choice = recycling.result_recommendation.selected_candidate
        recycling_target = recycling_inflip.parent / "job-deb.xplor"
        check("phase recycling: recommended completed candidate is cycle 3 SharpED",
              recycling_choice is not None and recycling_choice.cycle == 3 and recycling_choice.source == "deblurred")
        check("phase recycling: selected scientific map bytes reach Jana, never preview bytes",
              recycling_target.read_bytes() == Path(recycling_choice.map_path).read_bytes()
              and recycling_target.read_bytes() != recycling_preview.read_bytes())
        check("phase recycling: matching SharpED CIF remains attached to the selected result",
              Path(recycling_choice.structure_path) == Path(recycling_results[2].deblur_edma_cif))
        check("phase recycling: handoff invokes Jana exactly once in original .inflip directory",
              len(gui_handoff_calls) == 1
              and gui_handoff_calls[0][0] == (str(recycling_exe), str(recycling_exe.parent / "deblurrer" / "calc_m80.inflip"))
              and gui_handoff_calls[0][1] == recycling_inflip.parent)

        # Full configuration starts idle. A manually completed run auto-opens
        # the shared selector; the Pass button opens that same component again.
        full, full_results = build_window(appmod, launch_mode="full_configuration")
        gui_windows.append(full)
        full_inflip, _full_exe, _full_preview = configure_real_handoff(full, full_results)
        check("full configuration: opening from Jana does not start a run",
              full._run_status == "READY" and full.results == [])
        opened.clear()
        QDialog.exec = reject_dialog
        run_to_completion(full, full_results, app)
        check("full configuration: manual completion auto-opens Result Selection once",
              len(opened) == 1 and opened[0].property("resultContext") == "JANA2020")
        opened.clear()
        QDialog.exec = reject_dialog
        full._on_jana_action_clicked()
        check("full configuration: Pass to Jana2020 reopens the same Result Selection",
              len(opened) == 1 and opened[0].property("resultContext") == "JANA2020")
        check("full configuration: original Jana context remains the active run context",
              Path(full.last_run_config.jana_inflip) == full_inflip)
        gui_handoff_calls.clear()
        QDialog.exec = lambda _dialog: QDialog.Accepted
        full._on_jana_action_clicked()
        full_choice = full.result_recommendation.selected_candidate
        check("full configuration: recommended cycle 3 SharpED result is handed off",
              full_choice is not None and full_choice.cycle == 3 and full_choice.source == "deblurred"
              and (full_inflip.parent / "job-deb.xplor").read_bytes() == Path(full_choice.map_path).read_bytes())
        check("full configuration: accepted selector invokes one handoff only",
              len(gui_handoff_calls) == 1)

        # Graceful stop retains the last completed result and can hand it off.
        stopped_choice_window, stopped_choice_results = build_window(appmod, launch_mode="phase_recycling")
        gui_windows.append(stopped_choice_window)
        stopped_inflip, _stopped_exe, _stopped_preview = configure_real_handoff(stopped_choice_window, stopped_choice_results)
        stopped_choice_window.results = stopped_choice_results[:2]
        stopped_choice_window._set_run_status("Running")
        opened.clear()
        QDialog.exec = reject_dialog
        stopped_choice_window._finish_stopped_run(2)
        app.processEvents()
        check("graceful stop: completed result remains handoff-capable",
              stopped_choice_window._run_status == "STOPPED"
              and stopped_choice_window.jana_action_btn.isEnabled() and len(opened) == 1)
        gui_handoff_calls.clear()
        QDialog.exec = lambda _dialog: QDialog.Accepted
        stopped_choice_window._on_jana_action_clicked()
        stopped_choice = stopped_choice_window.result_recommendation.selected_candidate
        check("graceful stop: best completed cycle 2 SharpED map is handed off",
              stopped_choice is not None and stopped_choice.cycle == 2 and stopped_choice.source == "deblurred"
              and (stopped_inflip.parent / "job-deb.xplor").read_bytes() == Path(stopped_choice.map_path).read_bytes()
              and len(gui_handoff_calls) == 1)

        # Manual override selects an existing non-recommended Superflip result.
        override, override_results = build_window(appmod, launch_mode="full_configuration")
        gui_windows.append(override)
        override.results = override_results
        override_inflip, _override_exe, override_preview = configure_real_handoff(override, override_results)
        gui_handoff_calls.clear()
        QDialog.exec = accept_candidate(lambda candidate: candidate.cycle == 1 and candidate.source == "superflip")
        override.open_result_selector("jana")
        override_choice = override.result_recommendation.selected_candidate
        override_target = override_inflip.parent / "job-phase-studio-superflip-cycle_001.xplor"
        check("manual override: requested cycle 1 Superflip candidate replaces recommendation",
              override_choice is not None and override_choice.cycle == 1 and override_choice.source == "superflip")
        check("manual override: exact Superflip map and matching CIF stay paired",
              override_target.read_bytes() == Path(override_results[0].superflip_map).read_bytes()
              and Path(override_choice.structure_path) == Path(override_results[0].superflip_edma_cif))
        check("manual override: no preview substitution, duplicate handoff, or recomputation",
              override_target.read_bytes() != override_preview.read_bytes() and len(gui_handoff_calls) == 1)
    finally:
        appmod.run_command = original_run_command
        appmod.threading.Thread = original_handoff_thread
        QDialog.exec = reject_dialog

    for window in (win, standalone, map_only, jana, stopped, *gui_windows):
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
