"""Real Qt review/log controls and a controlled stop, using synthetic artifacts."""
import sys,os,tempfile,json,hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication,QDialog
from phase_studio import app as a
from phase_studio.result_selection import ResultSelectionDialog
from phase_studio.run_review import workflow_status_text
from phase_studio.run_provenance import safe
import test_jana_completion as fixture
settings=tempfile.TemporaryDirectory();QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,settings.name)
qt=QApplication([]);a.apply_phase_studio_style(qt)
def events():
    for _ in range(8):qt.processEvents()
with patch.multiple(a.IterativeSuperflipPipelineQtGUI,load_settings=lambda self:None,save_settings=lambda self:None,refresh_sharped_models=lambda self:None):
    backend,results=fixture.build_window(a,cycles=3)
backend.timer.stop();backend._jana_wizard_handoff_available=lambda:False
cfg=backend.last_run_config;cfg.cycles=5;cfg.run_id='fixture-review';backend._active_run_id=cfg.run_id
results=[replace(r,run_id=cfg.run_id) for r in results]
backend.results=results[:2]
log=a.RunDiagnosticLog(cfg.work_dir/'log.txt',cfg);backend._run_diagnostic_log=log;p=log.provenance
for result in results[:2]:p.manifest['cycles'][str(result.cycle)]={'status':'completed','source_cycle':result.cycle,'result':safe(result),'reflection_input':{}}
backend._set_run_status('Running');backend._apply_cycle_progress_state(a.CycleProgressState(3,5,'Superflip',1,7,busy=True))
backend.stop_btn.click();events()
assert p.manifest['status']=='stopping_after_current_cycle' and p.manifest['finished'] is None
assert 'Stop after current cycle requested.' in (cfg.work_dir/'log.txt').read_text(encoding='utf8')
backend.results=results
p.manifest['cycles']['3']={'status':'completed','source_cycle':3,'result':safe(results[2]),'reflection_input':{}}
state=SimpleNamespace(cfg=cfg,run_id=cfg.run_id,provenance=p,diagnostic_log=None,completed_cycles=2)
assert backend._finalize_completed_cycle(state,3,['Superflip'])
p.finish('stopped');backend._poll_queue();events()
assert p.manifest['status']=='stopped' and p.manifest['completed_cycles']==3
codes=[x['code'] for x in p.manifest['lifecycle']]
for code in ('STOP_REQUESTED','FINISHING_CURRENT_CYCLE','CURRENT_CYCLE_COMPLETED','STOPPED_BY_USER','RESULTS_AVAILABLE'):assert code in codes
assert '3 of 5' in backend.log_text.toPlainText()
for cycle in (1,2,3):
    for component in ('Superflip','SharpED'):
        p.event('log',component,cycle,{'message':f'{component} cycle {cycle} science','category':'SCIENTIFIC_RESULT'},'WARNING' if component=='SharpED' else 'INFO')
p.checkpoint()
protected=[cfg.work_dir/'events.jsonl',cfg.work_dir/'run_manifest.json',*[Path(r.superflip_edma_cif) for r in results],*[Path(r.superflip_map) for r in results]]
before={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
opened=[];details=[]
def capture(dialog):
    if isinstance(dialog,ResultSelectionDialog):opened.append(dialog)
    else:details.append(dialog.windowTitle())
    return QDialog.Rejected
with patch.object(QDialog,'exec',capture):backend.open_result_selector('standalone',initial_source='superflip')
selector=opened[-1];selector._rotate_timer.stop();selector.show();events();selector.resize(1250,820);events()
assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in before.items() if path.suffix not in ('.jsonl','.json'))
before={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
selected=selector.selected_candidate;selector._execution_log_button.click();events();viewer=selector._run_log_viewer
assert '3 of 5' in selector._run_status_label.text() and '3 of 5' in viewer.status.text()
assert viewer.isVisible() and not viewer.isModal() and selector.selected_candidate==selected
viewer.cycle_filter.setChecked(True);viewer.family_filter.setChecked(True);events()
assert f'Superflip cycle {selected.cycle} science' in viewer.text.toPlainText()
assert 'SharpED cycle' not in viewer.text.toPlainText()
selector._sharped_btn.click();events()
assert viewer.family=='deblurred' and viewer.cycle==selector.selected_candidate.cycle
assert f'SharpED cycle {viewer.cycle} science' in viewer.text.toPlainText()
viewer.kind.setCurrentIndex(viewer.kind.findData('warnings'));viewer.search.setText('science');events()
assert 'WARNING' in viewer.text.toPlainText()
with patch.object(QDialog,'exec',capture):selector._why_cycle_button.click();selector._candidate_info.click()
assert 'Why this cycle?' in details and 'Displayed candidate and transfer identity' in details
assert all(hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in before.items())
out=ROOT/'build/final-review207/gui';out.mkdir(parents=True,exist_ok=True)
selector.grab().save(str(out/'result-selection.png'));viewer.grab().save(str(out/'filtered-execution-log.png'));backend.resize(1600,1050);backend.show();events();backend.grab().save(str(out/'stopped-run-overview.png'))
viewer.close();selector.close()
with patch.object(QDialog,'exec',capture):backend.open_result_selector('standalone')
reopened=opened[-1];reopened._rotate_timer.stop();reopened._execution_log_button.click();events()
assert len(reopened._run_log_viewer.review.records)>=len(viewer.review.records)
reopened._run_log_viewer.close();reopened.close()
log.close();backend._run_diagnostic_log=None;backend.last_run_config=None
original_events=(cfg.work_dir/'events.jsonl').read_bytes()
with patch.object(a.QFileDialog,'getExistingDirectory',return_value=str(cfg.work_dir)):
    backend.execution_log_open_button.click();events()
    historical=backend._execution_log_viewers[-1]
    assert '3 of 5' in historical.status.text() and (cfg.work_dir/'events.jsonl').read_bytes()==original_events
    historical.close()
backend.close();events()
print('PASS real Qt log access, cycle/family filters, recommendation details, controlled stop 3/5, reopen and immutable files')
