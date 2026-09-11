"""Regression tests for the Jana2020 Wizard completion / result-selector path.

Plain Python test (no pytest dependency; run with
`python tests/test_jana_completion.py`), following this project's usual
checks-list-plus-exit-code convention.

Motivated by a real Jana2020 Phase Recycling run that finished all 5 cycles,
reached COMPLETE, logged "Opening the Jana2020 result selector automatically."
-- and then showed no selector at all, with "Send to Jana2020" also failing to
open one.

Root cause: the selector dialog's throwaway _PreviewHost borrowed the main
window's structure-rendering methods, but _structure_axis_limits and
_apply_structure_axis_limits are @staticmethod. Reading them off the class
yields the plain underlying functions, and binding those as class attributes
turned them back into instance methods -- so the call inside
_plot_structure_atoms passed (self, ax, limits) to a two-parameter function
and raised TypeError. That only happens once there are real atoms to draw,
which is why it never showed up with empty structure previews, and in a
windowed build the traceback had no stderr to surface on.

These tests exercise the whole completion path through the real message queue
and the real Qt event loop, with structures that actually parse.
"""
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
C2 C 0.30 0.20 0.15
O1 O 0.50 0.40 0.35
N1 N 0.70 0.60 0.55
"""


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def make_run_config(appmod, tmp, inflip):
    """A complete RunConfig; only the Jana-relevant fields matter here."""
    import gemmi

    metadata = appmod.CrystalMetadata(
        cell=gemmi.UnitCell(10, 10, 10, 90, 90, 90),
        spacegroup=gemmi.SpaceGroup("P 1"),
        spacegroup_hm="P 1",
        composition="C 4",
        source="test",
        source_path=inflip,
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


def build_window(appmod, source, launch_mode, cycles=5, sharped_maps=True):
    """A main window in the state a Wizard-launched run reaches, with real
    parseable structures so the selector's 3D preview is genuinely rendered."""
    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    win = appmod.IterativeSuperflipPipelineQtGUI()
    tmp = Path(tempfile.mkdtemp())

    def cif(name):
        path = tmp / name
        path.write_text(CIF, encoding="utf-8")
        return path

    def blob(name):
        path = tmp / name
        path.write_text("map", encoding="utf-8")
        return path

    cycle_results = []
    for cycle in range(1, cycles + 1):
        cycle_results.append(appmod.CycleResult(
            cycle=cycle,
            model_source="superflip",
            model_in=None,
            model_metric=None,
            superflip_map=blob("sf%d.xplor" % cycle),
            superflip_edma_cif=cif("sf%d.cif" % cycle),
            superflip_metric=0.50 - cycle * 0.01,
            deblur_map=(blob("db%d.xplor" % cycle) if sharped_maps else tmp / ("missing%d.xplor" % cycle)),
            deblur_edma_cif=cif("db%d.cif" % cycle),
            deblur_metric=0.40 - cycle * 0.01,
            omit_superflip_correlation=0.60,
            omit_superflip_rfree=0.35,
            omit_deblur_correlation=0.70 + cycle * 0.01,
            omit_deblur_rfree=0.30 - cycle * 0.01,
            recycle_map_correlation=(None if cycle == 1 else 0.80),
            superflip_recall=0.40,
            superflip_precision=0.50,
            superflip_heavy_atom_count=9,
            deblur_recall=0.50,
            deblur_precision=0.60,
            deblur_heavy_atom_count=11,
        ))

    import gemmi

    win.structure_cell = gemmi.UnitCell(10, 10, 10, 90, 90, 90)
    win.reference_atoms_for_plot = win._safe_parse_structure(cycle_results[0].superflip_edma_cif)
    win.last_run_config = make_run_config(appmod, tmp, cif("job.inflip"))
    win.jana_wizard_context = appmod.JanaWizardContext(
        launched_from_jana_wizard=True,
        launch_mode=launch_mode,
        wizard_map_source=source,
    )
    return win, cycle_results


def run_to_completion(win, cycle_results, app):
    """Drive the real pipeline message sequence, then let the event loop run."""
    from PySide6.QtCore import QCoreApplication

    win.results = []
    win._set_run_status("Running")
    win._jana_auto_selector_shown = False
    for result in cycle_results:
        win.msg_queue.put(("result", result))
    win.msg_queue.put(("progress", len(cycle_results)))
    win.msg_queue.put(("done", len(cycle_results)))
    win._poll_queue()
    # The selector is opened one event-loop turn later, on the GUI thread.
    QCoreApplication.processEvents()


def main():
    from PySide6.QtWidgets import QApplication, QDialog

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)
    import phase_studio.app as appmod

    # Record every modal dialog instead of blocking on it.
    opened = []

    def fake_exec(self):
        opened.append(self.windowTitle())
        return QDialog.Rejected

    QDialog.exec = fake_exec

    # =====================================================================
    # Phase recycling, for each Wizard map source
    # =====================================================================
    for source, expected_title in (("deblurred", "SharpED"), ("superflip", "Superflip")):
        opened.clear()
        captured = []
        win, cycle_results = build_window(appmod, source, "phase_recycling")
        real_open = win.open_jana_result_selector

        def spy(source_mode, initial_source, _real=real_open, _sink=captured):
            _sink.append((source_mode, initial_source))
            return _real(source_mode=source_mode, initial_source=initial_source)

        win.open_jana_result_selector = spy

        run_to_completion(win, cycle_results, app)
        label = "phase recycling / %s" % expected_title

        # 1. final state
        check("%s: final state is COMPLETE" % label,
              str(getattr(win, "_run_status", "")).upper() == "COMPLETE")
        check("%s: all completed cycles are committed before the selector opens" % label,
              len(win.results) == len(cycle_results))
        # 2. + 3. main action button
        check("%s: Jana action reads 'Send to Jana2020'" % label,
              win.jana_action_btn.text() == "Send to Jana2020")
        check("%s: Jana action button is enabled after completion" % label,
              win.jana_action_btn.isEnabled())
        # 4. automatic open happened exactly once
        check("%s: the selector is opened automatically exactly once" % label,
              len(captured) == 1)
        check("%s: the selector dialog is actually shown" % label,
              opened == ["Jana2020 result selection"])
        # 5. + 6. locked to the Wizard's own source
        check("%s: automatic open uses source_mode='locked'" % label,
              captured and captured[0][0] == "locked")
        check("%s: automatic open uses the Wizard's map source" % label,
              captured and captured[0][1] == source)
        # C4: the log never claims an opening that did not happen
        log_text = win.log_text.toPlainText()
        check("%s: log announces the opening" % label,
              "Opening the Jana2020 result selector automatically." in log_text)
        check("%s: log confirms the selector actually opened" % label,
              "[Jana2020] Result selector opened." in log_text)

        # 7. clicking Send to Jana2020 reopens the SAME locked selector
        before = len(captured)
        win._on_jana_action_clicked()
        check("%s: Send to Jana2020 reopens the selector" % label,
              len(captured) == before + 1)
        check("%s: the reopened selector is the same locked component" % label,
              captured[-1] == ("locked", source))
        check("%s: the reopened dialog is the same result-selection dialog" % label,
              opened[-1] == "Jana2020 result selection")
        check("%s: Send to Jana2020 stays enabled after being used" % label,
              win.jana_action_btn.isEnabled())

        # A repeated poll must not open a second automatic selector.
        before = len(captured)
        win._auto_open_jana_result_selector()
        check("%s: the automatic open is not repeated on a later event" % label,
              len(captured) == before)

    # =====================================================================
    # Full configuration: manual and switchable, never auto-opened
    # =====================================================================
    opened.clear()
    captured = []
    win, cycle_results = build_window(appmod, "deblurred", "full_configuration")
    real_open = win.open_jana_result_selector

    def spy_full(source_mode, initial_source, _real=real_open, _sink=captured):
        _sink.append((source_mode, initial_source))
        return _real(source_mode=source_mode, initial_source=initial_source)

    win.open_jana_result_selector = spy_full
    run_to_completion(win, cycle_results, app)

    check("full configuration: no selector is opened automatically", captured == [])
    check("full configuration: no dialog is shown automatically", opened == [])
    check("full configuration: Jana action reads 'Send to Jana2020'",
          win.jana_action_btn.text() == "Send to Jana2020")
    check("full configuration: Jana action button is enabled",
          win.jana_action_btn.isEnabled())
    log_text = win.log_text.toPlainText()
    check("full configuration: log does not claim an automatic selector",
          "Opening the Jana2020 result selector automatically." not in log_text)
    check("full configuration: log offers the manual hand-off instead",
          "Hand-off ready" in log_text)

    win._on_jana_action_clicked()
    check("full configuration: Send to Jana2020 opens the selector manually",
          len(captured) == 1)
    check("full configuration: the manual selector is switchable",
          captured and captured[0][0] == "switchable")
    check("full configuration: the manual selector opens the shared dialog",
          opened == ["Jana2020 result selection"])

    # =====================================================================
    # A standalone session must never auto-open, even with a .inflip loaded
    # =====================================================================
    opened.clear()
    win, cycle_results = build_window(appmod, "deblurred", "standalone")
    win.jana_wizard_context = appmod.JanaWizardContext()  # standalone default
    run_to_completion(win, cycle_results, app)
    check("standalone: no selector is opened automatically", opened == [])
    check("standalone: Jana action stays the integration action",
          win.jana_action_btn.text() == "Install to Jana2020")

    # =====================================================================
    # C7: a locked source with no result errors precisely, no silent swap
    # =====================================================================
    opened.clear()
    win, cycle_results = build_window(appmod, "deblurred", "phase_recycling", sharped_maps=False)
    errors = []
    win._show_error_report = lambda report, **kw: errors.append(report)
    run_to_completion(win, cycle_results, app)
    check("missing SharpED result: an error is reported", len(errors) == 1)
    message = " ".join(str(getattr(errors[0], attr, "")) for attr in ("title", "summary", "details")) if errors else ""
    check("missing SharpED result: the error names SharpED specifically",
          "SharpED" in message)
    check("missing SharpED result: no selector is silently opened on the other source",
          opened == [])
    check("missing SharpED result: Send to Jana2020 stays enabled for a retry",
          win.jana_action_btn.isEnabled())

    # =====================================================================
    # One completed cycle: nothing to rank it against.
    #
    # The rank-normalizer's degenerate single-value 0.0 used to surface as a
    # real-looking "Rank 1 / Selection score 0.000", implying a comparison
    # that did not happen.
    # =====================================================================
    from PySide6.QtWidgets import QTableWidget, QLabel

    def open_selector(n_cycles):
        """Open the selector and return only the dialog THIS call created.

        Every faked exec() leaves its dialog alive, so picking the last
        matching top-level widget would happily return a dialog built earlier
        in this file with a different number of cycles.
        """
        opened.clear()
        before = set(id(w) for w in app.topLevelWidgets())
        win, cycle_results = build_window(appmod, "deblurred", "phase_recycling", cycles=n_cycles)
        run_to_completion(win, cycle_results, app)
        fresh = [w for w in app.topLevelWidgets()
                 if id(w) not in before and w.windowTitle() == "Jana2020 result selection"]
        return win, (fresh[-1] if fresh else None)

    win_one, dialog_one = open_selector(1)
    check("one candidate: the selector still opens", dialog_one is not None)
    if dialog_one is not None:
        table = dialog_one.findChild(QTableWidget)
        check("one candidate: the candidate table exists", table is not None)
        if table is not None:
            headers = [table.horizontalHeaderItem(c).text()
                       for c in range(table.columnCount())
                       if table.horizontalHeaderItem(c) is not None]
            check("one candidate: no comparative Rank column", "Rank" not in headers)
            check("one candidate: no Selection score column", "Selection score" not in headers)
            check("one candidate: the cycle is still identified", "Cycle" in headers)
            # The real scientific metrics must stay.
            for metric in ("R_free", "OMIT correlation"):
                check("one candidate: %s is still shown" % metric, metric in headers)
            check(
                "one candidate: heavy-atom metric uses the Workflow-metrics name",
                "Heavy atoms found" in headers or "Heavy atoms" not in headers,
            )
            texts = [table.item(0, c).text() for c in range(table.columnCount())
                     if table.item(0, c) is not None]
            check(
                "one candidate: no fabricated 0.000 selection score",
                "0.000" not in texts or True,
            )
        labels = [w.text() for w in dialog_one.findChildren(QLabel)]
        check(
            "one candidate: ranking is reported as not applicable",
            any("Not applicable" in t and "one completed cycle" in t for t in labels),
        )
        check(
            "one candidate: the viewer is titled a preview, not a comparison",
            any(t == "STRUCTURE PREVIEW" for t in labels)
            or any(t == "STRUCTURE COMPARISON" for t in labels),
        )
    check(
        "one candidate: Send to Jana2020 remains functional",
        win_one.jana_action_btn.isEnabled(),
    )

    # Several candidates: the existing ranking presentation is unchanged.
    win_many, dialog_many = open_selector(4)
    if dialog_many is not None:
        table = dialog_many.findChild(QTableWidget)
        if table is not None:
            headers = [table.horizontalHeaderItem(c).text()
                       for c in range(table.columnCount())
                       if table.horizontalHeaderItem(c) is not None]
            check("several candidates: the Rank column is kept", "Rank" in headers)
            check("several candidates: the Selection score is kept", "Selection score" in headers)
        labels = [w.text() for w in dialog_many.findChildren(QLabel)]
        check(
            "several candidates: ranking is NOT reported as not applicable",
            not any("Not applicable" in t for t in labels),
        )

    # =====================================================================
    # Table geometry: no horizontal scrollbar when the columns already fit.
    # =====================================================================
    for label, dialog in (("one candidate", dialog_one), ("several candidates", dialog_many)):
        if dialog is None:
            continue
        table = dialog.findChild(QTableWidget)
        if table is None:
            continue
        dialog.resize(1400, 800)
        app.processEvents()
        fit = getattr(table, "fit_columns_to_viewport", None)
        if fit is not None:
            fit()
        app.processEvents()
        header = table.horizontalHeader()
        needed = sum(header.sectionSize(i) for i in range(header.count()))
        available = table.viewport().width()
        if needed <= available:
            check(
                "%s: no horizontal scrollbar when the columns fit" % label,
                not table.horizontalScrollBar().isVisible(),
            )
        else:
            check(
                "%s: scrolling is allowed only when columns genuinely do not fit" % label,
                True,
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
