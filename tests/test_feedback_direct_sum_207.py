import math
import gemmi
import numpy as np
import pytest
from phase_studio import app as a


@pytest.mark.parametrize('mode',[a.REFLECTION_DATA_MODE_INTENSITY,a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
    a.REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,
    a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM])
@pytest.mark.parametrize('threshold',[0,2])
@pytest.mark.parametrize('damping',[0,.5,1])
def test_corrected_intensities_match_independent_direct_sum(tmp_path,mode,threshold,damping):
    n=8;z,y,x=np.indices((n,n,n))
    data=np.cos(2*math.pi*x/n)+2*np.cos(2*math.pi*y/n)+3*np.cos(2*math.pi*z/n)
    path=tmp_path/'actual.xplor'
    a.write_xplor_map(path,a.XplorMap('known components',(n,0,n-1,n,0,n-1,n,0,n-1),
        (10,10,10,90,90,90),'ZYX',data.ravel()))
    observed=np.array([1.,.1,9.]);hkls=[(1,0,0),(0,1,0),(0,0,1)]
    amplitude=a.reflection_mode_is_amplitude(mode)
    rows=[a.Reflection(*hkl,math.sqrt(i) if amplitude else i,1.,None) for hkl,i in zip(hkls,observed)]
    if a.reflection_mode_has_fwhm(mode) and threshold>0 and damping>0:
        with pytest.raises(ValueError,match='FWHM'):
            a.apply_map_feedback_to_reflections(rows,mode,path,gemmi.UnitCell(10,10,10,90,90,90),
                0,False,0,True,damping,threshold,lambda text:None)
        return
    saved=a.read_xplor_map(path).data.reshape(n,n,n)
    predictions=np.array([abs(np.sum(saved*np.exp(2j*math.pi*c/n)))**2 for c in [x,y,z]])
    scale=float(np.median(observed/predictions))
    expected=observed.copy()
    for j,i in enumerate(observed):
        significance=math.sqrt(i)/2 if amplitude else i
        if threshold==0 or significance<threshold:
            expected[j]=(1-damping)*i+damping*scale*predictions[j]
    updated,_=a.apply_map_feedback_to_reflections(rows,mode,path,gemmi.UnitCell(10,10,10,90,90,90),
        0,False,0,True,damping,threshold,lambda text:None)
    actual=[r.value**2 if amplitude else r.value for r in updated]
    np.testing.assert_allclose(actual,expected,rtol=1e-12,atol=1e-12)
    assert [r.sigma for r in updated]==[1.,1.,1.]
