"""Independent phase sign checks: off-origin density and direct positive-exponent sum."""
import math
import importlib.util
from pathlib import Path
import gemmi
import numpy as np
import pytest
from phase_studio import app as a


def impulse():
    data = np.zeros((12, 10, 8))
    data[3, 2, 1] = 1
    return a.XplorMap('off-origin', (8,0,7,10,0,9,12,0,11),
                      (10,11,12,90,90,90), 'ZYX', data.ravel())


@pytest.mark.parametrize('hkl', [(1,0,0), (0,1,0), (0,0,1), (1,1,1), (-1,0,0)])
def test_map_phase_matches_direct_sum_and_gemmi(tmp_path, hkl):
    xmap = impulse()
    grid = gemmi.FloatGrid(8,10,12)
    grid.unit_cell = gemmi.UnitCell(*xmap.cell)
    grid.spacegroup = gemmi.SpaceGroup('P 1')
    grid.set_value(1,2,3,1)
    independent = np.exp(2j * math.pi * np.dot(hkl, [1/8,2/10,3/12]))
    gemmi_coefficient = gemmi.transform_map_to_f_phi(grid, half_l=False, use_scale=False).get_value(*hkl)
    assert gemmi_coefficient == pytest.approx(independent, abs=1e-6)
    path = tmp_path/'impulse.xplor'
    a.write_xplor_map(path, xmap)
    for intensity, phase in [a.xplor_fft_predictions_from_map(xmap,[hkl])[hkl],
                             a.xplor_fft_intensity_phase(path,hkl)]:
        assert intensity == pytest.approx(1)
        assert np.exp(1j*math.radians(phase)) == pytest.approx(independent,abs=1e-12)


def test_synthesis_places_density_at_positive_coordinate():
    # Complete Fourier series of a delta at x=1/8; direct positive-sign F(h).
    rows = [a.Reflection(h,0,0,1,None,None) for h in range(-3,4)]
    phases = {(r.h,0,0): 360*r.h/8 for r in rows}
    result, used = a.synthesize_xplor_map_from_phases(rows, a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        (8,0,7,1,0,0,1,0,0), (10,11,12,90,90,90), 'ZYX', phases,
        'direct Fourier series', gemmi.SpaceGroup('P 1'))
    expected = np.array([sum(np.exp(2j*math.pi*h*(1/8-x/8)) for h in range(-3,4)).real/8 for x in range(8)])
    assert used == 7
    np.testing.assert_allclose(result.data, expected, atol=1e-14)
    assert int(np.argmax(result.data)) == 1


def test_native_superflip_phase_interoperability(tmp_path):
    executable = Path('C:/Jana2020/SUPERFLIP/superflip.exe')
    if not executable.is_file():
        pytest.skip('Native Superflip unavailable; analytic and Gemmi checks run separately')
    helper_path = Path(__file__).resolve().parents[1]/'packaging/tools/verify_fwhm_policy_207.py'
    spec = importlib.util.spec_from_file_location('native_phase_fixture', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    mode = a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA
    helper.native_case(executable, tmp_path, mode)
    folder = tmp_path/mode.replace(' ','_').replace('/','_')
    predictions = a.xplor_fft_predictions(folder/'check.xplor',[(1,0,0),(0,1,0),(0,0,1)])
    for intensity, phase in predictions.values():
        assert intensity > 0
        # Native map serialization has six significant digits.
        assert phase == pytest.approx(90,abs=1e-4)


@pytest.mark.parametrize('spacegroup', ['P 21','P 31','P 41','P 61'])
def test_synthesis_symmetry_matches_direct_atomic_sum(spacegroup):
    sg = gemmi.SpaceGroup(spacegroup)
    positions = [op.apply_to_xyz([.13,.21,.32]) for op in sg.operations()]
    def coefficient(hkl):
        return sum(np.exp(2j*math.pi*np.dot(hkl,p)) for p in positions)
    hkl = (1,2,1)
    f = coefficient(hkl)
    row = a.Reflection(*hkl,float(abs(f)),None,None)
    result, _ = a.synthesize_xplor_map_from_phases([row],a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
        (16,0,15,16,0,15,16,0,15),(10,10,12,90,90,120),'ZYX',
        {hkl:float(np.angle(f,deg=True))},'independent symmetry',sg)
    equivalents = {tuple(op.apply_to_hkl(hkl)) for op in sg.operations()}
    predictions = a.xplor_fft_predictions_from_map(result,list(equivalents))
    for key in equivalents:
        intensity,phase = predictions[key]
        actual = math.sqrt(intensity)*np.exp(1j*math.radians(phase))
        assert actual == pytest.approx(coefficient(key),abs=1e-12)
