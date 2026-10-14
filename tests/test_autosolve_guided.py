"""Phase Studio 2.0.1 guided Autosolve: shared phase search, first Predicted
structure, initial Predicted-model tuning, model-seeded five-cycle
refinement, Final Review, strict-improvement extension, handoff and
measured-data correction.

What is REAL here (only the external programs are faked):

  * the ordinary cycle loop (_run_pipeline_cycles) and Superflip input
    writer (run_superflip_cycle -> write_superflip_input), so every
    generated ``.inflip`` and ``current_modelfile.cif`` is inspected;
  * the EDMA input writer (run_edma_on_xplor): the generated ``.inp`` with
    its absolute ``plimit`` is read by the fake EDMA process, which recovers
    the sigma multiplier from the map it was given;
  * the SharpED client (run_sharped_deblur -> SharpEDServerClient.execute):
    the fake server transport reads the model field of every multipart
    upload request actually sent.

Fakes: Superflip writes an XPLOR map (sigma 2.0); the SharpED server returns
an XPLOR map (sigma 4.0); EDMA writes peaks whose coordinates encode the map
they came from (x = 0.01*cycle, +0.5 for a SharpED map), whose count falls
as the threshold rises (count = 10*(3.2 - sigma)); map assessment returns
scripted amplitude R values (the reference-free profile's primary metric).

Plain Python test (no pytest dependency); run with
`python tests/test_autosolve_guided.py`.
"""
import json
import os
import queue
import re
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

results_log = []

PHASE_BOOST = "koala phase boost 2"
PROGRESSIVE = "koala model progressive"
SUPERFLIP_SIGMA = 2.0
SHARPED_SIGMA = 4.0


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def peaks_for(multiplier):
    return max(1, int(round(10 * (3.2 - float(multiplier)))))


def map_kind(name):
    name = Path(name).name
    if name.startswith("prediction"):
        return "pred"
    return "sf" if "superflip" in name else "db"


def map_cycle(name):
    match = re.search(r"cycle_(\d+)", Path(name).name)
    return int(match.group(1)) if match else 0


class Fakes:
    """External programs only: Superflip process, EDMA process, SharpED server."""

    def __init__(self):
        from phase_studio.xplor_io import XplorMap

        self.XplorMap = XplorMap
        self.superflip_inputs = []      # generated .inflip paths
        self.edma = []                  # dicts: map, kind, cycle, multiplier, plimit, inp
        self.requests = []              # (uploaded file name, model) from the multipart body
        self.scores = {}                # (kind, cycle) -> amplitude_rf (None = unavailable)
        self.fail_model = ""
        self.fail_edma = False
        self._tokens = 0

    def xplor_text(self, sigma, title):
        from phase_studio.xplor_io import write_xplor_map

        base = np.arange(64, dtype=np.float64) - 31.5
        data = base / base.std() * float(sigma)
        path = Path(tempfile.mkdtemp()) / "m.xplor"
        write_xplor_map(path, self.XplorMap(title, (4, 0, 3, 4, 0, 3, 4, 0, 3), (10, 10, 10, 90, 90, 90), "ZYX", data))
        return path.read_bytes()

    # --- processes (run_command) --------------------------------------------
    def run_command(self, cmd, cwd=None, log_path=None, log=None, stop_event=None, **_kwargs):
        exe = Path(str(cmd[0])).name.lower()
        cwd = Path(cwd)
        inp = cwd / cmd[1]
        if exe == "superflip.exe":
            self.superflip_inputs.append(inp)
            (cwd / f"{inp.stem}.xplor").write_bytes(self.xplor_text(SUPERFLIP_SIGMA, inp.stem))
            if log_path is not None:
                Path(log_path).write_text("superflip ok\n", encoding="utf-8")
            return
        if exe == "edma.exe":
            import phase_studio.app as appmod

            if self.fail_edma:
                raise RuntimeError("EDMA failed (test)")
            text = inp.read_text(encoding="utf-8")
            keys = {line.split()[0]: line.split(None, 1)[1] for line in text.splitlines() if len(line.split()) > 1}
            map_name = keys["inputfile"]
            plimit = float(keys["plimit"])
            _mean, sigma = appmod.xplor_tail_mean_sigma(cwd / map_name)
            multiplier = round(plimit / float(sigma), 3)
            kind, cycle = map_kind(map_name), map_cycle(map_name)
            self.edma.append(dict(map=map_name, kind=kind, cycle=cycle, multiplier=multiplier, plimit=plimit, inp=text))
            offset = 0.0 if kind == "sf" else 0.5
            rows = [
                (
                    f"{offset + 0.01 * cycle:.4f} {0.03 * i:.4f} 0.5000 "
                    f"{offset + 0.01 * cycle:.4f} {0.03 * i:.4f} 0.5000 "
                    f"1.000 2.920000 {100.0 - i:.3f}"
                )
                for i in range(peaks_for(multiplier))
            ]
            (cwd / f"{keys['outputbase']}.coo").write_text("\n".join(rows) + "\n", encoding="utf-8")
            if log_path is not None:
                Path(log_path).write_text("EDMA ok\n", encoding="utf-8")
            return
        raise AssertionError(f"unexpected external command {cmd}")

    # --- SharpED server transport (SharpEDServerClient._request_bytes) -------
    def transport(self, client, method, url, data=None, headers=None):
        if method == "POST":
            body = bytes(data or b"")
            model = re.search(rb'name="model"\r\n\r\n(.*?)\r\n', body, re.S).group(1).decode("utf-8")
            filename = re.search(rb'filename="([^"]+)"', body).group(1).decode("utf-8")
            if self.fail_model and model == self.fail_model:
                raise RuntimeError("SharpED server unavailable (test)")
            self.requests.append((filename, model))
            self._tokens += 1
            token = f"job{self._tokens}"
            return json.dumps({"success": True, "job_id": self._tokens, "token": token,
                               "status_url": "/api/user/sharp-ed/status/" + token}).encode()
        if "/status/" in url:
            token = url.rsplit("/", 1)[1]
            return json.dumps({"status": "completed", "download_url": "/api/user/sharp-ed/download/" + token}).encode()
        if "/download/" in url:
            return self.xplor_text(SHARPED_SIGMA, "sharped")
        raise AssertionError(url)

    def assess(self, map_path, _context, *_args, **_kwargs):
        from phase_studio.map_quality import MapQualityMetrics

        key = (map_kind(map_path), map_cycle(map_path))
        return MapQualityMetrics(amplitude_rf=self.scores.get(key, 0.50), amplitude_cc=0.5, triplet_c3=0.5)

    def counts(self):
        return len(self.superflip_inputs), len(self.requests), len(self.edma)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import gemmi
    import phase_studio.app as appmod
    import phase_studio.autosolve_review as guided
    import phase_studio.sharped_server_client as api
    from phase_studio.map_quality import ValidationProfile
    import test_jana_completion as tjc

    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    PROFILE = ValidationProfile.REFERENCE_FREE

    # Safety net: outside the explicit fakes nothing external may run.
    def _offline_guard(*_args, **_kwargs):
        raise AssertionError("test attempted a real external call")

    appmod.run_command = _offline_guard
    api.SharpEDServerClient._request_bytes = _offline_guard

    def build(option="A", jana=True):
        temp = Path(tempfile.mkdtemp())
        inflip = temp / "job.inflip"
        inflip.write_text("title guided fixture\n", encoding="utf-8")
        (temp / "reference.cif").write_text(tjc.CIF, encoding="utf-8")
        cfg = tjc.make_run_config(appmod, temp, inflip)
        for key, value in dict(
            cycles=5, reconstruction_mode="superflip", referencefile_mode="omit",
            modelfile_source="deblurred_edma_cif", map_export_format="xplor", structure_export_format="cif",
            reflection_data_mode=appmod.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
            run_sharped=True, run_edma_superflip=True, run_edma_deblurred=True,
            symmetrize_deblurred_map=False, compute_omit_maps=False,
            plimit_superflip=guided.OBSERVED_THRESHOLD_SIGMA, plimit_deblur=guided.PREDICTED_THRESHOLD_SIGMA,
            sharped_model=PHASE_BOOST, superflip_exe="superflip.exe", edma_exe="edma.exe",
            edma_threshold_mode="manual", perform_algorithm="CF", jana_return_to_jana=True,
            sharped_api_token="test-token", sharped_base_url="https://sharped.invalid",
            sharped_max_upload_mb=0.0, sharped_poll_seconds=1, sharped_max_polls=3,
            sharped_timeout_seconds=600, sharped_outres=0.2, sharped_map_value_exponent=1.0,
            sharped_elements="C", merge_distance=0.01, edma_maxima="all", edma_fullcell="no",
            edma_numberofatoms="", edma_centerofcharge=False, edma_chlimit="", edma_chlimlist="",
        ).items():
            setattr(cfg, key, value)
        observed = temp / "observed.hkl"
        observed.write_text("1 0 0 10 1\n", encoding="utf-8")
        ref_ctx = appmod.ReferenceContext(
            cif_path=temp / "reference.cif", work_ref_cif=temp / "reference.cif",
            cell=gemmi.UnitCell(10, 10, 10, 90, 90, 90), spacegroup=gemmi.SpaceGroup("P 1"),
            spacegroup_hm="P 1", composition="C 60", atoms=[],
        )
        state = appmod.PipelineState(
            cfg=cfg, ref_ctx=ref_ctx, observed_hkls={cfg.reflection_data_mode: observed},
            configured_data_mode=cfg.reflection_data_mode, referencefile_mode="omit",
            explicit_superflip_referencefile=None, modelfile_mode="deblurred_edma_cif",
            use_xplor_modelfile=False, use_cif_modelfile=True, use_superflip_xplor_modelfile=False,
            sharped_elements="C", exclude_labels=[], progress_stages=appmod.cycle_progress_stages(cfg),
            current_reflections=[appmod.Reflection(1, 0, 0, 10.0, 1.0)],
            validation_context=SimpleNamespace(profile=PROFILE),
        )
        win = appmod.IterativeSuperflipPipelineQtGUI()
        # The Driver is the only consumer of the backend queue (the backend's
        # own 50 ms poll timer would otherwise race it for events).
        win.timer.stop()
        win.jana_wizard_context = appmod.JanaWizardContext(
            launched_from_jana_wizard=jana, launch_mode="autosolve", autosolve_option=option,
        )
        win.current_validation_profile = PROFILE
        win.last_run_config = cfg
        win._resume_state = state
        win._autosolve_stage = "search"
        win._autosolve_search_deblur_sigma = guided.PREDICTED_THRESHOLD_SIGMA
        win._autosolve_policy = appmod.AdaptiveCyclePolicy(PROFILE, initial=5, block_size=3)
        win._set_widget_value_from_string(win.inputs["cycles"], "5")
        win._set_run_status("Running")
        win.progress_bar.setRange(0, 5)
        win._set_overall_progress_value(0)
        win.errors = []
        win._show_error_report = lambda report, **_kw: win.errors.append(report)
        return win, state

    class Driver:
        """Synchronous stand-in for start_run/continue_run + the worker's
        final "done" event: runs the REAL cycle loop block by block."""

        def __init__(self, win, state, fakes):
            self.win, self.state, self.fakes = win, state, fakes
            self.pending = 0
            self.blocks = []
            self.progress_values = []
            self.logs = []
            win.continue_run = self._request

        def _request(self):
            self.pending += 1

        def _drain(self):
            while True:
                try:
                    kind, payload = self.win.msg_queue.get_nowait()
                except queue.Empty:
                    return
                if isinstance(payload, appmod.RunScopedPayload):
                    payload = payload.payload
                if kind == "log":
                    self.logs.append(getattr(payload, "text", str(payload)))
                elif kind == "progress":
                    self.win._set_overall_progress_value(int(payload))
                    self.progress_values.append(self.win.progress_bar.value())
                elif kind.startswith("autosolve_"):
                    self.win.msg_queue.put((kind, payload))
                    self.win._poll_queue()

        def run_block(self):
            win, state = self.win, self.state
            state.cfg.cycles = win._spin_value("cycles")
            win.progress_bar.setRange(0, max(1, state.cfg.cycles))
            win._set_overall_progress_value(state.completed_cycles)
            self.progress_values.append(win.progress_bar.value())
            before = state.completed_cycles
            win._run_pipeline_cycles(state)
            win.results = list(state.all_results)
            self._drain()
            self.blocks.append((before + 1, state.completed_cycles))
            win._autosolve_on_run_done()
            self.wait_tasks()

        def run_until_idle(self):
            self.run_block()
            self.continue_pending()

        def continue_pending(self):
            while self.pending:
                self.pending -= 1
                self.run_block()

        def wait_tasks(self, timeout=30.0):
            deadline = time.time() + timeout
            while time.time() < deadline:
                task = self.win._autosolve_task
                busy = self.win.autosolve_review_busy() if self.win.autosolve_panels else False
                if (task is None or not task.is_alive()) and not busy and self.win.msg_queue.empty():
                    break
                self._drain()
                app.processEvents()
                time.sleep(0.01)
            self._drain()

    class Patches:
        def __init__(self, fakes):
            self.items = [
                patch.object(appmod, "run_command", side_effect=fakes.run_command),
                patch.object(api.SharpEDServerClient, "_request_bytes",
                             lambda client, method, url, data=None, headers=None: fakes.transport(client, method, url, data, headers)),
                patch.object(appmod, "export_phased_reflections_from_map"),
                patch.object(appmod, "parse_superflip_cycle_metrics", return_value=appmod.SuperflipLogMetrics()),
                patch.object(appmod, "assess_xplor_map", side_effect=fakes.assess),
                patch.object(appmod, "xplor_map_correlation", return_value=None),
                patch.object(appmod, "nearest_metric_to_reference", return_value=None),
                patch.object(appmod, "atom_reference_match_metrics", return_value=None),
                patch.object(appmod, "count_heavy_atoms", return_value=0),
                patch.object(appmod, "write_metrics_csv"),
                patch.object(appmod, "write_map_quality_report"),
            ]

        def __enter__(self):
            for item in self.items:
                item.start()
            return self

        def __exit__(self, *_exc):
            for item in reversed(self.items):
                item.stop()

    def identity(cif):
        """(source, cycle, atom count) encoded by the fake EDMA peaks."""
        atoms = appmod.parse_cif_atoms(Path(cif))
        if not atoms:
            return None
        x = float(appmod.wrap_frac(atoms[0].frac)[0])
        source = "sharped" if x >= 0.5 - 1e-6 else "superflip"
        cycle = int(round((x - (0.5 if source == "sharped" else 0.0)) / 0.01))
        return source, cycle, len(atoms)

    def superflip_model(inflip_path):
        """The model file the generated Superflip input REALLY uses."""
        text = Path(inflip_path).read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^\s*modelfile\s+(\S+)", text, re.MULTILINE | re.IGNORECASE)
        if not match:
            return None, None
        path = Path(inflip_path).parent / match.group(1).strip('"')
        return path, (identity(path) if path.suffix.lower() == ".cif" else None)

    def search_scores(fakes, best=4):
        for c in range(1, 6):
            fakes.scores[("sf", c)] = 0.30 if c == best else 0.50 + 0.001 * c
            fakes.scores[("db", c)] = 0.40
        fakes.scores[("pred", best)] = 0.28

    def wait_panel(win, driver, role):
        deadline = time.time() + 30
        while time.time() < deadline and win.autosolve_panels[role].busy:
            driver._drain()
            app.processEvents()
            time.sleep(0.01)

    def tune(win, driver, role, target):
        """Step a panel with + atoms / - atoms until it reaches `target`."""
        for _ in range(40):
            current = win.autosolve_panels[role].threshold_sigma
            if abs(current - target) < 1e-9:
                return True
            if not win.autosolve_adjust_threshold(role, current > target):
                return False
            wait_panel(win, driver, role)
        return False

    def session(option="A", jana=True):
        """Shared search -> first prediction -> initial Predicted-model tuning."""
        f = Fakes()
        search_scores(f)
        w, st = build(option, jana=jana)
        d = Driver(w, st, f)
        with Patches(f):
            d.run_until_idle()
        return w, st, d, f

    def refine(w, d, f, role, block_scores=None, extra_blocks=None):
        """Refine/Recalculate from `role`; run blocks until Review returns."""
        with Patches(f):
            for c, (sf, db) in (block_scores or {}).items():
                f.scores[("sf", c)] = sf
                f.scores[("db", c)] = db
            for c, (sf, db) in (extra_blocks or {}).items():
                f.scores[("sf", c)] = sf
                f.scores[("db", c)] = db
            started = w.autosolve_recalculate(role)
            d.continue_pending()
        return started

    def flat_block(first, sf=0.45, db=0.35):
        return {c: (sf, db) for c in range(first, first + 3)}

    def final_review_session(option="A", jana=True):
        w, st, d, f = session(option, jana=jana)
        refine(w, d, f, "predicted", flat_block(6))
        return w, st, d, f

    # =====================================================================
    # 1. Preflight: both exact models, from the SAME catalog response.
    # =====================================================================
    import phase_studio.requirements as reqs

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def get_models(self):
            return SimpleNamespace(default_model=PHASE_BOOST, models=["koala phase boost", PHASE_BOOST, PROGRESSIVE])

    status = reqs.check_sharped_api("https://example.invalid", "token", client_factory=FakeClient)
    check("preflight keeps the catalog's exact model names from its one request",
          status.ok and PHASE_BOOST in status.sharped_models and PROGRESSIVE in status.sharped_models)
    check("exact model match only ('koala phase boost' does not satisfy 'koala phase boost 2')",
          guided.missing_required_models(["koala phase boost", PROGRESSIVE]) == [PHASE_BOOST])
    win, _state = build()
    win._sharped_catalog_models = ("koala phase boost", PROGRESSIVE)
    check("preflight fails clearly when 'koala phase boost 2' is unavailable, naming it",
          win._autosolve_models_available() is False and "'koala phase boost 2'" in str(vars(win.errors[-1])))
    win._sharped_catalog_models = (PHASE_BOOST,)
    check("preflight fails when 'koala model progressive' is unavailable", win._autosolve_models_available() is False)
    win._sharped_catalog_models = (PHASE_BOOST, PROGRESSIVE)
    check("preflight passes when both exact models are listed", win._autosolve_models_available() is True)
    win.close()

    # =====================================================================
    # 2. Threshold policy: 1.0 / 1.0 defaults, 0.1-3.0, variable step.
    # =====================================================================
    check("defaults: Charge-flipping solution 1.0 sigma, Model prediction 1.0 sigma",
          guided.OBSERVED_THRESHOLD_SIGMA == 1.0 and guided.PREDICTED_THRESHOLD_SIGMA == 1.0)
    down, value = [1.2], 1.2
    while (nxt := guided.stepped_threshold(value, True)) is not None:
        down.append(nxt)
        value = nxt
    check(f"+ atoms (down) sequence 1.2 -> ... -> 0.1 and no lower: {down}",
          down == [1.2, 1.0, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1])
    up, value = [0.1], 0.1
    while (nxt := guided.stepped_threshold(value, False)) is not None:
        up.append(nxt)
        value = nxt
    check(f"- atoms (up) sequence 0.1 -> ... -> 3.0 and no higher: {up}",
          up == [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0])
    check("steps are exact two-decimal values (no floating-point artifacts)",
          all(repr(v) == repr(round(v, 2)) for v in down + up)
          and guided.format_sigma(0.15) == "0.15 σ")

    # =====================================================================
    # 3. Shared phase search -> first prediction -> initial tuning.
    # =====================================================================
    fakes = Fakes()
    search_scores(fakes)
    win, state = build("A")
    driver = Driver(win, state, fakes)
    with Patches(fakes):
        win._run_pipeline_cycles(state)
        win.results = list(state.all_results)
        driver._drain()
        check("during the search there is no Model prediction (phase-boost output is not one)",
              win.autosolve_display_panel("predicted") is None and win.autosolve_predicted_candidates() == [])
        search_requests = list(fakes.requests)
        search_edma = list(fakes.edma)
        win._autosolve_on_run_done()
        driver.wait_tasks()
    check("shared search: the fixed 5-cycle budget ran before prediction",
          state.completed_cycles == 5 and len(fakes.superflip_inputs) == 5)
    check("search: every SharpED REQUEST sent carries model exactly 'koala phase boost 2'",
          len(search_requests) == 5 and all(model == PHASE_BOOST for _file, model in search_requests))
    check("search: zero requests use 'koala phase boost' (without 2) or 'koala model progressive'",
          not any(model in {"koala phase boost", PROGRESSIVE} for _file, model in search_requests))
    sf_inputs = [e for e in search_edma if e["kind"] == "sf"]
    db_inputs = [e for e in search_edma if e["kind"] == "db"]
    check("search EDMA input: Superflip maps at exactly 1.0 sigma (generated plimit = 1.0 x map sigma)",
          len(sf_inputs) == 5 and all(e["multiplier"] == 1.0 and abs(e["plimit"] - SUPERFLIP_SIGMA) < 1e-6 for e in sf_inputs))
    check("search EDMA input: phase-boost SharpED maps at exactly 1.0 sigma (not 2.0)",
          len(db_inputs) == 5 and all(e["multiplier"] == 1.0 and abs(e["plimit"] - SHARPED_SIGMA) < 1e-6 for e in db_inputs))
    check("search EDMA input files literally say 'plimit 2' / 'plimit 4' (1.0 x sigma)",
          all("plimit 2\n" in e["inp"] for e in sf_inputs) and all("plimit 4\n" in e["inp"] for e in db_inputs))
    check("results carry exact provenance ('koala phase boost 2', EDMA 1.0 / 1.0 sigma)",
          all(r.sharped_model == PHASE_BOOST and r.superflip_edma_sigma == 1.0 and r.deblur_edma_sigma == 1.0
              for r in state.all_results))
    check("log: '[SharpED] Model: koala phase boost 2' before each search submission",
          sum(1 for line in driver.logs if line == f"[SharpED] Model: {PHASE_BOOST}") == 5)
    model2, ident2 = superflip_model(fakes.superflip_inputs[1])
    check("search feedback: cycle 2's generated Superflip input names a CIF model (a STRUCTURE)",
          model2 is not None and model2.suffix.lower() == ".cif")
    check("search feedback: that model is cycle 1's SharpED map -> EDMA(1.0) structure",
          ident2 == ("sharped", 1, peaks_for(1.0)))
    prediction_requests = fakes.requests[len(search_requests):]
    check("first prediction: exactly ONE SharpED request, model exactly 'koala model progressive'",
          prediction_requests == [("cycle_004_superflip.xplor", PROGRESSIVE)])
    pred_edma = [e for e in fakes.edma if e["kind"] == "pred"]
    check("first prediction: EDMA on the progressive map at exactly 1.0 sigma (generated input)",
          len(pred_edma) == 1 and pred_edma[0]["multiplier"] == 1.0)
    check("log: '[SharpED] Model: koala model progressive' before the prediction",
          f"[SharpED] Model: {PROGRESSIVE}" in driver.logs)
    check("log: the prediction's EDMA is labelled as the Model prediction map, not a Superflip map",
          any(line.strip().startswith("[EDMA] Model prediction map · threshold 1 σ") for line in driver.logs)
          and not any(line.startswith("[EDMA] Superflip map") and "prediction" in line for line in driver.logs))
    check("after the first prediction: INITIAL Predicted-model tuning, not the Final Review",
          win._autosolve_stage == "tuning" and str(win._run_status).upper() == "REVIEW")
    task = win._autosolve_task
    check("tuning: no scientific work runs (no worker, no task, queue empty)",
          (win.worker is None or not win.worker.is_alive()) and (task is None or not task.is_alive()) and win.msg_queue.empty())
    check("tuning: the stale 'SharpED · downloading' progress line is cleared (row reads 'Review')",
          win._cycle_progress_state is None and win.current_cycle_detail.text() == "Review"
          and win.current_cycle_stage_counter.text() == "")
    observed = win.autosolve_panels["observed"]
    predicted = win.autosolve_panels["predicted"]
    check("tuning: Charge-flipping solution = best Superflip cycle 4 at 1.0 sigma; Predicted = cycle 4 at 1.0 sigma",
          observed.cycle == 4 and observed.threshold_sigma == 1.0 and predicted.cycle == 4 and predicted.threshold_sigma == 1.0)
    check("tuning: technical labels", observed.technical_label() == "Superflip · EDMA 1.00 σ"
          and predicted.technical_label() == "SharpED · koala model progressive · EDMA 1.00 σ")
    before = fakes.counts()
    check("tuning: Charge-flipping solution is read-only (+/- refused, nothing runs)",
          win.autosolve_adjust_threshold("observed", True) is False and fakes.counts() == before)
    check("tuning: Charge-flipping solution cannot Recalculate", win.autosolve_recalculate("observed") is False)
    check("tuning: nothing can be passed yet (either panel)",
          win.autosolve_pass_panel("observed") is False and win.autosolve_pass_panel("predicted") is False)
    check("tuning: no measured-data correction yet", win.autosolve_request_correction("intensity") is False)

    # + atoms / - atoms on the Model prediction: EDMA only, same map.
    edma_log_start = len(driver.logs)
    with Patches(fakes):
        for add_atoms, expected in ((True, 0.8), (True, 0.7), (False, 0.8), (True, 0.7)):
            panel = win.autosolve_panels["predicted"]
            map_hash = guided.file_sha256(panel.map_path)
            before = fakes.counts()
            started = win.autosolve_adjust_threshold("predicted", add_atoms)
            second = win.autosolve_adjust_threshold("predicted", add_atoms)
            wait_panel(win, driver, "predicted")
            after = fakes.counts()
            label = f"{'+ atoms' if add_atoms else '- atoms'} (Predicted) -> {expected:.1f} sigma"
            check(f"{label}: applied", started and win.autosolve_panels["predicted"].threshold_sigma == expected)
            check(f"{label}: a second click while EDMA runs is refused (one EDMA at a time)", second is False)
            check(f"{label}: Superflip 0 / SharpED 0 / EDMA 1", (after[0] - before[0], after[1] - before[1], after[2] - before[2]) == (0, 0, 1))
            check(f"{label}: generated EDMA input uses exactly {expected:.1f} sigma", fakes.edma[-1]["multiplier"] == expected)
            check(f"{label}: canonical map hash unchanged", guided.file_sha256(win.autosolve_panels["predicted"].map_path) == map_hash)
            ident = identity(win.autosolve_panels["predicted"].current_cif)
            check(f"{label}: displayed structure is the progressive map's at {expected:.1f} sigma",
                  ident == ("sharped", 4, peaks_for(expected)))
            check(f"{label}: activity cleared afterwards (no stale progress)", win.current_cycle_detail.text() == "Review")
        driver._drain()
    threshold_logs = driver.logs[edma_log_start:]
    check("threshold EDMA log names the Model prediction map (never 'Superflip map')",
          any(line.strip().startswith("[EDMA] Model prediction map · threshold 0.7 σ") for line in threshold_logs)
          and not any(line.strip().startswith("[EDMA] Superflip map") for line in threshold_logs))
    check("tuning: Charge-flipping solution threshold untouched (1.0 sigma)", win.autosolve_panels["observed"].threshold_sigma == 1.0)

    # =====================================================================
    # 4. Refine 3 cycles from the tuned Model prediction (0.7 sigma).
    # =====================================================================
    seed_identity = identity(Path(win.autosolve_panels["predicted"].current_cif))
    n_sf, n_req, n_edma = fakes.counts()
    started = refine(win, driver, fakes, "predicted", flat_block(6))
    inputs = {p.parent.name: p for p in fakes.superflip_inputs}
    check("Refine starts refinement from the Model prediction", started)
    check("refinement: exactly 3 cycles before the improvement decision", driver.blocks[-1] == (6, 8))
    model6, ident6 = superflip_model(inputs["cycle_006"])
    check("seed: cycle 6's generated current_modelfile.cif is the tuned 0.7-sigma Model prediction",
          model6 is not None and model6.name == "current_modelfile.cif" and ident6 == seed_identity
          and seed_identity == ("sharped", 4, peaks_for(0.7)))
    check("seed: NOT cycle 5's default-threshold SharpED structure", ident6 != ("sharped", 5, peaks_for(1.0)))
    model7, ident7 = superflip_model(inputs["cycle_007"])
    check("topology: cycle 7's model is cycle 6's progressive map -> EDMA(0.7) structure",
          ident7 == ("sharped", 6, peaks_for(0.7)))
    block_requests = fakes.requests[n_req:]
    check("refinement: every SharpED request carries exactly 'koala model progressive'",
          len(block_requests) == 3 and all(model == PROGRESSIVE for _file, model in block_requests))
    check("refinement: SharpED runs on each refinement cycle's own Superflip map",
          [file for file, _m in block_requests] == [f"cycle_{c:03d}_superflip.xplor" for c in range(6, 9)])
    block_db = [e for e in fakes.edma[n_edma:] if e["kind"] == "db"]
    check("refinement: every progressive EDMA in the block uses exactly 0.7 sigma (generated input)",
          len(block_db) == 3 and all(e["multiplier"] == 0.7 for e in block_db))
    block_sf = [e for e in fakes.edma[n_edma:] if e["kind"] == "sf"]
    check("refinement: Observed-data EDMA stays at 1.0 sigma", len(block_sf) == 3 and all(e["multiplier"] == 1.0 for e in block_sf))
    check("log: '[Refinement seed] Model prediction · Cycle 4 · EDMA 0.7 σ' for the first cycle",
          any(line.startswith("[Refinement seed] Model prediction · Cycle 4 · EDMA 0.70 σ") for line in driver.logs))
    check("log: the first refinement cycle does NOT claim its model came 'from cycle 5'",
          not any("[Cycle 6] Next-cycle model" in line for line in driver.logs))
    check("log: later cycles keep the usual previous-cycle description",
          any("[Cycle 7] Next-cycle model" in line and "(from cycle 6)" in line for line in driver.logs))
    check("log: every refinement submission is preceded by '[SharpED] Model: koala model progressive'",
          sum(1 for line in driver.logs if line == f"[SharpED] Model: {PROGRESSIVE}") == 4)
    check("after the block: Final Review (not tuning)", win._autosolve_stage == "review")
    check("after the block: the Predicted threshold is still 0.7 sigma (no hidden reset)",
          win.autosolve_panels["predicted"].threshold_sigma == 0.7)
    check("after the block: Charge-flipping solution starts at 1.0 sigma", win.autosolve_panels["observed"].threshold_sigma == 1.0)
    check("final review: idle progress row shows 'Review' only", win.current_cycle_detail.text() == "Review")
    check("progress: the overall bar never regressed through search, prediction and refinement",
          all(b >= a for a, b in zip(driver.progress_values, driver.progress_values[1:])))

    # =====================================================================
    # 4b. Refinement-seed display state (items 16-18): once a refinement
    # block starts, the panel that seeded it must keep showing EXACTLY the
    # structure/threshold it was seeded from -- not a silent jump back to
    # the pre-tuning default -- until a genuinely new completed candidate
    # from this block exists. Split autosolve_recalculate() (synchronous,
    # sets up the block) from continue_pending() (runs it) to inspect the
    # in-between state a real user would see during "Refinement cycle 1".
    # =====================================================================
    seed_win, seed_state, seed_driver, seed_fakes = session("A")
    with Patches(seed_fakes):
        tuned = tune(seed_win, seed_driver, "predicted", 0.6)
    check("seed display: Model prediction tunable to 0.6 sigma", tuned)
    seed_panel_before = seed_win.autosolve_panels["predicted"]
    seed_identity_before = identity(Path(seed_panel_before.current_cif))
    check("seed display: before refinement starts, no seed-display state yet",
          not seed_win.autosolve_panel_shows_refinement_seed("predicted"))

    with Patches(seed_fakes):
        started = seed_win.autosolve_recalculate("predicted")
    check("seed display: Refine starts the block", started)
    check("seed display: mid-block (before cycle 1's own candidate exists), the panel "
          "still shows the seed's own tuned structure",
          seed_win.autosolve_panel_shows_refinement_seed("predicted")
          and seed_win.autosolve_display_panel("predicted") is seed_win.autosolve_panels["predicted"]
          and seed_win.autosolve_panels["predicted"].threshold_sigma == 0.6
          and identity(Path(seed_win.autosolve_panels["predicted"].current_cif)) == seed_identity_before)
    check("seed display: the seed note names the tuned 0.6-sigma structure, not a default threshold",
          seed_win.autosolve_refinement["seed_note"] == f"Model prediction · Cycle 4 · EDMA {guided.format_sigma(0.6)}")

    # Cycle 7's score (0.20) genuinely beats the pre-refinement best (cycle
    # 4, 0.28), so the post-block "best" is a real new candidate, not just
    # the seed re-surfacing because nothing else exists yet.
    for c, (sf, db) in flat_block(6).items():
        seed_fakes.scores[("sf", c)] = sf
        seed_fakes.scores[("db", c)] = db
    seed_fakes.scores[("db", 7)] = 0.20
    with Patches(seed_fakes):
        seed_driver.continue_pending()
    check("seed display: once new completed candidates exist, ranking takes back over",
          not seed_win.autosolve_panel_shows_refinement_seed("predicted"))
    check("seed display: once a block candidate genuinely beats the seed (cycle 7), the display "
          "switches to it -- not stuck on the stale seed",
          seed_win.autosolve_display_panel("predicted").cycle == 7
          and identity(Path(seed_win.autosolve_display_panel("predicted").current_cif)) != seed_identity_before)

    # =====================================================================
    # 5. Final Review: both panels, own thresholds; Recalculate from each.
    # =====================================================================
    targets = {"observed": 0.9, "predicted": 0.6}
    for role, expected_source in (("observed", "superflip"), ("predicted", "sharped")):
        w, st, d, f = final_review_session("A")
        with Patches(f):
            # 0.9 sigma lies off the 1.0-anchored step grid; start from 1.1
            # so + atoms reaches it through the normal EDMA-only path.
            w.autosolve_panels["observed"].threshold_sigma = 1.1
            tuned_obs = tune(w, d, "observed", 0.9)
            tuned_pred = tune(w, d, "predicted", 0.6)
        chosen = w.autosolve_panels[role]
        chosen_identity = identity(chosen.current_cif)
        before_inputs = len(f.superflip_inputs)
        first_block_cycle = st.completed_cycles + 1
        n_edma_before = len(f.edma)
        refine(w, d, f, role, flat_block(first_block_cycle))
        _model, ident = superflip_model(f.superflip_inputs[before_inputs])
        check(f"Final Review: both panels tuned independently (Observed 0.9, Predicted 0.6) [{role}]", tuned_obs and tuned_pred)
        check(f"Final Review Recalculate from {role}: the first Superflip model IS this panel's structure "
              f"({guided.format_sigma(targets[role])})",
              ident == chosen_identity and chosen_identity[0] == expected_source
              and chosen_identity[2] == peaks_for(targets[role]))
        block_db = [e for e in f.edma[n_edma_before:] if e["kind"] == "db"]
        check(f"Final Review Recalculate from {role}: the captured {targets[role]:.1f} sigma drives the block's progressive EDMA",
              len(block_db) == 3 and all(e["multiplier"] == targets[role] for e in block_db))

    # Four actions and handoff only in the Final Review.
    w, st, d, f = final_review_session("A")
    handoffs = []
    def capture_selector(source):
        handoffs.append(source)
        w.autosolve_handoff_state = "selecting"

    with Patches(f), patch.object(w, "_autosolve_handoff", side_effect=capture_selector):
        tune(w, d, "observed", 0.8)
        before = f.counts()
        check("Final Review: Charge-flipping solution can be passed", w.autosolve_pass_panel("observed"))
        obs = w.autosolve_panels["observed"]
        result = w._autosolve_result_for_panel(obs)
        check("Final Review: a duplicate pass is blocked while selecting", w.autosolve_pass_panel("observed") is False)
        check("Observed selector: Superflip source, canonical map, structure at the CURRENT 0.8 sigma",
              handoffs == ["superflip"] and result is not None and Path(result.superflip_map) == Path(obs.map_path)
              and Path(result.superflip_edma_cif) == Path(obs.current_cif) and result.superflip_edma_sigma == 0.8)
        check("Observed selector: no Superflip/SharpED rerun", f.counts()[:2] == before[:2])
        w.autosolve_handoff_state = "idle"
        handoffs.clear()
        check("Final Review: Model prediction can be passed", w.autosolve_pass_panel("predicted"))
        pred = w.autosolve_panels["predicted"]
        result = w._autosolve_result_for_panel(pred)
        check("Predicted selector: SharpED source, canonical progressive map, current threshold, exact model",
              handoffs == ["deblurred"] and result is not None and Path(result.deblur_map) == Path(pred.map_path)
              and Path(result.deblur_edma_cif) == Path(pred.current_cif) and result.sharped_model == PROGRESSIVE)
        check("Predicted selector: SharpED is not rerun", f.counts()[1] == before[1])
    w.autosolve_handoff_state = "idle"

    # =====================================================================
    # 6. Automatic +3 on strict improvement, goal-specific.
    # =====================================================================
    def extend_case(option, sf_better, db_better, db_value=None):
        w, st, d, f = session(option)
        block = {c: (0.10 if sf_better and c == 7 else 0.45,
                     db_value if db_value is not None else (0.10 if db_better and c == 7 else 0.35))
                 for c in range(6, 9)}
        refine(w, d, f, "predicted", block, flat_block(9))
        return w, d

    w, d = extend_case("A", True, False)
    check("goal 'Solve the phase problem': a strict Observed-data improvement extends by +3",
          d.blocks[-2:] == [(6, 8), (9, 11)] and w._autosolve_stage == "review")
    w, d = extend_case("B", True, False)
    check("goal 'Predict the structure model': an Observed-only improvement does NOT extend", d.blocks[-1] == (6, 8))
    w, d = extend_case("A", False, True)
    check("goal 'Solve the phase problem': a Predicted-only improvement does NOT extend", d.blocks[-1] == (6, 8))
    w, d = extend_case("B", False, True)
    check("goal 'Predict the structure model': a strict Predicted improvement extends by +3",
          d.blocks[-2:] == [(6, 8), (9, 11)])
    w, d = extend_case("B", False, False, db_value=0.28)
    check("a tie is NOT an improvement (earlier cycle wins) -> Final Review",
          d.blocks[-1] == (6, 8) and w._autosolve_stage == "review")
    w, d = extend_case("B", False, False)
    check("CASE B: no strict improvement -> exactly one block, Final Review",
          d.blocks[-1] == (6, 8) and w._autosolve_stage == "review")
    w, st, d, f = session("B")
    refine(w, d, f, "predicted", {c: (None, None) for c in range(6, 9)})
    check("CASE C: unavailable primary metric -> no improvement claimed, usable Final Review",
          d.blocks[-1] == (6, 8) and w._autosolve_stage == "review" and w.autosolve_panels["predicted"].cycle == 4)

    w, st, d, f = session("B")
    w.inputs["cycles"].setMaximum(7)
    before = f.counts()
    check("maximum-cycle protection: Refine beyond the workflow maximum is refused",
          w.autosolve_recalculate("predicted") is False and f.counts() == before)
    w.inputs["cycles"].setMaximum(999)

    # =====================================================================
    # 7. Failures, retry, cancel, standalone.
    # =====================================================================
    f = Fakes()
    search_scores(f)
    w, st = build("A")
    d = Driver(w, st, f)
    with Patches(f):
        f.fail_model = PROGRESSIVE
        d.run_block()
        failed_stage = w._autosolve_stage
        search_cycles = len(f.superflip_inputs)
        f.fail_model = ""
        n_req = len(f.requests)
        w.autosolve_retry()
        d.wait_tasks()
    check("prediction failure keeps the completed search (stage prediction_failed)",
          failed_stage == "prediction_failed" and st.completed_cycles == 5)
    check("prediction retry: only the prediction runs again (0 Superflip, 1 SharpED request)",
          len(f.superflip_inputs) == search_cycles and len(f.requests) - n_req == 1 and w._autosolve_stage == "tuning")
    with Patches(f):
        f.fail_edma = True
        sigma_before = w.autosolve_panels["predicted"].threshold_sigma
        n_req = len(f.requests)
        w.autosolve_adjust_threshold("predicted", True)
        wait_panel(w, d, "predicted")
        f.fail_edma = False
    check("threshold failure: SharpED not rerun, previous structure/threshold kept, activity cleared",
          len(f.requests) == n_req and w.autosolve_panels["predicted"].threshold_sigma == sigma_before
          and bool(w.autosolve_panels["predicted"].error) and w.current_cycle_detail.text() == "Review")
    w.autosolve_cancel()
    check("Cancel from tuning: terminal CANCELLED, nothing passed", str(w._run_status).upper() == "CANCELLED")

    w, st, d, f = final_review_session("A", jana=False)
    saved = []
    w._export_selected_candidate = lambda candidate: saved.append(candidate) or True
    with patch.object(appmod, "perform_jana_handoff", side_effect=AssertionError("standalone must never hand off")):
        check("standalone Final Review: Save map and model uses the export authority", w.autosolve_pass_panel("predicted") is True)
    pred = w.autosolve_panels["predicted"]
    check("standalone: the saved pair is the current map + current-threshold structure",
          saved and Path(saved[0].map_path) == Path(pred.map_path) and Path(saved[0].structure_path) == Path(pred.current_cif))

    # =====================================================================
    # 8. Measured-data correction: provenance, originals kept.
    # =====================================================================
    w, st, d, f = final_review_session("B")
    original = next(iter(st.observed_hkls.values()))
    original_hash = guided.file_sha256(original)
    plan, _detail = w.autosolve_correction_plan()
    check("Final Review (non-FWHM data): 'Correct suspect intensities' applies", plan == "intensity")
    n_req = len(f.requests)
    with Patches(f):
        started = w.autosolve_request_correction("intensity")
        d.continue_pending()
    check("correction runs the existing Map Feedback stage (weak-intensity, from the next cycle)",
          started and st.cfg.map_feedback_intensity_enabled and st.cfg.map_feedback_intensity_from_cycle == 9)
    correction_models = [model for file, model in f.requests[n_req:] if file.startswith("cycle_")]
    check("correction: the phase search continues with 'koala phase boost 2'",
          correction_models and all(model == PHASE_BOOST for model in correction_models))
    check("correction: afterwards a new Model prediction is tuned (tuning stage again)", w._autosolve_stage == "tuning")
    check("correction: the ORIGINAL measured reflection file is untouched", guided.file_sha256(original) == original_hash)
    provenance = json.loads((Path(st.cfg.work_dir) / "autosolve_result_provenance.json").read_text(encoding="utf-8"))
    entry = next((e for e in provenance["entries"] if e.get("action") == "measured_data_correction"), None)
    check("correction provenance: 'measured reflection data modified' and the routine are recorded",
          entry is not None and entry["measured_reflection_data_modified"] is True
          and entry["correction"] == "Correct suspect intensities" and entry["original_measured_data"] == str(original))

    # =====================================================================
    # 9. AutosolveWindow: tuning, refinement, Final Review, busy, dialog.
    # =====================================================================
    from phase_studio.autosolve_window import AutosolveWindow
    from PySide6.QtCore import QPoint as _QPoint

    def texts(aw, role):
        column = aw.review_columns[role]
        return [column[k].text() for k in ("add", "remove", "recalc", "pass_") if column[k].isVisibleTo(aw)]

    def visible_pass_buttons(aw):
        return [b for b in aw.findChildren(type(aw.cancel_button)) if b.isVisibleTo(aw) and b.text() == "Pass to Jana2020"]

    w, st, d, f = session("A")
    aw = AutosolveWindow(w, "A")
    aw.resize(1366, 860)
    aw.show()
    app.processEvents()
    aw._refresh_tick()
    app.processEvents()
    captions = [t.get_text() for t in aw._panel_captions]
    check("window tuning: panels titled 'Charge-flipping solution' / 'Model prediction', 'Best · Cycle 4' on both",
          "Charge-flipping solution" in captions and "Model prediction" in captions and captions.count("Best · Cycle 4") == 2)
    check("window tuning: Charge-flipping solution shows NO actions (comparison only)",
          texts(aw, "observed") == [] and not aw.review_columns["observed"]["actions"].isVisibleTo(aw))
    check("window tuning: Model prediction shows exactly '+ atoms', '- atoms', 'Refine 3 cycles'",
          texts(aw, "predicted") == ["+ atoms", "- atoms", "Refine 3 cycles"])
    check("window tuning: early Pass to Jana2020 is available for completed results",
          len(visible_pass_buttons(aw)) == 1 and aw.pass_now_button.isEnabled())
    check("window tuning: headline 'Predicted-model tuning'", "Predicted-model tuning" in aw.status_headline.text())
    check("window tuning: bottom progress row shows 'Review', no stale SharpED/Stage text",
          w.current_cycle_detail.text() == "Review" and w.current_cycle_stage_counter.text() == "")
    check("window tuning (item 25): the idle cycle-loop progress bars are collapsed, not sitting "
          "at their last completed value", not w.run_status_panel.isVisible())
    check("window tuning: no measured-data correction offered yet", not aw.correction_row_widget.isVisibleTo(aw))
    w.autosolve_panels["predicted"].busy_sigma = 0.7
    w.autosolve_activity = "Model prediction · EDMA 0.70 σ · recalculating structure"
    aw._refresh_tick()
    check("window busy: one consistent busy state (all Predicted actions disabled) + status text",
          not any(aw.review_columns["predicted"][k].isEnabled() for k in ("add", "remove", "recalc"))
          and aw.review_columns["predicted"]["status"].text() == "Recalculating structure at 0.70 σ…")
    check("window busy: the headline names only the EDMA operation (no SharpED)",
          "EDMA 0.70 σ" in aw.status_headline.text() and "downloading" not in aw.status_headline.text())
    w.autosolve_panels["predicted"].busy_sigma = None
    w.autosolve_activity = ""
    aw.close()

    w._autosolve_stage = "refinement"
    w.autosolve_refinement = {"role": "predicted", "cycle": 4, "threshold_sigma": 0.7, "block": 1, "block_start": 6,
                              "seed_note": "Model prediction · Cycle 4 · EDMA 0.70 σ"}
    w._cycle_progress_state = appmod.CycleProgressState(cycle_index=6, cycle_total=8, stage_name="Superflip", stage_index=1, stage_total=5)
    w._set_run_status("Running")
    aw = AutosolveWindow(w, "A")
    aw.show()
    aw._refresh_tick()
    check("window refinement: 'Refinement cycle 1 of 3' with the cycle/stage", "Refinement cycle 1 of 3" in aw.status_headline.text())
    check("window refinement: the seed is shown ('Refinement seed: Cycle 4 · EDMA 0.7 σ')",
          aw.review_columns["predicted"]["status"].text() == "Refinement seed: Cycle 4 · EDMA 0.70 σ")
    check("window refinement: panel actions are hidden while early Pass remains available",
          texts(aw, "observed") == [] and texts(aw, "predicted") == []
          and len(visible_pass_buttons(aw)) == 1 and aw.pass_now_button.isEnabled())
    check("window refinement (item 25): actively running -- the progress bars stay visible, not collapsed",
          w.run_status_panel.isVisible())
    aw.close()

    w, st, d, f = final_review_session("A")
    aw = AutosolveWindow(w, "A")
    aw.resize(1366, 860)
    aw.show()
    app.processEvents()
    aw._refresh_tick()
    app.processEvents()
    for role in ("observed", "predicted"):
        check(f"window Final Review ({role}): '+ atoms', '- atoms', 'Recalculate', 'Pass to Jana2020'",
              texts(aw, role) == ["+ atoms", "- atoms", "Recalculate", "Pass to Jana2020"])
    check("window Final Review (item 25): idle -- the completed cycle-loop progress bars are collapsed",
          not w.run_status_panel.isVisible())

    def y_of(widget):
        return widget.mapTo(aw, _QPoint(0, 0)).y()

    cols = aw.review_columns
    check("window Final Review: composition, origin and action rows aligned across panels",
          y_of(cols["observed"]["formula"]) == y_of(cols["predicted"]["formula"])
          and y_of(cols["observed"]["detail"]) == y_of(cols["predicted"]["detail"])
          and y_of(cols["observed"]["actions"]) == y_of(cols["predicted"]["actions"]))
    check("window Final Review: action rows have the same height",
          cols["observed"]["actions"].height() == cols["predicted"]["actions"].height())
    for _ in range(10):   # let deferred log/geometry refits settle first
        app.processEvents()
        aw._refresh_tick()
    action_y = y_of(cols["observed"]["actions"])
    w.autosolve_panels["predicted"].busy_sigma = 0.6
    aw._refresh_tick()
    app.processEvents()
    check("window Final Review busy: no action row jumps vertically",
          y_of(cols["observed"]["actions"]) == action_y and y_of(cols["predicted"]["actions"]) == action_y)
    check("window Final Review busy: both panels' actions wait (single EDMA worker)",
          not any(cols[r][k].isEnabled() for r in ("observed", "predicted") for k in ("add", "remove", "recalc", "pass_")))
    w.autosolve_panels["predicted"].busy_sigma = None
    aw._refresh_tick()
    app.processEvents()
    check("window Final Review: the Predicted warning wraps inside its own panel",
          cols["predicted"]["warning"].isVisible() and cols["predicted"]["warning"].width() <= cols["predicted"]["column"].width())
    check("window Final Review: EDMA threshold and atom count appear once in one local line",
          all("EDMA" not in cols[r]["detail"].text()
              and cols[r]["threshold"].text().count("σ") == 1
              and "EDMA sites" in cols[r]["threshold"].text()
              for r in ("observed", "predicted")))
    metadata_bottom = max(
        y_of(cols[role][name]) + cols[role][name].height()
        for role in ("observed", "predicted")
        for name in ("formula", "detail", "threshold", "actions", "status", "warning")
        if cols[role][name].isVisibleTo(aw)
    )
    check("window Final Review: all result metadata and validation notes end above Execution Log",
          metadata_bottom <= y_of(aw.log_section_widget))
    check("window Final Review: 'Correct suspect intensities' offered", aw.correction_buttons["intensity"].isVisible())
    shown = []
    requested = []
    w.autosolve_request_correction = lambda kind: requested.append(kind) or True

    def fake_exec(box, choice):
        shown.append(box.text())
        for button in box.buttons():
            if button.text() == choice:
                button.click()
        return 0

    with patch.object(QMessageBox, "exec", lambda box: fake_exec(box, "Cancel")):
        aw.correction_buttons["intensity"].click()
    check("correction: clicking first shows the confirmation warning (nothing modified on Cancel)",
          shown and "modifies the measured reflection data" in shown[0]
          and "The original measured data will be retained for validation." in shown[0] and requested == [])
    with patch.object(QMessageBox, "exec", lambda box: fake_exec(box, "Correct intensities")):
        aw.correction_buttons["intensity"].click()
    check("correction: 'Correct intensities' confirms and runs the correction", requested == ["intensity"])
    aw.close()

    f = Fakes()
    search_scores(f)
    w, st = build("A")
    with Patches(f):
        w._run_pipeline_cycles(st)
    w.results = list(st.all_results)
    aw = AutosolveWindow(w, "A")
    aw.show()
    aw._refresh_tick()
    fig_texts = [t.get_text() for t in aw.structure_figure.findobj(lambda a: hasattr(a, "get_text"))]
    check("window search: Predicted panel waits ('Generated after the phase search')",
          any("Generated after the phase search" in t for t in fig_texts))
    check("window search: completed results enable early Pass while panel actions remain hidden",
          texts(aw, "observed") == [] and texts(aw, "predicted") == []
          and len(visible_pass_buttons(aw)) == 1 and aw.pass_now_button.isEnabled())
    w._autosolve_stage = "predicting"
    aw._refresh_tick()
    check("window prediction: 'Generating predicted structure…'", "Generating predicted structure…" in aw.status_headline.text())
    aw.close()

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
