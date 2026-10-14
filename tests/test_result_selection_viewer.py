"""Focused 2.0.2 Result Selection structure-viewer regressions."""
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

results_log = []


def check(name, condition):
    results_log.append((name, bool(condition)))
    print(("PASS" if condition else "FAIL") + " - " + name)


def cif_text(formula="C O", element_a="C", element_b="O"):
    return f"""data_viewer
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P -1'
_chemical_formula_sum '{formula}'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
A1 {element_a} 0.10 0.10 0.10
B1 {element_b} 0.20 0.10 0.10
"""


def large_cif(atom_count=1400):
    rows = []
    z_slices = max(1, (atom_count + 279) // 280)
    for index in range(atom_count):
        x = (index % 20) / 20.0 + 0.001
        y = ((index // 20) % 14) / 14.0 + 0.001
        z = (index // 280) / z_slices + 0.001
        rows.append(f"C{index + 1} C {x:.5f} {y:.5f} {z:.5f}")
    return """data_large
_cell_length_a 20
_cell_length_b 20
_cell_length_c 20
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P 1'
_chemical_formula_sum 'C{atom_count}'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
""".format(atom_count=atom_count) + "\n".join(rows) + "\n"


def main():
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtWidgets import QApplication, QDialog, QSizePolicy
    import phase_studio.app as appmod
    import phase_studio.autosolve_window as viewer
    from phase_studio.map_quality import ResultCandidate
    import test_jana_completion as tjc

    app = QApplication.instance() or QApplication([sys.argv[0]])
    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.refresh_sharped_models = lambda self: None

    temp = Path(tempfile.mkdtemp())
    molecule_cif = temp / "molecule.cif"
    predicted_cif = temp / "predicted.cif"
    reference_cif = temp / "wrong_reference.cif"
    molecule_cif.write_text(cif_text(), encoding="utf-8")
    predicted_cif.write_text(cif_text("N O", "N", "O"), encoding="utf-8")
    reference_cif.write_text(cif_text("Zn8 I8", "Zn", "I"), encoding="utf-8")
    composition_label, composition_text = appmod.structure_composition_display(
        molecule_cif, "Ag2 S2 C2 H2 O2 N2",
    )
    check("authoritative composition retains hydrogen hidden by the renderer",
          composition_label == "Composition" and composition_text == "Ag2 S2 C2 H2 O2 N2")

    # Exact crystallographic header from the real jana_context_fixture_Superflip.inflip.
    # Jana exposes this as Superflip's input/search composition; it does not
    # expose a separate definitive chemical-formula field in the .inflip.
    real_inflip = temp / "jana_context_fixture_Superflip.inflip"
    real_inflip.write_text(
        "cell 29.7485 40.8555 57.9220 92.68 90.73 109.68\n"
        "spacegroup P-1\n"
        "composition Ag2 S2 C2 H2 O2 N2\n",
        encoding="utf-8",
    )
    (temp / "jana_context_fixture.inflip").write_text(real_inflip.read_text(encoding="utf-8"), encoding="utf-8")
    (temp / "jana_context_fixture.m50").write_text(
        "Version Jana2020\ncell 10 10 10 90 90 90\nspgroup P-1\nunitsnumb 2\n"
        "atlist Ag C\nend\n", encoding="utf-8",
    )
    (temp / "jana_context_fixture.m40").write_text(
        "    2    0    0    1    0\n0\n0\n0\n0\n"
        "Ag1       1  1     1.000000 0.100000 0.200000 0.300000\n"
        "C1        2  1     1.000000 0.200000 0.300000 0.400000\n",
        encoding="utf-8",
    )
    real_metadata = appmod.resolve_crystal_metadata(
        appmod.METADATA_SOURCE_INFLIP, jana_inflip=real_inflip,
    )
    real_label = appmod.crystal_metadata_composition_label(real_metadata)
    authority = appmod.project_composition_for_metadata(real_metadata)
    check("Jana m40/m50 is the central model-composition authority",
          authority.value == "Ag1 C1" and authority.semantic_type == "jana_model"
          and authority.confidence == "authoritative")
    raw_edma_cif = temp / "raw_edma_counts.cif"
    raw_edma_cif.write_text(
        cif_text("Ag284 S283 O283 N283 C283", "Ag", "S"), encoding="utf-8",
    )
    displayed_label, displayed_value = appmod.structure_composition_display(
        raw_edma_cif, authority.value, real_label,
    )
    check("input/search composition remains available only as input metadata",
          displayed_label == "Composition" and displayed_value == "Ag1 C1")

    p1 = temp / "asu_p1.cif"
    p1.write_text(cif_text("Ag99", "C", "O").replace("P -1", "P 1"), encoding="utf-8")
    from phase_studio.autosolve_window import prepare_structure_presentation, structure_site_summary
    display = prepare_structure_presentation(raw_edma_cif, "cell")
    check("full-cell display count never replaces the detected CIF count",
          display["detected"] == 2 and display["displayed"] == 4)
    check("independent ASU count is recorded separately from symmetry expansion",
          display["independent_asu_sites"] == 2)
    check("shared viewer metadata distinguishes detection and display",
          "displayed in Full cell: 4" in structure_site_summary(raw_edma_cif, display, "cell")
          and "CIF EDMA sites: 2" in structure_site_summary(raw_edma_cif, display, "cell"))
    check("P1 EDMA composition counts each coordinate site without formula normalization",
          appmod.edma_asu_composition_from_cif(p1) == "C1 O1")
    inversion = temp / "asu_inversion.cif"
    inversion.write_text(cif_text("Ag99", "C", "C").replace(
        "B1 C 0.20 0.10 0.10", "B1 C 0.90 0.90 0.90"
    ), encoding="utf-8")
    check("P-1 EDMA composition reduces inversion-related full-cell copies",
          appmod.edma_asu_composition_from_cif(inversion) == "C1")
    special = temp / "asu_special.cif"
    special.write_text(cif_text("Ag99", "Zn", "Zn").replace(
        "A1 Zn 0.10 0.10 0.10", "A1 Zn 0.00 0.00 0.00"
    ).replace("B1 Zn 0.20 0.10 0.10", "B1 Zn 1.00 1.00 1.00"), encoding="utf-8")
    check("special-position duplicate images count as one EDMA ASU site",
          appmod.edma_asu_composition_from_cif(special) == "Zn1")
    check("EDMA ASU composition never borrows the inflip/Jana model composition",
          appmod.edma_asu_composition_from_cif(raw_edma_cif) == "Ag1 S1"
          and authority.value == "Ag1 C1")

    win, cycle_results = tjc.build_window(appmod, launch_mode="standalone", cycles=3)
    win.last_run_config = replace(
        win.last_run_config, crystal_metadata=real_metadata,
    )
    for result in cycle_results:
        result.superflip_edma_cif = molecule_cif
        result.deblur_edma_cif = predicted_cif
        result.superflip_edma_sigma = 1.0
        result.deblur_edma_sigma = 0.4
        result.sharped_model = "koala model progressive"
    win.results = cycle_results
    win.last_run_config.run_sharped = True

    opened = []
    with patch.object(appmod.ResultSelectionDialog, "exec", lambda dialog: opened.append(dialog) or QDialog.Rejected):
        win.open_result_selector("standalone")
    dialog = opened[0]
    dialog.show()
    app.processEvents()
    app.processEvents()
    available = dialog.available_geometry_at_open
    action_rect = QRect(dialog._action_button.mapToGlobal(QPoint(0, 0)), dialog._action_button.size())
    close_rect = QRect(dialog._close_button.mapToGlobal(QPoint(0, 0)), dialog._close_button.size())
    check("Result Selection opens as a normal non-maximized window inside availableGeometry",
          not dialog.isMaximized() and available.contains(dialog.frameGeometry()))
    check("Pass/Save action is globally inside availableGeometry",
          dialog._action_button.isVisible() and available.contains(action_rect))
    check("Return action is globally inside availableGeometry",
          dialog._close_button.isVisible() and available.contains(close_rect))
    check("selected summary and actions share one fixed footer outside the splitter",
          dialog._selected_output_summary.parentWidget() is dialog._footer
          and dialog._action_button.parentWidget() is dialog._footer
          and dialog._footer.sizePolicy().verticalPolicy() == QSizePolicy.Fixed)
    dialog.resize(dialog.width(), 520)
    app.processEvents()
    action_rect = QRect(dialog._action_button.mapToGlobal(QPoint(0, 0)), dialog._action_button.size())
    close_rect = QRect(dialog._close_button.mapToGlobal(QPoint(0, 0)), dialog._close_button.size())
    check("manual vertical shrink preserves both footer actions",
          available.contains(action_rect) and available.contains(close_rect)
          and dialog._footer.isVisible())
    canvas_rect = QRect(dialog._preview_canvas.mapToGlobal(QPoint(0, 0)), dialog._preview_canvas.size())
    footer_top = dialog._footer.mapToGlobal(QPoint(0, 0)).y()
    check("reduced-height preview keeps a meaningful canvas above the fixed footer",
          dialog._preview_canvas.height() >= 130 and canvas_rect.bottom() < footer_top)
    check("interaction help stays outside the scientific canvas",
          dialog._preview_canvas.toolTip() == ""
          and any(
              child.objectName() == "structureInteractionHint"
              for child in dialog.findChildren(type(dialog._metadata_label))
          ))
    check("Result Selection uses a large full-width two-segment output selector",
          dialog._superflip_btn.minimumHeight() >= 40
          and dialog._sharped_btn.minimumHeight() >= 40
          and dialog._superflip_btn.subtitle_label.text() == "Superflip phase solution"
          and dialog._sharped_btn.subtitle_label.text() == "SharpED-processed map")
    dialog._superflip_btn.setChecked(True)
    candidate = dialog.selected_candidate
    check("Result Selection starts with a real completed candidate", candidate is not None)

    molecule = dialog._candidate_presentation(candidate)
    molecule_atoms, _coords, molecule_bonds, formula, detected, _fit, molecule_cell = molecule
    check("Complete molecules shows one completed bonded molecule", len(molecule_atoms) == 2 and len(molecule_bonds) == 1)
    check("Complete molecules reports asymmetric-unit EDMA sites separately", detected == 2)
    check("Complete molecules does not draw a unit-cell frame", molecule_cell == [])
    dialog._render_preview(candidate)
    check("embedded molecular viewer hides Matplotlib axes and panes",
          not dialog._preview_figure.axes[0].axison)
    formula_before = formula

    dialog._cell_button.setChecked(True)
    full = dialog._candidate_presentation(candidate)
    check("Full cell expands the inversion-related unit-cell contents", len(full[0]) == 4)
    check("Full cell draws the unit-cell frame and no molecular bonds", len(full[6]) == 12 and full[2] == [])
    check("formula is independent of Complete molecules / Full cell", full[3] == formula_before)
    dialog._molecule_button.setChecked(True)
    check("switching back to Complete molecules is deterministic", dialog._candidate_presentation(candidate)[1].tolist() == molecule[1].tolist())

    original_builder = viewer.build_complete_molecule_view
    dialog._presentation_cache.clear()
    with patch.object(viewer, "build_complete_molecule_view", wraps=original_builder) as build_view:
        dialog._render_preview(candidate)
        dialog._fit_preview()
        dialog._reset_preview()
        dialog._auto_rotate_tick()
        check("camera actions do not rebuild cached molecular geometry", build_view.call_count == 1)
        dialog._cell_button.setChecked(True)
        dialog._molecule_button.setChecked(True)
        check("mode round-trip reuses cached Complete-molecules geometry", build_view.call_count == 1)

    dialog._sharped_btn.setChecked(True)
    app.processEvents()
    sharped = dialog.selected_candidate
    check("source switch updates selected scientific source", sharped is not None and sharped.source == "deblurred")
    check("source switch uses the selected EDMA candidate composition",
          dialog._current_formula == "N1 O1")
    check("source switch updates the rendered-element legend", "N" in dialog._element_legend.text())
    check("source switch metadata names cycle, model and EDMA ASU composition", all(
        text in dialog._metadata_label.text() for text in (
            "Cycle", "koala model progressive", "EDMA asymmetric-unit composition", "N₁ O₁",
        )
    ))
    check("detected count appears once in EDMA status, not duplicated in metadata",
          "EDMA sites" not in dialog._metadata_label.text()
          and dialog._threshold_status.text().count("EDMA sites") == 1)
    check("latest candidate has an explicit checked Latest state",
          dialog._latest_cycle_button.isChecked() and not dialog._latest_cycle_button.isEnabled())
    check("scientific canvas has no duplicate floating source/cycle title",
          not dialog._preview_figure.texts)
    check("EDMA state and atom controls are grouped together",
          "0.40" in dialog._threshold_status.text()
          and dialog._threshold_status.parentWidget() is dialog._preview_section)
    check("Result Selection states the exact output that will be exported", all(
        text in dialog._selected_output_summary.text()
        for text in ("Selected for export", "Model prediction", "Cycle 3", "0.4")
    ))
    dialog._superflip_btn.setChecked(True)
    restored = dialog.selected_candidate
    check("switching back preserves Superflip's prior selection",
          restored is not None and restored.cycle == candidate.cycle
          and restored.source == candidate.source and restored.map_path == candidate.map_path)

    dialog._sharped_btn.setChecked(True)
    chosen = dialog.selected_candidate
    result = win._cycle_result_for_candidate(chosen)
    check("preview identity is the exact selected handoff candidate identity",
          dialog.preview_candidate_id == chosen.candidate_id
          and dialog.preview_structure_hash == chosen.structure_sha256)
    check("preview model equals the threshold-specific handoff model",
          Path(chosen.structure_path) == Path(result.deblur_edma_cif) and result.deblur_edma_sigma == 0.4)
    check("viewer controls never change the selected map path", Path(chosen.map_path) == Path(result.deblur_map))
    identity_before_view_changes = (
        chosen.candidate_id, chosen.map_sha256, chosen.structure_sha256,
    )
    dialog._cell_button.setChecked(True)
    dialog._molecule_button.setChecked(True)
    dialog._cell_button.setChecked(True)
    dialog._molecule_button.setChecked(True)
    check("Complete molecules / Full cell never changes scientific candidate identity",
          dialog.selected_candidate is chosen
          and identity_before_view_changes == (
              chosen.candidate_id, chosen.map_sha256, chosen.structure_sha256,
          ))

    threshold_calls = []
    original_map = chosen.map_path
    dialog._adjust_threshold = lambda item, add: (
        threshold_calls.append((item.source, item.cycle, add))
        or replace(item, edma_sigma=0.3, structure_path=str(predicted_cif))
    )
    dialog._adjust_threshold_async = None
    dialog._sync_action_button()
    dialog._add_atoms_button.click()
    tuned = dialog.selected_candidate
    check("Result Selection + atoms invokes one EDMA-only threshold callback",
          threshold_calls == [("deblurred", chosen.cycle, True)])
    check("threshold tuning preserves exact map identity",
          tuned.map_path == original_map and tuned.edma_sigma == 0.3)
    check("threshold-tuned candidate remains the handoff selection", dialog._current_candidate == tuned)
    dialog._auto_rotate_button.setChecked(False)
    azimuth = dialog._preview_host.structure_azim
    dialog._open_fullscreen()
    app.processEvents()
    check("Result Selection fullscreen hosts the live selected-candidate viewer",
          dialog._preview_section.parentWidget() is dialog._detached_viewer)
    check("true fullscreen hides the embedded redundant Fullscreen action",
          not dialog._fullscreen_button.isVisible()
          and dialog._detached_viewer.fullscreen_button.text() == "Exit fullscreen")
    dialog._detached_viewer.close()
    app.processEvents()
    check("fullscreen close restores the same candidate and camera",
          dialog.selected_candidate == tuned and dialog._preview_host.structure_azim == azimuth
          and dialog._fullscreen_button.isVisible())

    large_path = temp / "large.cif"
    large_path.write_text(large_cif(), encoding="utf-8")
    large_candidate = replace(
        chosen, structure_path=str(large_path), usable_structure=True,
        edma_sigma=0.4, sharped_model="koala model progressive",
    )
    dialog._cell_button.setChecked(True)
    large = dialog._candidate_presentation(large_candidate)
    check("large Full-cell presentation retains all 1,400 atoms", len(large[0]) == 1400)
    dialog._render_preview(large_candidate)
    app.processEvents()
    app.processEvents()
    axis = dialog._preview_host._structure_interactive_axes[0]
    check("large model uses bounded batched artists", len(axis.collections) <= 2)
    from mpl_toolkits.mplot3d import proj3d
    projected_points = np.vstack((
        large[1], np.asarray(large[6], dtype=np.float64).reshape(-1, 3),
    ))
    dialog._preview_canvas.draw()
    px, py, _pz = proj3d.proj_transform(
        projected_points[:, 0], projected_points[:, 1], projected_points[:, 2], axis.get_proj(),
    )
    projected_pixels = axis.transData.transform(np.column_stack((px, py)))
    viewport = axis.get_window_extent()
    projected_fill = float(np.max(np.ptp(projected_pixels, axis=0))) / min(viewport.width, viewport.height)
    check("post-layout Full-cell Fit uses 70-85% of the limiting viewport dimension",
          0.70 <= projected_fill <= 0.85)
    cache_size = len(dialog._presentation_cache)
    dialog._auto_rotate_tick()
    dialog._fit_preview()
    check("large-model camera motion does not rebuild static geometry", len(dialog._presentation_cache) == cache_size)

    stress_path = temp / "large-2000.cif"
    stress_path.write_text(large_cif(2000), encoding="utf-8")
    stress_candidate = replace(large_candidate, structure_path=str(stress_path), edma_sigma=0.3)
    stress = dialog._candidate_presentation(stress_candidate)
    check("2,000-atom Full-cell presentation retains all atoms", len(stress[0]) == 2000)
    dialog._render_preview(stress_candidate)
    stress_axis = dialog._preview_host._structure_interactive_axes[0]
    check("2,000-atom model keeps bounded batched artists", len(stress_axis.collections) <= 2)
    stress_cache_size = len(dialog._presentation_cache)
    dialog._auto_rotate_tick()
    dialog._fit_preview()
    check("2,000-atom camera motion reuses prepared geometry",
          len(dialog._presentation_cache) == stress_cache_size)

    settings_values = {}
    win.settings = type("MemorySettings", (), {
        "setValue": lambda self, key, value: settings_values.__setitem__(key, value),
        "value": lambda self, key, default=None: settings_values.get(key, default),
        "sync": lambda self: None,
    })()
    win._structure_source_paths.update({
        "reference": reference_cif, "superflip": molecule_cif, "deblur": predicted_cif,
    })
    win.reference_atoms_for_plot = win._classic_structure_atoms(reference_cif)
    win._sync_classic_review_controls()
    win._set_classic_structure_view_mode("molecule")
    molecule_counts = tuple(map(len, (
        win.reference_atoms_for_plot, win.superflip_atoms_for_plot, win.deblur_atoms_for_plot,
    )))
    classic_formulas = [text.get_text().split(" · ", 1)[0] for text in win.structure_metadata_texts]
    check("classic shared Complete-molecules mode applies to all three panels", molecule_counts == (2, 2, 2))
    check("wrong Reference formula remains isolated from both result formulas",
          win._classic_structure_formula("reference", ()) == "Zn8 I8"
          and win._classic_structure_formula("superflip", ()) == "C1 O1"
          and win._classic_structure_formula("deblur", ()) == "N1 O1")
    candidate_formulas_with_reference = (
        win._classic_structure_formula("superflip", ()),
        win._classic_structure_formula("deblur", ()),
    )
    win._structure_source_paths["reference"] = None
    win.reference_atoms_for_plot = []
    win._update_structure_views()
    check("candidate formulas are identical when the wrong Reference is removed",
          candidate_formulas_with_reference == (
              win._classic_structure_formula("superflip", ()),
              win._classic_structure_formula("deblur", ()),
          ) == ("C1 O1", "N1 O1"))
    win._structure_source_paths["reference"] = reference_cif
    win.reference_atoms_for_plot = win._classic_structure_atoms(reference_cif)
    win._update_structure_views()
    check("Professional mode exposes independent completed-cycle history",
          all(win.classic_review_controls[p]["combo"].count() == 4 for p in ("superflip", "deblur")))
    win.classic_review_controls["superflip"]["combo"].setCurrentIndex(1)
    check("Professional cycle selection follows the selected canonical cycle",
          win._classic_selected_candidate("superflip").cycle == 1
          and "Cycle 1" in win.classic_review_controls["superflip"]["metadata"].text())
    win.classic_review_controls["superflip"]["combo"].setCurrentIndex(0)
    check("Professional Latest resumes independent follow-latest state",
          win._classic_selected_candidate("superflip").cycle == 3)
    check("classic comparison exposes one Fullscreen action per structure",
          set(win.structure_fullscreen_buttons) == {"reference", "superflip", "deblur"})
    win._open_classic_structure_fullscreen("reference")
    app.processEvents()
    reference_fullscreen = win._classic_detached_viewers["reference"]
    check("classic Reference fullscreen contains one structure only",
          len(reference_fullscreen.figure.axes) == 1 and "Reference" in reference_fullscreen.metadata_label.text()
          and "SharpED" not in reference_fullscreen.metadata_label.text())
    reference_fullscreen.close()
    win.classic_review_controls["deblur"]["combo"].setCurrentIndex(2)
    win._open_classic_structure_fullscreen("deblur")
    app.processEvents()
    sharped_fullscreen = win._classic_detached_viewers["deblur"]
    check("classic SharpED fullscreen contains one structure only",
          len(sharped_fullscreen.figure.axes) == 1 and "SharpED" in sharped_fullscreen.metadata_label.text()
          and "Reference" not in sharped_fullscreen.metadata_label.text())
    check("Professional fullscreen follows the selected cycle, threshold and formula",
          all(text in sharped_fullscreen.metadata_label.text()
              for text in ("Cycle 2", "EDMA 0.4", "N1 O1")))
    sharped_fullscreen.close()
    threshold_calls = []
    original_retune = win.request_result_candidate_retune
    def fake_retune(candidate, add, callback):
        threshold_calls.append((candidate.source, candidate.cycle, add))
        callback(replace(candidate, edma_sigma=0.3), None, None)
        return type("Request", (), {"threshold": 0.3})()
    win.request_result_candidate_retune = fake_retune
    win._classic_adjust_threshold("superflip", True)
    check("Professional + atoms delegates to the shared candidate EDMA retune authority",
          threshold_calls == [("superflip", 3, True)])
    win.request_result_candidate_retune = original_retune
    check("classic viewer has one shared union element legend", all(
        element in win.structure_element_legend.text() for element in ("C", "N", "O")
    ))
    win._set_classic_structure_view_mode("cell")
    cell_counts = tuple(map(len, (
        win.reference_atoms_for_plot, win.superflip_atoms_for_plot, win.deblur_atoms_for_plot,
    )))
    check("classic shared Full-cell mode expands all three panels together", cell_counts == (4, 4, 4))
    check("classic formulas remain independent of the shared view mode",
          [text.get_text().split(" · ", 1)[0] for text in win.structure_metadata_texts] == classic_formulas)
    win._structure_source_paths["deblur"] = None
    win.deblur_atoms_for_plot = []
    win.results = [replace(result, deblur_quality=None) for result in win.results]
    win._sync_classic_review_controls()
    win._update_structure_views()
    check("unavailable SharpED panel shows no borrowed or fabricated formula",
          win._classic_structure_formula("deblur", []) == ""
          and "Zn8" not in win.structure_metadata_texts[2].get_text()
          and "N1 O1" not in win.structure_metadata_texts[2].get_text())
    check("classic view mode is persisted through the shared settings authority",
          str(win.settings.value("viewer/structure_view_mode", "")) == "cell")

    dialog.close()
    win.close()
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
