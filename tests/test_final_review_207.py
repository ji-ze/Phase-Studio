"""Scientific artifact, persisted-review and lifecycle acceptance regressions."""
from pathlib import Path
import hashlib,threading
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pytest
from phase_studio import app as a


def fixture_map(path):
    m=a.XplorMap('immutable input',(2,0,1,2,0,1,2,0,1),(10,11,12,90,91,90),'ZYX',np.arange(8,dtype=float)/7)
    a.write_xplor_map(path,m)
    return m


def test_normalization_rejects_source_alias(tmp_path):
    source=tmp_path/'source.xplor';fixture_map(source);before=source.read_bytes()
    with pytest.raises(ValueError,match='separate|original|same'):
        a.normalize_xplor_for_edma(source,source)
    assert source.read_bytes()==before


def test_normalization_publish_is_atomic_for_concurrent_readers(tmp_path,monkeypatch):
    source=tmp_path/'source.xplor';fixture_map(source);before=source.read_bytes()
    target=tmp_path/'edma.xplor';target.write_bytes(b'previous finalized artifact')
    started=threading.Event();release=threading.Event();writer=a.write_xplor_map
    def delayed(path,*args,**kwargs):
        path.write_bytes(b'partial transform');started.set()
        assert release.wait(10)
        writer(path,*args,**kwargs)
    monkeypatch.setattr(a,'write_xplor_map',delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(a.normalize_xplor_for_edma,source,target)
        try:
            assert started.wait(10)
            assert source.read_bytes()==before
            assert target.read_bytes()==b'previous finalized artifact'
        finally:release.set()
        pending.result()
    assert source.read_bytes()==before
    expected=tmp_path/'expected.xplor';writer(expected,a.read_xplor_map(source),title='immutable input',values_per_line=1)
    assert target.read_bytes()==expected.read_bytes()



def test_failed_normalization_keeps_previous_final_artifact(tmp_path,monkeypatch):
    source=tmp_path/'source.xplor';fixture_map(source);before=source.read_bytes()
    target=tmp_path/'consumer.xplor';target.write_bytes(b'old complete')
    def fail(path,*args,**kwargs):path.write_bytes(b'partial');raise OSError('controlled failure')
    monkeypatch.setattr(a,'write_xplor_map',fail)
    with pytest.raises(OSError):a.normalize_xplor_for_edma(source,target)
    assert source.read_bytes()==before and target.read_bytes()==b'old complete'
    assert not list(tmp_path.glob('.*.tmp'))


def test_sealed_publication_refuses_changed_source_and_preserves_targets(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'changed source')
    target=tmp_path/'target';target.write_bytes(b'previous completed output')
    with pytest.raises(RuntimeError):
        a._publish_protocol_transaction([(source,target)],expected_hashes={target.resolve():hashlib.sha256(b'expected source').hexdigest()})
    assert target.read_bytes()==b'previous completed output'
    assert not list(tmp_path.glob('.*publish-*'))


def test_persisted_review_filters_survive_reopen_without_writing(tmp_path):
    import json
    from phase_studio.run_review import PersistedRunReview
    rows=[dict(cycle=cycle,component=family,event_type='log',severity=severity,payload={'message':message,'category':category})
        for cycle,family,severity,message,category in [(1,'Superflip','INFO','scientific amplitude','SCIENTIFIC_RESULT'),(2,'SharpED','WARNING','server warning','WARNING'),(2,'EDMA','INFO','unknown family','USER_PROGRESS')]]
    path=tmp_path/'events.jsonl';path.write_text(''.join(json.dumps(row)+'\n' for row in rows)+'{"incomplete"')
    before=path.read_bytes();review=PersistedRunReview(tmp_path)
    assert len(review.events())==3 and review.incomplete_records==1
    assert review.events(cycle=2,family='deblurred',kind='warnings',search='server')==[rows[1]]
    assert review.events(kind='scientific')[0]==rows[0]
    assert PersistedRunReview(tmp_path).events()==rows and path.read_bytes()==before


def test_stop_lifecycle_is_not_premature_completion(tmp_path):
    import json
    from test_run_provenance_207 import config
    from phase_studio.run_provenance import RunProvenance
    from phase_studio.run_review import workflow_status_text
    cfg=config(tmp_path);cfg.cycles=5;p=RunProvenance(tmp_path,cfg)
    p.event('STOP_REQUESTED','Workflow',3,{'message':'stop requested'})
    p.event('FINISHING_CURRENT_CYCLE','Workflow',3,{'message':'finishing'})
    assert p.manifest['status']=='stopping_after_current_cycle' and p.manifest['finished'] is None
    for cycle in (1,2,3):p.manifest['cycles'][str(cycle)]={'status':'completed','source_cycle':cycle,'result':{},'reflection_input':{}}
    p.event('CURRENT_CYCLE_COMPLETED','Workflow',3,{'message':'cycle completed'})
    p.finish('stopped');p.event('STOPPED_BY_USER','Workflow',3,{'message':'stopped'})
    p.event('RESULTS_AVAILABLE','Workflow',3,{'message':'results available'})
    assert p.manifest['completed_cycles']==3 and p.manifest['status']=='stopped'
    assert '3 of 5' in workflow_status_text(p.manifest)
    assert [e['code'] for e in p.manifest['lifecycle']]==['STOP_REQUESTED','FINISHING_CURRENT_CYCLE','CURRENT_CYCLE_COMPLETED','STOPPED_BY_USER','RESULTS_AVAILABLE']
    assert 'Final selection: Pending' in p.summary()
    p.close();assert json.loads((tmp_path/'run_manifest.json').read_text())['status']=='stopped'


def test_disabled_feedback_claim_requires_matching_inventory():
    from phase_studio.run_review import disabled_feedback_summary
    m={'effective_config':dict(map_feedback_missing_enabled=False,map_feedback_intensity_enabled=False,redistribute_overlaps=False),
       'reflection_inventory':dict(actual_input={'sha256':'original'},absent_from_written=0,duplicates_merged=0,parser_rejections=0)}
    exact=disabled_feedback_summary(m,{'reflection_input':{'sha256':'original'}})
    assert exact=='Map Feedback: Disabled. Original measured reflection input retained.'
    assert 'not established' in disabled_feedback_summary(m,{'reflection_input':{'sha256':'different'}})
    m['effective_config']['redistribute_overlaps']=True
    assert disabled_feedback_summary(m,{}) is None


def test_legacy_amplitude_auxiliary_is_not_claimed_as_measured_uncertainty():
    from phase_studio.run_review import uncertainty_description
    assert 'dummy' in uncertainty_description(a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA)
    assert 'not sigma' in uncertainty_description(a.REFLECTION_DATA_MODE_INTENSITY_FWHM)


def test_persisted_export_is_read_only_and_redacts_sensitive_fields(tmp_path):
    import json,zipfile
    from phase_studio.run_review import PersistedRunReview
    directory=tmp_path/'run';directory.mkdir()
    manifest={'status':'stopped','completed_cycles':3,'configured_cycles':5,'api_token':'SECRET_API','oauth':{'refresh_token':'SECRET_REFRESH'},'file':r'C:\Users\Alice\Private work\map.xplor','job_id':'private-job-abc','scientific_sha256':'a'*64,'density_std':1.25,'network_file':r'\\PrivateHost\UserShare\Alice\map.xplor','username':'PrivateOwner'}
    source=directory/'run_manifest.json';source.write_text(json.dumps(manifest));before=source.read_bytes()
    (directory/'diagnostic.log').write_text('job_id=private-job-abc\nContact alice@example.com\nAuthorization: Bearer SECRET_BEARER')
    target=tmp_path/'sanitized.zip';PersistedRunReview(directory).export_sanitized(target)
    with zipfile.ZipFile(target) as z:combined=b'\n'.join(z.read(name) for name in z.namelist()).decode()
    for secret in ('SECRET_API','SECRET_REFRESH','SECRET_BEARER','private-job-abc','Alice','alice@example.com','PrivateHost','UserShare','PrivateOwner'):assert secret not in combined
    assert 'a'*64 in combined and '1.25' in combined and source.read_bytes()==before


def test_metric_bodies_only_change_reviewed_holdout_scale():
    import ast,subprocess
    old=subprocess.check_output(['git','show','62582d2:phase_studio/map_quality.py'],text=True)
    current=Path(a.__file__).with_name('map_quality.py').read_text(encoding='utf8')
    def funcs(text):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
    before,after=funcs(old),funcs(current)
    for name in ('scaled_amplitude_metrics','recommend_best_result'):assert before[name]==after[name]
    reviewed=subprocess.check_output(['git','show','8a40fa1:phase_studio/map_quality.py'],text=True)
    reviewed_functions=funcs(reviewed)
    for name in ('compute_map_quality','amplitude_r_factor_at_scale'):
        assert after[name]==reviewed_functions[name]
    get=lambda text:next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='compute_map_quality')
    old_node,new_node=get(old),get(current)
    free_keyword=lambda node:[n for n in ast.walk(node) if isinstance(n,ast.keyword) and n.arg=='r_free']
    before_free,after_free=free_keyword(old_node),free_keyword(new_node)
    assert len(before_free)==len(after_free)==1
    before_free[0].value=after_free[0].value
    assert ast.dump(old_node)==ast.dump(new_node)  # Every other metric expression stays historical.


@pytest.mark.parametrize('scale',['1','1.25','1.5','2'])
def test_actual_review_gui(scale):
    import os,sys,subprocess
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('final_review_gui_207.py'))],env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('outcome,count,status',[('complete',5,'completed'),('complete',3,'partial'),('cancelled',3,'cancelled'),('failed',2,'failed')])
def test_terminal_outcomes_are_distinct(tmp_path,outcome,count,status):
    from test_run_provenance_207 import config
    from phase_studio.run_provenance import RunProvenance
    cfg=config(tmp_path);cfg.cycles=5;p=RunProvenance(tmp_path,cfg)
    for cycle in range(1,count+1):p.manifest['cycles'][str(cycle)]={'status':'completed','source_cycle':cycle,'result':{},'reflection_input':{}}
    p.finish(outcome)
    assert p.manifest['status']==status and p.manifest['completed_cycles']==count
    p.close()


@pytest.mark.parametrize('component',['Superflip','SharpED','EDMA'])
def test_failed_operation_identity_and_results_preserved(tmp_path,component):
    from test_run_provenance_207 import config
    from phase_studio.run_provenance import RunProvenance
    source=tmp_path/'completed-result.xplor';fixture_map(source);before=source.read_bytes()
    p=RunProvenance(tmp_path,config(tmp_path));p.operation('started',component,2);p.operation('finished',component,2,status='failed');p.finish('failed')
    assert p.manifest['status']=='failed' and p.manifest['warnings'][-1]['component']==component
    assert source.read_bytes()==before;p.close()


def test_partial_utf8_event_export_is_transparent_and_read_only(tmp_path):
    import json,zipfile
    from phase_studio.run_review import PersistedRunReview
    root=tmp_path/'run';root.mkdir();path=root/'events.jsonl'
    original=b'{"event_type":"complete","payload":{}}\n{"broken":"\xc3';path.write_bytes(original)
    target=tmp_path/'shared.zip';PersistedRunReview(root).export_sanitized(target)
    with zipfile.ZipFile(target) as z:
        assert json.loads(z.read('export_notes.json'))['incomplete_event_lines_omitted']==1
        assert len(z.read('events.jsonl').splitlines())==1
    assert path.read_bytes()==original


@pytest.mark.parametrize('confirm,mutate,success',[(True,False,True),(False,False,False),(True,True,False)])
def test_actual_export_confirmation_and_candidate_identity(tmp_path,monkeypatch,confirm,mutate,success):
    from types import SimpleNamespace
    from phase_studio.map_quality import ResultCandidate,MapQualityMetrics
    from test_jana_completion import CIF
    from test_run_provenance_207 import config
    from phase_studio.run_provenance import RunProvenance
    source=tmp_path/'cycle_002_superflip.xplor';fixture_map(source)
    structure=tmp_path/'cycle_002_superflip.cif';structure.write_text(CIF)
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    candidate=ResultCandidate(2,'superflip',str(source),str(structure),MapQualityMetrics(),candidate_id='sealed-cycle-2',map_sha256=digest(source),structure_sha256=digest(structure))
    p=RunProvenance(tmp_path,config(tmp_path));destination=tmp_path/'chosen destination'
    owner=SimpleNamespace(last_run_config=None,_run_diagnostic_log=SimpleNamespace(provenance=p),_append_execution_log=lambda *args,**kwargs:None)
    monkeypatch.setattr(a.QFileDialog,'getExistingDirectory',lambda *args:str(destination))
    def approve(parent,rows):
        row=dict(rows);assert str(destination)==row['Actual destination'] and row['Selected cycle']==2
        assert source.name in row['Intended output filenames'] and row['Map SHA-256']==candidate.map_sha256
        if mutate:source.write_bytes(b'changed after candidate preview')
        return confirm
    monkeypatch.setattr(a,'confirm_candidate_transfer',approve)
    assert a.IterativeSuperflipPipelineQtGUI._export_selected_candidate(owner,candidate)==success
    if success:
        assert digest(destination/source.name)==candidate.map_sha256 and digest(destination/structure.name)==candidate.structure_sha256
        assert p.manifest['exports'][-1]['status']=='completed' and len(p.manifest['selections'])==1
    else:assert not destination.exists() and not p.manifest['selections']
    p.close()



def test_recorded_validation_family_is_filterable(tmp_path):
    import json
    from phase_studio.run_review import PersistedRunReview
    row={'component':'Validation','cycle':2,'event_type':'log','severity':'INFO','payload':{'family':'deblurred','category':'SCIENTIFIC_RESULT','message':'reference dependent result'}}
    (tmp_path/'events.jsonl').write_text(json.dumps(row)+'\n')
    assert PersistedRunReview(tmp_path).events(cycle=2,family='deblurred',kind='scientific')==[row]


def test_unknown_saved_status_does_not_invent_zero_or_process_liveness():
    from phase_studio.run_review import workflow_status_text
    assert 'unavailable' in workflow_status_text({})
    value=workflow_status_text({'status':'running'})
    assert 'unavailable' in value and 'not verified' in value and '0 of' not in value
