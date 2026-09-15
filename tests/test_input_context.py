"""Resolved input/configuration boundary and GUI capture guards."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from phase_studio import app as appmod
    from phase_studio import input_context as context

    app = QApplication.instance() or QApplication([sys.argv[0]])
    checks = []

    def check(name, condition):
        checks.append((name, bool(condition)))
        print(("PASS" if condition else "FAIL") + " - " + name)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        inflip = root / "job.inflip"
        inflip.write_text(
            "title input context\ncell 10 10 10 90 90 90\nspacegroup P1\n"
            "composition C 1\nfbegin\n0 0 1 10 1\nfend\n",
            encoding="utf-8",
        )
        hkl = root / "external.hkl"
        hkl.write_text("1 0 0 10 1\n", encoding="utf-8")
        reference = root / "reference.cif"
        reference.write_text(
            "data_ref\n_cell_length_a 10\n_cell_length_b 10\n_cell_length_c 10\n"
            "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
            "_space_group_name_H-M_alt 'P 1'\n_chemical_formula_sum 'C 1'\n",
            encoding="utf-8",
        )
        initial_model = root / "initial.xplor"
        initial_model.write_text("model", encoding="utf-8")

        external = context.resolve_run_inputs(
            input_mode=context.INPUT_MODE_EXTERNAL,
            hkl_value=str(hkl), jana_inflip_value=str(inflip),
            reference_value=str(reference), first_model_value=str(initial_model),
            launched_from_jana_wizard=False, structure_suffixes={".cif", ".ins", ".res"},
        )
        check("External HKL resolves the selected scientific HKL", external.hkl == hkl.resolve())
        check("External HKL ignores a stale remembered .inflip", external.jana_inflip is None)
        check("reference model resolves as both structure and Superflip reference",
              external.reference_cif == reference.resolve()
              and external.superflip_referencefile == reference.resolve())
        check("initial model is captured as an independent resolved path",
              external.first_cycle_modelfile == initial_model.resolve())
        check("standalone input resolution cannot enable Jana handoff", not external.jana_return_to_jana)

        embedded = context.resolve_run_inputs(
            input_mode=context.INPUT_MODE_INFLIP,
            hkl_value="", jana_inflip_value=str(inflip), reference_value="",
            first_model_value="", launched_from_jana_wizard=True,
            structure_suffixes={".cif", ".ins", ".res"},
        )
        check("Jana input preserves the original resolved .inflip", embedded.jana_inflip == inflip.resolve())
        check("pure Jana input records embedded HKL and reference sentinels",
              context.uses_embedded_hkl(embedded.hkl)
              and embedded.reference_cif.name == context.USE_REFERENCE_FROM_INFLIP)
        check("Jana launch plus active .inflip enables handoff", embedded.jana_return_to_jana)

        overridden = context.resolve_run_inputs(
            input_mode=context.INPUT_MODE_INFLIP_OVERRIDES,
            hkl_value="", jana_inflip_value=str(inflip), reference_value=str(reference),
            first_model_value=str(initial_model), launched_from_jana_wizard=True,
            structure_suffixes={".cif", ".ins", ".res"},
        )
        check("empty HKL override retains embedded-HKL fallback", context.uses_embedded_hkl(overridden.hkl))
        check("Jana override retains external reference and initial model",
              overridden.superflip_referencefile == reference.resolve()
              and overridden.first_cycle_modelfile == initial_model.resolve())

        check("External mode rejects inactive Jana metadata in favor of reference",
              context.reconcile_metadata_source(
                  context.METADATA_SOURCE_INFLIP, context.INPUT_MODE_EXTERNAL,
                  str(inflip), str(reference), {".cif", ".ins", ".res"},
              ) == context.METADATA_SOURCE_REFERENCE)
        check("missing metadata inputs fall back to manual",
              context.reconcile_metadata_source(
                  context.METADATA_SOURCE_REFERENCE, context.INPUT_MODE_EXTERNAL,
                  str(inflip), str(root / "missing.cif"), {".cif", ".ins", ".res"},
              ) == context.METADATA_SOURCE_MANUAL)
        availability = context.input_control_availability(
            context.INPUT_MODE_EXTERNAL, context.METADATA_SOURCE_REFERENCE,
        )
        check("Basic input control availability follows resolved External mode",
              availability == {"jana_inflip": False, "hkl": True,
                               "reference_cif": True, "reflection_data_mode": True})

        real_save = appmod.IterativeSuperflipPipelineQtGUI.save_settings
        real_load = appmod.IterativeSuperflipPipelineQtGUI.load_settings
        with patch.object(appmod.IterativeSuperflipPipelineQtGUI, "load_settings"), \
             patch.object(appmod.IterativeSuperflipPipelineQtGUI, "save_settings"), \
             patch.object(appmod.IterativeSuperflipPipelineQtGUI, "refresh_sharped_models"):
            window = appmod.IterativeSuperflipPipelineQtGUI()
        window.settings = QSettings(str(root / "settings.ini"), QSettings.IniFormat)
        window._set_widget_value_from_string(window.inputs["input_source_mode"],
                                             appmod.INPUT_MODE_LABELS[appmod.INPUT_MODE_EXTERNAL])
        window._set_widget_value_from_string(window.inputs["jana_inflip"], str(inflip))
        window._set_widget_value_from_string(window.inputs["hkl"], str(hkl))
        window._set_widget_value_from_string(window.inputs["reference_cif"], str(reference))
        window._set_widget_value_from_string(window.inputs["first_cycle_modelfile"], str(initial_model))
        window._set_widget_value_from_string(window.inputs["metadata_source"],
                                             appmod.METADATA_SOURCE_LABELS[appmod.METADATA_SOURCE_REFERENCE])
        captured = window.get_config()
        check("GUI capture uses the resolved External HKL boundary",
              captured.hkl == hkl.resolve() and captured.jana_inflip is None)
        check("GUI capture preserves reference and initial models",
              captured.reference_cif == reference.resolve()
              and captured.first_cycle_modelfile == initial_model.resolve())
        window._set_widget_value_from_string(window.inputs["hkl"], str(root / "later.hkl"))
        window._set_widget_value_from_string(window.inputs["reference_cif"], str(root / "later.cif"))
        check("captured RunConfig is unaffected by later widget edits",
              captured.hkl == hkl.resolve() and captured.reference_cif == reference.resolve())
        window.last_run_config = captured
        window.results = [object()]
        check("standalone cannot enter Jana handoff with stale .inflip state",
              not window._jana_wizard_handoff_available())

        window.jana_wizard_context = appmod.JanaWizardContext(
            launched_from_jana_wizard=True, launch_mode="full_configuration",
        )
        window._set_widget_value_from_string(window.inputs["input_source_mode"],
                                             appmod.INPUT_MODE_LABELS[appmod.INPUT_MODE_INFLIP])
        window._set_widget_value_from_string(window.inputs["jana_inflip"], str(inflip))
        window._set_widget_value_from_string(window.inputs["reference_cif"], "")
        window._set_widget_value_from_string(window.inputs["metadata_source"],
                                             appmod.METADATA_SOURCE_LABELS[appmod.METADATA_SOURCE_INFLIP])
        jana_config = window.get_config()
        window.last_run_config = jana_config
        check("full-configuration capture preserves authoritative Jana context",
              jana_config.jana_inflip == inflip.resolve() and jana_config.jana_return_to_jana)
        check("Jana context survives until completed results become handoff-capable",
              window._jana_wizard_handoff_available())

        window.settings.clear()
        window._set_widget_value_from_string(window.inputs["input_source_mode"],
                                             appmod.INPUT_MODE_LABELS[appmod.INPUT_MODE_EXTERNAL])
        real_save(window)
        window._set_widget_value_from_string(window.inputs["input_source_mode"],
                                             appmod.INPUT_MODE_LABELS[appmod.INPUT_MODE_INFLIP])
        real_load(window)
        check("current QSettings input-mode value round-trips unchanged",
              window._combo_value("input_source_mode") == appmod.INPUT_MODE_LABELS[appmod.INPUT_MODE_EXTERNAL])
        window.settings.clear()
        window.settings.setValue("inputs/plimit", "2.75")
        window.settings.setValue("inputs/export_superflip_jana", True)
        real_load(window)
        check("legacy QSettings fixtures retain their old interpretation",
              abs(window._dspin_value("plimit_superflip") - 2.75) < 1e-9
              and abs(window._dspin_value("plimit_deblur") - 2.75) < 1e-9
              and window._combo_value("map_export_format") == "jana")

        window.timer.stop()
        window.close()

    failures = [name for name, passed in checks if not passed]
    if failures:
        print(f"\n{len(failures)} of {len(checks)} checks FAILED:")
        for failure in failures:
            print("  - " + failure)
        return 1
    print(f"\nAll {len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
