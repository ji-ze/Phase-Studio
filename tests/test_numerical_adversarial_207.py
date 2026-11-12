"""Independent counterexamples from the 2.0.7 adversarial scientific audit."""
import math
import itertools
from types import SimpleNamespace
import numpy as np
import gemmi
import pytest
from phase_studio import app as a, map_quality as q, edma_threshold as e

@pytest.mark.parametrize('parameters',[(10,10,12,90,90,60),(10,11,12,75,95,110),(9,9,13,90,90,120)])
def test_periodic_distance_is_lattice_minimum(parameters):
    cell=gemmi.UnitCell(*parameters);orth=np.array(cell.orth.mat)
    shifts=np.array(list(itertools.product(range(-4,5),repeat=3)))
    for delta in np.random.default_rng(2071112).uniform(-.5,.5,(16,3)):
        expected=min(np.linalg.norm((delta-shifts)@orth.T,axis=1))
        assert np.linalg.svd(orth)[1][-1]*4.5>expected
        assert a.frac_distance_angstrom(cell,delta,np.zeros(3))==pytest.approx(expected,abs=2e-12)

@pytest.mark.parametrize('symbol',['C 2','I 2 2 2','F m -3 m'])
def test_reference_expansion_includes_centering(symbol):
    sg=gemmi.SpaceGroup(symbol);point=np.array([.137,.219,.323]);cell=gemmi.UnitCell(20,20,20,90,90,90)
    for position in [point,np.zeros(3)]:
        expected={tuple(np.round(np.mod(op.apply_to_xyz(position),1),10)) for op in sg.operations()}
        actual=a.expanded_unique_atoms([a.AtomSite('C','C',position)],cell,sg,merge_tol_a=1e-5)
        assert {tuple(np.round(atom.frac,10)) for atom in actual}==expected

def synthesis(hkl,phase,sg):
    return a.synthesize_xplor_map_from_phases([a.Reflection(*hkl,1,None)],a.REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA,
        (8,0,7,8,0,7,8,0,7),(10,10,12,90,90,90),'ZYX',{hkl:phase},'audit',gemmi.SpaceGroup(sg))[0]

@pytest.mark.parametrize('sg,hkl',[('P 21',(0,1,0)),('C 2',(1,0,0)),('I 2 2 2',(1,0,0))])
def test_synthesis_cannot_create_systematic_absences(sg,hkl):
    assert gemmi.SpaceGroup(sg).operations().is_systematically_absent(hkl)
    result=synthesis(hkl,0,sg)
    assert np.max(abs(result.data))==0

def test_centric_phase_projection_keeps_observed_amplitude():
    result=synthesis((1,0,0),60,'P -1')
    # Nearest allowed phase is 0 degrees; direct inversion-related pair.
    z,y,x=np.indices((8,8,8));expected=2*np.cos(2*np.pi*x/8)/512
    np.testing.assert_allclose(result.data,expected.ravel(),atol=1e-15,rtol=0)

def test_self_conjugate_nyquist_phase_cannot_be_silently_discarded():
    with pytest.raises(ValueError,match='Hermitian|Nyquist|inconsistent'):
        synthesis((4,0,0),45,'P 1')

def test_fft_alias_and_layout_are_rejected(tmp_path):
    z,y,x=np.indices((8,8,8));m=a.XplorMap('alias',(8,0,7,8,0,7,8,0,7),(10,10,10,90,90,90),'ZYX',np.cos(2*np.pi*x/8).ravel())
    p=tmp_path/'map.xplor';a.write_xplor_map(p,m)
    with pytest.raises(ValueError,match='undersampl'):a.xplor_fft_predictions_from_map(m,[(9,0,0)])
    with pytest.raises(ValueError,match='undersampl'):a.xplor_fft_intensity_phase(p,(9,0,0))
    m.axis_order='XYZ'
    with pytest.raises((ValueError,RuntimeError),match='layout|axis'):a.xplor_fft_predictions_from_map(m,[(1,0,0)])

@pytest.mark.parametrize('exponent',[-150,-40,-10,0,40,150,200])
def test_scaled_residuals_do_not_depend_on_common_units(exponent):
    factor=10.**exponent;fo=np.array([2.,4.,6.])*factor;fc=np.array([1.,2.,3.])*factor
    result=q.scaled_amplitude_metrics(fo,fc)
    assert result.scale==pytest.approx(2,abs=2e-14)
    assert result.r_factor==pytest.approx(0,abs=2e-14)
    assert result.correlation==pytest.approx(1,abs=2e-14)
    assert q.amplitude_r_factor_at_scale(fc,fc,2)==pytest.approx(1,abs=2e-14)

def test_experimental_edma_free_residual_does_not_fit_free_data():
    fc=np.arange(1.,41);fo=fc.copy();fo[:20]*=2;free=np.arange(40)>=20
    evaluator=SimpleNamespace(cell=gemmi.UnitCell(10,10,10,90,90,90),spacegroup=gemmi.SpaceGroup('P 1'),
        fo=fo,fcalc=lambda sites:fc,free_mask=free,work_mask=~free,holdout_available=True)
    sites=[e.PeakSite('C',(i/10,.2,.3)) for i in range(5)]
    actual=e.evaluate_edma_candidate(1.,sites,evaluator,None)
    assert actual.info.r_free==pytest.approx(1,abs=1e-14)
    # Perturb only free observations: the working scale must remain 2.
    fo[free]*=4
    actual=e.evaluate_edma_candidate(1.,sites,evaluator,None)
    assert actual.info.r_free==pytest.approx(.5,abs=1e-14)

def test_free_bootstrap_uses_fixed_work_scale():
    fc=np.arange(1.,41);fo=fc.copy();fo[:20]*=2
    samples=np.tile(np.arange(20,40),(3,1))
    r,cc=e._bootstrap_r_cc(fo,fc,samples,fixed_scale=2.)
    np.testing.assert_allclose(r,1,atol=1e-14,rtol=0)
    np.testing.assert_allclose(cc,1,atol=1e-14,rtol=0)

def test_bootstrap_extreme_common_scale_is_stable():
    fc=np.arange(1.,21)*1e200;fo=2*fc;samples=np.tile(np.arange(20),(3,1))
    residual,correlation=e._bootstrap_r_cc(fo,fc,samples)
    np.testing.assert_allclose(residual,0,atol=2e-14,rtol=0)
    np.testing.assert_allclose(correlation,1,atol=2e-14,rtol=0)

def test_overall_b_fit_uses_log_difference_without_ratio_overflow():
    base=np.arange(1.,21);fc=base*1e-200;fo=base*1e200
    actual=e.apply_overall_b(fo,fc,np.linspace(.01,1,20),np.ones(20,dtype=bool))
    np.testing.assert_allclose(actual,fc,rtol=2e-12,atol=0)

def test_insufficient_holdout_is_not_reclassified_as_work():
    refs=[q.FrozenReflection(h,0,0,float(h)) for h in range(1,25)]
    context=q.make_validation_context(refs,free_hkls=[(1,0,0)])
    evaluator=e.ModelAgreementEvaluator(context,gemmi.UnitCell(10,10,10,90,90,90),gemmi.SpaceGroup('P 1'))
    assert not evaluator.holdout_available
    assert evaluator.criterion_mask().sum()==1
    assert not evaluator.criterion_fit_mask()[0]
    assert 'unavailable' in evaluator.criterion_label()

def test_cif_wrapped_rows_are_not_silently_dropped(tmp_path):
    p=tmp_path/'wrapped.cif'
    p.write_text("data_a\n_cell_length_a 10\n_cell_length_b 11\n_cell_length_c 12\n_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n_space_group_name_H-M_alt 'P 1'\nloop_\n_atom_site_label\n_atom_site_type_symbol\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\nC1 C .1 .2 .3\n'C two' C .4\n.5 .6\n")
    expected=gemmi.make_small_structure_from_block(gemmi.cif.read_file(str(p)).sole_block())
    actual=a.parse_cif_atoms(p)
    assert len(actual)==len(expected.sites)==2
    np.testing.assert_allclose([v.frac for v in actual],[[s.fract.x,s.fract.y,s.fract.z] for s in expected.sites],atol=1e-15)

@pytest.mark.parametrize('mode',[a.REFLECTION_DATA_MODE_INTENSITY,a.REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA,
    a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM,
    a.REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA])
def test_small_measurements_survive_native_serialization(tmp_path,mode):
    p=tmp_path/'small.hkl';row=a.Reflection(1,0,0,1e-9,2e-10,90.)
    assert a.write_observed_reflections(p,[row],0,mode)==1
    # Native Superflip rejects exponent notation in reflection records.
    for line in p.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            assert 'e' not in line.lower()
    columns=a.reflection_columns_for_mode(mode)
    actual=a.read_hkl(p,*columns[:2])[0]
    assert actual.value==pytest.approx(row.value,rel=1e-14,abs=0)
    assert actual.sigma==pytest.approx(row.sigma,rel=1e-14,abs=0)

def test_small_amplitude_uncertainty_export_is_not_zero(tmp_path):
    p=tmp_path/'phase.hkl'
    a.write_standardized_hkl_with_phase(p,[a.Reflection(1,0,0,1e-9,2e-10,90.)],0,a.REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA)
    values=[line.split() for line in p.read_text().splitlines() if not line.startswith('#')][0]
    assert float(values[3])==pytest.approx(1e-18,rel=1e-14,abs=0)
    assert float(values[4])==pytest.approx(4e-19,rel=1e-14,abs=0)

def test_map_correlation_requires_same_frame(tmp_path):
    first=a.XplorMap('a',(8,0,7,8,0,7,8,0,7),(10,11,12,90,90,90),'ZYX',np.arange(512,dtype=float))
    second=a.XplorMap('b',(4,0,3,8,0,7,16,0,15),first.cell,'ZYX',first.data)
    pa,pb=tmp_path/'a.xplor',tmp_path/'b.xplor';a.write_xplor_map(pa,first);a.write_xplor_map(pb,second)
    assert a.xplor_map_correlation(pa,pb) is None
