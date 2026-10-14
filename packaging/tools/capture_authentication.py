"""Real Qt onboarding captures with fake keys, fake storage and mocked checks.
No authentication, user credentials, account sign-in or scientific jobs.
"""
import os,sys,json,time,threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.pop('SHARPED_API_TOKEN',None)
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QSettings,QCoreApplication,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication,QDialog,QLineEdit
from PySide6.QtTest import QTest
from phase_studio import requirements as req
from phase_studio.credentials import CredentialStore
from phase_studio.sharped_access import SharpEDAccessDialog
from phase_studio.ui_style import apply_phase_studio_style
from phase_studio import jana_superflip as js

app=QApplication([]);apply_phase_studio_style(app)
class FakeDeviceStore:
    def __init__(self):self.values={}
    def read(self,origin):return self.values.get(origin,'')
    def write(self,origin,key):self.values[origin]=key
    def delete(self,origin):self.values.pop(origin,None)

scale=os.environ.get('QT_SCALE_FACTOR','1')
out=ROOT/'docs/screenshots/2.0.3-authentication'/('scale-'+scale)
out.mkdir(parents=True,exist_ok=True)
work=ROOT/'build/authentication-capture'/('scale-'+scale);work.mkdir(parents=True,exist_ok=True)
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(work/'settings'))
js.SharpEDServerClient.get_models=lambda self:SimpleNamespace(models=['PEAK A (model prediction)','SEED (cyclic CF)','UNIVERSAL'],default_model='UNIVERSAL')
path=work/'onboarding-fixture.inflip'
path.write_text('title onboarding_fixture\nperform CF\noutputformat xplor\ndimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\ndataformat intensity\nfbegin\n1 0 0 10 2\nendf\n',encoding='utf8')
with patch.object(QDialog,'exec',lambda self:QDialog.Rejected):
    wizard=js._JanaWorkflowWizard([],path);wizard.run()
wizard.superflip_sharped_tile._trigger();wizard.cycles.setValue(3)
wizard._adjust_dialog_size=lambda:None
wizard.dialog.resize(900,820);wizard.dialog.show()
for _ in range(8):app.processEvents()
before=(wizard.inflip_path,wizard.cycles.value(),wizard.model.currentText(),wizard.workflow_state['key'])
store=CredentialStore(FakeDeviceStore())
status=lambda state:req.RequirementStatus(req.RequirementKind.SHARPED,state)
d=SharpEDAccessDialog(wizard.dialog,status(req.RequirementState.TOKEN_MISSING),store=store,verify=lambda key:status(req.RequirementState.OK))
# Model the supported 630-logical-pixel desktop dialog. Software scale changes
# device pixels; the separate geometry tests check the real available screen.
d.resize(630,650)

def capture(name,window=d):
    for _ in range(8):app.processEvents()
    if window is d:
        assert d.isModal()
        assert d._footer.geometry().bottom()<d.height()
        assert d.connect_button.geometry().right()<d._footer.width()
    image=window.grab();assert image.save(str(out/(name+'.png')))
    data=dict(mocked=True,backend='in-memory fixture',scale=float(scale),logical_size=window.size().toTuple(),device_pixel_ratio=image.devicePixelRatio())
    if window is d:
        data.update(key_hidden=d.key_edit.echoMode()==QLineEdit.Password,connecting=d._connecting,scroll_maximum=d._scroll.verticalScrollBar().maximum())
    (out/(name+'.json')).write_text(json.dumps(data,indent=2),encoding='utf8')

try:
    capture('01-missing-key')
    capture('02-first-connection-instructions')
    d.key_edit.setText('DEMO-ACCESS-KEY-NOT-A-CREDENTIAL');d._scroll.ensureWidgetVisible(d.key_edit)
    capture('03-hidden-key')
    d.show_button.setChecked(True);capture('04-visible-demo-key');d.show_button.setChecked(False)
    gate=threading.Event()
    d.verify=lambda key:(gate.wait(2),status(req.RequirementState.TOKEN_REJECTED))[1]
    d._connect_access();capture('05-connecting');gate.set()
    while d._connecting:QTest.qWait(10)
    capture('06-invalid-key')
    d.show_feedback(status(req.RequirementState.ACCESS_DENIED).message);capture('07-account-permission')
    d.show_feedback(status(req.RequirementState.SERVER_UNREACHABLE).message);capture('08-connection-failure')
    d.show_feedback(status(req.RequirementState.SERVER_UNAVAILABLE).message);capture('09-server-unavailable')
    d.feedback.setVisible(False);d._scroll.verticalScrollBar().setValue(0);capture('10-cancellation')
    d.back_button.click()
    assert d.selected_key is None
    assert before==(wizard.inflip_path,wizard.cycles.value(),wizard.model.currentText(),wizard.workflow_state['key'])
    capture('11-returned-to-preserved-wizard',wizard.dialog)
    d.show_button.setChecked(False)
finally:
    QThreadPool.globalInstance().waitForDone(3000)
    QTest.qWait(360)
    wizard.refresh_timer.stop();d.close();wizard.dialog.close()
    d.deleteLater();wizard.dialog.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    import shiboken6
    shiboken6.delete(app)
