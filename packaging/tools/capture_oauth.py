"""Actual Qt OAuth UI with a local mock provider, labelled fixture evidence."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from PySide6.QtCore import QSettings,QCoreApplication,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtTest import QTest
from phase_studio import jana_superflip as js
from phase_studio.credentials import CredentialStore
from phase_studio.oauth import OAuthAttempt,OAuthCredential
from phase_studio.oauth_ui import OAuthWorker
from phase_studio.sharped_access import SharpEDAccessDialog
from phase_studio.ui_style import apply_phase_studio_style
from test_oauth import Provider
from types import SimpleNamespace

scale=os.environ.get("QT_SCALE_FACTOR","1")
out=ROOT/"docs/screenshots/2.0.4-oauth"/("scale-"+scale);out.mkdir(parents=True,exist_ok=True)
work=ROOT/"build/oauth-capture"/("scale-"+scale);work.mkdir(parents=True,exist_ok=True)
QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(work/"settings"))
app=QApplication([]);apply_phase_studio_style(app)
js.SharpEDServerClient.get_models=lambda self:SimpleNamespace(models=["SEED (cyclic CF)","PEAK A (model prediction)"],default_model="PEAK A (model prediction)")
source=work/"onboarding-fixture.inflip"
source.write_text("title fixture\nperform CF\noutputformat xplor\ndimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\ndataformat intensity\nfbegin\n1 0 0 10 2\nendf\n",encoding="utf8")
with patch.object(QDialog,"exec",lambda self:QDialog.Rejected):
    wizard=js._JanaWorkflowWizard([],source);wizard.run()
wizard.superflip_sharped_tile._trigger();wizard.cycles.setValue(3);wizard.dialog.show()
before=(wizard.inflip_path,wizard.cycles.value(),wizard.model.currentText(),wizard.workflow_state["key"])
store=CredentialStore();provider=Provider();urls=[];dialogs=[]
def settle():
    for _ in range(8):app.processEvents()
def capture(name,window):
    settle();pix=window.grab();assert pix.save(str(out/(name+".png")))
    (out/(name+".json")).write_text(json.dumps(dict(mocked=True,provider="local mock OAuth",scale=float(scale),size=window.size().toTuple(),dpr=pix.devicePixelRatio()),indent=2))
def wait(check):
    end=time.monotonic()+4
    while not check() and time.monotonic()<end:QTest.qWait(10)
    assert check()
def dialog():
    d=SharpEDAccessDialog(wizard.dialog,store=store);dialogs.append(d);d.show();settle();return d
try:
    with patch("phase_studio.oauth_ui.OAuthWorker",side_effect=lambda:OAuthWorker(OAuthAttempt(provider))),patch("phase_studio.sharped_access.QDesktopServices.openUrl",side_effect=lambda u:(urls.append(u.toString()) or True)):
        d=dialog();capture("01-sign-in",d)
        d.sign_in_button.click();wait(lambda:bool(urls));capture("02-browser-waiting",d)
        gate=threading.Event();entered=threading.Event();original=provider.json
        def gated(url,form=None):
            if form is not None:entered.set();gate.wait(3)
            return original(url,form)
        provider.json=gated
        with urlopen(provider.base+"/oauth/authorize?"+urlsplit(urls[-1]).query) as r:code=json.load(r)
        callback=d._oauth_worker.attempt.redirect_uri
        def finish():
            with urlopen(callback+"?"+urlencode(code),timeout=4) as r:r.read()
        thread=threading.Thread(target=finish);thread.start();wait(entered.is_set);QTest.qWait(40)
        capture("03-exchange",d)
        accepted=d.accept
        d.accept=lambda:(capture("04-authorization-completed",d),accepted())
        gate.set();wait(lambda:d.result()==QDialog.Accepted);thread.join(4)
        provider.json=original
        d2=dialog();d2.show_feedback("Sign-in cancelled.");capture("05-cancelled",d2);d2.close()
        store.activate_oauth(OAuthCredential("MOCK-EXPIRED-NOT-A-CREDENTIAL",0))
        d3=dialog();capture("06-expired",d3);d3.close()
        d4=dialog();d4.show_feedback("Your Jana2020 account does not currently have permission to use SharpED processing.")
        capture("07-access-not-permitted-mocked",d4)
        d4.manual_button.setChecked(True);settle();d4._scroll.ensureWidgetVisible(d4.key_edit)
        capture("08-manual-fallback",d4);d4.close()
        assert before==(wizard.inflip_path,wizard.cycles.value(),wizard.model.currentText(),wizard.workflow_state["key"])
        capture("09-preserved-jana-wizard",wizard.dialog)
finally:
    for d in dialogs:d.close()
    QThreadPool.globalInstance().waitForDone(4000)
    provider.close();wizard.refresh_timer.stop();wizard.dialog.close()
    for d in dialogs:d.deleteLater()
    wizard.dialog.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    import shiboken6
    shiboken6.delete(app)
