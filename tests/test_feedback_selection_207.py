"""Selected-result feedback is input provenance, never a quality/ranking signal."""
import csv
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import gemmi
from phase_studio import app as a
from phase_studio.feedback_diagnostics import (FeedbackCapture,save_report,save_original_reflections,
    input_comparison,load_summaries,export_csv,compare_stage,written_input_difference)
from phase_studio.feedback_selection import selected_input,FeedbackHistory


def recorded_step(root,*,cycle=7,intensity=False,powder=True,start=5):
    mode=a.REFLECTION_DATA_MODE_INTENSITY_FWHM
    rows=[a.Reflection(1,0,0,10.,.1),a.Reflection(2,0,0,20.,.1)]
    if not (root/'feedback_diagnostics/original_reflections.json').exists():
        save_original_reflections(root,rows,mode)
    initial=root/f'cycle_{cycle:03d}_input.hkl'
    if initial.exists():
        from phase_studio.hkl_diagnostics import read_diagnostic_reflections
        rows=list(read_diagnostic_reflections(initial,mode)[0])
    else:
        initial=root/'original.hkl';a.write_observed_reflections(initial,rows,0,data_mode=mode)
    cfg=SimpleNamespace(cycles=10,map_feedback_missing_enabled=False,map_feedback_missing_from_cycle=start,
        map_feedback_missing_percent_limit=0,map_feedback_intensity_enabled=intensity,
        map_feedback_intensity_from_cycle=start,map_feedback_intensity_damping=.5,
        redistribute_overlaps=powder,powder_redistribution_from_cycle=start,powder_wavelength=.39986)
    cell=gemmi.UnitCell(10,10,10,90,90,90)
    with FeedbackCapture(cycle,mode,rows,cfg) as capture,patch.object(a,'xplor_fft_predictions',
         return_value=({(1,0,0):(3.,0.),(2,0,0):(1.,0.)} if cycle==8 else
                       {(1,0,0):(1.,0.),(2,0,0):(3.,0.)})),patch.object(a,'assign_powder_overlap_groups',
         return_value={(1,0,0):1,(2,0,0):1}):
        output=rows
        if cycle>=start and intensity:
            output,_=a.apply_map_feedback_to_reflections(output,mode,Path('controlled-map'),cell,0,False,0,True,.5,0,lambda _:None)
        if cycle>=start and powder:
            output,_=a.redistribute_overlap_reflections(output,mode,Path('controlled-map'),cell,.39986,.2,1,lambda _:None)
    target=root/f'cycle_{cycle+1:03d}_input.hkl'
    a.write_observed_reflections(target,output,0,data_mode=mode)
    report=capture.report();report['cycle_input']=input_comparison(root,initial,mode)
    report['target_input']=input_comparison(root,target,mode)
    report['written_input_difference']=written_input_difference(initial,target,mode)
    report['next_cycle_reflection_file']=str(target);report['written_reflections']=len(output)
    return save_report(root,report),report


@pytest.mark.parametrize('intensity,powder,expected',[(False,True,'Applied'),(True,False,'Applied'),
    (True,True,'Applied'),(False,False,'Disabled')])
def test_selected_input_uses_preceding_step_and_separate_operations(tmp_path,intensity,powder,expected):
    summary,report=recorded_step(tmp_path,intensity=intensity,powder=powder)
    result=selected_input([summary],8)
    assert result['status']==expected and 'after cycle 7' in result['headline']
    assert 'shared by Superflip and SharpED' in result['text']
    assert selected_input([summary],7)['status']=='Unavailable'  # after 7 is not input 7
    assert 'after cycle 8 affect input 9' in result['text']
    assert ('Powder overlap repartitioning: Applied' in result['text']) is powder
    assert ('Intensity correction: Applied' in result['text']) is intensity
    assert 'Cumulative vs original:' in result['text']
    if powder and not intensity:
        op=report['operations'][2]
        assert op['modified_reflections']==2 and op['modified_groups']==1 and op['conservation']
        assert op['mean_absolute_relative_percent']==18.75
        assert op['maximum_absolute_relative_percent']==25
        target=report['target_input'];assert target['cumulative']['mean_absolute_relative_percent']==18.75
        out=tmp_path/'changes.csv';export_csv(out,report)
        exported=list(csv.DictReader(out.open()))
        assert [float(r['after']) for r in exported]==[7.5,22.5]
        assert [float(r['signed_relative_percent']) for r in exported]==[-25.,12.5]
        assert math.fsum(float(r['before']) for r in exported)==math.fsum(float(r['after']) for r in exported)


def test_future_missing_and_input_hash_mismatch_are_explicit(tmp_path):
    summary,_=recorded_step(tmp_path,start=9)
    data=selected_input([summary],8)
    assert data['status']=='Not yet reached' and ': Applied' not in data['text']
    assert selected_input([],8)['status']=='Unavailable'
    assert 'Detailed Map Feedback changes unavailable for this run.' in selected_input([],8)['text']
    current=dict(source_cycle=8,target_cycle=9,cycle_input={'sha256':'different'},operations=[])
    result=selected_input([summary,current],8)
    assert result['status']=='Unavailable' and 'does not match' in result['text']


def test_original_first_cycle_and_cumulative_edge_cases(tmp_path):
    _,report=recorded_step(tmp_path,cycle=1,start=5)
    assert selected_input([report],1)['status']=='Original input'
    mode=a.REFLECTION_DATA_MODE_INTENSITY
    original=[a.Reflection(1,0,0,0,None),a.Reflection(2,0,0,-3,None),a.Reflection(3,0,0,5,None)]
    save_original_reflections(tmp_path,original,mode)
    path=tmp_path/'written.hkl'
    # Actual file omits HKL3 and adds HKL4. Neither absence is an intensity of zero.
    path.write_text('1 0 0 1\n2 0 0 -1\n4 0 0 9\n')
    data=input_comparison(tmp_path,path,mode)
    c=data['cumulative'];assert c['added_reflections']==1 and c['removed_reflections']==1
    assert c['mean_absolute_relative_percent'] is None and c['modified_reflections']==2
    assert all(r['relative_percent'] is None for r in c['rows'])
    path.write_text('1 0 0 1\n1 0 0 2\n')
    assert input_comparison(tmp_path,path,mode)['status']=='Unavailable'
    assert compare_stage([a.Reflection(1,0,0,float('nan'),None)],
        [a.Reflection(1,0,0,2,None)],mode)['rows'][0]['before'] is None


def test_run_replacement_does_not_reuse_old_cycles(tmp_path):
    recorded_step(tmp_path)
    save_original_reflections(tmp_path,[a.Reflection(1,0,0,1,None)],a.REFLECTION_DATA_MODE_INTENSITY,run_id='new run')
    assert load_summaries(tmp_path)==[]
    history=FeedbackHistory(tmp_path)
    assert history.selected(8)['status']=='Unavailable'


def test_gui_four_scales_and_two_contexts():
    import subprocess,sys
    root=Path(__file__).resolve().parents[1]
    for scale in ('1','1.25','1.5','2'):
        run=subprocess.run([sys.executable,str(root/'tests/feedback_selection_gui_207.py'),scale],
            cwd=root,env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},
            capture_output=True,text=True,timeout=90)
        assert run.returncode==0,scale+': '+run.stdout+run.stderr
