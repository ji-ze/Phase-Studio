"""Regression tests for the Autosolve launch-path fix (Phase Studio 2.0.0):

Autosolve must open its own dedicated, simplified AutosolveWindow and must
NEVER show the full multi-tab IterativeSuperflipPipelineQtGUI. Professional
mode must do the exact opposite. Advanced and Original Superflip keep their
established, unrelated routes.

Plain Python test (no pytest dependency); run with
`python tests/test_autosolve_window_routing.py`.
"""
import inspect
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)
    import phase_studio.app as appmod
    import phase_studio.jana_superflip as js
    from phase_studio.autosolve_window import AutosolveWindow

    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.start_run = lambda self: self._set_run_status("RUNNING")
    QApplication.exec = lambda self: 0

    tmp = Path(tempfile.mkdtemp())
    inflip = tmp / "job.inflip"
    inflip.write_text("title autosolve routing fixture\n", encoding="utf-8")
    jana_root = tmp / "Jana Active"
    scientific_dir = jana_root / "SUPERFLIP"
    scientific_dir.mkdir(parents=True)
    (scientific_dir / "superflip.exe").write_bytes(b"active scientific Superflip")
    (scientific_dir / "EDMA.exe").write_bytes(b"active EDMA")
    js.application_dir = lambda: jana_root

    def track_shown():
        shown = {"autosolve": False, "full_gui": False}
        created = []
        orig_autosolve_show = AutosolveWindow.show
        orig_show = appmod.IterativeSuperflipPipelineQtGUI.show

        def fake_autosolve_show(self):
            shown["autosolve"] = True
            created.append(self)
            # The backend is a real (hidden) QMainWindow with its own 50ms
            # QTimer; it never goes through .show() so it must be tracked
            # here explicitly to be cleaned up too.
            created.append(self.backend)
            return orig_autosolve_show(self)

        def fake_show(self):
            shown["full_gui"] = True
            created.append(self)
            return orig_show(self)

        AutosolveWindow.show = fake_autosolve_show
        appmod.IterativeSuperflipPipelineQtGUI.show = fake_show

        def restore():
            # Close/delete every window this launch created before the next
            # iteration constructs another one -- otherwise a stale QTimer
            # (this test's QApplication.exec() stub never runs a real event
            # loop to let Qt settle) can fire against an already-collected
            # C++ object on a later app.processEvents() call.
            AutosolveWindow.show = orig_autosolve_show
            appmod.IterativeSuperflipPipelineQtGUI.show = orig_show
            for window in created:
                window.close()
                window.deleteLater()
            app.processEvents()

        return shown, restore

    successful_start = appmod.IterativeSuperflipPipelineQtGUI.start_run
    appmod.IterativeSuperflipPipelineQtGUI.start_run = lambda self: None
    shown, restore = track_shown()
    try:
        code = js.launch_autosolve_from_jana(inflip, js.JanaRunOptions(action="autosolve", autosolve_option="A"))
        check("failed preflight never creates an Autosolve execution window", code == 1 and not shown["autosolve"])
        check("failed preflight never exposes the hidden backend", not shown["full_gui"])
    finally:
        restore()
        appmod.IterativeSuperflipPipelineQtGUI.start_run = successful_start

    # =====================================================================
    # Item 25: Autosolve (Option A and Option B) must show AutosolveWindow
    # and must NEVER show the full GUI.
    # =====================================================================
    for option in ("A", "B"):
        shown, restore = track_shown()
        try:
            options = js.JanaRunOptions(action="autosolve", autosolve_option=option)
            code = js.launch_autosolve_from_jana(inflip, options)
            check(f"Autosolve Option {option}: launch returns success", code == 0)
            check(f"Autosolve Option {option}: AutosolveWindow is shown", shown["autosolve"])
            check(f"Autosolve Option {option}: the full Phase Studio GUI is NEVER shown", not shown["full_gui"])
        finally:
            restore()

    # =====================================================================
    # Item 26: Professional mode ("Open full configuration" / action="edit")
    # must show the full GUI and must NEVER show AutosolveWindow.
    # =====================================================================
    shown, restore = track_shown()
    try:
        options = js.JanaRunOptions(action="edit")
        code = js.launch_phase_studio_from_jana(inflip, options)
        check("Professional mode: launch returns success", code == 0)
        check("Professional mode: the full Phase Studio GUI is shown", shown["full_gui"])
        check("Professional mode: AutosolveWindow is NEVER shown", not shown["autosolve"])
    finally:
        restore()

    # =====================================================================
    # Item 27/28: Advanced (Superflip + SharpED / Phase recycling) and
    # Original Superflip keep their established, already-tested routes --
    # confirmed statically here (their runtime behavior is already covered
    # by test_jana_completion.py / test_wizard_geometry.py / test_jana_
    # wizard_hierarchy.py); this only guards against a routing regression
    # that silently redirects them into launch_autosolve_from_jana.
    # =====================================================================
    main_source = inspect.getsource(js.main)
    check(
        "main(): 'recycle' (Advanced -> Phase recycling) still calls launch_phase_studio_from_jana",
        '"recycle"' in main_source and "auto_start=True, diagnostic_log=logger" in main_source,
    )
    check(
        "main(): 'edit' (Professional mode) still calls launch_phase_studio_from_jana",
        '"edit"' in main_source and "inflip_path, options, diagnostic_log=logger" in main_source,
    )
    check(
        "main(): 'autosolve' calls launch_autosolve_from_jana, not launch_phase_studio_from_jana",
        '"autosolve"' in main_source and "launch_autosolve_from_jana(" in main_source
        and "inflip_path, options, diagnostic_log=logger" in main_source,
    )
    check(
        "main(): Original Superflip / Superflip + SharpED ('run') still fall through to run_jana_superflip",
        "run_jana_superflip(args, options, logger)" in main_source,
    )

    # =====================================================================
    # Effective Autosolve EDMA thresholds (2.0.1 correction pass): BOTH
    # sides of the shared phase search default to 1.0 sigma (Observed-data/
    # Superflip lowered from 1.20 in the initial 2.0.1 pass; SharpED further
    # lowered from 2.00 in this correction pass). plimit_superflip/
    # plimit_deblur are fixed RunConfig fields read identically for every
    # cycle (cycle 1, cycle 2+, and every adaptive extension) -- not
    # something that varies per cycle -- so confirming the widget value
    # Autosolve actually configures covers all of them.
    # =====================================================================
    captured_backends = []
    captured_inflips = []
    orig_autosolve_init = AutosolveWindow.__init__

    def capturing_init(self, backend, option, *args, **kwargs):
        captured_backends.append(backend)
        captured_inflips.append(kwargs.get("inflip_path"))
        orig_autosolve_init(self, backend, option, *args, **kwargs)

    AutosolveWindow.__init__ = capturing_init
    shown, restore = track_shown()
    try:
        options = js.JanaRunOptions(action="autosolve", autosolve_option="A")
        js.launch_autosolve_from_jana(inflip, options)
        backend = captured_backends[-1]
        check(
            "Autosolve: effective Observed-data (Superflip) EDMA threshold is 1.0 sigma",
            abs(backend._dspin_value("plimit_superflip") - 1.00) < 1e-9,
        )
        check(
            "Autosolve: effective SharpED EDMA threshold is 1.0 sigma (lowered from 2.00)",
            abs(backend._dspin_value("plimit_deblur") - 1.00) < 1e-9,
        )
        check(
            "Autosolve: the window is given the ACTIVE job's .inflip (shown as its input line)",
            captured_inflips and Path(captured_inflips[-1]) == Path(inflip),
        )
    finally:
        restore()
        AutosolveWindow.__init__ = orig_autosolve_init

    # =====================================================================
    # Routing decision (2.0.0, intentional): BOTH Autosolve and the Advanced
    # "Phase recycling with Superflip + SharpED" card run the ORDINARY
    # per-cycle loop (_run_pipeline_cycles, reconstruction_mode
    # "superflip"). Autosolve picks the continuation map automatically;
    # Advanced lets the user pick it. The specialized "sharped_recycle"
    # mechanism stays Professional-only. Checked behaviorally on the
    # backend each launch actually starts.
    # =====================================================================
    started = []
    appmod.IterativeSuperflipPipelineQtGUI.start_run = lambda self: (started.append(self), self._set_run_status("RUNNING"))
    import phase_studio.autosolve_review as js_guided

    def started_mode(window):
        # Exactly the two expressions get_config() uses for these RunConfig
        # fields (the minimal fixture .inflip has no cell, so the full
        # config cannot be resolved here).
        return (
            appmod.normalize_reconstruction_mode(window._combo_value("reconstruction_mode")),
            appmod.normalize_modelfile_source(window._combo_value("modelfile_source")),
        )

    for map_choice, expected_tab in (("superflip_xplor", "superflip"), ("deblurred_xplor", "deblurred")):
        shown, restore = track_shown()
        started.clear()
        try:
            options = js.JanaRunOptions(
                action="recycle", cycles=4, next_cycle_modelfile=map_choice,
                use_deblurred_map=expected_tab == "deblurred",
            )
            js.launch_phase_studio_from_jana(inflip, options, auto_start=True)
            check(f"Advanced phase recycling ({map_choice}): a run is started", len(started) == 1)
            check(
                f"Advanced phase recycling ({map_choice}): Execution is shown without displaying Professional mode",
                shown["autosolve"] and not shown["full_gui"],
            )
            if started:
                mode, model_source = started_mode(started[0])
                check(f"Advanced phase recycling ({map_choice}): ordinary loop (reconstruction_mode superflip), never sharped_recycle",
                      mode == "superflip")
                check(f"Advanced phase recycling ({map_choice}): the next cycle is initialized from the SharpED map (unchanged science)",
                      model_source == "deblurred_xplor")
                check(f"Advanced phase recycling ({map_choice}): the handoff-map choice sets Result Selection's starting tab",
                      started[0]._initial_result_source(None, True, True) == expected_tab)
        finally:
            restore()

    for option in ("A", "B"):
        shown, restore = track_shown()
        started.clear()
        try:
            js.launch_autosolve_from_jana(inflip, js.JanaRunOptions(action="autosolve", autosolve_option=option))
            check(f"Autosolve Option {option}: a run is started", len(started) == 1)
            if started:
                mode, model_source = started_mode(started[0])
                check(f"Autosolve Option {option}: ordinary loop (reconstruction_mode superflip), never sharped_recycle",
                      mode == "superflip")
                check(f"Autosolve Option {option}: shared search feeds the SharpED map's EDMA STRUCTURE forward "
                      "(deblurred_edma_cif), not the raw map",
                      model_source == "deblurred_edma_cif")
                check(f"Autosolve Option {option}: shared search uses SharpED '{js_guided.PHASE_SEARCH_MODEL}'",
                      started[0]._combo_value("sharped_model") == js_guided.PHASE_SEARCH_MODEL)
        finally:
            restore()
    appmod.IterativeSuperflipPipelineQtGUI.start_run = lambda self: self._set_run_status("RUNNING")

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
