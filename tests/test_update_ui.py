"""Shared service, storage and both real launch UIs with mocked GitHub metadata."""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def test_update_service_and_launch_paths_at_three_scales():
    for scale in ('1','1.25','1.5'):
        result=subprocess.run([sys.executable,__file__,'--child'],cwd=ROOT,
            env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},
            capture_output=True,text=True,timeout=70)
        assert result.returncode==0,scale+'\n'+result.stdout+result.stderr


def check():
    import tempfile
    import threading
    import time
    from unittest.mock import patch, Mock
    sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
    from PySide6.QtCore import QSettings,Qt,QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QDialog,QLabel
    from phase_studio import update_ui as ui
    from phase_studio.update_checker import Release,CHECK_INTERVAL
    from phase_studio import app as a
    qt=QApplication([]);a.apply_phase_studio_style(qt)
    now=[1_800_000_000.]
    calls=[];thread_ids=[];opens=[]
    from phase_studio.version import VERSION
    parts=tuple(map(int,VERSION.split('.')))
    future=parts[:2]+(parts[2]+1,)
    future_label='.'.join(map(str,future))
    latest=[Release(future)]
    def fetch():
        calls.append(True);thread_ids.append(threading.get_ident())
        return latest[0]
    def settle(service=None):
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            qt.processEvents();time.sleep(.002)
            if service is None or not service.busy: break
        assert service is None or not service.busy
        for _ in range(12):qt.processEvents()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
        settings=QSettings(str(root/'updates.ini'),QSettings.IniFormat)
        settings.setValue('inputs/sentinel','unchanged')
        def state():return ui.UpdateState(QSettings(str(root/'updates.ini'),QSettings.IniFormat),root/'updates.lock')
        store=state()
        assert store.enabled()
        assert store.claim_check(now[0])
        store.cache(Release(future),now[0])
        assert not state().claim_check(now[0])
        assert not state().claim_check(now[0]+CHECK_INTERVAL-1)
        assert state().claim_check(now[0]+CHECK_INTERVAL)
        store.cache(Release(future),now[0])
        assert state().cached(now[0]).version==future
        assert state().cached(now[0]+CHECK_INTERVAL) is None
        assert store.claim_notification(Release(future))
        assert not state().claim_notification(Release(future))
        read_only=Mock(wraps=settings)
        read_only.status.return_value=QSettings.AccessError
        assert not ui.UpdateState(read_only,root/'read-only.lock').claim_check(now[0]+2*CHECK_INTERVAL)
        assert state().claim_notification(Release((2,1,0)))
        assert not state().claim_notification(Release(future))
        settings.remove('updates');settings.sync()
        service=ui.UpdateService(qt,state=state(),fetcher=fetch,clock=lambda:now[0],automatic_allowed=True,browser=lambda url:opens.append(url.toString()))
        qt._phase_studio_updates=service
        assert ui.update_service() is service
        quiet_parent=QDialog();quiet_parent.show()
        for version in ((2,0,3),(2,0,4),parts,(1,99,99)):
            key='-'.join(map(str,version))
            quiet=ui.UpdateService(qt,state=ui.UpdateState(QSettings(str(root/(key+'.ini')),QSettings.IniFormat),root/(key+'.lock')),
                fetcher=lambda v=version:Release(v),clock=lambda:now[0],automatic_allowed=True)
            quiet.check(quiet_parent);settle(quiet)
            assert quiet.notice is None
        quiet_parent.close()
        parent=QDialog();parent.setWindowTitle('Controlled fixture parent');parent.show();settle()
        other=QDialog();other.show();settle()
        service.attach(parent,automatic=False);service.attach(other,mode='jana',automatic=False)
        version_button = ui.wizard_update_menu(parent, automatic=False)
        assert not version_button.update_available
        service.check(parent);settle(service)
        assert version_button.update_available
        assert calls and all(t!=threading.get_ident() for t in thread_ids)
        dialog=service.notice
        assert dialog and future_label in dialog.message.text()
        assert not dialog.isModal() and dialog.testAttribute(Qt.WA_ShowWithoutActivating)
        assert opens==[]
        assert dialog.rect().contains(dialog.later_button.geometry())
        assert dialog.rect().contains(dialog.view_button.geometry())
        dialog.later_button.click();settle()
        assert service.notice is None
        service.check(other,mode='jana');settle(service)
        assert service.notice is None and len(calls)==1
        # A separate service/process shares both persisted interval and dismissal.
        second=ui.UpdateService(qt,state=state(),fetcher=fetch,clock=lambda:now[0],automatic_allowed=True)
        second.check(other,mode='jana');settle(second)
        assert second.notice is None and len(calls)==1
        # Manual checking bypasses automatic opt-out and prior dismissal.
        service.set_enabled(False)
        service.check(parent);settle(service);assert len(calls)==1
        service.check(parent,manual=True);settle(service)
        assert service.notice is not None
        service.notice.view_button.click();settle()
        assert opens==['https://github.com/ji-ze/Phase-Studio/releases']
        latest[0]=Release((2,0,3));service.check(parent,manual=True);settle(service)
        assert not version_button.update_available
        assert service.notice.title.text()=='Phase Studio is up to date' and VERSION in service.notice.message.text()
        latest[0]=Release(future);service.check(parent,manual=True);settle(service)
        assert service.notice.release.version==future
        service.notice.close();settle()
        # Manual failures are generic, automatic failures stay silent and throttled.
        latest[0]=None;service.check(parent,manual=True);settle(service)
        assert not version_button.update_available
        assert service.notice.message.text()=='Check your internet connection and try again.'
        service.notice.close();settle();service.set_enabled(True)
        now[0]+=CHECK_INTERVAL;before=len(calls)
        service.check(parent);settle(service);assert service.notice is None and len(calls)==before+1
        service.check(other);settle(service);assert len(calls)==before+1
        # Slow background requests do not prevent Qt events or duplicate requests.
        gate=threading.Event();ticks=[]
        def slow():gate.wait(3);return Release((2,1,0))
        service.fetcher=slow;now[0]+=CHECK_INTERVAL
        start=time.monotonic();service.check(parent)
        assert time.monotonic()-start<.2
        QTimer.singleShot(0,lambda:ticks.append(True));qt.processEvents();assert ticks
        service.check(other,mode='jana',manual=True)
        gate.set();settle(service)
        assert any('Jana2020 software release' in label.text() for label in service.notice.findChildren(QLabel))
        service.notice.close();settle()
        # Closed/destroyed request owners cannot produce an orphan popup.
        gate.clear();service.check(parent,manual=True);parent.close();parent.deleteLater();qt.processEvents();gate.set();settle(service)
        assert service.notice is None
        assert settings.value('inputs/sentinel')=='unchanged'
        # Real standalone startup attaches only after the normal window opens.
        service.fetcher=fetch;service.automatic_allowed=False
        with patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None):
            class Splash:
                def set_status(self,*args):pass
                def finish(self,window):assert window.isVisible()
                def close(self):pass
            win=a.initialize_main_window(qt,Splash())
            assert win.isVisible() and win.update_check_button.text()=='Check for updates'
            assert any(ref() is win for ref,_ in service._windows)
            win._phase_studio_distribution='jana'
            assert service.mode(win,None)=='jana'
            win._phase_studio_distribution='standalone'
            latest[0]=Release(future);win.update_check_button.click();settle(service)
            assert service.notice is not None
            service.notice.close();win.timer.stop();win.close();settle()
        # Real Wizard header uses the same service and supplies Jana distribution context.
        import phase_studio.jana_superflip as js
        from test_wizard_text_clipping import write_inflip
        jana=root/'Jana';(jana/'SUPERFLIP').mkdir(parents=True)
        for binary in ('superflip.exe','EDMA.exe'):(jana/'SUPERFLIP'/binary).write_bytes(b'fixture')
        inflip=write_inflip(root)
        with patch.object(js,'application_dir',lambda:jana),patch.object(QDialog,'exec',lambda self:QDialog.Rejected):
            wizard=js._JanaWorkflowWizard([],inflip);wizard.run();wizard.dialog.show();settle()
            assert wizard.brand_header.isAncestorOf(wizard.update_menu)
            assert not wizard.footer.isAncestorOf(wizard.update_menu)
            actions=wizard.update_menu.menu().actions()
            assert actions[0].text()=='Check for updates'
            assert actions[-1].text()=='About Phase Studio'
            assert 'Updates and application information' in wizard.update_menu.toolTip()
            assert any(ref() is wizard.dialog and mode=='jana' for ref,mode in service._windows)
            actions[0].trigger();settle(service)
            assert any('Jana2020 software release' in label.text() for label in service.notice.findChildren(QLabel))
            assert service.notice.rect().contains(service.notice.view_button.geometry())
            assert service.notice.rect().contains(service.notice.later_button.geometry())
            assert ui.update_service() is service
            service.notice.close();wizard.dialog.close();settle()
        other.close()
    print('Update state, cross-window claims, async delivery, both actual launch paths and explicit browser action passed.')


if __name__=='__main__':check() if '--child' in sys.argv else test_update_service_and_launch_paths_at_three_scales()
