"""Independent numerical contracts for declared reflection column semantics."""
from pathlib import Path
from unittest.mock import patch
import math
import numpy as np
import pytest
import gemmi
from phase_studio import app as a

SIGMA=[a.REFLECTION_DATA_MODE_INTENSITY,a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
       a.REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA]
WIDTH=[a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM]


@pytest.mark.parametrize('mode',SIGMA+WIDTH)
def test_observed_column_meaning_and_value_policy(tmp_path,mode):
    rows=[a.Reflection(i,0,0,v,.125,90.) for i,v in enumerate([0.,1e-8,10.,-1.,float('nan'),float('inf')],1)]
    path=tmp_path/'observed.hkl'
    assert a.write_observed_reflections(path,rows,0,mode)==3
    records=[line.split() for line in path.read_text().splitlines() if not line.startswith('#')]
    # Audit N09: the mathematical value must survive serialization. The prior
    # expectation explicitly encoded the independently reproduced loss to zero.
    assert [float(r[3]) for r in records]==[0.,1e-8,10.]
    assert all(float(r[-1])==.125 for r in records)
    if mode in WIDTH:
        assert 'FWHM(degrees_2theta)' in path.read_text()
        assert 'sigma(' not in path.read_text()
        assert a.reflection_signal_to_noise(rows[2],mode) is None
    elif a.reflection_mode_has_phase(mode):
        assert all(float(r[4])==.25 for r in records)
        loaded=a.read_hkl(path,4,6,True)
        assert all(r.phase==90. for r in loaded)
        from phase_studio.hkl_diagnostics import read_diagnostic_reflections
        assert all(r.phase==90. for r in read_diagnostic_reflections(path,mode)[0])


@pytest.mark.parametrize('mode',WIDTH)
def test_positive_threshold_rejected_before_any_file_mutation(tmp_path,mode):
    row=a.Reflection(1,0,0,1000,.001)
    for writer in (a.write_observed_reflections,a.write_standardized_hkl_with_phase,a.write_shelx_fcf):
        path=tmp_path/'existing';path.write_bytes(b'preserve')
        with pytest.raises(ValueError,match='FWHM'):writer(path,[row],2,mode)
        assert path.read_bytes()==b'preserve'
    assert a.estimate_sigma_for_reflection_value([row],500) is None


@pytest.mark.parametrize('mode',SIGMA)
def test_legitimate_mode_native_gate_and_missing_uncertainties(tmp_path,mode):
    rows=[a.Reflection(1,0,0,6,2),a.Reflection(2,0,0,5.9,2),a.Reflection(3,0,0,100,None),
          a.Reflection(4,0,0,100,0),a.Reflection(5,0,0,100,float('inf'))]
    path=tmp_path/'filtered'
    assert a.write_observed_reflections(path,rows,3,mode)==1
    assert next(line for line in path.read_text().splitlines() if not line.startswith('#')).split()[:3]==['1','0','0']
    assert a.map_feedback_intensity_significance(rows[0],mode)==(1.5 if a.reflection_mode_is_amplitude(mode) else 3.)
    for writer in (a.write_standardized_hkl_with_phase,a.write_shelx_fcf):
        assert writer(tmp_path/'export',[rows[0]],3,mode)==1
        fields=[line.split() for line in (tmp_path/'export').read_text().splitlines() if line.strip() and line.lstrip()[0].isdigit()][-1]
        assert float(fields[3])==(36 if a.reflection_mode_is_amplitude(mode) else 6)
        assert float(fields[4])==(24 if a.reflection_mode_is_amplitude(mode) else 2)


def test_uncertainty_free_input_and_missing_auxiliary(tmp_path):
    assert a.parse_reflection_line('1 0 0 12 ?',4,5).sigma is None
    rows=[a.Reflection(1,0,0,12,None),a.Reflection(2,0,0,0,None)]
    with pytest.raises(ValueError,match='uncertainties'):a.write_observed_reflections(tmp_path/'x',rows,2)
    assert a.write_observed_reflections(tmp_path/'x',rows,0)==2
    for writer in (a.write_standardized_hkl_with_phase,a.write_shelx_fcf):
        with pytest.raises(ValueError,match='uncertainties'):writer(tmp_path/'export',rows,0)
        assert not (tmp_path/'export').exists()


@pytest.mark.parametrize('mode',WIDTH)
def test_widths_do_not_weight_duplicate_intensities_or_supply_new_widths(tmp_path,mode):
    rows=[a.Reflection(1,0,0,10,.1),a.Reflection(1,0,0,30,.1)]
    result=a.merge_duplicate_reflections(rows,mode)
    assert result[0].value==20 and result[0].sigma==.1
    rows[1].sigma=.2
    with pytest.raises(ValueError,match='Conflicting FWHM'):a.merge_duplicate_reflections(rows,mode)
    with pytest.raises(ValueError,match='measured FWHM'):
        a.apply_map_feedback_to_reflections(rows,mode,tmp_path/'absent-map',gemmi.UnitCell(10,10,10,90,90,90),0,True,10,False,0,0,lambda _:None)


@pytest.mark.parametrize('mode',WIDTH)
def test_powder_correction_conserves_intensity_and_preserves_widths(tmp_path,mode):
    rows=[a.Reflection(1,0,0,2,.2),a.Reflection(2,0,0,4,.3)]
    original=sum(r.value**2 if a.reflection_mode_is_amplitude(mode) else r.value for r in rows)
    with patch.object(a,'assign_powder_overlap_groups',return_value={(1,0,0):1,(2,0,0):1}),patch.object(a,'xplor_fft_predictions',return_value={(1,0,0):(3,0),(2,0,0):(1,0)}):
        updated,_=a.redistribute_overlap_reflections(rows,mode,tmp_path/'map',gemmi.UnitCell(10,10,10,90,90,90),1,.2,1,lambda _:None)
    assert [r.sigma for r in updated]==[.2,.3]
    assert sum(r.value**2 if a.reflection_mode_is_amplitude(mode) else r.value for r in updated)==pytest.approx(original)
    assert a.write_observed_reflections(tmp_path/'powder',updated,0,mode)==2


def test_native_width_keyword_requires_real_wavelength():
    assert a.powder_superflip_keywords('',1.5406)=='lambda 1.5406'
    # Effective resolved metadata wins over a stale incoming declaration.
    assert a.powder_superflip_keywords('lambda 0.5',1.54)=='lambda 1.54'
    assert a.powder_superflip_keywords('lambda 0.5',0)=='lambda 0.5'
    with pytest.raises(ValueError,match='wavelength'):a.powder_superflip_keywords('')


@pytest.mark.parametrize('mode',WIDTH)
def test_missing_nonfinite_nonpositive_widths_are_not_fabricated(tmp_path,mode):
    rows=[a.Reflection(i,0,0,10,width) for i,width in enumerate([None,float('nan'),float('inf'),0,-1,.05],1)]
    assert a.write_observed_reflections(tmp_path/'out',rows,0,mode)==1
    assert (tmp_path/'out').read_text().splitlines()[-1].split()[:3]==['6','0','0']


def test_genuine_duplicates_keep_independent_inverse_variance_golden():
    rows=[a.Reflection(1,0,0,10,1),a.Reflection(1,0,0,20,2)]
    result=a.merge_duplicate_reflections(rows,a.REFLECTION_DATA_MODE_INTENSITY)[0]
    assert result.value==12 and result.sigma==pytest.approx(math.sqrt(.8))


def test_unknown_phases_and_zero_amplitude_uncertainty_export(tmp_path):
    mode=a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA
    a.write_observed_reflections(tmp_path/'unknown',[a.Reflection(1,0,0,4,1,None)],0,mode)
    assert (tmp_path/'unknown').read_text().splitlines()[-1].split()[4]=='?'
    for writer in (a.write_standardized_hkl_with_phase,a.write_shelx_fcf):
        with pytest.raises(ValueError,match='F=0'):writer(tmp_path/'export',[a.Reflection(1,0,0,0,1)],0,mode)
        assert not (tmp_path/'export').exists()


def test_powder_boundary_cannot_reinterpret_measurement_sigma_or_invalid_values():
    with pytest.raises(ValueError,match='measurement sigma'):
        a.validate_powder_reflections([a.Reflection(1,0,0,10,1)],a.REFLECTION_DATA_MODE_INTENSITY)
    for value,width in [(float('nan'),.1),(-1,.1),(10,None),(10,0),(10,float('inf'))]:
        with pytest.raises(ValueError,match='finite'):
            a.validate_powder_reflections([a.Reflection(1,0,0,value,width)],a.REFLECTION_DATA_MODE_INTENSITY_FWHM)


def test_unresolved_layout_cannot_enter_a_scientific_writer(tmp_path):
    for threshold in (0,2):
        with pytest.raises(ValueError,match='exact reflection column'):
            a.write_observed_reflections(tmp_path/'out',[a.Reflection(1,0,0,10,.1)],threshold,a.REFLECTION_DATA_MODE_AUTO)
        assert not (tmp_path/'out').exists()
