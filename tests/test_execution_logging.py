"""Concise GUI/full forensic logging and project-path guards."""
import re
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase_studio.app import ExecutionLogRecord, RunDiagnosticLog, classify_log_record
from phase_studio.error_reporting import build_error_report
from phase_studio.jana_superflip import jana_project_log_path, safe_wrapper_log_dir


failures = []


def check(name, condition):
    print(("PASS" if condition else "FAIL") + " - " + name)
    if not condition:
        failures.append(name)


def main():
    root = Path(tempfile.mkdtemp())
    project = root / "Test User" / "Jana projekt Žluťoučký"
    install = root / "Program Files" / "Jana2020" / "SUPERFLIP"
    run_dir = project / "phase_studio_full_run_job" / "run_0003"
    project.mkdir(parents=True)
    install.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    inflip = project / "job with spaces.inflip"
    inflip.write_text("title test\n", encoding="utf-8")
    sf = install / "superflip_original.exe"
    edma = install / "EDMA.exe"
    sf.write_bytes(b"program")
    edma.write_bytes(b"program")

    cfg = SimpleNamespace(
        run_id="run_0003", jana_inflip=inflip, hkl=project / "job.hkl",
        work_dir=run_dir, superflip_exe=sf, edma_exe=edma,
        sharped_base_url="https://sharped.example.test",
    )
    before_install = {p.relative_to(install): p.read_bytes() for p in install.rglob("*") if p.is_file()}
    log = RunDiagnosticLog(run_dir / "log.txt", cfg)
    records = (
        ExecutionLogRecord("Superflip complete", "SUCCESS", "Superflip", "SCIENTIFIC_RESULT"),
        ExecutionLogRecord(
            f"Map: {run_dir / 'map.xplor'} · SHA-256 abcdef", "DETAIL", "SharpED", "DIAGNOSTIC",
        ),
        ExecutionLogRecord("Charge-flipping solution · EDMA started", "INFO", "EDMA", "USER_PROGRESS"),
    )
    threads = [threading.Thread(target=log.write, args=(record,)) for record in records]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    log.close()
    text = (run_dir / "log.txt").read_text(encoding="utf-8")

    check("run diagnostic log is anchored inside the isolated run directory",
          (run_dir / "log.txt").is_file())
    check("project-level log indexes the GUI run and its run diagnostic path",
          "Phase Studio 2.0.4 · run_0003" in (project / "log.txt").read_text(encoding="utf-8")
          and f"Run log: {(run_dir / 'log.txt').resolve()}" in (project / "log.txt").read_text(encoding="utf-8"))
    check("run log identifies project, input, run and program locations",
          all(token in text for token in (
              str(project.resolve()), str(inflip.resolve()), "Run: run_0003",
              str(sf), str(edma), str(run_dir.resolve()),
              "Phase Studio version: 2.0.4", "Project log:", "Run log:",
              "Input .inflip:", "Phase Studio integration root:",
              "SharpED endpoint: https://sharped.example.test",
          )))
    check("every concurrent record has a millisecond timestamp and category",
          len(re.findall(r"^\d{2}:\d{2}:\d{2}\.\d{3} \[", text, re.MULTILINE)) == len(records))
    check("persistent diagnostics retain paths and hashes hidden from the GUI",
          "SHA-256 abcdef" in text and str(run_dir / "map.xplor") in text)
    check("program installation remains byte-identical and receives no generated files",
          before_install == {p.relative_to(install): p.read_bytes() for p in install.rglob("*") if p.is_file()})

    path_record = classify_log_record(f"Output: {run_dir / 'map.xplor'} · SHA-256 abc")
    progress_record = classify_log_record("SharpED processing", subsystem="SharpED")
    result_record = classify_log_record("EDMA complete", level="SUCCESS", subsystem="EDMA")
    normalize_record = classify_log_record(
        "Superflip normalize value 'atoms' is not passed to Superflip; the normalize keyword is omitted for compatibility.",
        level="WARNING", subsystem="Superflip",
    )
    tile_detail = classify_log_record("[SharpED] Uploading tile_0001_in.xplor · 12.0 MiB")
    tile_summary = classify_log_record("[SharpED] Tile 2/4 complete")
    polling_record = classify_log_record("[SharpED] Processing…", subsystem="SharpED")
    tls_record = classify_log_record("TLS trust: system CA bundle", subsystem="SharpED")
    check("absolute paths and hashes classify as DIAGNOSTIC", path_record.category == "DIAGNOSTIC")
    check("workflow transitions classify as USER_PROGRESS", progress_record.category == "USER_PROGRESS")
    check("successful scientific results classify as SCIENTIFIC_RESULT",
          result_record.category == "SCIENTIFIC_RESULT")
    check("expected normalize compatibility text stays in the detailed log",
          normalize_record.category == "DIAGNOSTIC")
    check("per-tile filenames stay diagnostic while tile summaries remain user-visible",
          tile_detail.category == "DIAGNOSTIC"
          and tile_summary.category == "SCIENTIFIC_RESULT")
    check("TLS trust and repeated HTTP polling remain diagnostic-only",
          polling_record.category == "DIAGNOSTIC" and tls_record.category == "DIAGNOSTIC")
    check("incoming .inflip determines the project log despite unrelated CWD/install paths",
          jana_project_log_path(inflip_path=inflip) == project.resolve() / "log.txt")
    check("missing project context falls back to writable temp rather than CWD/executable",
          jana_project_log_path().parent == safe_wrapper_log_dir()
          and jana_project_log_path().parent not in {project.resolve(), install.resolve()})

    resolver_report = build_error_report(
        FileNotFoundError(
            r"The active Jana2020 Superflip executable was not found: "
            r"C:\Jana2020\SharpED\SUPERFLIP\superflip.exe"
        ),
        subsystem="Jana2020", operation="Resolve Superflip executable",
    )
    check("Superflip path resolution is classified as Jana integration, never SharpED server",
          resolver_report.subsystem == "Jana2020 integration"
          and resolver_report.category == "superflip_runtime"
          and resolver_report.operation == "Resolve Superflip executable"
          and resolver_report.summary == (
              "The Superflip executable for the active Jana2020 installation could not be resolved."
          ))

    blocked_parent = root / "blocked-run-log-parent"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    fallback_cfg = SimpleNamespace(**{**cfg.__dict__, "run_id": "run_0004"})
    fallback_log = RunDiagnosticLog(blocked_parent / "run_0004" / "log.txt", fallback_cfg)
    fallback_path = fallback_log.path
    fallback_reason = fallback_log.fallback_reason
    fallback_log.close()
    check("unwritable preferred run log falls back to OS runtime storage without breaking execution",
          bool(fallback_reason) and fallback_path.is_file()
          and str(fallback_path).startswith(str(Path(tempfile.gettempdir()).resolve()))
          and install.resolve() not in fallback_path.parents)

    if failures:
        print(f"\n{len(failures)} check(s) FAILED: {failures}")
        return 1
    print(f"\nAll {16} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
