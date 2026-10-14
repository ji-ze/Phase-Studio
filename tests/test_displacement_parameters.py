"""Scientific guards for Biso/Uiso representation at export boundaries."""
from __future__ import annotations

import math
import os
from pathlib import Path
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import gemmi
import numpy as np

from phase_studio import app as appmod
from phase_studio.displacement import (
    EIGHT_PI_SQUARED,
    IsotropicDisplacementKind,
    UISO_MAX,
    UISO_MIN,
    biso_to_uiso,
    export_uiso_statistics,
    match_uiso_by_fractional_coordinate,
    normalize_export_uiso,
    normalize_jana_m40_isotropic_displacements,
    parse_edma_coo_isotropic_displacements,
    uiso_to_biso,
)


def main() -> None:
    checks = 0

    def check(label: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(label)

    for biso, expected in (
        (1.0, 0.012665147955292222),
        (2.0, 0.025330295910584444),
        (2.92, 0.03698223202945329),
        (3.2, 0.04052847345693511),
    ):
        actual = biso_to_uiso(biso)
        check(f"Biso {biso:g} converts mathematically to Uiso", math.isclose(actual, biso / (8.0 * math.pi**2), rel_tol=0.0, abs_tol=1e-14))
        check(f"Biso {biso:g} matches the known Uiso fixture", math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-14))
        check(f"Biso {biso:g} round trips", math.isclose(uiso_to_biso(actual), biso, rel_tol=0.0, abs_tol=1e-12))

    for raw, expected, direction in (
        (-0.005, 0.010, "lower"),
        (0.005, 0.010, "lower"),
        (0.010, 0.010, ""),
        (0.025, 0.025, ""),
        (0.037, 0.037, ""),
        (0.100, 0.100, ""),
        (0.150, 0.150, ""),
        (0.180, 0.150, "upper"),
        (0.300, 0.150, "upper"),
    ):
        normalized = normalize_export_uiso(raw, IsotropicDisplacementKind.UISO)
        check(
            f"Uiso export policy maps {raw:g} to {expected:g}",
            normalized.uiso_angstrom2 == expected and normalized.clamp_direction == direction,
        )
    from_biso = normalize_export_uiso(2.92, IsotropicDisplacementKind.BISO)
    check("Biso is converted before export clamping", math.isclose(from_biso.raw_uiso_angstrom2, 2.92 / EIGHT_PI_SQUARED, abs_tol=1e-14) and not from_biso.was_clamped)
    already_uiso_value = normalize_export_uiso(0.037, IsotropicDisplacementKind.UISO)
    check("already-Uiso export input is not converted twice", already_uiso_value.raw_uiso_angstrom2 == 0.037)
    check("nonfinite export values are rejected", all(
        _raises_value_error(lambda value=value: normalize_export_uiso(value, IsotropicDisplacementKind.UISO))
        for value in (float("nan"), float("inf"), float("-inf"))
    ))
    stats = export_uiso_statistics((-0.005, 0.025, 0.300))
    check("export statistics count lower, upper and unchanged sites", (stats.lower_clamped, stats.upper_clamped, stats.unchanged) == (1, 1, 1) and stats.final_min == UISO_MIN and stats.final_max == UISO_MAX)

    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        source = tmp / "edma.m40"
        source.write_text(
            "    2    0    0    0\n"
            " 1.000000 0.000000 0.000000 0.000000 0.000000 0.000000\n"
            " 0.000000\n"
            " 0.000000 0.000000 0.000000 0.000000 0.000000 0.000000\n"
            " 0.000000 0.000000 0.000000 0.000000 0.000000 0.000000\n"
            "C1        1  1     1.000000 0.100000 0.200000 0.300000\n"
            "   2.9200   1.0000\n"
            "O1        2  1     0.500000-0.100000 0.400000 0.500000\n"
            "   1.0000   0.5000\n",
            encoding="utf-8",
        )
        records = normalize_jana_m40_isotropic_displacements(
            source, source_kind=IsotropicDisplacementKind.BISO,
        )
        lines = source.read_text(encoding="utf-8").splitlines()
        check("all declared EDMA m40 sites are converted", len(records) == 2)
        check("m40 first site writes Uiso", lines[6].split()[0] == f"{biso_to_uiso(2.92):.6f}")
        check("m40 occupancy, coordinates, labels and auxiliary field stay unchanged", "C1        1  1     1.000000 0.100000 0.200000 0.300000" in lines and lines[6].split()[1] == "1.0000")
        check("m40 parser accepts the converted site count", appmod._m40_model_count(source) == 2)

        bounded_m40 = tmp / "bounded.m40"
        bounded_m40.write_text(
            source.read_text(encoding="utf-8").replace(f"{biso_to_uiso(2.92):.6f}", "-0.005000", 1),
            encoding="utf-8",
        )
        bounded_records = normalize_jana_m40_isotropic_displacements(
            bounded_m40, source_kind=IsotropicDisplacementKind.UISO,
        )
        # A Uiso source skips unit conversion but still receives the export
        # safety clamp when it lies outside the allowed interval.
        bounded_biso_m40 = tmp / "bounded-biso.m40"
        bounded_biso_m40.write_text(
            source.read_text(encoding="utf-8").replace(f"{biso_to_uiso(2.92):.6f}", "-0.394784", 1),
            encoding="utf-8",
        )
        bounded_biso_records = normalize_jana_m40_isotropic_displacements(
            bounded_biso_m40, source_kind=IsotropicDisplacementKind.BISO,
        )
        check("m40 lower-bound export writes 0.010000", bounded_biso_m40.read_text(encoding="utf-8").splitlines()[6].split()[0] == "0.010000" and bounded_biso_records[0].clamp_direction == "lower")
        check("explicit Uiso parsing clamps without double conversion", bounded_records[0].raw_uiso_angstrom2 == -0.005 and bounded_records[0].uiso_angstrom2 == UISO_MIN and bounded_m40.read_text(encoding="utf-8").splitlines()[6].split()[0] == "0.010000")

        already_uiso = tmp / "already-uiso.m40"
        already_uiso.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        before = already_uiso.read_bytes()
        parsed = normalize_jana_m40_isotropic_displacements(
            already_uiso, source_kind=IsotropicDisplacementKind.UISO,
        )
        check("explicit already-Uiso input is not converted again", already_uiso.read_bytes() == before and math.isclose(parsed[0].uiso_angstrom2, biso_to_uiso(2.92), abs_tol=5e-7))

        coo = tmp / "edma.coo"
        coo.write_text(
            "# x y z x_coc y_coc z_coc charge density vol.\n"
            "0.100000 0.200000 0.300000 0.1 0.2 0.3 4.5 2.920000 8.0\n"
            "0.900000 0.400000 0.500000 0.9 0.4 0.5 3.0 1.000000 7.0\n",
            encoding="utf-8",
        )
        coo_records = parse_edma_coo_isotropic_displacements(
            coo, source_kind=IsotropicDisplacementKind.BISO,
        )
        check("EDMA coo parser retains the complete peak set", len(coo_records) == 2)
        check("EDMA coo Biso field converts to canonical Uiso", math.isclose(coo_records[0].uiso_angstrom2, biso_to_uiso(2.92), abs_tol=1e-14))
        matched = match_uiso_by_fractional_coordinate((1.1, 0.2, 0.3), coo_records)
        check("periodic coordinate matching supplies the correct peak Uiso", math.isclose(matched, biso_to_uiso(2.92), abs_tol=1e-14))

        invalid = tmp / "invalid.m40"
        invalid.write_text("1 0 0 0\nC1 1 1 1.0 0.1 0.2 0.3\n", encoding="utf-8")
        try:
            normalize_jana_m40_isotropic_displacements(invalid, source_kind=IsotropicDisplacementKind.BISO)
        except ValueError:
            invalid_rejected = True
        else:
            invalid_rejected = False
        check("missing displacement record is rejected explicitly", invalid_rejected)

        uiso = biso_to_uiso(2.92)
        atom = appmod.AtomSite("C1", "C", np.asarray((0.1, 0.2, 0.3)), uiso_angstrom2=uiso)
        cell = gemmi.UnitCell(10, 11, 12, 90, 90, 90)
        sg = gemmi.find_spacegroup_by_name("P 1")
        cif = tmp / "site.cif"
        pdb = tmp / "site.pdb"
        appmod.write_structure_cif(cif, cell, sg, "P 1", [atom])
        appmod.write_structure_pdb(pdb, cell, "P 1", [atom])
        parsed_atom = appmod.parse_cif_atoms(cif)[0]
        check("CIF declares and writes Uiso", "_atom_site_U_iso_or_equiv" in cif.read_text(encoding="utf-8") and math.isclose(parsed_atom.uiso_angstrom2, uiso, abs_tol=5e-7))
        pdb_biso = float(pdb.read_text(encoding="utf-8").splitlines()[1][60:66])
        check("PDB temperature-factor column writes Biso", math.isclose(pdb_biso, 2.92, abs_tol=0.005))

        bounded_atoms = [
            appmod.AtomSite("C1", "C", np.asarray((0.1, 0.2, 0.3)), uiso_angstrom2=0.005),
            appmod.AtomSite("O1", "O", np.asarray((0.4, 0.5, 0.6)), uiso_angstrom2=0.180),
        ]
        bounded_cif = tmp / "bounded.cif"
        bounded_pdb = tmp / "bounded.pdb"
        raw_cif = tmp / "scientific-raw.cif"
        appmod.write_structure_cif(raw_cif, cell, sg, "P 1", bounded_atoms)
        raw_before = raw_cif.read_bytes()
        appmod.write_structure_cif(
            bounded_cif, cell, sg, "P 1", bounded_atoms, bound_edma_uiso=True,
        )
        appmod.write_structure_pdb(
            bounded_pdb, cell, "P 1", bounded_atoms, bound_edma_uiso=True,
        )
        parsed_bounded = appmod.parse_cif_atoms(bounded_cif)
        check("bounded CIF serializes exact lower and upper Uiso", [a.uiso_angstrom2 for a in parsed_bounded] == [UISO_MIN, UISO_MAX])
        pdb_lines = [line for line in bounded_pdb.read_text(encoding="utf-8").splitlines() if line.startswith("HETATM")]
        pdb_values = [float(line[60:66]) for line in pdb_lines]
        check("bounded PDB converts the same final Uiso back to Biso", math.isclose(pdb_values[0], uiso_to_biso(UISO_MIN), abs_tol=0.005) and math.isclose(pdb_values[1], uiso_to_biso(UISO_MAX), abs_tol=0.005))
        check("bounded CIF/PDB preserve coordinates and site count", len(parsed_bounded) == len(bounded_atoms) == len(pdb_lines) and all(np.allclose(parsed.frac, source.frac) for parsed, source in zip(parsed_bounded, bounded_atoms)))
        check("bounded export does not modify the scientific source CIF", raw_cif.read_bytes() == raw_before and [a.uiso_angstrom2 for a in appmod.parse_cif_atoms(raw_cif)] == [0.005, 0.180])

    check("negative Biso is rejected", _raises_value_error(lambda: biso_to_uiso(-0.1)))
    check("missing displacement is rejected", _raises_value_error(lambda: biso_to_uiso(float("nan"))))
    print(f"displacement parameter checks passed: {checks}")


def _raises_value_error(callback) -> bool:
    try:
        callback()
    except ValueError:
        return True
    return False


if __name__ == "__main__":
    main()
