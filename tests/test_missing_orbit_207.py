"""Missing completion must preserve holdout isolation and extinction rules."""
import inspect
import math
import gemmi
import numpy as np
from phase_studio import app as a


def test_missing_completion_excludes_free_orbits_and_systematic_absences(tmp_path):
    n=8
    z,y,x=np.indices((n,n,n))
    # Deliberately inconsistent prediction has strong forbidden 010 and held-out
    # 100 coefficients. These cannot become eligible measured work reflections.
    data=np.cos(2*math.pi*x/n)+10*np.cos(2*math.pi*y/n)
    path=tmp_path/'predictions.xplor'
    a.write_xplor_map(path,a.XplorMap('adversarial map',(n,0,n-1,n,0,n-1,n,0,n-1),
        (10,11,12,90,90,90),'ZYX',data.ravel()))
    rows=[a.Reflection(1,1,0,10,None),a.Reflection(-1,1,0,10,None),a.Reflection(0,0,1,10,None)]
    sg=gemmi.SpaceGroup('P 21')
    kwargs={'excluded_hkls':frozenset({(1,0,0)})}
    if 'spacegroup' in inspect.signature(a.apply_map_feedback_to_reflections).parameters:
        kwargs['spacegroup']=sg
    updated,_=a.apply_map_feedback_to_reflections(rows,a.REFLECTION_DATA_MODE_INTENSITY,path,
        gemmi.UnitCell(10,11,12,90,90,90),0,True,100,False,0,0,lambda text:None,**kwargs)
    added={(r.h,r.k,r.l) for r in updated[len(rows):]}
    assert (-1,0,0) not in added, 'Friedel mate of held-out 100 leaked into work data'
    assert all(not sg.operations().is_systematically_absent(hkl) for hkl in added)
