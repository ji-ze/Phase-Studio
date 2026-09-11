"""Regression tests for how Phase Studio launches external calculation
processes (EDMA, Superflip).

Plain Python test (no pytest dependency; run with
`python tests/test_process_launch.py`), following this project's usual
checks-list-plus-exit-code convention.

Motivated by a real Jana2020 Phase Recycling run in which a black EDMA
console window popped up over the GUI on every EDMA execution (twice per
cycle). Phase Studio's GUI executables are built windowed, so the process
has no console of its own; starting a console-subsystem child then makes
Windows allocate a brand new console *with a visible window* for it.
Redirecting stdout/stderr does not prevent that -- only CREATE_NO_WINDOW
does.

What these tests pin down:
  - EDMA is launched with the hidden-console creation flags on Windows.
  - Everything else about that launch is unchanged: command line, working
    directory, captured stdout, exit code, and stop_event cancellation.
  - Hiding is opt-in per call site, never global (run_command's default).
  - The flags are Windows-only; nothing is forced on Linux/macOS.
"""
import io
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


class FakePopen:
    """Stands in for subprocess.Popen: records exactly how it was called and
    replays a fixed stdout, without launching anything."""

    instances = []

    def __init__(self, cmd, **kwargs):
        self.cmd = list(cmd)
        self.kwargs = dict(kwargs)
        self.pid = 4242
        self.returncode = None
        self.terminated = False
        self.killed = False
        self._polls = 0
        self.stdout = io.BytesIO(b"EDMA line 1\nEDMA line 2\n")
        FakePopen.instances.append(self)

    def poll(self):
        # Alive for the first couple of polls so the cancellation path can be
        # exercised, then reports a clean exit.
        self._polls += 1
        if self._polls < 3:
            return None
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 1

    def kill(self):
        self.killed = True
        self.returncode = 1


class FailingPopen(FakePopen):
    def poll(self):
        self.returncode = 3
        return 3


def main():
    from phase_studio import process_utils
    import phase_studio.app as appmod

    is_windows = sys.platform == "win32"
    tmp = Path(tempfile.mkdtemp())

    # =====================================================================
    # process_utils.no_console_popen_kwargs()
    # =====================================================================
    kwargs = process_utils.no_console_popen_kwargs()
    if is_windows:
        check(
            "Windows: no_console_popen_kwargs sets CREATE_NO_WINDOW",
            kwargs.get("creationflags") == subprocess.CREATE_NO_WINDOW,
        )
        startupinfo = kwargs.get("startupinfo")
        check("Windows: STARTUPINFO supplied", startupinfo is not None)
        check(
            "Windows: STARTF_USESHOWWINDOW set",
            bool(getattr(startupinfo, "dwFlags", 0) & subprocess.STARTF_USESHOWWINDOW),
        )
        check(
            "Windows: wShowWindow is SW_HIDE",
            getattr(startupinfo, "wShowWindow", None) == subprocess.SW_HIDE,
        )
        check(
            "Windows: DETACHED_PROCESS is not used (it would break pipe capture)",
            not (kwargs.get("creationflags", 0) & 0x00000008),
        )
    else:
        check("Non-Windows: no console flags are forced", kwargs == {})

    # =====================================================================
    # run_command: hidden vs. default launch
    # =====================================================================
    original_popen = subprocess.Popen
    lines = []
    try:
        subprocess.Popen = FakePopen

        # --- hidden (what EDMA uses) ---
        FakePopen.instances.clear()
        log_path = tmp / "hidden.log"
        code = appmod.run_command(
            ["EDMA.exe", "job_edma.inp"],
            cwd=tmp,
            log_path=log_path,
            log=lines.append,
            hide_console=True,
        )
        hidden = FakePopen.instances[-1]
        check("hidden run_command returns the process exit code", code == 0)
        check(
            "hidden launch keeps the exact command line",
            hidden.cmd == ["EDMA.exe", "job_edma.inp"],
        )
        check("hidden launch keeps the working directory", hidden.kwargs.get("cwd") == str(tmp))
        check(
            "hidden launch still captures stdout via a pipe",
            hidden.kwargs.get("stdout") == subprocess.PIPE,
        )
        check(
            "hidden launch still folds stderr into stdout",
            hidden.kwargs.get("stderr") == subprocess.STDOUT,
        )
        check(
            "hidden launch writes the captured output to the log file unchanged",
            log_path.read_bytes() == b"EDMA line 1\nEDMA line 2\n",
        )
        if is_windows:
            check(
                "hidden launch passes CREATE_NO_WINDOW",
                hidden.kwargs.get("creationflags") == subprocess.CREATE_NO_WINDOW,
            )
            check(
                "hidden launch points stdin at DEVNULL (no invisible blocking prompt)",
                hidden.kwargs.get("stdin") == subprocess.DEVNULL,
            )
        else:
            check(
                "non-Windows hidden launch adds no creation flags",
                "creationflags" not in hidden.kwargs,
            )

        # --- default: every other call site is untouched ---
        FakePopen.instances.clear()
        appmod.run_command(
            ["superflip.exe", "job.inflip"],
            cwd=tmp,
            log_path=tmp / "default.log",
            log=lines.append,
        )
        default = FakePopen.instances[-1]
        check(
            "console hiding is opt-in: default launch adds no creation flags",
            "creationflags" not in default.kwargs,
        )
        check(
            "console hiding is opt-in: default launch leaves stdin inherited",
            "stdin" not in default.kwargs,
        )

        # --- cancellation still terminates the child ---
        FakePopen.instances.clear()
        stop = threading.Event()
        stop.set()
        cancelled = False
        try:
            appmod.run_command(
                ["EDMA.exe", "job_edma.inp"],
                cwd=tmp,
                log_path=tmp / "cancel.log",
                log=lines.append,
                stop_event=stop,
                hide_console=True,
            )
        except RuntimeError as exc:
            cancelled = "Immediate stop requested" in str(exc)
        check("hidden launch still honours stop_event cancellation", cancelled)
        check(
            "hidden launch still terminates the child on cancel",
            FakePopen.instances[-1].terminated,
        )

        # --- a non-zero exit is still an error ---
        FakePopen.instances.clear()
        subprocess.Popen = FailingPopen
        failed = False
        try:
            appmod.run_command(
                ["EDMA.exe", "job_edma.inp"],
                cwd=tmp,
                log_path=tmp / "fail.log",
                log=lines.append,
                hide_console=True,
            )
        except RuntimeError as exc:
            failed = "failed with code 3" in str(exc)
        check("hidden launch still raises on a non-zero exit code", failed)
    finally:
        subprocess.Popen = original_popen

    # =====================================================================
    # The EDMA call site actually opts in
    # =====================================================================
    import gemmi

    recorded = {}

    class _Stop(Exception):
        pass

    def fake_run_command(cmd, cwd, log_path, log, **kwargs):
        recorded["cmd"] = list(cmd)
        recorded["cwd"] = cwd
        recorded["kwargs"] = dict(kwargs)
        raise _Stop()

    def fake_normalize(src, dst, log=None):
        Path(dst).write_text("map", encoding="utf-8")
        return dst

    real_run_command = appmod.run_command
    real_normalize = appmod.normalize_xplor_for_edma
    real_plimit = appmod.edma_absolute_plimit
    try:
        appmod.run_command = fake_run_command
        appmod.normalize_xplor_for_edma = fake_normalize
        appmod.edma_absolute_plimit = lambda path, sigma: (1.0, 0.5)

        ref_ctx = appmod.ReferenceContext(
            cif_path=tmp / "ref.cif",
            work_ref_cif=tmp / "ref_work.cif",
            cell=gemmi.UnitCell(10, 10, 10, 90, 90, 90),
            spacegroup=gemmi.SpaceGroup("P 1"),
            spacegroup_hm="P 1",
            composition="C 4",
            atoms=[],
        )
        xplor = tmp / "cycle.xplor"
        xplor.write_text("map", encoding="utf-8")
        out_dir = tmp / "edma_out"
        try:
            appmod.run_edma_on_xplor(
                xplor_map=xplor,
                out_dir=out_dir,
                prefix="cyc001",
                ref_ctx=ref_ctx,
                plimit_sigma=3.0,
                merge_distance_a=0.5,
                edma_exe="EDMA.exe",
                log=lambda _m: None,
            )
        except _Stop:
            pass
        check("EDMA launch was routed through run_command", "kwargs" in recorded)
        check(
            "EDMA is launched with hide_console=True",
            recorded.get("kwargs", {}).get("hide_console") is True,
        )
        check(
            "EDMA command line is unchanged (exe + input file name)",
            recorded.get("cmd") == ["EDMA.exe", "cyc001_edma.inp"],
        )
        check(
            "EDMA working directory is unchanged (the cycle output directory)",
            Path(str(recorded.get("cwd", ""))) == out_dir,
        )
        check(
            "EDMA still receives the stop_event for cancellation",
            "stop_event" in recorded.get("kwargs", {}),
        )
    finally:
        appmod.run_command = real_run_command
        appmod.normalize_xplor_for_edma = real_normalize
        appmod.edma_absolute_plimit = real_plimit

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
