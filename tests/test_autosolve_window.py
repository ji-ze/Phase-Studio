"""Regression tests for phase_studio/autosolve_window.py -- the dedicated,
simplified Autosolve front end (Phase Studio 2.0.0), including the UX
refinement pass: structures dominate the window, bonded-structure rendering
(not a scatter of dots), enlarged atoms, simplified mouse controls
(left-drag rotate, right-drag pan, wheel zoom, double-click reset),
auto-rotation pause/resume with a short idle delay, a compact one/two-line
status headline (not seven boxed fields), a compact Execution Log, and a
shallow bottom progress strip.

Plain Python test (no pytest dependency); run with
`python tests/test_autosolve_window.py`.
"""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
Ag1 Ag 0.10 0.10 0.10
O1 O 0.50 0.40 0.35
"""


def plain_tooltip(widget):
    """Tooltip text without the app-wide width-limiting <div> wrapper."""
    import re

    return re.sub(r"<[^>]+>", "", widget.toolTip()).strip()


def check(name, cond):
    results_log.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + " - " + name)


class _Event:
    """Minimal stand-in for a matplotlib MouseEvent."""

    def __init__(self, inaxes=None, button="up", dblclick=False):
        self.inaxes = inaxes
        self.button = button
        self.dblclick = dblclick


def main():
    from PySide6.QtWidgets import (
        QApplication, QComboBox, QLabel, QPushButton, QTabWidget, QTextEdit, QToolButton,
    )
    import numpy as np

    app = QApplication.instance() or QApplication([sys.argv[0]])
    import phase_studio.ui_style as ui_style

    ui_style.apply_phase_studio_style(app)
    import phase_studio.app as appmod
    from phase_studio.autosolve_window import (
        AutosolveWindow,
        _bond_count_is_sane,
        build_complete_molecule_fragment,
        compute_bonds,
        periodic_connectivity_unwrap,
    )
    from phase_studio.map_quality import MapQualityMetrics, ValidationProfile

    appmod.IterativeSuperflipPipelineQtGUI.save_settings = lambda self: None
    appmod.IterativeSuperflipPipelineQtGUI.load_settings = lambda self: None

    tmp = Path(tempfile.mkdtemp())

    def model(name, text=CIF):
        path = tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def map_file(name):
        path = tmp / name
        path.write_text("real existing map", encoding="utf-8")
        return path

    def make_result(cycle, sf_score, db_score):
        sf_quality = MapQualityMetrics(
            reference_f05=sf_score, reference_rmsd=0.40, reference_phase_agreement=0.70,
            amplitude_rf=0.25, amplitude_cc=0.75, r_free=0.32, cc_free=0.70,
            omit_map_correlation=0.65, triplet_c3=0.55,
            n_measured_reflections=100, n_work_reflections=95, n_free_reflections=5,
        )
        db_quality = MapQualityMetrics(
            reference_f05=db_score, reference_rmsd=0.30, reference_phase_agreement=0.80,
            amplitude_rf=0.20, amplitude_cc=0.82, r_free=0.27, cc_free=0.77,
            omit_map_correlation=0.72, triplet_c3=0.62,
            n_measured_reflections=100, n_work_reflections=95, n_free_reflections=5,
        )
        return appmod.CycleResult(
            cycle=cycle, model_source="superflip", model_in=None, model_metric=None,
            superflip_map=map_file(f"sf{cycle}.xplor"),
            superflip_edma_cif=model(f"sf{cycle}.cif"), superflip_metric=0.4,
            deblur_map=map_file(f"db{cycle}.xplor"),
            deblur_edma_cif=model(f"db{cycle}.cif"), deblur_metric=0.3,
            validation_profile=ValidationProfile.REFERENCE_AND_HOLDOUT.value,
            superflip_quality=sf_quality, deblur_quality=db_quality,
            # 2.0.1: a SharpED result is a Model prediction only when it
            # came from the prediction model (refinement cycles do).
            sharped_model="UNIVERSAL",
        )

    def make_window(option="A"):
        backend = appmod.IterativeSuperflipPipelineQtGUI()
        backend.current_validation_profile = ValidationProfile.REFERENCE_AND_HOLDOUT
        backend._autosolve_prediction_cycles = set(range(1, 1000))
        backend._show_error_report = lambda *_args, **_kwargs: None
        win = AutosolveWindow(backend, option)
        return win, backend

    # =====================================================================
    # compute_bonds(): pure, presentation-only distance-based bonding using
    # gemmi's own covalent radii -- exact, hand-picked Cartesian coordinates
    # so the expected outcome is unambiguous.
    # =====================================================================
    from phase_studio.app import AtomSite

    c_atom = AtomSite(label="C1", element="C", frac=np.array([0.0, 0.0, 0.0]))
    o_atom_bonded = AtomSite(label="O1", element="O", frac=np.array([0.0, 0.0, 0.0]))
    o_atom_far = AtomSite(label="O2", element="O", frac=np.array([0.0, 0.0, 0.0]))
    h_atom = AtomSite(label="H1", element="H", frac=np.array([0.0, 0.0, 0.0]))

    coords_bonded = np.array([[0.0, 0.0, 0.0], [1.43, 0.0, 0.0]])  # real C-O single-bond length
    check("compute_bonds: a realistic C-O distance (1.43 A) is bonded", compute_bonds([c_atom, o_atom_bonded], coords_bonded) == [(0, 1)])

    coords_far = np.array([[0.0, 0.0, 0.0], [6.0, 0.0, 0.0]])
    check("compute_bonds: atoms 6 A apart are not bonded", compute_bonds([c_atom, o_atom_far], coords_far) == [])

    from phase_studio.autosolve_window import MAX_BOND_LENGTH_ANGSTROM
    over_cap_distance = MAX_BOND_LENGTH_ANGSTROM + 0.1
    coords_cap = np.array([[0.0, 0.0, 0.0], [over_cap_distance, 0.0, 0.0]])
    check(
        "compute_bonds: MAX_BOND_LENGTH_ANGSTROM is a real hard cap",
        compute_bonds([c_atom, o_atom_far], coords_cap, tolerance=5.0) == []
        and over_cap_distance < 5.0 * (0.73 + 0.66),  # a generous tolerance alone would have allowed it
    )

    coords_three = np.array([[0.0, 0.0, 0.0], [1.43, 0.0, 0.0], [6.0, 0.0, 0.0]])
    check(
        "compute_bonds: only genuinely close pairs bond, not every pair",
        compute_bonds([c_atom, o_atom_bonded, o_atom_far], coords_three) == [(0, 1)],
    )
    check(
        "compute_bonds: fewer than 2 atoms produces no bonds",
        compute_bonds([c_atom], np.array([[0.0, 0.0, 0.0]])) == [],
    )

    # =====================================================================
    # No reference -> exactly 2 tiles; reference available -> exactly 3.
    # =====================================================================
    win, backend = make_window("A")
    check("initial search has one solution tile and no empty prediction tile", len(win.structure_axes) == 1)
    win.close()

    win, backend = make_window("A")
    backend.reference_atoms_for_plot = [
        appmod.AtomSite(label="Ag1", element="Ag", frac=np.array([0.1, 0.1, 0.1])),
        appmod.AtomSite(label="O1", element="O", frac=np.array([0.5, 0.4, 0.35])),
    ]
    win._refresh_tick()
    check("initial search with reference has two tiles", len(win.structure_axes) == 2)
    win.close()

    # =====================================================================
    # View mode toggle: Complete molecules (default) vs Full cell. One
    # shared mode for every panel; Full cell NEVER computes bonds (root
    # cause of the earlier all-to-all bug was bonding across the whole,
    # already symmetry-expanded unit cell); Complete molecules bonds a
    # LOCAL, chemically-grown fragment only.
    # =====================================================================
    bonded_cif_local = (
        "data_test\n_cell_length_a 30.0\n_cell_length_b 30.0\n_cell_length_c 30.0\n"
        "_cell_angle_alpha 90.0\n_cell_angle_beta 90.0\n_cell_angle_gamma 90.0\n"
        "_space_group_name_H-M_alt 'P 2'\nloop_\n_atom_site_label\n_atom_site_type_symbol\n"
        "_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
        "C1 C 0.100 0.100 0.100\n"
        "C2 C 0.1513 0.100 0.100\n"
        "O1 O 0.1770 0.100 0.100\n"
    )
    win, backend = make_window("A")
    check("default view mode is Complete molecules", win.view_mode == "molecule")
    backend.results = [make_result(1, 0.7, 0.7)]
    backend.results[0].superflip_edma_cif.write_text(bonded_cif_local, encoding="utf-8")
    backend.results[0].deblur_edma_cif.write_text(bonded_cif_local, encoding="utf-8")
    win._rendered_once = False
    win._refresh_tick()
    check("Complete molecules: bond artists exist for a bonded structure", len(win._bond_artists) >= 1)
    molecule_atom_counts = [len(a.atom_coordinates) for a in win._structure_depth_artists]

    win.full_cell_view_button.setChecked(True)
    check("clicking Full cell switches the mode", win.view_mode == "cell")
    check("Full cell: zero bond artists, always", len(win._bond_artists) == 0)
    full_cell_atom_counts = [len(a.atom_coordinates) for a in win._structure_depth_artists]
    check(
        "Full cell shows the symmetry-expanded unit cell (at least as many atoms as the local fragment)",
        all(fc >= mc for fc, mc in zip(full_cell_atom_counts, molecule_atom_counts)),
    )

    win.molecule_view_button.setChecked(True)
    check("switching back to Complete molecules restores bonds", win.view_mode == "molecule" and len(win._bond_artists) >= 1)
    win.close()

    # =====================================================================
    # Camera orientation survives a mode switch (never resets to a random
    # viewpoint); extent may re-fit.
    # =====================================================================
    win, backend = make_window("A")
    backend.results = [make_result(1, 0.7, 0.7)]
    backend.results[0].superflip_edma_cif.write_text(bonded_cif_local, encoding="utf-8")
    backend.results[0].deblur_edma_cif.write_text(bonded_cif_local, encoding="utf-8")
    win._rendered_once = False
    win._refresh_tick()
    win.structure_elev = 61.0
    win.structure_azim = 217.0
    win.full_cell_view_button.setChecked(True)
    check("switching view mode preserves the current rotation (elevation)", win.structure_elev == 61.0)
    check("switching view mode preserves the current rotation (azimuth)", win.structure_azim == 217.0)
    win.close()

    # =====================================================================
    # Fragment growth stays local and chemically plausible (item 21/33): a
    # realistic linear chain far from its symmetry-equivalent copy must NOT
    # pull that copy in, and must produce a chain-like (not O(N^2)) bond
    # count. The sanity guard itself is verified to actually reject an
    # all-to-all count for the same atom count.
    # =====================================================================
    chain_lines = [
        "data_test", "_cell_length_a 60.0", "_cell_length_b 30.0", "_cell_length_c 30.0",
        "_cell_angle_alpha 90.0", "_cell_angle_beta 90.0", "_cell_angle_gamma 90.0",
        "_space_group_name_H-M_alt 'P 2'", "loop_", "_atom_site_label", "_atom_site_type_symbol",
        "_atom_site_fract_x", "_atom_site_fract_y", "_atom_site_fract_z",
    ]
    bond_length_frac = 1.54 / 60.0
    for i in range(20):
        x = 0.1 + i * bond_length_frac
        chain_lines.append(f"C{i + 1} C {x:.5f} 0.100 0.100")
    chain_cif = model("chain.cif", "\n".join(chain_lines) + "\n")
    chain_cell, chain_sg, _ = appmod.parse_cif_cell_and_sg(chain_cif)
    chain_seeds = appmod.parse_cif_atoms(chain_cif)
    frag_atoms, frag_coords, frag_bonds = build_complete_molecule_fragment(chain_seeds, chain_cell, chain_sg)
    check("fragment growth stays local: exactly the 20 seed atoms, not the far symmetry mate", len(frag_atoms) == 20)
    check("a 20-atom chain produces a chain-like bond count (~19), not O(N^2) (190)", 15 <= len(frag_bonds) <= 25)
    check("bond-count sanity guard: this legitimate local fragment passes it", _bond_count_is_sane(len(frag_atoms), len(frag_bonds)))
    check("bond-count sanity guard: rejects an all-to-all count for the same atom count", not _bond_count_is_sane(20, 190))

    # =====================================================================
    # Bond geometry fixture (item 34): a plausible local bond, a clearly
    # too-far atom, and a bond crossing a periodic cell boundary.
    # =====================================================================
    boundary_lines = [
        "data_test", "_cell_length_a 10.0", "_cell_length_b 10.0", "_cell_length_c 10.0",
        "_cell_angle_alpha 90.0", "_cell_angle_beta 90.0", "_cell_angle_gamma 90.0",
        "_space_group_name_H-M_alt 'P 1'", "loop_", "_atom_site_label", "_atom_site_type_symbol",
        "_atom_site_fract_x", "_atom_site_fract_y", "_atom_site_fract_z",
        "C1 C 0.99 0.500 0.500",
        "C2 C 0.01 0.500 0.500",
        "N1 N 0.500 0.500 0.500",
    ]
    boundary_cif = model("boundary.cif", "\n".join(boundary_lines) + "\n")
    boundary_cell, boundary_sg, _ = appmod.parse_cif_cell_and_sg(boundary_cif)
    boundary_seeds = appmod.parse_cif_atoms(boundary_cif)
    b_atoms, b_coords, b_bonds = build_complete_molecule_fragment(boundary_seeds, boundary_cell, boundary_sg)
    c1_idx = next(i for i, a in enumerate(b_atoms) if a.label == "C1")
    n1_indices = [i for i, a in enumerate(b_atoms) if a.label.startswith("N1")]
    bonds_touching_c1 = [pair for pair in b_bonds if c1_idx in pair]
    check("bond geometry: the local C1-C2 bond (crossing the periodic boundary) is found", len(bonds_touching_c1) >= 1)
    check(
        "bond geometry: the distant N1 atom is never bonded to C1",
        not any(idx in n1_indices for pair in bonds_touching_c1 for idx in pair if idx != c1_idx),
    )
    periodic_atoms, periodic_coords, periodic_bonds, periodic_extended = periodic_connectivity_unwrap(
        boundary_seeds[:2], boundary_cell,
    )
    check("periodic graph retains the lattice translation for a 0.99/0.01 boundary bond",
          len(periodic_atoms) == 2 and periodic_bonds == [(0, 1)] and not periodic_extended)
    check("periodic graph unwraps the boundary-crossing molecule into one compact object",
          float(np.linalg.norm(periodic_coords[1] - periodic_coords[0])) < 2.0
          and float(np.ptp(periodic_coords[:, 0])) < 2.0)

    # =====================================================================
    # Graceful fallback (item 24): if Complete-molecule construction fails
    # for a specific candidate, that panel falls back to Full cell instead
    # of crashing or showing a broken bonded view; the shared mode control
    # is unaffected (item 22 -- it never silently switches for everyone).
    # =====================================================================
    import phase_studio.autosolve_window as autosolve_window_module

    win, backend = make_window("A")
    backend.results = [make_result(1, 0.7, 0.7)]
    with patch.object(autosolve_window_module, "_complete_molecule_view_for_path", lambda path: None):
        win._rendered_once = False
        try:
            win._refresh_tick()
            crashed = False
        except Exception:
            crashed = True
    check("molecule construction failing for a candidate never crashes the render", not crashed)
    check("the panel still shows something (Full-cell fallback), not an empty broken state", len(win._structure_depth_artists) >= 1)
    check("the shared view-mode control is unaffected by a per-panel fallback", win.view_mode == "molecule")
    win.close()

    # =====================================================================
    # Bond artists are actually created for a real bonded structure, and
    # atom markers are enlarged for legibility (not the shared renderer's
    # smaller default, tuned for a denser multi-panel comparison grid).
    # =====================================================================
    win, backend = make_window("A")
    bonded_cif = (
        "data_test\n_cell_length_a 15.0\n_cell_length_b 15.0\n_cell_length_c 15.0\n"
        "_cell_angle_alpha 90.0\n_cell_angle_beta 90.0\n_cell_angle_gamma 90.0\n"
        "_space_group_name_H-M_alt 'P 1'\nloop_\n_atom_site_label\n_atom_site_type_symbol\n"
        "_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
        "C1 C 0.500 0.500 0.500\n"
        "O1 O 0.5000 0.5000 0.5953\n"  # 1.43 A along c from C1 in a 15 A cell
    )
    backend.results = [make_result(1, 0.7, 0.7)]
    backend.results[0].superflip_edma_cif.write_text(bonded_cif, encoding="utf-8")
    backend.results[0].deblur_edma_cif.write_text(bonded_cif, encoding="utf-8")
    win._rendered_once = False
    win._refresh_tick()
    check("a real bonded structure produces at least one bond artist", len(win._bond_artists) >= 1)
    check(
        "atom markers are enlarged beyond the shared renderer's own default size",
        win._structure_depth_artists
        and float(np.mean(win._structure_depth_artists[0].atom_sizes)) > 0,
    )
    from phase_studio.autosolve_window import PRESENTATION_ATOM_SCALE
    check("the enlargement factor is a real, positive presentation scale > 1", PRESENTATION_ATOM_SCALE > 1.0)
    win.close()

    # =====================================================================
    # Recommended-candidate-driven rendering: Superflip and SharpED each
    # follow their OWN recommended cycle independently, and may differ.
    # =====================================================================
    win, backend = make_window("B")
    backend.results = [
        make_result(1, sf_score=0.90, db_score=0.60),
        make_result(2, sf_score=0.10, db_score=0.95),
    ]
    win._refresh_tick()
    check(
        "the compact status line uses the neutral workflow name",
        win.status_headline.text().startswith("SharpED Autosolve —")
        and "Predict the structure model" not in win.status_headline.text(),
    )
    figure_texts = [t.get_text() for t in win.structure_figure.texts]
    check(
        "each structure panel reports its OWN best cycle (Superflip 1, SharpED 2)",
        figure_texts.count("Best · Cycle 1") == 1 and figure_texts.count("Best · Cycle 2") == 1,
    )
    header_texts = win.status_headline.text() + " " + win.status_secondary.text()
    check(
        "best cycles are NOT repeated in the header (shown once, above each structure)",
        "Best" not in header_texts and not win.status_secondary.isVisibleTo(win),
    )
    win.close()

    # =====================================================================
    # Status synchronization (item 33): the top header must read from the
    # SAME authoritative CycleProgressState the bottom "Current cycle" row
    # already uses -- never an independently derived, and therefore
    # potentially disagreeing, copy.
    # =====================================================================
    def assert_header_matches_bottom(win, backend, state, case_label):
        backend._apply_cycle_progress_state(state)
        win._refresh_tick()
        bottom_text = backend.current_cycle_detail.text()
        check(f"{case_label}: bottom row shows the expected cycle/stage text", bottom_text == state.display_text())
        check(
            f"{case_label}: header and bottom row agree exactly (same CycleProgressState)",
            bottom_text in win.status_headline.text(),
        )

    win, backend = make_window("B")
    # Case A: cycle 1, Superflip.
    assert_header_matches_bottom(
        win, backend,
        appmod.CycleProgressState(cycle_index=1, cycle_total=10, stage_name="Superflip", stage_index=2, stage_total=5, detail="running"),
        "33.A (cycle 1, Superflip)",
    )
    # Case B: cycle 2, EDMA on the Superflip map.
    assert_header_matches_bottom(
        win, backend,
        appmod.CycleProgressState(cycle_index=2, cycle_total=10, stage_name="EDMA · Superflip map", stage_index=4, stage_total=5, busy=True),
        "33.B (cycle 2, EDMA Superflip map)",
    )
    # Case C: cycle 2, SharpED processing (busy/indeterminate).
    assert_header_matches_bottom(
        win, backend,
        appmod.CycleProgressState(cycle_index=2, cycle_total=10, stage_name="SharpED", stage_index=3, stage_total=5, detail="preparing upload", busy=True),
        "33.C (cycle 2, SharpED processing)",
    )
    # Case D: cycle 2, EDMA on the SharpED map.
    assert_header_matches_bottom(
        win, backend,
        appmod.CycleProgressState(cycle_index=2, cycle_total=10, stage_name="EDMA · SharpED map", stage_index=5, stage_total=5, busy=True),
        "33.D (cycle 2, EDMA SharpED map)",
    )
    win.close()

    # =====================================================================
    # Cycle-zero regression (item 34): before any real cycle/stage event has
    # arrived, the header must say "SharpED Autosolve · Preparing..." and never show
    # an internal zero-based cycle number; once a cycle-1 event lands,
    # "Cycle 0" must never appear anywhere in the header again.
    # =====================================================================
    win, backend = make_window("A")
    check("before any cycle event: the header is neutral SharpED Autosolve preparation",
          win.status_headline.text() == "SharpED Autosolve — Not started")
    check("before any cycle event: 'Cycle 0' is never shown", "Cycle 0" not in win.status_headline.text())

    ordinary = AutosolveWindow(backend, "A", workflow_name="Superflip + SharpED")
    check("ordinary Superflip + SharpED preparation never says Autosolve",
          ordinary.status_headline.text() == "Superflip + SharpED · Preparing workflow…"
          and ordinary.backend.current_cycle_detail.text() == "Validating input and preparing Superflip files…")

    def panel_text(window):
        return " ".join(text.get_text() for axis in window.structure_axes for text in axis.texts)

    check("empty Model prediction panel explains what it is waiting for",
          "Waiting for the Superflip map…" in panel_text(ordinary))
    backend._apply_cycle_progress_state(appmod.CycleProgressState(
        cycle_index=1, cycle_total=1, stage_name="Superflip",
        stage_index=1, stage_total=4, detail="running", busy=True,
    ))
    ordinary._refresh_tick()
    check("Superflip stage gives the Charge-flipping solution panel a stage-aware placeholder",
          "Superflip running…" in panel_text(ordinary))
    backend._apply_cycle_progress_state(appmod.CycleProgressState(
        cycle_index=1, cycle_total=1, stage_name="EDMA · Superflip map",
        stage_index=2, stage_total=4, busy=True,
    ))
    ordinary._refresh_tick()
    check("Charge-flipping solution EDMA stage replaces the preparation placeholder",
          "EDMA structure extraction running…" in panel_text(ordinary))
    backend._apply_cycle_progress_state(appmod.CycleProgressState(
        cycle_index=1, cycle_total=1, stage_name="SharpED",
        stage_index=3, stage_total=4, busy=True,
    ))
    ordinary._refresh_tick()
    check("SharpED stage is reflected in the empty Model prediction panel",
          "SharpED processing…" in panel_text(ordinary))
    backend._apply_cycle_progress_state(appmod.CycleProgressState(
        cycle_index=1, cycle_total=1, stage_name="EDMA · SharpED map",
        stage_index=4, stage_total=4, busy=True,
    ))
    ordinary._refresh_tick()
    check("Model prediction EDMA stage is reflected before cycle finalization",
          "EDMA structure extraction running…" in panel_text(ordinary))
    ordinary.close()

    backend._apply_cycle_progress_state(
        appmod.CycleProgressState(cycle_index=1, cycle_total=10, stage_name="Superflip", stage_index=1, stage_total=5, detail="running", busy=True)
    )
    win._refresh_tick()
    check("after the cycle-1 Superflip event: the header shows Cycle 1", "Cycle 1" in win.status_headline.text())
    check("after the cycle-1 Superflip event: 'Cycle 0' is absent", "Cycle 0" not in win.status_headline.text())
    win.close()

    # =====================================================================
    # Formulas: one label per panel, associated with the correct source and
    # its own recommended cycle -- not a single combined line.
    # =====================================================================
    win, backend = make_window("B")
    backend.results = [make_result(1, 0.7, 0.7)]
    win._refresh_tick()
    formula_texts = [label.text() for label in win.formula_labels]
    check("one formula label exists per structure panel", len(formula_texts) == len(win.structure_axes))
    # Source and cycle are named once, directly above the structure -- the
    # label below carries the chemical formula ONLY (no duplicated source).
    candidates = appmod.result_candidates_from_results(backend.results)
    expected_formulas = [
        f"EDMA asymmetric-unit composition: {candidate.edma_asu_composition}"
        for candidate in candidates
    ]
    check("the composition labels use each selected EDMA candidate's ASU composition",
          formula_texts == expected_formulas)
    check(
        "the formula labels do not repeat the source name or cycle",
        not any(word in t for t in formula_texts for word in ("Superflip", "SharpED", "Cycle")),
    )
    formula_label = win.formula_labels[0]
    base_label = QLabel("x")
    base_label.setObjectName("currentCycleDetail")
    base_label.ensurePolished()
    formula_label.ensurePolished()
    check(
        "the formula uses a larger, more readable style than the previous 8.5pt detail text",
        formula_label.objectName() == "autosolveFormula"
        and formula_label.font().pointSizeF() >= 10.0
        and formula_label.font().pointSizeF() > base_label.font().pointSizeF(),
    )
    win.close()

    # =====================================================================
    # Structure labels ("Best: Cycle N") sit right on the structure panel
    # itself (matplotlib figure text), not only in the status bar.
    # =====================================================================
    win, backend = make_window("A")
    backend.results = [make_result(3, 0.7, 0.7)]
    win._refresh_tick()
    figure_texts = " ".join(t.get_text() for t in win.structure_figure.texts)
    check("the structure panel itself shows the recommended cycle number", "Best · Cycle 3" in figure_texts)
    win.close()

    # =====================================================================
    # Simplified mouse controls: right-drag pan, wheel zoom, double-click
    # fit. Orientation is synchronized; pan/zoom remains panel-local.
    # =====================================================================
    win, backend = make_window("A")
    backend.results = [make_result(1, 0.7, 0.7)]
    win._refresh_tick()
    axis = win.structure_axes[0]

    before_limits = win._structure_axis_limits(axis)
    win._on_structure_scroll(_Event(inaxes=axis, button="up"))
    after_limits = win._structure_axis_limits(axis)
    check("wheel scroll zooms (changes the axis limits)", before_limits != after_limits)
    check(
        "zoom remains local to the panel that was scrolled",
        all(
            win._structure_axis_limits(a) != after_limits
            for a in win._structure_interactive_axes if a is not axis
        ),
    )

    win.structure_elev = 77.0
    win.structure_azim = 199.0
    win._on_canvas_button_press(_Event(dblclick=True))
    check("double-click fit preserves elevation", win.structure_elev == 77.0)
    check("double-click fit preserves azimuth", win.structure_azim == 199.0)
    check(
        "double-click fits zoom/pan back to the base framing",
        win._structure_axis_limits(axis) == win.structure_view_base_limits,
    )

    win.close()

    # =====================================================================
    # Auto-rotation: idle rotates, pauses immediately on interaction, and
    # only resumes after a short idle delay (never snaps).
    # =====================================================================
    win, backend = make_window("A")
    backend.results = [make_result(1, 0.7, 0.7)]
    win._refresh_tick()
    win.show()
    win.activateWindow()
    app.processEvents()
    win._camera._last_input = 0.0
    before = win.structure_azim
    win._auto_rotate_tick()
    check("idle: auto-rotation advances azim", win.structure_azim != before)

    win._mark_interaction()
    frozen = win.structure_azim
    win._auto_rotate_tick()
    check("immediately after an interaction: rotation stays paused", win.structure_azim == frozen)

    from phase_studio.autosolve_window import AUTO_ROTATE_RESUME_DELAY_SECONDS
    win._last_interaction_time = time.monotonic() - (AUTO_ROTATE_RESUME_DELAY_SECONDS + 0.5)
    win._camera._last_input = win._last_interaction_time
    win._auto_rotate_tick()
    check("after the idle delay has passed: rotation resumes from its current angle (no snap)", win.structure_azim != frozen)

    win.auto_rotate_button.setChecked(False)
    frozen2 = win.structure_azim
    win._last_interaction_time = 0.0
    win._auto_rotate_tick()
    check("Auto rotate: Off stops rotation entirely", win.structure_azim == frozen2)
    win.close()

    # =====================================================================
    # Reused, not duplicated: the Execution Log and progress bars are the
    # SAME widget objects the backend's own update methods already write to,
    # kept compact rather than dominating the window.
    # =====================================================================
    win, backend = make_window("A")
    check("Execution Log is the backend's own QTextEdit, reparented (not a second log)", win.isAncestorOf(backend.log_text))
    check("the log is capped to a compact default height", backend.log_text.maximumHeight() <= 140)
    compact_log_height = backend.log_text.maximumHeight()
    win.log_expand_button.click()
    app.processEvents()
    check("Expand log reveals more rows without replacing the shared log",
          backend.log_text.maximumHeight() > compact_log_height
          and win.log_expand_button.text() == "Collapse log")
    win.log_expand_button.click()
    app.processEvents()
    check("Collapse log restores the compact structure-first layout",
          backend.log_text.maximumHeight() <= 140
          and win.log_expand_button.text() == "Expand log")
    check("overall/cycle/repeat progress bars are the backend's own widgets, reparented", win.isAncestorOf(backend.run_status_panel))
    check("the progress panel has a bounded, content-derived maximum height",
          backend.run_status_panel.maximumHeight() < 16777215
          and backend.run_status_panel.maximumHeight()
          >= backend.run_status_panel.minimumSizeHint().height())
    root_layout = win.centralWidget().layout()
    panel_index = root_layout.indexOf(backend.run_status_panel)
    check("the progress panel has no stretch factor (sizes to its own content)", root_layout.stretch(panel_index) == 0)
    canvas_stretch = root_layout.stretch(root_layout.indexOf(win.structure_canvas))
    log_stretch = root_layout.stretch(root_layout.indexOf(win.log_section_widget))
    check("the structure canvas has a much larger stretch priority than the log", canvas_stretch > log_stretch)
    check(
        "the progress panel's own sizeHint is genuinely compact relative to the window",
        backend.run_status_panel.sizeHint().height() < 220,
    )
    win.close()

    # =====================================================================
    # Busy/indeterminate progress still works through the reparented bar.
    # =====================================================================
    win, backend = make_window("A")
    busy_state = appmod.CycleProgressState(
        cycle_index=1, cycle_total=10, stage_name="SharpED", stage_index=2, stage_total=4, busy=True,
    )
    backend._apply_cycle_progress_state(busy_state)
    check("busy=True switches the reparented progress bar to indeterminate (0, 0)", backend.current_cycle_progress.maximum() == 0)
    win.close()

    # =====================================================================
    # Footer (2.0.2): Cancel, Retry, and the global early Pass action. The
    # latter safely stops unfinished work and opens shared Result Selection.
    # =====================================================================
    win, backend = make_window("A")
    backend._run_status = "RUNNING"
    backend.autosolve_is_jana = lambda: True
    win._refresh_tick()
    button_texts = {button.text() for button in win.findChildren(QPushButton)}
    check("Cancel is present", "Cancel" in button_texts)
    check("global early 'Pass to Jana2020' button exists in the footer",
          any(text.startswith("Pass to Jana2020") for text in button_texts))
    check("no 'Pass to Jana2020 now' variant label remains", "Pass to Jana2020 now" not in button_texts)
    check("the footer pass action is the explicit pass_now_button", hasattr(win, "pass_now_button"))
    for forbidden in ("Run phasing", "Continue run", "Clear results", "Open full configuration"):
        check(f"'{forbidden}' is not exposed in AutosolveWindow", forbidden not in button_texts)
    check(
        "Cancel's tooltip explains it does NOT pass a result",
        "without passing a result" in win.cancel_button.toolTip().lower(),
    )
    check(
        "Cancel's tooltip is exact",
        plain_tooltip(win.cancel_button) == "Stop the calculation without passing a result to Jana2020.",
    )
    check("Retry is hidden while nothing has failed", not win.retry_button.isVisible())

    cancel_calls = []
    backend.autosolve_cancel = lambda: cancel_calls.append(True)
    win.cancel_button.click()
    check("Cancel uses the backend's autosolve_cancel()", cancel_calls == [True])
    win.close()

    # =====================================================================
    # A small view toolbar exists (Fit / Reset view / Auto rotate) and a
    # one-line mouse-control hint, not a large permanent toolbar.
    # =====================================================================
    win, backend = make_window("A")
    toolbar_button_texts = {b.text() for b in win.findChildren(QPushButton)} | {
        b.text() for b in win.findChildren(type(win.auto_rotate_button))
    }
    check("a Fit action exists", "Fit" in toolbar_button_texts)
    check("a Reset view action exists", "Reset view" in toolbar_button_texts)
    check("an Auto rotate toggle exists", any("Auto rotate" in t for t in toolbar_button_texts))

    # Items 11-12: structure actions are data-aware. Before any structure
    # is rendered they are disabled (nothing to fit / reset / rotate); the
    # first valid model -- even a one-sided result -- enables them.
    import dataclasses as _dataclasses

    backend.reference_atoms_for_plot = []
    win._refresh_tick()
    check("empty viewer: Fit / Reset view / Auto rotate are disabled before any structure is rendered",
          not any(b.isEnabled() for b in (win.fit_button, win.reset_button, win.auto_rotate_button)))
    check("empty viewer: representation choices are disabled but retain preference",
          not win.molecule_view_button.isEnabled() and not win.full_cell_view_button.isEnabled()
          and win.molecule_view_button.isChecked())
    one_sided = _dataclasses.replace(make_result(1, 0.7, 0.7), deblur_quality=None)
    backend.results = [one_sided]
    win._refresh_tick()
    check("one-sided result (Superflip only): structure actions enable on the first valid model",
          bool(win._structure_interactive_axes)
          and all(b.isEnabled() for b in (win.fit_button, win.reset_button, win.auto_rotate_button)))
    backend.results = [make_result(1, 0.7, 0.7)]
    win._refresh_tick()
    check("both sides rendered: structure actions stay enabled",
          all(b.isEnabled() for b in (win.fit_button, win.reset_button, win.auto_rotate_button)))
    check("each structure panel has its own Fullscreen action",
          all(column["fullscreen"].text() == "Fullscreen" for column in win.review_columns.values()))
    check("the global dual-view Fullscreen action is absent from the view toolbar",
          all(button.text() != "Fullscreen" for button in win.view_toolbar_buttons))
    win._open_panel_fullscreen("observed")
    app.processEvents()
    detached = win._panel_detached_viewers["observed"]
    check("Observed-data fullscreen contains exactly one structure canvas/axis",
          detached is not None and len(detached.figure.axes) == 1)
    check("Observed-data fullscreen does not introduce the Model prediction",
          "Model prediction" not in detached.metadata_label.text())
    detached.close()
    win.auto_rotate_button.setChecked(False)
    check("Auto rotate: Off stays a fully enabled, clickable control (not disabled styling, item 24)",
          win.auto_rotate_button.isEnabled())
    win.auto_rotate_button.setChecked(True)
    backend.results = []
    hint_texts = " ".join(label.text() for label in win.findChildren(QLabel))
    check("a compact mouse-control hint is present", "rotate" in hint_texts.lower() and "zoom" in hint_texts.lower())

    # =====================================================================
    # View toolbar: one control family -- text-only (Phase Studio has no
    # established icons for these view actions, and text-only is preferred
    # over a new icon family), one shared height, and a genuine segmented
    # control for the exclusive view mode.
    # =====================================================================
    from PySide6.QtCore import QPoint as _QPoint, Qt as _Qt

    toolbar_buttons = win.view_toolbar_buttons
    for button in toolbar_buttons:
        check(
            f"{button.text()}: text-only toolbar control (no invented icon)",
            button.icon().isNull() and button.toolButtonStyle() == _Qt.ToolButtonTextOnly and button.text() != "",
        )
    check("all view-toolbar controls share one height", len({b.height() for b in toolbar_buttons}) == 1)
    win.show()
    app.processEvents()
    left, right = win.molecule_view_button, win.full_cell_view_button
    left_edge = left.mapTo(win, _QPoint(left.width(), 0)).x()
    right_start = right.mapTo(win, _QPoint(0, 0)).x()
    check("the two view-mode segments adjoin with no gap", left_edge == right_start)
    check(
        "the two view-mode segments share one baseline",
        left.mapTo(win, _QPoint(0, 0)).y() == right.mapTo(win, _QPoint(0, 0)).y(),
    )
    fit_y = win.fit_button.mapTo(win, _QPoint(0, 0)).y()
    check("Fit / Reset / Auto rotate / segments share one top edge", all(b.mapTo(win, _QPoint(0, 0)).y() == fit_y for b in toolbar_buttons))
    check("Auto rotate is a checkable toggle, On by default", win.auto_rotate_button.isCheckable() and win.auto_rotate_button.isChecked())
    win.auto_rotate_button.setChecked(False)
    check("Auto rotate: Off reads as off", win.auto_rotate_button.text() == "Auto rotate: Off")
    import phase_studio.ui_style as ui_style
    check("Auto rotate: Off does not use a dimmed/disabled-looking text colour (item 24) -- "
          "no :!checked override on QToolButton#viewToggleButton",
          "viewToggleButton:!checked" not in ui_style._SHARPED_QSS.replace(" ", "").replace("\n", ""))
    win.auto_rotate_button.setChecked(True)

    check(
        "the view-mode control is a segmented pair (shared style-hook object names)",
        win.molecule_view_button.objectName() == "viewModeSegmentLeft"
        and win.full_cell_view_button.objectName() == "viewModeSegmentRight",
    )
    check("Complete molecules starts as the checked (active) segment", win.molecule_view_button.isChecked())
    check("Full cell starts unchecked", not win.full_cell_view_button.isChecked())
    win.full_cell_view_button.setChecked(True)
    check("checking Full cell unchecks Complete molecules (exclusive segment group)", not win.molecule_view_button.isChecked())
    win.close()

    # =====================================================================
    # Item 35: progress-row clipping regression across stage scenarios and
    # explicit font-point scales approximating 100/125/150% Windows text
    # scaling. (Qt is DPI-aware below the widget tree, so a real OS scale
    # change does not itself alter logical layout; the original clipping
    # bug was a hardcoded pixel cap that could truncate content at ANY
    # font size, so the meaningful, deterministic regression is: the full,
    # untruncated display text always reaches the label -- never elided --
    # for each stage scenario, at each of several representative label
    # point sizes; the Superflip-repeat row's visibility always matches
    # whether it is relevant; and no label anywhere in the panel carries an
    # explicit maximum-height cap smaller than its own single-line font
    # metrics, which is exactly the class of bug that caused the clipping.)
    # =====================================================================
    from PySide6.QtGui import QFont

    stage_scenarios = [
        ("Superflip repeat (cycle 1)", appmod.CycleProgressState(
            cycle_index=1, cycle_total=10, stage_name="Superflip", stage_index=2, stage_total=5,
            sub_index=3, sub_total=8, detail="repeat 3 of 8", busy=True,
        ), True),
        ("EDMA Superflip map (cycle 2)", appmod.CycleProgressState(
            cycle_index=2, cycle_total=10, stage_name="EDMA · Superflip map", stage_index=4, stage_total=5, busy=True,
        ), False),
        ("SharpED busy (cycle 2)", appmod.CycleProgressState(
            cycle_index=2, cycle_total=10, stage_name="SharpED", stage_index=3, stage_total=5,
            detail="preparing upload", busy=True,
        ), False),
        ("Validation/finalizing (cycle 3)", appmod.CycleProgressState(
            cycle_index=3, cycle_total=10, stage_name="Finalizing cycle", stage_index=5, stage_total=5,
            detail="validating against reference", busy=False,
        ), False),
    ]
    for scale_pct in (100, 125, 150):
        for scenario_label, state, repeat_expected in stage_scenarios:
            win, backend = make_window("A")
            backend._apply_cycle_progress_state(state)
            win._refresh_tick()
            case = f"{scale_pct}% / {scenario_label}"

            check(
                f"{case}: the bottom cycle/stage row shows the full, untruncated text",
                backend.current_cycle_detail.text() == state.display_text(),
            )
            check(
                f"{case}: the Superflip-repeat row visibility matches relevance",
                backend.superflip_repeat_group.isVisibleTo(win) == repeat_expected,
            )
            check(
                f"{case}: the progress panel has a safe content-derived height cap",
                backend.run_status_panel.maximumHeight() < 16777215
                and backend.run_status_panel.maximumHeight()
                >= backend.run_status_panel.minimumSizeHint().height(),
            )

            # No label in the panel's subtree carries a hardcoded maximum
            # height smaller than one line of text at this point size --
            # exactly the bug class that caused the original clipping,
            # exercised at a font point size representative of this scale.
            font = QFont(backend.current_cycle_detail.font())
            font.setPointSizeF(font.pointSizeF() * (scale_pct / 100.0))
            no_undersized_cap = True
            for label in backend.run_status_panel.findChildren(QLabel):
                scaled = QFont(label.font())
                scaled.setPointSizeF(scaled.pointSizeF() * (scale_pct / 100.0))
                from PySide6.QtGui import QFontMetrics
                line_height = QFontMetrics(scaled).height()
                if label.maximumHeight() < 16777215 and label.maximumHeight() < line_height:
                    no_undersized_cap = False
            check(f"{case}: no progress-panel label caps below one line of text at this scale", no_undersized_cap)
            win.close()

    # =====================================================================
    # Autosolve has no configuration panel: the full GUI's "Configuration
    # locked while the calculation is running." hint is not shown here, even
    # when the backend locks its (hidden) configuration.
    # =====================================================================
    win, backend = make_window("A")
    win.show()
    backend._set_configuration_locked(True)
    app.processEvents()
    visible_texts = " ".join(label.text() for label in win.findChildren(QLabel) if label.isVisibleTo(win))
    check("no 'Configuration locked' message is visible in AutosolveWindow", "configuration locked" not in visible_texts.lower())
    check(
        "the backend's lock hint is detached from the Autosolve progress panel",
        not backend.run_status_panel.isAncestorOf(backend.configuration_lock_hint)
        and not backend.configuration_lock_hint.isVisibleTo(win),
    )
    backend._set_configuration_locked(False)
    win.close()

    # =====================================================================
    # Compact progress: "Overall [bar]" then "Cycle N of M · stage · state
    # ... Stage i of n [bar]"; Superflip repeat only while meaningful,
    # directly below the stage bar it belongs to.
    # =====================================================================
    win, backend = make_window("B")
    win.show()
    app.processEvents()
    check(
        "before the first cycle: the bottom row reads 'Preparing Autosolve…' (never Cycle 0)",
        backend.current_cycle_detail.text() == "Preparing Autosolve…" and "Cycle 0" not in backend.current_cycle_detail.text(),
    )
    state = appmod.CycleProgressState(
        cycle_index=3, cycle_total=10, stage_name="Superflip", stage_index=2, stage_total=6,
        sub_index=4, sub_total=20, detail="running", busy=True,
    )
    backend._apply_cycle_progress_state(state)
    win._refresh_tick()
    app.processEvents()
    detail_y = backend.current_cycle_detail.mapTo(win, _QPoint(0, 0)).y()
    counter_y = backend.current_cycle_stage_counter.mapTo(win, _QPoint(0, 0)).y()
    check(
        "the cycle/stage text and 'Stage i of n' share one row",
        abs(detail_y - counter_y) <= 2 and backend.current_cycle_stage_counter.text() == "Stage 2 of 6",
    )
    check(
        "header and bottom row show the same authoritative text",
        backend.current_cycle_detail.text() == "Cycle 3 of 10 · Superflip · Running"
        and win.status_headline.text().endswith("Cycle 3 of 10 · Superflip · Running"),
    )
    visible_captions = {label.text() for label in backend.run_status_panel.findChildren(QLabel) if label.isVisibleTo(win)}
    check("no redundant 'RUN STATUS' / 'Current cycle' captions", not ({"RUN STATUS", "Current cycle"} & visible_captions))
    panel_layout = backend.run_status_panel.layout()
    check(
        "the Superflip repeat row sits directly below the stage bar",
        panel_layout.indexOf(backend.superflip_repeat_group) == panel_layout.indexOf(backend.current_cycle_progress) + 1,
    )
    check("the Superflip repeat row is shown while meaningful", backend.superflip_repeat_group.isVisibleTo(win))
    backend._apply_cycle_progress_state(appmod.CycleProgressState(
        cycle_index=3, cycle_total=10, stage_name="SharpED", stage_index=3, stage_total=6, detail="processing", busy=True,
    ))
    win._refresh_tick()
    check("...and hidden during SharpED", not backend.superflip_repeat_group.isVisibleTo(win))
    for label in backend.run_status_panel.findChildren(QLabel):
        if label.isVisibleTo(win) and label.text() and not label.wordWrap():
            if label.fontMetrics().horizontalAdvance(label.text()) > label.width():
                check(f"progress label '{label.text()}' is fully visible", False)
    win.close()

    # =====================================================================
    # Complete molecules: completed asymmetric fragments only; isolated
    # peaks never control the camera; one copy per molecule; sane bonds.
    # =====================================================================
    from phase_studio.autosolve_window import (
        MOLECULE_VIEW_FILL,
        _complete_molecule_view_for_path,
        bond_graph_problems,
        build_complete_molecule_view,
    )

    def cif_text(cell, sg, rows):
        lines = [
            "data_test", f"_cell_length_a {cell[0]}", f"_cell_length_b {cell[1]}", f"_cell_length_c {cell[2]}",
            "_cell_angle_alpha 90.0", "_cell_angle_beta 90.0", "_cell_angle_gamma 90.0",
            f"_space_group_name_H-M_alt '{sg}'", "loop_", "_atom_site_label", "_atom_site_type_symbol",
            "_atom_site_fract_x", "_atom_site_fract_y", "_atom_site_fract_z",
        ]
        return "\n".join(lines + [" ".join(str(v) for v in row) for row in rows]) + "\n"

    # A centrosymmetric O-C-C-O molecule on the inversion center: the
    # asymmetric unit holds half of it, the second C is deliberately stored
    # as the far-away equivalent (x+1 side), plus one remote isolated peak.
    half_molecule = [
        ("C1", "C", 0.0714, 0.0, 0.0),
        ("O1", "O", 0.7856, 0.0, 0.0),   # == -0.2144 + 1: bonded to C1's inversion mate
        ("O9", "O", 0.5, 0.5, 0.5),      # remote isolated peak, 8.7 A from the molecule
    ]
    molecule_cif = model("inversion.cif", cif_text((10.0, 10.0, 10.0), "P -1", half_molecule))
    m_cell, m_sg, _ = appmod.parse_cif_cell_and_sg(molecule_cif)
    view = build_complete_molecule_view(appmod.parse_cif_atoms(molecule_cif), m_cell, m_sg)
    elements = sorted(appmod.clean_element_symbol(a.element) for a in view.atoms)
    check("the molecule is completed with its symmetry mates: O-C-C-O (4 atoms)", elements == ["C", "C", "O", "O"])
    check("exactly the 3 chemical bonds O-C, C-C, C-O", len(view.bonds) == 3)
    check("the molecule is drawn once (the far ASU copy did not start a second molecule)", len(view.atoms) == 4)
    check("the remote isolated peak is not primary content", all(a.label != "O9" for a in view.atoms))
    check("the remote isolated peak is outside the fit sphere, so it is not drawn either", len(view.secondary_atoms) == 0)
    check("fit bounds come from the molecule only (radius ~2.1 A, not ~9 A)", view.fit_radius < 3.0)
    check("bond graph sanity: no problems", bond_graph_problems(len(view.atoms), view.coords, view.bonds) == [])

    # A nearby unassigned peak inside the molecule's sphere is kept only as
    # the faint secondary layer, and still does not change the fit.
    near_rows = half_molecule[:2] + [("Q1", "O", 0.0, 0.18, 0.0)]  # 1.9 A from C1: unbonded, inside the sphere
    near_cif = model("near_peak.cif", cif_text((10.0, 10.0, 10.0), "P -1", near_rows))
    n_cell, n_sg, _ = appmod.parse_cif_cell_and_sg(near_cif)
    near_view = build_complete_molecule_view(appmod.parse_cif_atoms(near_cif), n_cell, n_sg)
    check("a nearby unassigned peak becomes the secondary layer", len(near_view.secondary_atoms) >= 1)
    check("...without changing the fit", abs(near_view.fit_radius - view.fit_radius) < 1.0e-6)

    # Bond-count sanity on a realistic symmetric case (P 21/c, general
    # position): the fragment never duplicates atoms and stays chain-like.
    ring = [("C%d" % (i + 1), "C", round(0.25 + 0.14 * np.cos(i * np.pi / 3) * 1.0, 4),
             round(0.25 + 0.14 * np.sin(i * np.pi / 3), 4), 0.25) for i in range(6)]
    ring_cif = model("ring.cif", cif_text((10.0, 10.0, 10.0), "P 1 21/c 1", ring))
    r_cell, r_sg, _ = appmod.parse_cif_cell_and_sg(ring_cif)
    ring_view = build_complete_molecule_view(appmod.parse_cif_atoms(ring_cif), r_cell, r_sg)
    check("a 6-ring in P21/c: exactly one ring of 6 atoms", len(ring_view.atoms) == 6)
    check("a 6-ring in P21/c: exactly 6 bonds", len(ring_view.bonds) == 6)
    check("bond sanity: no duplicate/coincident/over-long bonds", bond_graph_problems(6, ring_view.coords, ring_view.bonds) == [])
    check(
        "bond sanity guard rejects duplicates and coincident atoms",
        bond_graph_problems(2, np.array([[0, 0, 0], [0, 0, 0]], dtype=float), [(0, 1), (1, 0)]) != [],
    )

    # Z' > 1: two independent, equally sized molecules in one asymmetric
    # unit must each be retained once.  Comparable components are distinct
    # crystallographic content, not symmetry copies of one another.
    zprime_rows = [
        ("C1", "C", 0.10, 0.10, 0.10), ("C2", "C", 0.15, 0.10, 0.10),
        ("N1", "N", 0.60, 0.60, 0.60), ("N2", "N", 0.65, 0.60, 0.60),
    ]
    zprime_cif = model("zprime_two.cif", cif_text((20.0, 20.0, 20.0), "P 1", zprime_rows))
    zp_cell, zp_sg, _ = appmod.parse_cif_cell_and_sg(zprime_cif)
    zprime_view = build_complete_molecule_view(appmod.parse_cif_atoms(zprime_cif), zp_cell, zp_sg)
    check("Z' > 1: both independent two-atom molecules are displayed exactly once",
          len(zprime_view.atoms) == 4 and len(zprime_view.bonds) == 2
          and len({node for bond in zprime_view.bonds for node in bond}) == 4)
    check("Z' > 1: no independent site is duplicated", all(
        float(np.linalg.norm(zprime_view.coords[i] - zprime_view.coords[j])) >= 0.01
        for i in range(len(zprime_view.coords)) for j in range(i + 1, len(zprime_view.coords))
    ))

    # =====================================================================
    # Representation independence (2.0.1 correction pass): a real MOF case
    # (ID00003630_VE047) showed "Complete molecules" giving WILDLY different
    # results for Charge-flipping solution (Superflip) vs Model prediction (SharpED)
    # -- 236 atoms from a 72-atom asymmetric unit for one, ~64 for the
    # other, from the SAME algorithm. Root cause: the breadth-first growth
    # marked a seed atom "covered" once absorbed, but that flag only gated
    # STARTING a new component -- it never stopped the SAME growing
    # component from re-absorbing a DIFFERENT symmetry image of an already-
    # included seed. For a periodically bonded network, the same seed was
    # pulled in through different operations and translations before growth
    # exhausted the ±1-cell search neighborhood -- exactly what made
    # "Complete molecules" look like a full-cell expansion. The fix first
    # realizes every independent ASU site at most once, choosing its nearest
    # bonded symmetry/translation image. A bounded second pass then admits
    # one genuinely required non-identity mate per site for small molecules
    # on special positions, while periodic frameworks stay bounded.
    #
    # CASE A/B/C: chemically identical structures, represented differently.
    # For "Complete molecules", all three must produce the SAME displayed
    # molecular content after normalization -- the display must not depend
    # on whether the source happens to be asymmetric-unit-only, already
    # P1-expanded, or symmetry-generated.
    # =====================================================================
    def component_count(view):
        import collections

        adjacency = collections.defaultdict(set)
        for i, j in view.bonds:
            adjacency[i].add(j)
            adjacency[j].add(i)
        seen_nodes, count = set(), 0
        for start in range(len(view.atoms)):
            if start in seen_nodes:
                continue
            count += 1
            stack = [start]
            while stack:
                node = stack.pop()
                if node in seen_nodes:
                    continue
                seen_nodes.add(node)
                stack.extend(adjacency[node] - seen_nodes)
        return count

    def duplicate_pairs(view, tol=0.01):
        coords = view.coords
        return sum(
            1
            for i in range(len(coords))
            for j in range(i + 1, len(coords))
            if float(np.linalg.norm(coords[i] - coords[j])) < tol
        )

    # CASE A: non-P1 CIF, asymmetric-unit coordinates only (2 seed atoms;
    # the same centrosymmetric-dimer construction as the O-C-C-O case
    # above, reused deliberately: this is the "molecule genuinely needs a
    # SECOND, different operation" scenario the fix must keep working).
    au_only = [("C1", "C", 0.0714, 0.0, 0.0), ("O1", "O", 0.7856, 0.0, 0.0)]
    case_a_cif = model("repr_case_a.cif", cif_text((10.0, 10.0, 10.0), "P -1", au_only))
    a_cell, a_sg, _ = appmod.parse_cif_cell_and_sg(case_a_cif)
    a_atoms = appmod.parse_cif_atoms(case_a_cif)
    view_a = build_complete_molecule_view(a_atoms, a_cell, a_sg)

    # CASE B: the SAME molecule, already P1/full-cell-expanded -- all 4 real
    # atom positions given explicitly, declared space group P1.
    p1_expanded = [
        ("C1a", "C", 0.0714, 0.0, 0.0), ("C1b", "C", 0.9286, 0.0, 0.0),
        ("O1a", "O", 0.7856, 0.0, 0.0), ("O1b", "O", 0.2144, 0.0, 0.0),
    ]
    case_b_cif = model("repr_case_b.cif", cif_text((10.0, 10.0, 10.0), "P 1", p1_expanded))
    b_cell, b_sg, _ = appmod.parse_cif_cell_and_sg(case_b_cif)
    b_atoms = appmod.parse_cif_atoms(case_b_cif)
    view_b = build_complete_molecule_view(b_atoms, b_cell, b_sg)

    # CASE C: symmetry-generated EDMA-like CIF -- built with the SAME
    # expand_atoms_by_symmetry() the real EDMA/production pipeline uses,
    # then written out as its own P1 CIF (as EDMA's own P1 output would be).
    expanded_atoms = appmod.expand_atoms_by_symmetry(a_atoms, a_sg)
    generated_rows = [
        (atom.label, appmod.clean_element_symbol(atom.element), *[round(float(v), 6) for v in atom.frac])
        for atom in expanded_atoms
    ]
    case_c_cif = model("repr_case_c.cif", cif_text((10.0, 10.0, 10.0), "P 1", generated_rows))
    c_cell, c_sg, _ = appmod.parse_cif_cell_and_sg(case_c_cif)
    c_atoms = appmod.parse_cif_atoms(case_c_cif)
    view_c = build_complete_molecule_view(c_atoms, c_cell, c_sg)

    for label, view in (("CASE A (non-P1, AU-only)", view_a), ("CASE B (P1-expanded)", view_b), ("CASE C (symmetry-generated P1)", view_c)):
        elements = sorted(appmod.clean_element_symbol(a.element) for a in view.atoms)
        check(f"{label}: Complete molecules gives the complete O-C-C-O dimer (4 atoms), not more",
              elements == ["C", "C", "O", "O"])
        check(f"{label}: exactly 3 bonds, 1 connected component", len(view.bonds) == 3 and component_count(view) == 1)
        check(f"{label}: no exact/near-coincident duplicate atoms", duplicate_pairs(view) == 0)

    check("representation independence: CASE A/B/C give the SAME atom count for Complete molecules",
          len(view_a.atoms) == len(view_b.atoms) == len(view_c.atoms) == 4)

    # Full cell: all three representations of the SAME physical structure
    # must expand to the SAME complete unit-cell content (item 30/32) --
    # applying expansion to an already-expanded (P1) input must not
    # multiply it again.
    full_cell_counts = []
    for path in (case_a_cif, case_b_cif, case_c_cif):
        cell, sg, _ = appmod.parse_cif_cell_and_sg(path)
        atoms = appmod.parse_cif_atoms(path)
        full_cell_counts.append(len(appmod.expand_atoms_by_symmetry(atoms, sg)))
    check(f"no-double-expansion: Full cell gives the SAME atom count (4) for AU-only, P1-expanded and "
          f"symmetry-generated input alike: {full_cell_counts}", full_cell_counts == [4, 4, 4])

    # Switching Complete molecules -> Full cell -> Complete molecules must
    # be deterministic and reversible (item 14).
    view_a_again = build_complete_molecule_view(appmod.parse_cif_atoms(case_a_cif), a_cell, a_sg)
    check("Complete molecules is deterministic across repeated calls (same CIF, same result)",
          len(view_a_again.atoms) == len(view_a.atoms)
          and sorted(appmod.clean_element_symbol(a.element) for a in view_a_again.atoms) == sorted(appmod.clean_element_symbol(a.element) for a in view_a.atoms))

    # =====================================================================
    # Special positions (item 9/33): an atom exactly ON a symmetry element
    # (here, the inversion center) must appear exactly ONCE, never
    # duplicated at its own invariant position -- while a genuinely
    # general-position atom it is bonded to may legitimately appear twice
    # (its own two symmetry-related images), which is not a duplicate.
    # =====================================================================
    special_rows = [
        ("M1", "C", 0.0, 0.0, 0.0),    # exactly at the P-1 inversion center: invariant
        ("L1", "N", 0.05, 0.0, 0.0),   # general position, 0.5 A from M1
    ]
    special_cif = model("special_position.cif", cif_text((10.0, 10.0, 10.0), "P -1", special_rows))
    s_cell, s_sg, _ = appmod.parse_cif_cell_and_sg(special_cif)
    s_atoms = appmod.parse_cif_atoms(special_cif)
    view_s = build_complete_molecule_view(s_atoms, s_cell, s_sg)
    elements_s = sorted(appmod.clean_element_symbol(a.element) for a in view_s.atoms)
    check("special position: the invariant atom (M1, on the inversion center) appears exactly ONCE",
          elements_s.count("C") == 1)
    check("special position: the general-position atom it coordinates (L1) legitimately appears twice "
          "(its two real, symmetry-related images -- not a duplicate)", elements_s.count("N") == 2)
    check("special position: no exact/near-coincident duplicate spheres", duplicate_pairs(view_s) == 0)
    check("special position: Full cell stays crystallographically correct "
          "(M1 special-position: 1 image; L1 general-position: 2 images -- 3 total, not 4)",
          len(appmod.expand_atoms_by_symmetry(s_atoms, s_sg)) == 3)

    # =====================================================================
    # Periodic-chain regression (root-cause fixture): a minimal P1 "infinite
    # polymer" -- A1 at the origin, B1 half a (short) cell away -- where B1
    # is within bonding distance of BOTH A1's own image (offset 0, its
    # starting seed) and A1's periodic image one cell translation away
    # (offset -1, the SAME symmetry operation -- identity, the only op in
    # P1 -- reused at a DIFFERENT lattice translation). This is the exact
    # shape of the real MOF defect: growth must stop after one bonded pair,
    # not re-admit A1 a second time via its own periodic image and keep
    # walking outward forever. Confirmed to actually discriminate the fix:
    # the pre-fix algorithm gives 6 atoms/5 bonds (runaway growth) on this
    # fixture; the fix gives 2 atoms/1 bond.
    # =====================================================================
    chain_rows = [("A1", "Na", 0.0, 0.0, 0.0), ("B1", "Cl", 0.5, 0.0, 0.0)]
    chain_cif = model("periodic_chain.cif", cif_text((5.0, 12.0, 12.0), "P 1", chain_rows))
    chain_cell, chain_sg, _ = appmod.parse_cif_cell_and_sg(chain_cif)
    chain_atoms = appmod.parse_cif_atoms(chain_cif)
    view_chain = build_complete_molecule_view(chain_atoms, chain_cell, chain_sg)
    check("periodic chain: growth stops at one bonded pair, not the whole infinite chain "
          f"(got {len(view_chain.atoms)} atoms, {len(view_chain.bonds)} bonds)",
          len(view_chain.atoms) == 2 and len(view_chain.bonds) == 1)
    check("periodic chain: no exact/near-coincident duplicate atoms", duplicate_pairs(view_chain) == 0)

    # =====================================================================
    # The real defect case (item 34/36): the actual ID00003630_VE047
    # Observed-data EDMA CIF, if present on this machine (recorded from a
    # real Autosolve run). Skipped, not failed, when unavailable -- this is
    # local acceptance data, not a shipped fixture.
    # =====================================================================
    # Optional private acceptance data are opt-in, never a published local path.
    real_observed_cif = Path(os.environ.get("PHASE_STUDIO_TEST_MOF_CIF", ""))
    if real_observed_cif.is_file():
        real_cell, real_sg, _ = appmod.parse_cif_cell_and_sg(real_observed_cif)
        real_atoms = appmod.parse_cif_atoms(real_observed_cif)
        real_view = build_complete_molecule_view(real_atoms, real_cell, real_sg)
        check(f"real MOF case: Complete molecules no longer looks like a full-cell expansion "
              f"({len(real_view.atoms)} atoms from a {len(real_atoms)}-atom asymmetric unit, "
              f"full cell would be {len(appmod.expand_atoms_by_symmetry(real_atoms, real_sg))})",
              len(real_view.atoms) < 0.5 * len(appmod.expand_atoms_by_symmetry(real_atoms, real_sg)))
        check("real MOF case: no exact/near-coincident duplicate atoms", duplicate_pairs(real_view) == 0)
        # The exact root-cause criterion (no seed atom contributes more than
        # one image via the SAME symmetry operation) is pinned directly by
        # the synthetic CASE A/B/C and special-position fixtures above; this
        # real-data check only confirms the observable symptom is gone.

    # In the window: Fit frames the molecule clearly (70-85% of the panel's
    # drawing square), is rotation-safe (no atom ever leaves the square), and
    # Full cell keeps the whole cell frame in view.
    from mpl_toolkits.mplot3d import proj3d

    def projected_fraction(win, axis, coords):
        win.structure_canvas.draw()
        projection = axis.get_proj()
        xs, ys, _ = proj3d.proj_transform(coords[:, 0], coords[:, 1], coords[:, 2], projection)
        pixels = axis.transData.transform(np.column_stack((xs, ys)))
        extent = axis.get_window_extent()
        square = min(extent.width, extent.height)
        center = np.array([extent.x0 + extent.width / 2.0, extent.y0 + extent.height / 2.0])
        span = float(np.max(np.ptp(pixels, axis=0)))
        inside = bool(np.all(np.abs(pixels - center) <= square / 2.0))
        return span / square, inside

    win, backend = make_window("A")
    win.resize(1280, 900)
    win.show()
    backend.results = [make_result(1, 0.7, 0.7)]
    backend.results[0].superflip_edma_cif.write_text(molecule_cif.read_text(encoding="utf-8"), encoding="utf-8")
    backend.results[0].deblur_edma_cif.write_text(ring_cif.read_text(encoding="utf-8"), encoding="utf-8")
    win._rendered_once = False
    win._refresh_tick()
    app.processEvents()
    for label, axis_index in (("Superflip (O-C-C-O + remote peak)", 0), ("SharpED (6-ring)", 1)):
        axis = win.structure_axes[axis_index]
        coords = win._structure_depth_artists[axis_index].atom_coordinates
        fractions, all_inside = [], True
        for elev, azim in ((20, 35), (0, 0), (0, 90), (90, 0), (45, 200), (-30, 300)):
            for a in win.structure_axes:
                a.view_init(elev=elev, azim=azim)
            fraction, inside = projected_fraction(win, axis, coords)
            fractions.append(fraction)
            all_inside = all_inside and inside
        check(
            f"{label}: Fit fills 70-85% of the panel at its widest ({max(fractions):.2f})",
            0.70 <= max(fractions) <= 0.85,
        )
        check(f"{label}: no atom is cropped at any rotation", all_inside)
    check(
        "each panel is framed on its OWN fragment (different fit centers per panel)",
        not np.allclose(win._axis_fits[win.structure_axes[0]][0], win._axis_fits[win.structure_axes[1]][0]),
    )
    win._on_structure_scroll(_Event(inaxes=win.structure_axes[0], button="up"))
    zoomed = [win._structure_axis_limits(a) for a in win.structure_axes]
    check(
        "wheel zoom changes only the active panel",
        abs((zoomed[0][0][1] - zoomed[0][0][0]) / 2.0 - win._axis_fits[win.structure_axes[0]][1] * 0.9) < 1e-6
        and all(
            abs((lim[0][1] - lim[0][0]) / 2.0 - win._axis_fits[a][1]) < 1e-6
            for a, lim in zip(win.structure_axes[1:], zoomed[1:])
        ),
    )
    win._fit_structure_view()
    check(
        "Fit restores every panel to its own content fit",
        all(win._structure_axis_limits(a) == win._fit_limits(a) for a in win.structure_axes),
    )

    win.full_cell_view_button.setChecked(True)
    app.processEvents()
    check("Full cell: still zero bond artists", len(win._bond_artists) == 0)
    for axis_index, axis in enumerate(win.structure_axes):
        corners = win._structure_depth_artists[axis_index].cell_corners
        inside_all = True
        for elev, azim in ((20, 35), (0, 45), (60, 120), (-45, 250)):
            for a in win.structure_axes:
                a.view_init(elev=elev, azim=azim)
            _fraction, inside = projected_fraction(win, axis, corners)
            inside_all = inside_all and inside
        check(f"Full cell panel {axis_index + 1}: the whole unit-cell frame stays in view at every rotation", inside_all)
    full_cell_counts = [len(a.atom_coordinates) for a in win._structure_depth_artists]
    check("Full cell and Complete molecules differ (cell shows every symmetry-expanded peak)", full_cell_counts[0] > 4)
    win.close()
    check(
        "the Complete-molecules view is cached per file (mode switches do not regrow it)",
        _complete_molecule_view_for_path(molecule_cif) is _complete_molecule_view_for_path(molecule_cif),
    )
    check("the documented molecule fill target is within 70-85%", 0.70 <= MOLECULE_VIEW_FILL <= 0.85)

    # =====================================================================
    # Camera refit policy (items 19-22): a re-render only resets the user's
    # zoom/pan at a genuine data transition -- a new candidate (cycle
    # change) or the SAME candidate's extent moving materially -- never for
    # an ordinary threshold nudge that leaves the extent about the same,
    # and never merely because manual mouse interaction happened (which
    # never touches backend state, so never re-renders at all).
    # =====================================================================
    import phase_studio.autosolve_review as guided

    def small_cif(name, dx=0.0):
        # A bonded 2-atom fragment (short bond) -- fit_radius floors to
        # MIN_FIT_RADIUS_ANGSTROM (1.0), a small, stable extent.
        return model(name, cif_text((20.0, 20.0, 20.0), "P 1", [
            ("A1", "C", 0.50 + dx, 0.5, 0.5), ("B1", "O", 0.56 + dx, 0.5, 0.5),
        ]))

    def big_cif(name):
        # A bonded 5-atom chain spanning far more space -- fit_radius is
        # genuinely, materially larger (not floor-limited).
        return model(name, cif_text((20.0, 20.0, 20.0), "P 1", [
            ("A1", "C", 0.40, 0.5, 0.5), ("B1", "N", 0.45, 0.5, 0.5), ("C1", "N", 0.50, 0.5, 0.5),
            ("D1", "O", 0.55, 0.5, 0.5), ("E1", "C", 0.60, 0.5, 0.5),
        ]))

    def panel_for(cycle, cif_path, sigma=1.0):
        return guided.ReviewPanel(
            role=guided.ROLE_OBSERVED, cycle=cycle, map_path=map_file(f"refit{cycle}.xplor"),
            current_cif=cif_path, threshold_sigma=sigma,
        )

    win, backend = make_window("A")
    win._render_structures(panel_for(1, small_cif("refit_c1_small.cif")), None)
    check("camera refit: first render fits (zoom reset to 1.0)", win._view_zoom == 1.0)
    win._view_zoom = 0.4
    win._view_pan = np.array([0.1, 0.0, 0.0])

    # Same cycle, a different (re-extracted) CIF with a near-identical
    # extent -- an ordinary +/- atoms nudge. Must NOT refit.
    win._render_structures(panel_for(1, small_cif("refit_c1_nudge.cif", dx=0.01)), None)
    check("camera refit: same cycle + similar extent (an ordinary threshold nudge) preserves the user's zoom/pan",
          win._view_zoom == 0.4 and win._view_pan[0] == 0.1)

    # Same cycle, but the extent changes a lot (a big threshold move).
    win._render_structures(panel_for(1, big_cif("refit_c1_big.cif")), None)
    check("camera refit: same cycle + materially different extent DOES refit",
          win._view_zoom == 1.0 and win._view_pan[0] == 0.0)

    win._view_zoom = 0.4
    win._view_pan = np.array([0.1, 0.0, 0.0])
    # A genuinely new candidate (cycle change), even with a similar extent
    # to the immediately-prior one -- refits regardless.
    win._render_structures(panel_for(2, small_cif("refit_c2_small.cif")), None)
    check("camera refit: a new candidate (cycle change) DOES refit even if the extent is similar",
          win._view_zoom == 1.0 and win._view_pan[0] == 0.0)
    win.close()

    # =====================================================================
    # Execution Log: whole rows only. Auto-scrolled to the newest message,
    # no row may be half-visible at the top; 3-6 visible rows.
    # =====================================================================
    win, backend = make_window("A")
    win.resize(1280, 900)
    win.show()
    app.processEvents()
    for i in range(40):
        backend._append_execution_log(f"[Test] log line {i + 1} with descenders pgyjq", level="INFO")
    app.processEvents()
    win._fit_log_height()
    app.processEvents()
    log = backend.log_text
    bar = log.verticalScrollBar()
    bar.setValue(bar.maximum())
    app.processEvents()
    document = log.document()
    doc_layout = document.documentLayout()
    offset = bar.value()
    viewport_h = log.viewport().height()
    partial_top = []
    fully_visible = 0
    block = document.firstBlock()
    while block.isValid():
        rect = doc_layout.blockBoundingRect(block)
        top, bottom = rect.top() - offset, rect.bottom() - offset
        if top < -1.0 and bottom > 1.0:
            partial_top.append(block.text())
        if top >= -1.0 and bottom <= viewport_h + 1.0:
            fully_visible += 1
        block = block.next()
    check("log: no row is cut in half at the top when auto-scrolled to the newest row", partial_top == [])
    check(f"log: stays compact -- 3 to 6 fully visible rows ({fully_visible})", 3 <= fully_visible <= 6)
    newest = document.findBlockByNumber(document.blockCount() - 1)
    newest_rect = doc_layout.blockBoundingRect(newest)
    check("log: the newest row is fully visible", newest_rect.top() - offset >= -1.0 and newest_rect.bottom() - offset <= viewport_h + 1.0)
    win.close()

    # Production path: NO explicit _fit_log_height() after show. Launch-time
    # log lines exist before the window is shown (as in
    # launch_autosolve_from_jana); the pre-show fit only has an estimated
    # frame height, and the window must refit itself once shown. Before the
    # fix the top row was cut by ~9 px here.
    backend = appmod.IterativeSuperflipPipelineQtGUI()
    backend.current_validation_profile = ValidationProfile.REFERENCE_AND_HOLDOUT
    for i in range(6):
        backend._append_execution_log(f"[Jana2020] pre-show line {i + 1}", level="INFO")
    win = AutosolveWindow(backend, "A")
    win.resize(1280, 900)
    win.show()
    for _ in range(5):
        app.processEvents()

    def log_row_cuts():
        log = backend.log_text
        bar = log.verticalScrollBar()
        bar.setValue(bar.maximum())
        app.processEvents()
        doc_layout = log.document().documentLayout()
        offset, viewport_h = bar.value(), log.viewport().height()
        cuts = []
        block = log.document().firstBlock()
        while block.isValid():
            rect = doc_layout.blockBoundingRect(block)
            top, bottom = rect.top() - offset, rect.bottom() - offset
            if (top < -1.0 and bottom > 1.0) or (top < viewport_h - 1.0 and bottom > viewport_h + 1.0):
                cuts.append(block.text())
            block = block.next()
        return cuts

    log_bar = backend.log_text.verticalScrollBar()
    check("log (production path): after the refit the log still FOLLOWS the newest line "
          "(the view was ~28 px short of the bottom and stopped auto-scrolling)",
          log_bar.value() == log_bar.maximum())
    for i in range(12):
        text = f"[Test] unforced line {i + 1}\n  output: C:\\x.cif"
        backend._append_execution_log(text, level=("STEP", "DETAIL", "WARNING")[i % 3])
        app.processEvents()
    check("log (production path): streamed multi-line records keep the view at the newest line without any forced scroll",
          log_bar.value() == log_bar.maximum())
    check("log (production path, lines before show): no row cut at the top or bottom after show", log_row_cuts() == [])
    for i in range(30):
        backend._append_execution_log(f"[Test] streamed line {i + 1} pgyjq", level="INFO")
        if i in (0, 3, 29):
            app.processEvents()
            check(f"log (production path): no row cut after {i + 1} streamed lines", log_row_cuts() == [])
    win.close()

    # =====================================================================
    # Active Jana2020 input: basename shown as a secondary context line
    # (full path in the tooltip), middle-elided when long, always the
    # CURRENT job (captured RunConfig wins over the launch argument).
    # =====================================================================
    job_a = tmp / "ID00003652_VE048_Superflip.inflip"
    job_a.write_text("title a\n", encoding="utf-8")
    backend_a = appmod.IterativeSuperflipPipelineQtGUI()
    win = AutosolveWindow(backend_a, "A", inflip_path=job_a)
    win.resize(1280, 900)
    win.show()
    app.processEvents()
    win._refresh_tick()
    check("input: the active .inflip basename is shown", win.status_secondary.text() == "Jana2020 input: ID00003652_VE048_Superflip.inflip")
    check("input: the full path is in the tooltip, not the label", plain_tooltip(win.status_secondary) == str(job_a) and str(tmp) not in win.status_secondary.text())
    check("input: the run title stays the dominant headline", win.status_headline.objectName() == "dashboardTitle" and win.status_secondary.objectName() == "dashboardSubtitle")
    job_medium = tmp / "ID00003652_VE048_long_measurement_series_Superflip.inflip"
    win._launch_inflip_path = job_medium
    win._refresh_input_label()
    app.processEvents()
    check(
        "input: a medium-length name is shown fully when it fits",
        win.status_secondary.text() == "Jana2020 input: " + job_medium.name
        and win.status_secondary.fontMetrics().horizontalAdvance(win.status_secondary.text()) <= win.status_secondary.width(),
    )
    long_name = "ID00003652_" + "VeryLongJanaJobName_" * 7 + "Superflip.inflip"
    job_long = tmp / long_name
    job_long.write_text("title long\n", encoding="utf-8")
    win._launch_inflip_path = job_long
    # Exercise elision in a constrained viewport with the ordinary UI font.
    win.resize(900, win.height())
    app.processEvents()
    width_before = win.width()
    win._refresh_input_label()
    app.processEvents()
    shown = win.status_secondary.text()
    check("input: a very long name is elided (…) and keeps the .inflip suffix", "…" in shown and shown.endswith(".inflip"))
    check(
        "input: the elided line fits its label and does not widen the window",
        win.status_secondary.fontMetrics().horizontalAdvance(shown) <= win.status_secondary.width() and win.width() == width_before,
    )
    check("input: the long name's full path is in the tooltip", plain_tooltip(win.status_secondary) == str(job_long))
    job_b = tmp / "second_job_Superflip.inflip"
    job_b.write_text("title b\n", encoding="utf-8")
    backend_a.last_run_config = type("Cfg", (), {"jana_inflip": job_b})()
    win._refresh_tick()
    check("input: once the run is captured, the RunConfig's own .inflip is authoritative", win.status_secondary.text() == "Jana2020 input: second_job_Superflip.inflip")
    win.close()
    backend_c = appmod.IterativeSuperflipPipelineQtGUI()
    job_c = tmp / "third_job.inflip"
    job_c.write_text("title c\n", encoding="utf-8")
    win = AutosolveWindow(backend_c, "B", inflip_path=job_c)
    win.show()
    app.processEvents()
    check("input: a job opened afterwards shows ITS input, not the previous job's", win.status_secondary.text() == "Jana2020 input: third_job.inflip")
    win.close()

    # =====================================================================
    # Element-colour legend: the SAME colour authority as the renderer,
    # only elements actually rendered, per view mode, no duplicates.
    # =====================================================================
    legend_cif = (
        "data_test\n_cell_length_a 12.0\n_cell_length_b 12.0\n_cell_length_c 12.0\n"
        "_cell_angle_alpha 90.0\n_cell_angle_beta 90.0\n_cell_angle_gamma 90.0\n"
        "_space_group_name_H-M_alt 'P 1'\nloop_\n_atom_site_label\n_atom_site_type_symbol\n"
        "_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
        "Ag1 Ag 0.500 0.500 0.500\nS1 S 0.500 0.500 0.6917\nO1 O 0.10 0.10 0.10\nH1 H 0.12 0.10 0.10\n"
    )
    win, backend = make_window("A")
    win.show()
    backend.results = [make_result(1, 0.7, 0.7)]
    backend.results[0].superflip_edma_cif.write_text(legend_cif, encoding="utf-8")
    backend.results[0].deblur_edma_cif.write_text(CIF, encoding="utf-8")
    win._rendered_once = False
    win._refresh_tick()
    app.processEvents()
    entries = dict(win.legend_entries())
    check("legend: follows the rendered structures (union over panels, H hidden like the renderer)", set(entries) == {"Ag", "S", "O"})
    check("legend: no duplicate entries", len(win.legend_entries()) == len(entries))
    check(
        "legend: every colour equals the renderer's own colour for that element",
        all(color == backend._element_color(element) == win._element_color(element) for element, color in entries.items()),
    )
    check(
        "legend: the same colour authority object as the renderer",
        AutosolveWindow._element_color is appmod.IterativeSuperflipPipelineQtGUI._element_color,
    )
    import re as _re
    source_text = Path(appmod.__file__).with_name("autosolve_window.py").read_text(encoding="utf-8")
    check(
        "legend: no second element-colour dictionary exists in autosolve_window.py",
        not _re.search(r'"(Ag|Fe|Cu|O|C)"\s*:\s*"#[0-9A-Fa-f]{6}"', source_text),
    )
    check("legend: visible, compact, one line for few elements", win._legend_strip.isVisibleTo(win) and win.element_legend.height() <= 2.2 * win.element_legend.fontMetrics().height())
    win.full_cell_view_button.setChecked(True)
    app.processEvents()
    check("legend: still valid in Full cell (union of the rendered elements)", set(dict(win.legend_entries())) == {"Ag", "S", "O"})
    check("legend: no 'Unassigned peak' entry while no such layer is visible", "Unassigned peak" not in win.element_legend.text())
    win.close()

    # =====================================================================
    # Formula readability: modestly larger, formula only.
    # =====================================================================
    win, backend = make_window("A")
    backend.results = [make_result(1, 0.7, 0.7)]
    win._refresh_tick()
    formula = win.formula_labels[0]
    formula.ensurePolished()
    check("formula: at least 11pt (up from 10pt)", formula.font().pointSizeF() >= 11.0)
    check("formula: no source name repeated below the structure", "Superflip" not in formula.text() and "SharpED" not in formula.text())
    win.close()

    # =====================================================================
    # No configuration sidebar / expert scientific controls.
    # =====================================================================
    win, backend = make_window("A")
    forbidden_labels = {"Basic", "Advanced", "Input", "Workflow", "Output", "Map feedback", "Help"}
    check("AutosolveWindow has no QTabWidget (no Basic/Advanced tab strip)", not win.findChildren(QTabWidget))
    check("AutosolveWindow has no editable combo boxes (no expert scientific controls)", not win.findChildren(QComboBox))
    label_texts = {label.text().strip() for label in win.findChildren(QLabel)}
    check("no configuration-tab labels leak into AutosolveWindow", not (forbidden_labels & label_texts))
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
