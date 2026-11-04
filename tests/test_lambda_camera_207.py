"""Regression reproductions for the manually observed lambda/camera defects."""
import os,sys,subprocess
from pathlib import Path
import pytest
from phase_studio import app as a


def test_matching_m90_is_resolved_without_feedback(tmp_path):
    source=tmp_path/'ochlor.inflip';source.write_text('dataformat intensity fwhm\nfbegin\n1 0 0 10 .05\nendf\n')
    source.with_suffix('.m90').write_text('lambda 1.541866\nend\n')
    assert a.resolve_powder_wavelength(0,source,None)[0]==1.541866


def test_native_lambda_obeys_effective_override():
    assert a.powder_superflip_keywords('lambda 0.71073\nfwhmseparation .2',1.541866).splitlines()[0]=='lambda 1.541866'


@pytest.mark.parametrize('scale',['1','1.25','1.5','2'])
def test_real_qt_drag_and_metadata(scale):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'tests/lambda_camera_gui_207.py')],cwd=root,
        env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},capture_output=True,text=True,timeout=100)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize("manual,m90,inflip,cif,expected", [
    (1.1,1.2,1.3,1.4,1.1),(0,1.2,1.3,1.4,1.2),
    (0,0,1.3,1.4,1.3),(0,0,0,1.4,1.4),(0,0,0,0,0),
    (float('nan'),float('inf'),1.3,1.4,1.3)])
def test_resolution_precedence_conflicts_and_input_identity(tmp_path,manual,m90,inflip,cif,expected):
    import hashlib
    source=tmp_path/'project.inflip'
    source.write_text(f'lambda {inflip}\ndataformat intensity fwhm\nfbegin\n1 0 0 10 .1\nendf\n')
    source.with_suffix('.m90').write_text(f'lambda {m90}\nend\n')
    reference=tmp_path/'reference.cif';reference.write_text(f'data_test\n_diffrn_radiation_wavelength {cif}\n')
    paths=[source,source.with_suffix('.m90'),reference]
    before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    value,label=a.resolve_powder_wavelength(manual,source,reference)
    assert value==expected
    if expected and len({x for x in (manual,m90,inflip,cif) if x>0 and x<float('inf')})>1:
        assert 'conflicting wavelength' in label
    assert before==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]


def test_unrelated_m90_cannot_supply_wavelength(tmp_path):
    source=tmp_path/'project.inflip';source.write_text('dataformat intensity fwhm\n')
    unrelated=tmp_path/'unrelated.m90';unrelated.write_text('lambda 1.541866\nend\n')
    assert a.resolve_powder_wavelength(0,source,None,unrelated)==(0.,'none')
