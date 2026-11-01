import ast
import csv
import json
import math
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import gemmi
import pytest
from phase_studio import app as a
from phase_studio.feedback_diagnostics import FeedbackCapture,compare_stage,save_report,load_summaries,export_csv


def config(**kwargs):
    from types import SimpleNamespace
    values=dict(cycles=8,map_feedback_missing_enabled=False,map_feedback_missing_from_cycle=5,
        map_feedback_missing_percent_limit=0.,map_feedback_intensity_enabled=True,
        map_feedback_intensity_from_cycle=5,map_feedback_intensity_damping=.5,
        redistribute_overlaps=True,powder_redistribution_from_cycle=5,powder_wavelength=.39986)
    return SimpleNamespace(**(values|kwargs))


def test_authoritative_arrays_stages_and_conservation(tmp_path):
    rows=[a.Reflection(1,0,0,10,.1),a.Reflection(2,0,0,20,.1)]
    predictions={(1,0,0):(1.,0.),(2,0,0):(3.,0.)}
    groups={(1,0,0):1,(2,0,0):1}
    with FeedbackCapture(5,a.REFLECTION_DATA_MODE_INTENSITY_FWHM,rows,config()) as capture,patch.object(a,'xplor_fft_predictions',return_value=predictions),patch.object(a,'assign_powder_overlap_groups',return_value=groups):
        corrected,_=a.apply_map_feedback_to_reflections(rows,a.REFLECTION_DATA_MODE_INTENSITY_FWHM,Path('unused'),gemmi.UnitCell(10,10,10,90,90,90),0,False,0,True,.5,0,lambda _:None)
        final,_=a.redistribute_overlap_reflections(corrected,a.REFLECTION_DATA_MODE_INTENSITY_FWHM,Path('unused'),gemmi.UnitCell(10,10,10,90,90,90),.39986,.2,1,lambda _:None)
    report=capture.report();assert not report['errors']
    assert report['source_cycle']==5 and report['target_cycle']==6
    intensity,powder=report['operations'][1:]
    assert intensity['eligible_reflections']==2 and intensity['modified_reflections']==2
    assert intensity['mean_absolute_delta']==pytest.approx(5/3)
    assert powder['modified_groups']==1 and powder['conservation'] is True
    assert math.fsum(r.value for r in corrected)==pytest.approx(math.fsum(r.value for r in final),abs=1e-12)
    assert powder['rows'][0]['before']==corrected[0].value
    assert intensity['rows'][0]['after']==corrected[0].value
    summary=save_report(tmp_path,report)
    assert 'rows' not in summary['operations'][1]
    assert load_summaries(tmp_path)[0]['source_cycle']==5
    path=tmp_path/'data.csv';export_csv(path,report)
    parsed=list(csv.DictReader(path.open()))
    assert len(parsed)==4 and {r['operation'] for r in parsed}=={'intensity','powder'}
    assert float(parsed[0]['after'])==corrected[0].value
    assert json.loads(Path(summary['detail_path']).read_text())['operations'][2]['conservation'] is True


def test_statuses_and_empty_denominators():
    rows=[a.Reflection(i,0,0,v,None) for i,v in enumerate([0,-3,float('nan')],1)]
    after=[a.Reflection(i,0,0,v,None) for i,v in enumerate([1,-1,float('nan')],1)]
    d=compare_stage(rows,after,a.REFLECTION_DATA_MODE_INTENSITY,eligible={(1,0,0),(2,0,0)},groups={(1,0,0):1,(2,0,0):1})
    assert d['modified_reflections']==2 and d['mean_absolute_delta']==1.5
    assert d['mean_absolute_relative_percent'] is None and d['relative_population']==0
    assert d['conservation'] is False
    assert d['rows'][1]['before']==-3 and d['rows'][2]['before'] is None
    c=FeedbackCapture(4,'hkl I fwhm',rows,config())
    assert c.operations['powder']['status']=='Not yet reached'
    assert c.operations['missing']['status']=='Disabled'
    assert FeedbackCapture(5,'hkl I fwhm',rows,config(map_feedback_intensity_damping=0)).operations['intensity']['reason']=='Correction damping is zero'
    assert FeedbackCapture(5,'hkl I fwhm',rows,config(powder_wavelength=0)).operations['powder']['reason']=='Measured wavelength is unavailable'
    assert FeedbackCapture(8,'hkl I fwhm',rows,config()).report()['target_cycle'] is None


def test_missing_completion_and_no_map_signal():
    rows=[a.Reflection(1,0,0,10,None)]
    predictions={(1,0,0):(2.,0.)}
    with FeedbackCapture(5,a.REFLECTION_DATA_MODE_INTENSITY,rows,config(map_feedback_missing_enabled=True,map_feedback_missing_percent_limit=100)) as c,patch.object(a,'xplor_fft_predictions',side_effect=[predictions,{(2,0,0):(4.,0.)}]),patch.object(a,'candidate_missing_hkls_from_bounds',return_value=[(2,0,0)]):
        output,_=a.apply_map_feedback_to_reflections(rows,a.REFLECTION_DATA_MODE_INTENSITY,Path('unused'),gemmi.UnitCell(10,10,10,90,90,90),0,True,100,False,0,0,lambda _:None)
    missing=c.operations['missing']
    assert len(output)==2 and missing['added_reflections']==1 and missing['percentage_increase']==100
    assert missing['proposed_reflections']==1 and missing['status']=='Applied'
    rows.append(a.Reflection(2,0,0,20,.1))
    with FeedbackCapture(5,a.REFLECTION_DATA_MODE_INTENSITY,rows,config()) as c,patch.object(a,'xplor_fft_predictions',return_value={}),patch.object(a,'assign_powder_overlap_groups',return_value={(1,0,0):1,(2,0,0):1}):
        output,_=a.redistribute_overlap_reflections(rows,a.REFLECTION_DATA_MODE_INTENSITY,Path('unused'),gemmi.UnitCell(10,10,10,90,90,90),.39986,.2,1,lambda _:None)
    assert c.operations['powder']['eligible_groups']==0
    assert c.operations['powder']['modified_reflections']==0


def test_numerical_implementations_remain_identical_to_starting_source():
    baseline=subprocess.check_output(['git','show','2aa74fa:phase_studio/app.py']).decode('utf8')
    current=Path(a.__file__).read_text(encoding='utf8')
    for name,kind,count in [('apply_map_feedback_to_reflections','map',1),('redistribute_overlap_reflections','powder',2)]:
        get=lambda source:next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
        old,new=get(baseline),get(current)
        hooks=[n for n in ast.walk(new) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='record_feedback_observation']
        assert len(hooks)==count
        for hook in hooks:assert ast.dump(hook)==ast.dump(ast.parse(f'record_feedback_observation({kind!r}, locals())').body[0])
        for parent in ast.walk(new):
            for _,value in ast.iter_fields(parent):
                if isinstance(value,list):value[:]=[item for item in value if item not in hooks]
        assert ast.dump(old)==ast.dump(new)
