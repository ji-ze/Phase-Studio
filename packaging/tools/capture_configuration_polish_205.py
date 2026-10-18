"""Offline actual-Qt configuration acceptance with optional ten final captures."""
import os
import sys
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['PHASE_STUDIO_STARTUP_PROBE']='1'
os.environ.pop('SHARPED_API_TOKEN',None)
from PySide6.QtCore import QSettings,QRect,QPoint,Qt
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication,QDialog,QToolTip
from PySide6.QtTest import QTest
from phase_studio import jana_superflip as js
from phase_studio.credentials import CredentialStore
from phase_studio.ui_style import apply_phase_studio_style
from test_wizard_text_clipping import write_inflip

OUT=ROOT/'build/acceptance-superflip-sharped-wizard-2.0.5'
OUT.mkdir(parents=True,exist_ok=True)
qt=QApplication([]);apply_phase_studio_style(qt)
factor=float(os.environ.get('QT_SCALE_FACTOR','1'))
available=QRect(0,0,int(1920/factor),int(1040/factor))
capture='--capture' in sys.argv
evidence={}

def settle(w):
    for _ in range(25):qt.processEvents()
    w._size_stack_to_current_page(w.dialog.width())
    for _ in range(25):qt.processEvents()

def snap(name,w):
    settle(w);QToolTip.hideText()
    evidence[name]=dict(rect=w.dialog.geometry().getRect(),frame=w.dialog.frameGeometry().getRect(),dpr=w.dialog.devicePixelRatioF(),
        model=w.model.currentText(),manual=w.model_user_picked['value'],status=w.model_status.text(),account=w.connection_status.text(),
        scroll=w.scroll_area.verticalScrollBar().maximum(),fixture='Synthetic local input; mocked public catalogue; no real credentials or inference')
    if capture:assert w.dialog.grab().save(str(OUT/(name+'.png')))

with tempfile.TemporaryDirectory() as tmp,patch.object(QScreen,'availableGeometry',return_value=available):
    base=Path(tmp);source=write_inflip(base);original=source.read_bytes()
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
    factory=lambda org,app:QSettings(str(base/(app+'.ini')),QSettings.IniFormat)
    imports=js._qt_imports
    jana=base/'Jana';(jana/'SUPERFLIP').mkdir(parents=True)
    for name in ('superflip.exe','EDMA.exe'):(jana/'SUPERFLIP'/name).write_bytes(b'UI fixture never executed')
    peak,seed=js.SHARPED_ONE_CYCLE_MODEL,js.SHARPED_ITERATIVE_MODEL
    state=dict(models=[peak,seed,'Extra catalogue model','Long catalogue model name used to verify readable popup geometry'],fail=False,calls=0)
    def models(_client):
        state['calls']+=1
        if state['fail']:raise TimeoutError('mock offline request')
        return SimpleNamespace(models=list(state['models']),default_model='Extra catalogue model')
    with patch.object(js,'_qt_imports',lambda:imports()|{'QSettings':factory}),patch.object(js,'credential_store',CredentialStore(backend=None)),patch.object(js,'application_dir',lambda:jana),patch.object(QDialog,'exec',lambda self:QDialog.Rejected),patch.object(js.SharpEDServerClient,'get_models',models):
        w=js._JanaWorkflowWizard([],source);w.run();w.dialog.show();settle(w)
        initial=QRect(w.dialog.geometry())
        def stable():
            settle(w)
            assert w.dialog.geometry()==initial,(w.dialog.geometry(),initial)
            assert available.contains(QRect(w.cancel_button.mapToGlobal(QPoint()),w.cancel_button.size()))
            assert w.scroll_area.horizontalScrollBar().maximum()==0
            assert w.footer.geometry().bottom()<w.dialog.height()
        def pump():
            deadline=time.monotonic()+4
            while w.model_cache['inflight'] and time.monotonic()<deadline:
                qt.processEvents();w.refresh_timer.timeout.emit();QTest.qWait(5)
            assert not w.model_cache['inflight']
            settle(w)
        if factor==1:snap('01-initial-workflow',w)
        w.superflip_sharped_tile._trigger();pump();stable()
        assert state['calls']==1 and w.model.currentText()==seed and not w.model_user_picked['value']
        assert w.context_subtitle_label.text()=='Configure charge flipping and SharpED processing'
        assert w.primary_button.text()=='Next: Map feedback →'
        assert w.connection_status.text()=='Sign in with Jana2020'
        assert w.sharped_body.isHidden()
        if factor==1:snap('02-automatic-model',w)
        w.cycles.setValue(1);stable()
        assert w.model.currentText()==peak and w.model_recommendation.text()=='Automatically selected for 1 cycle'
        assert w.restore_automatic_model_button.isHidden() or w.manual_model_row.isHidden()
        if factor==1:snap('03-one-cycle-peak-a',w)
        w.cycles.setValue(3);stable()
        assert w.model.currentText()==seed and w.model_recommendation.text()=='Automatically selected for 3 cycles'
        assert 'may improve' in w.cycles_recommendation.text() and 'Balanced' not in w.cycles_recommendation.text()
        assert 'original measured diffraction data and independent crystallographic refinement' in w.warning_text.text()
        if factor==1:snap('04-three-cycle-seed',w)
        if factor==1.25:snap('09-configuration-dpi-125',w)
        if factor==1.5:snap('10-configuration-dpi-150',w)
        # Explicit selection of the recommended ID remains a manual choice.
        w.model.activated.emit(w.model.currentIndex());stable()
        assert w.model_user_picked['value'] and 'Matches recommended model' in w.manual_model_indicator.text()
        w.cycles.setValue(1);assert w.model.currentText()==seed
        w.cycles.setValue(3)
        if factor==1:snap('05-manual-model',w)
        w.sharped_toggle.setChecked(True);stable()
        assert w.sharped_toggle.arrowType()==Qt.DownArrow and w.sharped_body.isVisible()
        w.scroll_area.ensureWidgetVisible(w.api_token);settle(w)
        assert w.api_token.height()>=w.api_token.sizeHint().height()
        if factor==1:snap('06-advanced-settings',w)
        w.sharped_toggle.setChecked(False);stable()
        assert w.sharped_toggle.arrowType()==Qt.RightArrow
        if factor==1:snap('07-authentication-required',w)
        # Public discovery and the presence of an unverified key cannot imply Connected.
        w.api_token.setText('mock-key-not-a-real-credential')
        assert w.connection_status.text()=='SharpED account access'
        w.api_token.clear()
        # Removing the manual ID must not substitute an inference model.
        state['models'].remove(seed);w.refresh_models_button.click();pump();stable()
        assert w.model_user_picked['value'] and w.model.currentIndex()==-1 and w.model_policy_error
        assert 'Restore automatic' in w.model_status.text()
        w.cycles.setValue(1);assert w.model.currentIndex()==-1 and w.model_policy_error
        w.restore_automatic_model_button.click();stable()
        assert w.model.currentText()==peak and not w.model_user_picked['value'] and not w.model_policy_error
        assert w.model_status.text().endswith('models available')
        # Missing automatic policy cannot silently use the server default.
        state['models'].remove(peak);w.refresh_models_button.click();pump()
        assert w.model.currentIndex()==-1 and peak in w.model_policy_error
        state['models'][:]=[peak,seed,'Extra catalogue model'];w.refresh_models_button.click();pump()
        assert w.model.currentText()==peak and not w.model_policy_error
        state['fail']=True;w.refresh_models_button.click();pump();stable()
        assert 'unavailable' in w.model_status.text() and w.refresh_models_button.isEnabled()
        assert 'not been reverified' in w.model_status.toolTip()
        w.cycles.setValue(3);assert w.model_policy_error
        assert 'Connected' not in w.connection_status.text()
        state['fail']=False;w.refresh_models_button.click();pump();stable()
        assert w.model.currentText()==seed and not w.model_policy_error
        # Next/Back retains state and does not run authentication or inference.
        checks=[]
        w._ensure_workflow_requirements=lambda **kwargs:checks.append(kwargs) or False
        before_requests=state['calls'];w.primary_button.click();stable()
        assert w.stack.currentWidget() is w.page3 and not checks
        if factor==1:snap('08-map-feedback-after-next',w)
        w.primary_button.click();settle(w)
        assert checks==[{'needs_sharped':True}] and w.stack.currentWidget() is w.page3
        w.back_button.click();stable();assert w.stack.currentWidget() is w.page2
        assert state['calls']==before_requests and w.cycles.value()==3
        w.back_button.click();stable();assert w.stack.currentWidget() is w.page1
        w.superflip_sharped_tile._trigger();pump();stable();assert state['calls']==before_requests
        # Explicit user resize remains stable on navigation as well.
        w.dialog.resize(min(950,available.width()-20),min(720,available.height()-20));settle(w)
        initial=QRect(w.dialog.geometry());w.primary_button.click();stable();w.back_button.click();stable()
        w.cancel_button.click();assert w.result['action']=='cancel' and not w.dialog.isVisible()
        assert source.read_bytes()==original
        assert w.backing_window_holder['win'] is None

if capture:(OUT/('acceptance-dpi-'+str(factor)+'.json')).write_text(json.dumps(evidence,indent=2),encoding='utf8')
print('PASS configuration policy, missing/manual/automatic models, offline states, account truthfulness, navigation and geometry at DPR '+str(factor))
