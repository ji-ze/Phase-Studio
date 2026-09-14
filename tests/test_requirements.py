"""Regression tests for the shared pre-run requirements check.

Plain Python test (no pytest dependency; run with
`python tests/test_requirements.py`), following this project's usual
checks-list-plus-exit-code convention.

One authoritative implementation (phase_studio/requirements.py) decides whether
a requested workflow can start, and both the full Phase Studio GUI and the
Jana2020 Wizard use it, so the rules cannot drift apart.

The network is never contacted here: the SharpED client is replaced with stubs,
so the failure classification is asserted rather than hoped for.
"""
import os
import sys
import tempfile
import io
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def make_exe(directory, name):
    path = Path(directory) / name
    path.write_bytes(b"MZ fake executable")
    return path


def main():
    from phase_studio import requirements as reqs

    State = reqs.RequirementState
    Kind = reqs.RequirementKind

    # =====================================================================
    # Superflip
    # =====================================================================
    tmp = Path(tempfile.mkdtemp())
    empty = Path(tempfile.mkdtemp())

    real = make_exe(tmp, "superflip.exe")  # no marker -> a genuine Superflip
    status = reqs.check_superflip(str(real), jana_dir=empty)
    check("a configured, existing Superflip is accepted", status.ok)
    check("the accepted Superflip reports its path", status.path == real.resolve())

    status = reqs.check_superflip("", jana_dir=empty)
    check("an unconfigured Superflip is reported as not configured",
          status.state is State.NOT_CONFIGURED)
    check("an unconfigured Superflip is not OK", not status.ok)

    status = reqs.check_superflip(str(tmp / "does_not_exist.exe"), jana_dir=empty)
    check("a missing Superflip path is reported as not found",
          status.state is State.NOT_FOUND)

    wrong = make_exe(tmp, "unrelated.exe")
    status = reqs.check_superflip(str(wrong), jana_dir=empty)
    check("an arbitrary executable is not accepted as Superflip",
          status.state is State.WRONG_EXECUTABLE)

    # --- auto-detection from the standard Jana2020 directory ----------
    jana = Path(tempfile.mkdtemp())
    original = make_exe(jana, reqs.ORIGINAL_EXE_NAME)
    make_exe(jana, reqs.WRAPPER_EXE_NAME)
    status = reqs.check_superflip("", jana_dir=jana)
    check("an unconfigured Superflip is auto-detected in the Jana2020 directory",
          status.suggested_path == original.resolve())
    check("auto-detection prefers superflip_original.exe over superflip.exe",
          status.suggested_path is not None
          and status.suggested_path.name == reqs.ORIGINAL_EXE_NAME)

    # --- the Phase Studio wrapper must never be accepted as Superflip --
    marked = Path(tempfile.mkdtemp())
    wrapper = make_exe(marked, reqs.WRAPPER_EXE_NAME)
    marked_original = make_exe(marked, reqs.ORIGINAL_EXE_NAME)
    (marked / "phase_studio_integration.json").write_text(
        '{"product": "Phase Studio", "version": "1.0.8",'
        ' "wrapper": "superflip.exe", "original_superflip": "superflip_original.exe"}',
        encoding="utf-8",
    )
    check("a marked superflip.exe is identified as the Phase Studio wrapper",
          reqs.is_phase_studio_wrapper(wrapper))
    check("superflip_original.exe is never identified as the wrapper",
          not reqs.is_phase_studio_wrapper(marked_original))

    status = reqs.check_superflip(str(wrapper), jana_dir=empty)
    check("configuring the wrapper as Superflip is rejected",
          status.state is State.IS_PHASE_STUDIO_WRAPPER)
    check("rejecting the wrapper is not silently OK", not status.ok)
    check("rejecting the wrapper suggests the real executable beside it",
          status.suggested_path == marked_original)
    check("the wrapper rejection explains itself",
          "launcher" in status.message.lower())

    # An unmarked superflip.exe is a genuine Superflip and stays usable.
    plain = Path(tempfile.mkdtemp())
    plain_exe = make_exe(plain, reqs.WRAPPER_EXE_NAME)
    check("an unmarked superflip.exe is NOT assumed to be the wrapper",
          not reqs.is_phase_studio_wrapper(plain_exe))
    check("an unmarked superflip.exe is accepted as Superflip",
          reqs.check_superflip(str(plain_exe), jana_dir=empty).ok)

    # =====================================================================
    # EDMA
    # =====================================================================
    edma = make_exe(jana, reqs.EDMA_EXE_NAME)
    check("a configured, existing EDMA is accepted",
          reqs.check_edma(str(edma), jana_dir=empty).ok)
    check("an unconfigured EDMA is auto-detected in the Jana2020 directory",
          reqs.check_edma("", jana_dir=jana).suggested_path == edma.resolve())
    check("a missing EDMA is reported as not found",
          reqs.check_edma(str(tmp / "nope.exe"), jana_dir=empty).state is State.NOT_FOUND)
    check("an arbitrary executable is not accepted as EDMA",
          reqs.check_edma(str(wrong), jana_dir=empty).state is State.WRONG_EXECUTABLE)

    # The automatic installer copies only the expected member from the
    # official-style ZIP into a Phase Studio-owned directory.
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("package/readme.txt", "third-party package")
        archive.writestr("package/superflip.exe", b"MZ downloaded Superflip")

    class _Response(io.BytesIO):
        pass

    download_root = Path(tempfile.mkdtemp()) / "tools"
    downloaded = reqs.download_requirement_executable(
        Kind.SUPERFLIP,
        download_root,
        opener=lambda *_args, **_kwargs: _Response(archive_bytes.getvalue()),
    )
    check("automatic download installs the expected executable", downloaded.is_file())
    check("automatic download does not extract unrelated archive files",
          not (download_root / "readme.txt").exists())
    check("the automatically installed executable passes the same validation",
          reqs.check_superflip(str(downloaded), jana_dir=empty).ok)

    # =====================================================================
    # SharpED: classification, with the network stubbed out
    # =====================================================================
    class _Models:
        models = ["koala 2.0"]
        default_model = "koala 2.0"

    def factory(result=None, error=None):
        class _Client:
            def __init__(self, **_kwargs):
                pass

            def get_models(self, *_args, **_kwargs):
                if error is not None:
                    raise error
                return result

        return _Client

    status = reqs.check_sharped_api("https://jana.fzu.cz", "")
    check("a missing token is reported without contacting the server",
          status.state is State.TOKEN_MISSING)
    check("the missing-token message names the token",
          "token" in status.message.lower())

    status = reqs.check_sharped_api("https://jana.fzu.cz", "tok",
                                    client_factory=factory(result=_Models()))
    check("a healthy SharpED response is accepted", status.ok)

    class _HttpError(Exception):
        def __init__(self, code):
            super().__init__("HTTP Error %d" % code)
            self.code = code

    for code in (401, 403):
        status = reqs.check_sharped_api("https://jana.fzu.cz", "tok",
                                        client_factory=factory(error=_HttpError(code)))
        check("HTTP %d is classified as a rejected token" % code,
              status.state is State.TOKEN_REJECTED)
        check("HTTP %d advises creating a new token" % code,
              "Create token" in status.message)

    status = reqs.check_sharped_api("https://jana.fzu.cz", "tok",
                                    client_factory=factory(error=ConnectionError("refused")))
    check("a connection failure is classified as server unreachable",
          status.state is State.SERVER_UNREACHABLE)
    check("a network failure does NOT tell the user to replace their token",
          "token" not in status.message.lower())
    check("a network failure mentions the connection",
          "internet connection" in status.message.lower())

    status = reqs.check_sharped_api("https://jana.fzu.cz", "tok",
                                    client_factory=factory(error=ValueError("Expecting value: line 1")))
    check("a malformed response is classified as such",
          status.state is State.MALFORMED_RESPONSE)

    status = reqs.check_sharped_api("https://jana.fzu.cz", "tok",
                                    client_factory=factory(result=object()))
    check("a response without a model list is malformed",
          status.state is State.MALFORMED_RESPONSE)

    status = reqs.check_sharped_api("https://jana.fzu.cz", "tok",
                                    client_factory=factory(error=_HttpError(503)))
    check("a 5xx server error is classified as unreachable, not a bad token",
          status.state is State.SERVER_UNREACHABLE)

    status = reqs.check_sharped_api(
        "https://jana.fzu.cz", "tok",
        client_factory=factory(error=RuntimeError("unexpected public catalog failure")),
    )
    check("an unknown public request failure does not reject the token",
          status.state is State.MALFORMED_RESPONSE)

    # --- the token must never appear anywhere user-visible -------------
    secret = "SECRET-TOKEN-abcdef123456"
    leaks = []
    for error in (_HttpError(401), ConnectionError("refused to " + secret),
                  ValueError("bad json from https://x?token=" + secret)):
        st = reqs.check_sharped_api("https://jana.fzu.cz", secret,
                                    client_factory=factory(error=error))
        for text in (st.message, st.detail, str(st.state.value), st.title):
            if secret in str(text):
                leaks.append(str(text))
    check("the API token never appears in any status message or detail", not leaks)

    # =====================================================================
    # Only what the workflow needs is checked
    # =====================================================================
    required = reqs.requirements_for_workflow(needs_superflip=True, needs_edma=False,
                                              needs_sharped=False)
    check("a Superflip-only workflow asks for Superflip alone",
          required.kinds() == [Kind.SUPERFLIP])
    result = reqs.run_preflight(required, superflip_path=str(real), edma_path="",
                                jana_dir=empty)
    check("an EDMA-free workflow is not blocked by a missing EDMA", result.ok)

    result = reqs.run_preflight(
        reqs.requirements_for_workflow(
            needs_superflip=True, needs_edma=False, needs_sharped=False,
        ),
        superflip_path=str(real), sharped_token="", jana_dir=empty,
    )
    check("a SharpED-disabled workflow is not blocked by a missing token", result.ok)

    result = reqs.run_preflight(
        reqs.requirements_for_workflow(
            needs_superflip=True, needs_edma=False, needs_sharped=True,
        ),
        superflip_path=str(real), sharped_token="", jana_dir=empty,
    )
    check("a SharpED-enabled workflow is blocked by a missing token",
          not result.ok and result.first_failure.kind is Kind.SHARPED)

    required = reqs.requirements_for_workflow(needs_superflip=True, needs_edma=True,
                                              needs_sharped=False)
    check("remediation order is Superflip, then EDMA, then SharpED",
          required.kinds() == [Kind.SUPERFLIP, Kind.EDMA])
    result = reqs.run_preflight(required, superflip_path=str(real),
                                edma_path=str(tmp / "missing.exe"), jana_dir=empty)
    check("a workflow that needs EDMA IS blocked by a missing EDMA", not result.ok)
    check("only the failing requirement is reported",
          [f.kind for f in result.failures] == [Kind.EDMA])
    check("the first failure is offered for remediation first",
          result.first_failure is not None and result.first_failure.kind is Kind.EDMA)

    # --- automatic repair from the standard location -------------------
    required = reqs.requirements_for_workflow(needs_superflip=True, needs_edma=True,
                                              needs_sharped=False)
    result = reqs.run_preflight(required, superflip_path="", edma_path="",
                                jana_dir=jana, accept_suggestion=lambda _s: True)
    check("a correct Jana2020 installation satisfies the preflight unaided", result.ok)
    check("both repaired paths are reported back to the caller",
          len(result.repaired) == 2)
    check("the repaired Superflip is the real executable, not the wrapper",
          all(r.path.name != reqs.WRAPPER_EXE_NAME
              for r in result.repaired if r.kind is Kind.SUPERFLIP))

    marked_edma = make_exe(marked, reqs.EDMA_EXE_NAME)
    result = reqs.run_preflight(
        required, superflip_path=str(wrapper), edma_path="",
        jana_dir=marked, accept_suggestion=lambda _status: True,
    )
    check("combined Jana auto-detection chooses original Superflip beside the marked wrapper",
          result.ok and any(
              repaired.kind is Kind.SUPERFLIP and repaired.path == marked_original.resolve()
              for repaired in result.repaired
          ))
    check("combined Jana auto-detection chooses Jana's EDMA without modifying it",
          marked_edma.read_bytes() == b"MZ fake executable"
          and any(
              repaired.kind is Kind.EDMA and repaired.path == marked_edma.resolve()
              for repaired in result.repaired
          ))

    # Declining a suggestion must not silently satisfy the requirement.
    result = reqs.run_preflight(required, superflip_path="", edma_path="",
                                jana_dir=jana, accept_suggestion=lambda _s: False)
    check("declining an auto-detected path leaves the requirement unsatisfied",
          not result.ok)

    # =====================================================================
    # The GUI uses this same module
    # =====================================================================
    import inspect
    import phase_studio.app as appmod

    source = inspect.getsource(appmod.IterativeSuperflipPipelineQtGUI)
    check("the main window runs the shared preflight before a workflow starts",
          "_run_workflow_preflight" in source)
    check("the preflight is driven after configuration validation and before the worker",
          "if not self._ensure_workflow_requirements(cfg)" in source)
    check("the main window imports the shared requirements module",
          "from phase_studio import requirements as reqs" in source)

    import phase_studio.jana_superflip as jana
    wizard_source = inspect.getsource(jana._JanaWorkflowWizard)
    check("the Jana Wizard calls the shared requirement gate",
          "_ensure_workflow_requirements" in wizard_source)
    check("the obsolete generic missing-token warning is gone",
          "_show_missing_token_warning" not in inspect.getsource(jana))

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
