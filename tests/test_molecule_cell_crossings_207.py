"""Synthetic independent chains spanning several crystallographic cells."""
from collections import Counter

import gemmi
import numpy as np
import pytest

from phase_studio.app import AtomSite
from phase_studio.autosolve_window import build_complete_molecule_view


@pytest.mark.parametrize('translation', [(0, 0, 0), (3, -5, 2), (-4, 7, -3)])
@pytest.mark.parametrize('molecules', [1, 2])
def test_complete_chains_across_multiple_cell_faces(translation, molecules):
    cell = gemmi.UnitCell(80, 6, 30, 90, 90, 90)
    seeds = [AtomSite(f'C{m}_{i}', 'C', np.array([
        (2 + 35*m + 1.2*i)/80, (.3 + i)/6, .2 + .5*m,
    ]) + translation) for m in range(molecules) for i in range(20)]
    original = [(s.label, s.element, s.frac.copy()) for s in seeds]
    view = build_complete_molecule_view(seeds, cell, gemmi.SpaceGroup('P1'))
    # The independent Cartesian construction gives 20 atoms and 19 bonds
    # per chain: adjacent distance sqrt(1.2² + 1²), all other pairs too far.
    assert len(view.atoms) == 20 * molecules
    assert len(view.bonds) == 19 * molecules
    assert view.unassigned_peak_count == 0
    assert not view.secondary_atoms
    assert Counter(atom.label.removesuffix('_1') for atom in view.atoms) == Counter(s.label for s in seeds)
    for i, j in view.bonds:
        assert np.isclose(np.linalg.norm(view.coords[j] - view.coords[i]), np.sqrt(2.44), atol=1e-10)
    for s, (label, element, frac) in zip(seeds, original):
        assert s.label == label and s.element == element
        np.testing.assert_array_equal(s.frac, frac)
