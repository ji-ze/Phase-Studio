"""Regression tests for the model/reference file-selector formats.

Plain Python test (no pytest dependency; run with
`python tests/test_model_formats.py`), following this project's usual
checks-list-plus-exit-code convention.

Every model and reference selector -- in the main window and in the Jana2020
Wizard -- must build its file-dialog filter from one authoritative helper, and
no selector may offer an extension the code cannot actually handle.

The audit behind these sets:

  reference        REFERENCE_STRUCTURE_SUFFIXES | REFERENCE_DENSITY_SUFFIXES,
                   the same sets the reference-handling code already tests
                   suffixes against.
  Superflip model  exactly what run_superflip_cycle() will pass to Superflip as
                   a modelfile: .xplor (normalized first), .cif and .ccp4.
                   It raises for anything else.
  wrapper ref      the narrower .cif/.xplor set the single-pass Jana2020
                   wrapper validates; it rejects the rest, so offering more
                   would only produce a late failure.
"""
import inspect
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results_log = []


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


def extensions_in(filter_text):
    """Every extension a Qt filter string offers, excluding the catch-all."""
    found = set()
    for match in re.findall(r"\(([^)]*)\)", filter_text):
        for pattern in match.split():
            pattern = pattern.strip()
            if pattern in ("*", "*.*"):
                continue
            if pattern.startswith("*."):
                found.add(pattern[1:].lower())
    return found


def main():
    import phase_studio.app as appmod
    import phase_studio.jana_superflip as js

    # =====================================================================
    # The authoritative helpers exist and agree with the audited sets
    # =====================================================================
    for name in (
        "supported_reference_filters",
        "supported_model_filters",
        "supported_structure_filters",
        "supported_density_map_filters",
        "supported_wrapper_reference_filters",
    ):
        check("authoritative helper %s() exists" % name, hasattr(appmod, name))

    reference = appmod.supported_reference_filters()
    model = appmod.supported_model_filters()
    wrapper_reference = appmod.supported_wrapper_reference_filters()

    check(
        "reference filter offers exactly the audited reference suffixes",
        extensions_in(reference) == set(appmod.REFERENCE_FILE_SUFFIXES),
    )
    check(
        "model filter offers exactly what Superflip accepts as a modelfile",
        extensions_in(model) == set(appmod.SUPERFLIP_MODEL_SUFFIXES),
    )
    check(
        "wrapper reference filter offers exactly the wrapper's accepted set",
        extensions_in(wrapper_reference) == set(appmod.WRAPPER_REFERENCE_SUFFIXES),
    )
    check(
        "structure and density groups partition the reference set",
        set(appmod.REFERENCE_STRUCTURE_SUFFIXES) | set(appmod.REFERENCE_DENSITY_SUFFIXES)
        == set(appmod.REFERENCE_FILE_SUFFIXES),
    )

    # =====================================================================
    # Every offered extension is demonstrably supported by real code
    # =====================================================================
    model_source = inspect.getsource(appmod.run_superflip_cycle)
    for suffix in sorted(appmod.SUPERFLIP_MODEL_SUFFIXES):
        check(
            "model format %s is handled by run_superflip_cycle" % suffix,
            ('"%s"' % suffix) in model_source or ("'%s'" % suffix) in model_source,
        )
    check(
        "run_superflip_cycle rejects anything outside the offered model set",
        "Unsupported modelfile" in model_source,
    )
    # Nothing beyond what Superflip is actually given may be offered.
    check(
        "no model format is offered that Superflip is never given",
        extensions_in(model) <= set(appmod.SUPERFLIP_MODEL_SUFFIXES),
    )

    wrapper_source = inspect.getsource(js.run_jana_superflip)
    for suffix in sorted(appmod.WRAPPER_REFERENCE_SUFFIXES):
        check(
            "wrapper reference format %s appears in the wrapper's own validation" % suffix,
            ('"%s"' % suffix) in wrapper_source,
        )
    check(
        "the wrapper reference set is a subset of the full reference set",
        set(appmod.WRAPPER_REFERENCE_SUFFIXES) <= set(appmod.REFERENCE_FILE_SUFFIXES),
    )

    # Reference suffixes are the ones the reference-handling code tests against.
    app_source = inspect.getsource(appmod)
    check(
        "reference suffix sets are the ones the reference code actually uses",
        "REFERENCE_STRUCTURE_SUFFIXES" in app_source
        and "REFERENCE_DENSITY_SUFFIXES" in app_source,
    )

    # =====================================================================
    # Every selector uses the shared helper, with no local extension lists
    # =====================================================================
    build_source = inspect.getsource(appmod.IterativeSuperflipPipelineQtGUI)
    check(
        "main window reference selector uses the shared helper",
        "supported_reference_filters()" in build_source,
    )
    check(
        "main window initial-model selector uses the shared helper",
        "supported_model_filters()" in build_source,
    )

    wizard_source = inspect.getsource(js._JanaWorkflowWizard)
    check(
        "Wizard reference selector uses the shared helper",
        "supported_wrapper_reference_filters()" in wizard_source,
    )
    check(
        "Wizard initial-model selector uses the shared helper",
        "supported_model_filters()" in wizard_source,
    )

    # No selector may carry its own inline extension list any more.
    inline = re.findall(r'"[^"]*\*\.(?:cif|xplor|ccp4|m80)[^"]*"', build_source + wizard_source)
    check(
        "no selector carries a duplicated inline extension list",
        not inline,
    )

    # =====================================================================
    # The reference selector is named for what it accepts
    # =====================================================================
    check(
        "the reference selector is labelled a model, since it accepts maps too",
        '"Reference model"' in build_source,
    )
    # Scoped to the FILE SELECTOR row. The "Reference structure" metadata-source
    # option is a different label and stays: crystal metadata atoms are read
    # only from REFERENCE_STRUCTURE_SUFFIXES, so there it is accurate.
    selector_rows = re.findall(r'_add_path\([^)]*"reference_cif"[^)]*\)', build_source)
    check("the reference file-selector row was found", len(selector_rows) == 1)
    if selector_rows:
        check(
            "the reference selector row no longer calls itself a structure",
            "Reference structure" not in selector_rows[0],
        )
    check(
        "the metadata-source option keeps its structure-specific name",
        '"Reference structure"' in inspect.getsource(appmod),
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
