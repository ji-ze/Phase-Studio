"""Group invariants recomputed from written HKL using actual map FFT predictions."""
import math
import gemmi
import numpy as np
import pytest
from phase_studio import app as a


@pytest.mark.parametrize('mode',[a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM])
@pytest.mark.parametrize('mix',[0,.25,1])
@pytest.mark.parametrize('observed,map_values', [([10.,90.],[9.,1.]),([0.,100.],[1.,0.]),
                                               ([1e-6,1e6],[1.,1e6]),([10.,90.],[0.,0.])])
def test_written_overlap_total_and_independent_shares(tmp_path,mode,mix,observed,map_values):
    n=8
    z,y,x=np.indices((n,n,n))
    data=math.sqrt(map_values[0])*np.cos(2*math.pi*x/n)+math.sqrt(map_values[1])*np.cos(2*math.pi*y/n)
    path=tmp_path/'prediction.xplor'
    cell=gemmi.UnitCell(10,10,10,90,90,90)
    a.write_xplor_map(path,a.XplorMap('known Fourier components',(n,0,n-1,n,0,n-1,n,0,n-1),
                                    (10,10,10,90,90,90),'ZYX',data.ravel()))
    rows=[a.Reflection(*key,math.sqrt(i) if a.reflection_mode_is_amplitude(mode) else i,.1)
          for key,i in zip([(1,0,0),(0,1,0)],observed)]
    updated,_=a.redistribute_overlap_reflections(rows,mode,path,cell,1.0,1.0,mix,lambda text:None)
    output=tmp_path/'written.hkl'
    assert a.write_observed_reflections(output,updated,0,mode)==2
    actual=a.read_hkl(output)
    intensities=np.array([r.value**2 if a.reflection_mode_is_amplitude(mode) else r.value for r in actual])
    total=sum(observed)
    # Independently sum the actual serialized density, rather than expecting an
    # unquantized analytic weak coefficient after six-digit XPLOR serialization.
    saved=a.read_xplor_map(path).data.reshape(n,n,n)
    direct=np.array([abs(np.sum(saved*np.exp(2j*math.pi*coordinate/n)))**2 for coordinate in [x,y]])
    expected=np.array(observed) if sum(map_values)==0 else (
        (1-mix)*np.array(observed)+mix*total*direct/sum(direct))
    # Seven decimals in the written I or F column. Propagate the actual rounding
    # bound to intensity space rather than loosening a global relative tolerance.
    bounds=(2*np.sqrt(expected)*5e-8+2.5e-15 if a.reflection_mode_is_amplitude(mode)
            else np.full(2,5e-8))
    assert np.all(np.abs(intensities-expected)<=bounds+total*1e-12)
    assert abs(float(sum(intensities))-total)<=sum(bounds)+total*1e-12
    assert [r.sigma for r in actual]==[.1,.1]
