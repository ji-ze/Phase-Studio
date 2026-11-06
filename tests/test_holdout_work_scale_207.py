"""A free-set scale fit can conceal incorrect predicted amplitudes entirely."""
import numpy as np
import pytest
from phase_studio import app as a
from phase_studio.map_quality import FrozenReflection,make_validation_context,compute_map_quality


@pytest.mark.parametrize('work_factor,free_factor,free_observed_factor,expected',
                         [(1.,2.,1.,1.),(2.,2.,1.,0.),(1.,2.,3.,1/3),(1.,2.,.5,3.)])
def test_free_r_uses_only_work_set_scale(tmp_path,work_factor,free_factor,free_observed_factor,expected):
    n=32;x=np.arange(n)
    observed=[1.,2.,3.,1.,2.,3.]
    calculated=np.array(observed)*np.array([work_factor]*3+[free_factor]*3)
    observed[3:]=[fo*free_observed_factor for fo in observed[3:]]
    data=sum(2*amplitude*np.cos(2*np.pi*h*x/n)/n for h,amplitude in enumerate(calculated,1))
    path=tmp_path/'known-amplitudes.xplor'
    a.write_xplor_map(path,a.XplorMap('independent work/free scales',(n,0,n-1,1,0,0,1,0,0),
        (10,10,10,90,90,90),'ZYX',data))
    measured=[FrozenReflection(h,0,0,fo) for h,fo in enumerate(observed,1)]
    free=frozenset((h,0,0) for h in [4,5,6])
    context=make_validation_context(measured,free_hkls=free)
    saved=a.read_xplor_map(path)
    metrics=compute_map_quality(saved.data,saved.grid,saved.cell,saved.axis_order,context)
    assert metrics.r_work==pytest.approx(0,abs=1e-5)
    assert metrics.r_free==pytest.approx(expected,abs=1e-5)
    rows=[a.Reflection(h,0,0,fo**2,None) for h,fo in enumerate(observed,1)]
    predictions={(h,0,0):(fc**2,0) for h,fc in enumerate(calculated,1)}
    assert a.compute_rfree(rows,free,a.REFLECTION_DATA_MODE_INTENSITY,predictions)==pytest.approx(expected,abs=1e-12)


def test_no_work_scale_is_not_replaced_by_free_set_fit():
    free=frozenset((h,0,0) for h in [1,2,3])
    rows=[a.Reflection(h,0,0,float(h*h),None) for h in [1,2,3]]
    predictions={(h,0,0):(float(4*h*h),0) for h in [1,2,3]}
    assert a.compute_rfree(rows,free,a.REFLECTION_DATA_MODE_INTENSITY,predictions) is None
