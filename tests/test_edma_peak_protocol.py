"""EDMA maxima and Jana peak interchange are not atomic ADP measurements."""
from pathlib import Path

import gemmi
import numpy as np
import pytest

from phase_studio import app as application
from phase_studio.displacement import (
    IsotropicDisplacementKind, parse_edma_coo_isotropic_displacements,
    normalize_jana_m40_isotropic_displacements,
)
from phase_studio.edma_provenance import edma_export_provenance


def test_real_export_boundary_preserves_peak_protocol(tmp_path, monkeypatch):
    source = tmp_path / "density.xplor"
    source.write_text("fixture", encoding="utf-8")
    peak_m40 = ("2 0 0 0\nC1 1 1 1.000000 0.100000 0.200000 0.300000\n"
                "   1.4668   0.1692\nO1 2 1 1.000000 0.400000 0.500000 0.600000\n"
                "   0.0100   0.0533\n").encode()

    def edma_command(command, *, cwd, log_path, **kwargs):
        prefix = Path(command[1]).stem
        (cwd / (prefix + ".coo")).write_text(
            "# x y z x_coc y_coc z_coc charge density vol.\n"
            "0.1 0.2 0.3 0.1 0.2 0.3 0.16921 1.4668 6.8225\n"
            "0.4 0.5 0.6 0.4 0.5 0.6 0.0533 0.0100 2.0\n", encoding="utf-8")
        (cwd / (prefix + ".m40")).write_bytes(peak_m40)
        log_path.write_text("EDMA completed", encoding="utf-8")

    monkeypatch.setattr(application, "run_command", edma_command)
    monkeypatch.setattr(application, "normalize_xplor_for_edma", lambda *args: None)
    monkeypatch.setattr(application, "edma_absolute_plimit", lambda *args: (0.5, 1.0))
    context = application.ReferenceContext(source, source, gemmi.UnitCell(10, 11, 12, 90, 90, 90),
                                           gemmi.SpaceGroup("P 1"), "P 1", "C1 O1", [])
    messages = []
    cif = application.run_edma_on_xplor(source, tmp_path / "output", "candidate", context,
                                      .5, .75, "mock-edma", messages.append, structure_format="pdb")
    assert cif.with_suffix(".m40").read_bytes() == peak_m40
    with pytest.raises(ValueError, match="density/charge"):
        normalize_jana_m40_isotropic_displacements(
            cif.with_suffix(".m40"), source_kind=IsotropicDisplacementKind.BISO)
    assert cif.with_suffix(".m40").read_bytes() == peak_m40
    assert "_atom_site_U_iso_or_equiv" not in cif.read_text()
    atoms = application.parse_cif_atoms(cif)
    assert len(atoms) == 2 and all(atom.uiso_angstrom2 is None for atom in atoms)
    # The higher peak density receives oxygen under the existing composition
    # authority, even though its x_coc is lower than the carbon site's x_coc.
    assert next(atom.element for atom in atoms if np.allclose(atom.frac, (.1, .2, .3))) == "O"
    assert sorted(tuple(atom.frac) for atom in atoms) == [(0.1, 0.2, 0.3), (0.4, 0.5, 0.6)]
    lines = cif.with_suffix(".pdb").read_text().splitlines()
    assert all(line[60:66] == "      " for line in lines if line.startswith("HETATM"))
    provenance = edma_export_provenance(cif.with_suffix(".coo"), cif, cif.with_suffix(".m40"))
    assert provenance["raw_peaks"][0]["peak_density"] == 1.4668
    assert provenance["lower_clamped"] == provenance["upper_clamped"] == 0
    assert any("ADP unavailable" in message for message in messages)
    promoted = application.promote_threshold_structure(cif, tmp_path / "review", "superflip", 2, .5)
    assert promoted.read_bytes() == cif.read_bytes()
    assert promoted.with_suffix(".m40").read_bytes() == peak_m40
    assert promoted.with_name(promoted.stem + "_provenance.json").read_bytes() == cif.with_name(cif.stem + "_provenance.json").read_bytes()


def test_density_cannot_be_relabelled_biso(tmp_path):
    coo = tmp_path / "maxima.coo"
    coo.write_text("0.1 0.2 0.3 0.1 0.2 0.3 .2 1.4668 6.8\n")
    with pytest.raises(ValueError, match="not Biso/Uiso"):
        parse_edma_coo_isotropic_displacements(coo, source_kind=IsotropicDisplacementKind.BISO)
    coordinates, density = application.parse_edma_coo(coo)
    assert density.tolist() == [1.4668]  # column 8, never x_coc=0.1
    assert coordinates.tolist() == [[0.1, 0.2, 0.3]]


def test_four_column_and_flagged_peak_provenance(tmp_path):
    coo = tmp_path / "maxima.coo"
    coo.write_text("0.1 0.2 0.3 5.8\n0.4 0.5 0.6 1.7 !\n")
    cif = tmp_path / "maxima.cif"
    cif.write_text("data_test\n")
    provenance = edma_export_provenance(coo, cif, None)
    assert [p["peak_density"] for p in provenance["raw_peaks"]] == [5.8, 1.7]
    assert provenance["raw_peaks"][1]["edma_error_marker"]
    assert all(p["integrated_charge"] is None for p in provenance["raw_peaks"])


def test_all_disconnected_components_retained():
    from phase_studio.autosolve_window import build_complete_molecule_view
    cell = gemmi.UnitCell(30, 30, 30, 90, 90, 90)
    atoms = [application.AtomSite(str(i), "C", np.array(position)) for i, position in enumerate(
        [(0.1, .1, .1), (.14, .1, .1), (.18, .1, .1), (.7, .7, .7)])]
    view = build_complete_molecule_view(atoms, cell, gemmi.SpaceGroup("P 1"), retain_all_sites=True)
    assert len(view.atoms) == len(atoms)
    for original in atoms:
        assert any(np.allclose((shown.frac - original.frac) % 1, 0, atol=1e-10)
                   or np.allclose((original.frac - shown.frac) % 1, 0, atol=1e-10)
                   for shown in view.atoms)
    assert all(np.array_equal(atom.frac, original) for atom, original in zip(atoms, (
        np.array((.1,.1,.1)), np.array((.14,.1,.1)), np.array((.18,.1,.1)), np.array((.7,.7,.7)))))


def test_provenance_preserves_supported_legacy_indexed_maxima(tmp_path):
    coo=tmp_path/'legacy.coo';cif=tmp_path/'legacy.cif'
    coo.write_text('2 0.1 0.2 0.3 5.8\n3 0.4 0.5 0.6 1.7\n')
    cif.write_text('data_test\n')
    coordinates,densities=application.parse_edma_coo(coo)
    peaks=edma_export_provenance(coo,cif,None)['raw_peaks']
    assert [p['fractional'] for p in peaks]==coordinates.tolist()
    assert [p['peak_density'] for p in peaks]==densities.tolist()==[5.8,1.7]
    assert all(p['integrated_charge'] is None for p in peaks)
