"""Actual Qt update states at three DPIs; synthetic releases, no installation."""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def test_install_dialog_states_at_three_scales():
    for factor in ('1','1.25','1.5'):
        result=subprocess.run([sys.executable,__file__,'--child'],cwd=ROOT,
            env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':factor,'PHASE_STUDIO_STARTUP_PROBE':'1'},
            capture_output=True,text=True,timeout=60)
        assert result.returncode==0,factor+'\n'+result.stdout+result.stderr


def check():
    sys.path.insert(0,str(ROOT))
    import json,tempfile,threading,time
    from types import SimpleNamespace
    from unittest.mock import patch
    from PySide6.QtCore import QSettings,QRect,QTimer,Qt
    from PySide6.QtGui import QScreen,QTextDocument
    from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QDialog,QLabel
    from PySide6.QtTest import QTest
    from phase_studio.ui_style import apply_phase_studio_style
    from phase_studio.update_install_ui import UpdateInstallDialog
    from phase_studio.update_ui import UpdateNotice,install_application_header_menu
    from phase_studio.update_checker import Release
    from phase_studio.update_runtime import ReleaseOffer
    from phase_studio.update_manifest import UpdateVerificationError
    from phase_studio.ui_branding import create_phase_studio_brand_header
    from phase_studio.error_reporting import show_phase_studio_error
    qt=QApplication([]);apply_phase_studio_style(qt)
    scale=float(os.environ['QT_SCALE_FACTOR'])
    out=ROOT/'build/acceptance-updater'/f'scale-{scale}';out.mkdir(parents=True,exist_ok=True)
    release=Release((2,0,99),'https://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.99')
    facts={};dialogs=[]
    def settle():
        for _ in range(15):qt.processEvents()
    def wait(condition):
        deadline=time.monotonic()+8
        while not condition():
            QTest.qWait(10);settle();assert time.monotonic()<deadline
    def snap(name,widget):
        settle();assert widget.grab().save(str(out/(name+'.png')))
        facts[name]={'size':widget.size().toTuple(),'dpr':widget.devicePixelRatioF()}
    errors=[]
    def presenter(parent,report):errors.append(report)
    class Session:
        def __init__(self,version,jana=False):
            self.current=SimpleNamespace(profile='jana2020-onedir' if jana else 'standalone-onefile')
            self.stopped=False;self.events={name:threading.Event() for name in ('download','verify')}
            self.error=None
        def load_offer(self):
            return ReleaseOffer('2.0.99','2026-10-19T12:00:00Z',
                'Controlled acceptance release; not a public release.\n<b>These notes remain plain text.</b>',
                {'PhaseStudio-2.0.99-x64.exe':{'size':79*1048576},'PhaseStudio-Jana2020-2.0.99.zip':{'size':80*1048576}})
        def prepare(self,progress):
            if self.error:raise self.error
            progress('Downloading package',4*1048576,79*1048576);self.events['download'].wait(5)
            progress('Verifying release signature',0,0);self.events['verify'].wait(5)
            return self.load_offer()
        def launch_helper(self):return {'ready':True}
        def stop(self):
            self.stopped=True
            for event in self.events.values():event.set()
    with tempfile.TemporaryDirectory() as temporary,patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(1920/scale),int(1040/scale))):
        QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,temporary)
        owner=QWidget();layout=QVBoxLayout(owner);header=create_phase_studio_brand_header();layout.addWidget(header)
        menu=install_application_header_menu(header,owner,about=lambda:None,mode='standalone',automatic=False).menu_button
        owner.resize(650,170);owner.show();settle()
        menu.menu().popup(menu.mapToGlobal(menu.rect().bottomLeft()));snap('01-application-menu',menu.menu());menu.menu().hide()
        notice=UpdateNotice(owner);notice.show();snap('02-up-to-date',notice);notice.close()
        notice=UpdateNotice(owner,release=release)
        notice.show();assert not notice.update_button.isEnabled();assert notice.view_button.isEnabled()
        snap('03-public-installation-blocked',notice);notice.close()
        def make(jana=False):
            d=UpdateInstallDialog(owner,release,jana=jana,session_factory=Session,error_presenter=presenter)
            dialogs.append(d);d.show();wait(lambda:not d.busy and d.session is not None)
            return d
        d=make();assert d.package.text()=='Standalone application'
        assert '<b>' in d.notes.toPlainText()
        snap('04-standalone-offer',d)
        d.action.click();wait(lambda:d.status.text()=='Downloading package')
        assert d.progress.maximum()==1000 and 0<d.progress.value()<1000
        snap('05-downloading',d)
        d.session.events['download'].set();wait(lambda:d.status.text()=='Verifying release signature')
        assert d.progress.maximum()==0;snap('06-verifying',d)
        d.session.events['verify'].set();wait(lambda:d.phase=='prepared')
        assert d.action.text()=='Restart and install';snap('07-ready-to-restart',d)
        closed=[]
        with patch.object(QApplication,'closeAllWindows',lambda:closed.append(True)):
            d.action.click();wait(lambda:bool(closed))
        assert closed==[True]
        # The running scientific workflow is checked again after helper readiness.
        blocked=make();blocked.phase='prepared'
        with patch.object(blocked,'_scientific_work_running',side_effect=[False,True]),patch.object(QApplication,'closeAllWindows',lambda:closed.append(False)):
            blocked.action.click();wait(lambda:not blocked.busy)
        assert closed==[True] and blocked.session is None
        blocked.close()
        jana=make(True);assert jana.package.text()=='Jana2020 integration'
        snap('08-jana-offer',jana)
        jana.phase='prepared';jana.action.click();wait(lambda:jana.phase=='jana-ready')
        assert 'Cancel' in jana.status.text() and 'exit Jana2020' in jana.status.text()
        snap('09-jana-safe-reopen',jana);jana._cancel()
        for name,message in [('10-network-failure','GitHub release information is temporarily unavailable.'),
                ('11-signature-failure','Release signature verification failed.')]:
            failed=make();failed.session.error=UpdateVerificationError(message)
            failed.action.click();wait(lambda:not failed.busy)
            assert failed.phase=='offer' and failed.session is None
            snap(name,failed);failed.close()
        assert len(errors)>=3
        report=errors[-1]
        def capture_error():
            dialog=next(w for w in qt.topLevelWidgets() if w.objectName()=='phaseStudioErrorDialog')
            snap('12-standard-integrity-error',dialog);dialog.reject()
        QTimer.singleShot(0,capture_error)
        show_phase_studio_error(owner,report)
        # No normal action closes a busy scientific process, replaces its
        # candidate or invokes a scientific handoff callback.
        owner.close();settle()
    (out/'acceptance.json').write_text(json.dumps({'screenshots':facts,'synthetic_release':True,
        'installation_executed':False,'public_key_configured':False},indent=2),encoding='utf8')


if __name__=='__main__':check() if '--child' in sys.argv else test_install_dialog_states_at_three_scales()
