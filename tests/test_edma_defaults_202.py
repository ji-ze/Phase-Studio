"""Guards for Phase Studio 2.0.2's normal-workflow EDMA defaults."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from phase_studio import app as appmod
from phase_studio import autosolve_review as guided
from phase_studio.edma_defaults import NORMAL_EDMA_THRESHOLD_SIGMA
from phase_studio import jana_superflip as js


def main() -> None:
    checks = 0

    def check(label: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(label)

    check("one authoritative normal EDMA default is 0.50 sigma", NORMAL_EDMA_THRESHOLD_SIGMA == 0.5)
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        inflip = tmp / "job.inflip"
        inflip.write_text("title fixture\n", encoding="utf-8")
        original_application_dir = js.application_dir
        original_superflip = js.resolve_active_jana_superflip
        original_jana_root = js.resolve_jana_installation_root
        js.application_dir = lambda: tmp
        js.resolve_active_jana_superflip = lambda _path: tmp / "SUPERFLIP" / "superflip.exe"
        js.resolve_jana_installation_root = lambda _path: tmp
        try:
            for cycles in (1, 2, 5):
                imported = js.build_jana_handoff_import(
                    inflip,
                    js.JanaRunOptions(action="run", cycles=cycles),
                    {"plimit_superflip": "0.30", "plimit_deblur": "0.50"},
                )
                check(
                    f"fresh {cycles}-cycle Jana workflow overrides legacy thresholds",
                    float(imported.values["plimit_superflip"]) == 0.5
                    and float(imported.values["plimit_deblur"]) == 0.5,
                )
                check(
                    f"fresh {cycles}-cycle defaults are explicit handoff authority",
                    "plimit_superflip" in imported.handoff_keys and "plimit_deblur" in imported.handoff_keys,
                )
        finally:
            js.application_dir = original_application_dir
            js.resolve_active_jana_superflip = original_superflip
            js.resolve_jana_installation_root = original_jana_root

    app = QApplication.instance() or QApplication([])
    original_load = appmod.IterativeSuperflipPipelineQtGUI.load_settings
    original_save = appmod.IterativeSuperflipPipelineQtGUI.save_settings
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    try:
        window = appmod.IterativeSuperflipPipelineQtGUI()
        check(
            "fresh controls sharing normal policy initialize to 0.50/0.50",
            window._dspin_value("plimit_superflip") == 0.5
            and window._dspin_value("plimit_deblur") == 0.5,
        )
        window._set_widget_value_from_string(window.inputs["plimit_superflip"], "0.8")
        window._set_widget_value_from_string(window.inputs["plimit_deblur"], "1.2")
        check(
            "explicit user threshold edits remain available",
            window._dspin_value("plimit_superflip") == 0.8
            and window._dspin_value("plimit_deblur") == 1.2,
        )
        window._apply_workflow_preset("Recommended")
        check(
            "normal recommended preset resets both defaults to 0.50",
            window._dspin_value("plimit_superflip") == 0.5
            and window._dspin_value("plimit_deblur") == 0.5,
        )
        # Simulate persisted controls before Jana's explicit fresh-workflow
        # overlay. Neither the old normal default nor a prior user run leaks.
        for remembered in ('0.30', '1.00'):
            for key in ('plimit_superflip', 'plimit_deblur'):
                window._set_widget_value_from_string(window.inputs[key], remembered)
            window._apply_workflow_preset('recommended')
            check(
                f'fresh normal workflow replaces remembered {remembered} thresholds',
                window._dspin_value('plimit_superflip') == 0.5
                and window._dspin_value('plimit_deblur') == 0.5,
            )
        window.close()
    finally:
        appmod.IterativeSuperflipPipelineQtGUI.load_settings = original_load
        appmod.IterativeSuperflipPipelineQtGUI.save_settings = original_save

    check("+ atoms from 0.50 selects 0.40", guided.stepped_threshold(0.5, True) == 0.4)
    check("- atoms from 0.50 selects 0.60", guided.stepped_threshold(0.5, False) == 0.6)
    check("two + atoms steps select 0.30", guided.stepped_threshold(guided.stepped_threshold(0.5, True), True) == 0.3)
    check("two - atoms steps select 0.70", guided.stepped_threshold(guided.stepped_threshold(0.5, False), False) == 0.7)
    check("Autosolve retains its separate 1.00 sigma policy", guided.OBSERVED_THRESHOLD_SIGMA == guided.PREDICTED_THRESHOLD_SIGMA == 1.0)
    print(f"EDMA default checks passed: {checks}")


if __name__ == "__main__":
    main()
