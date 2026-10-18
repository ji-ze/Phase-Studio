"""Actual Qt layout/update acceptance. All metadata and accounts are offline fixtures."""
import os,sys,tempfile,time,threading,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen');os.environ['PHASE_STUDIO_STARTUP_PROBE']='1'
os.environ.pop('SHARPED_API_TOKEN',None)
from PySide6.QtCore import QSettings,QRect,QPoint,QTimer,Qt
from PySide6.QtWidgets import QApplication,QDialog,QLabel
from PySide6.QtTest import QTest
from PySide6.QtGui import QScreen
from phase_studio import jana_superflip as js,update_ui as ui
from phase_studio.update_checker import Release,CheckResult,VERSION,CHECK_INTERVAL,RETRY_INTERVAL,RELEASES_URL
from phase_studio.credentials import CredentialStore
from phase_studio.ui_style import apply_phase_studio_style
from test_wizard_text_clipping import write_inflip
OUT=ROOT/'build/acceptance-wizard-updates-2.0.5';OUT.mkdir(parents=True,exist_ok=True)
capture='--capture' in sys.argv;scale=float(os.environ.get('QT_SCALE_FACTOR','1'))
available=QRect(0,0,int(1920/scale),int(1040/scale))
qt=QApplication([]);apply_phase_studio_style(qt);records={}
def settle(service=None):
    until=time.monotonic()+4
    while True:
        qt.processEvents()
        if service is None or not service.busy:break
        assert time.monotonic()<until
        QTest.qWait(5)
    for _ in range(40):qt.processEvents()
def snap(name,widget,**extra):
    settle()
    records[name]=dict(rect=widget.geometry().getRect(),frame=widget.frameGeometry().getRect(),dpr=widget.devicePixelRatioF(),**extra)
    if capture:assert widget.grab().save(str(OUT/(name+'.png')))
with tempfile.TemporaryDirectory() as tmp,patch.object(QScreen,'availableGeometry',return_value=available):
    base=Path(tmp);source=write_inflip(base);original=source.read_bytes()
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
    settings=QSettings(str(base/'updates.ini'),QSettings.IniFormat)
    settings.setValue('inputs/sentinel','retained')
    def state():return ui.UpdateState(QSettings(str(base/'updates.ini'),QSettings.IniFormat),base/'updates.lock')
    now=[1_800_000_000.]
    installed=tuple(map(int,VERSION.split('.')));future=installed[:2]+(installed[2]+1,)
    next_release=Release(future,'https://github.com/ji-ze/Phase-Studio/releases/tag/v'+'.'.join(map(str,future)))
    store=state();store.set_enabled(False);assert not state().enabled()
    assert not state().claim_check(now[0]);assert state().claim_check(now[0],manual=True)
    store.set_enabled(True);store.cache(next_release,now[0])
    assert not state().claim_check(now[0]+CHECK_INTERVAL-1)
    assert state().claim_check(now[0]+CHECK_INTERVAL)
    assert state().cached(now[0]).url==next_release.url
    settings.remove('updates');settings.sync()
    assert store.claim_check(now[0]);store.failed(now[0])
    assert store.timestamp('lastSuccess')==0 and not state().claim_check(now[0]+1)
    assert state().claim_check(now[0]+RETRY_INTERVAL)
    store.failed(now[0]+RETRY_INTERVAL,3600)
    assert not state().claim_check(now[0]+RETRY_INTERVAL+3599)
    assert state().claim_check(now[0]+RETRY_INTERVAL+3600)
    settings.remove('updates');settings.sync()
    response=[Release(installed)];calls=[];threads=[];opened=[];gate=[None]
    def fetch():
        calls.append(True);threads.append(threading.get_ident())
        if gate[0] is not None:gate[0].wait(3)
        return response[0]
    service=ui.UpdateService(qt,state=state(),fetcher=fetch,clock=lambda:now[0],automatic_allowed=False,browser=lambda url:opened.append(url.toString()))
    qt._phase_studio_updates=service
    imports=js._qt_imports
    factory=lambda org,name:QSettings(str(base/(name+'.ini')),QSettings.IniFormat)
    jana=base/'Jana';(jana/'SUPERFLIP').mkdir(parents=True)
    for name in ('superflip.exe','EDMA.exe'):(jana/'SUPERFLIP'/name).write_bytes(b'never executed')
    with patch.object(js,'_qt_imports',lambda:imports()|{'QSettings':factory}),patch.object(js,'credential_store',CredentialStore(backend=None)),patch.object(QDialog,'exec',lambda self:QDialog.Rejected),patch.object(js,'application_dir',lambda:jana),patch.object(js.SharpEDServerClient,'get_models',lambda self:SimpleNamespace(models=[js.SHARPED_ONE_CYCLE_MODEL,js.SHARPED_ITERATIVE_MODEL],default_model=js.SHARPED_ONE_CYCLE_MODEL)):
        def build():
            w=js._JanaWorkflowWizard([],source);w.run();w.dialog.show();settle();return w
        w=build();initial=QRect(w.dialog.geometry())
        def accessible():
            settle();w._size_stack_to_current_page(w.dialog.width());settle()
            assert available.contains(QRect(w.cancel_button.mapToGlobal(QPoint()),w.cancel_button.size()))
            assert w.scroll_area.horizontalScrollBar().maximum()==0
            w.scroll_area.verticalScrollBar().setValue(w.scroll_area.verticalScrollBar().maximum());settle()
            for tile in (w.autosolve_tile,w.professional_mode_tile):
                point=tile.mapTo(w.scroll_area.viewport(),tile.rect().bottomRight())
                assert w.scroll_area.viewport().rect().contains(point),(point,w.scroll_area.viewport().rect())
                for label in (tile.title_label,tile.subtitle_label,tile.runtime_label):
                    if label.isVisible():assert label.height()>=label.heightForWidth(label.width())
            w.scroll_area.verticalScrollBar().setValue(0);settle()
        accessible()
        if scale==1:snap('01-initial-normal',w.dialog,breakpoint=w.summary_wide_minimum_width)
        if scale==1.25:snap('04-initial-dpi-125',w.dialog)
        if scale==1.5:
            w.scroll_area.verticalScrollBar().setValue(w.scroll_area.verticalScrollBar().maximum());settle()
            snap('05-initial-dpi-150',w.dialog,scroll_position=w.scroll_area.verticalScrollBar().value(),
                 fixture='Constrained work area: content scrolled to expose both complete secondary cards')
            w.scroll_area.verticalScrollBar().setValue(0);settle()
        # Both reported logical sizes, then a genuinely reduced desktop area.
        for width,height in ((950,990),(790,825),(790,640)):
            w.dialog.resize(min(width,available.width()-8),min(height,available.height()-8))
            from phase_studio.ui_branding import clamp_window_to_available_screen
            clamp_window_to_available_screen(w.dialog)
            settle();accessible()
            if scale==1 and height==825:snap('02-initial-reduced',w.dialog,breakpoint=w.summary_wide_minimum_width)
        w.files_toggle.click();settle();accessible()
        if scale==1:snap('03-advanced-input-expanded',w.dialog)
        w.files_toggle.click();settle()
        current=QRect(w.dialog.geometry());w.superflip_sharped_tile._trigger();settle()
        assert w.dialog.geometry()==current
        w.primary_button.click();settle();assert w.dialog.geometry()==current and w.stack.currentWidget() is w.page3
        w.back_button.click();w.back_button.click();settle();assert w.dialog.geometry()==current
        w.dialog.setGeometry(initial);settle()
        assert w.brand_header.isAncestorOf(w.update_menu)
        menu=w.update_menu.menu();w.update_menu.setFocus();menu.popup(w.update_menu.mapToGlobal(QPoint(0,w.update_menu.height())));settle()
        assert available.contains(menu.frameGeometry())
        assert abs(menu.geometry().right()-w.update_menu.mapToGlobal(QPoint(w.update_menu.width(),0)).x())<menu.width()
        if scale==1:snap('07-version-menu',menu,fixture='Actual native Qt popup; placement recorded relative to Wizard')
        QTest.keyClick(menu,Qt.Key_Down);assert menu.activeAction() is not None
        QTest.keyClick(menu,Qt.Key_Escape);settle();assert not menu.isVisible()
        assert w.update_menu.hasFocus()
        from phase_studio.ui_branding import clamp_window_to_available_screen
        for area in (available,QRect(-1280,0,1280,800)):
            with patch.object(QScreen,'availableGeometry',return_value=area):
                w.dialog.move(area.right()-w.dialog.width()+1,area.top())
                clamp_window_to_available_screen(w.dialog);settle()
                menu.popup(w.update_menu.mapToGlobal(QPoint(0,w.update_menu.height())));settle()
                assert area.contains(menu.frameGeometry())
                menu.close();settle()
        w.dialog.setGeometry(initial);settle()
        action=next(action for action in menu.actions() if action.text()=='Check for updates')
        # Manual async request: visible busy text and GUI events, no duplicate worker.
        preference=next(action for action in menu.actions() if action.isCheckable())
        preference.trigger();assert not state().enabled() and not preference.isChecked()
        gate[0]=threading.Event();ticks=[];action.trigger();settle()
        assert service.busy and not action.isEnabled() and action.text()=='Checking for updates…'
        before=len(calls);service.check(w.dialog,manual=True)
        QTimer.singleShot(0,lambda:ticks.append(True));qt.processEvents();assert ticks
        gate[0].set();settle(service);gate[0]=None
        assert len(calls)==before and all(t!=threading.get_ident() for t in threads)
        assert service.notice.title.text()=='Phase Studio is up to date'
        def notice_capture(name):
            if capture:
                label=QLabel('CONTROLLED MOCK GITHUB METADATA — NOT A LIVE RELEASE CHECK')
                label.setWordWrap(True);service.notice.layout().insertWidget(0,label);service.notice._fit()
            snap(name,service.notice,mocked=True)
        if scale==1:notice_capture('08-manual-up-to-date-mock')
        service.notice.close();settle()
        response[0]=next_release;action.trigger();settle(service)
        assert service.notice.release==next_release and not service.notice.isModal()
        if scale==1:notice_capture('09-new-release-mock')
        service.notice.view_button.click();settle();assert opened==[next_release.url]
        service.set_enabled(True)
        service._offer(w.dialog,'jana',next_release);settle();assert service.notice is None
        response[0]=CheckResult(error='network',detail='TimeoutError');action.trigger();settle(service)
        assert service.notice.title.text()=='Unable to check for updates'
        if scale==1:notice_capture('10-update-failure-mock')
        service.notice.close();settle()
        assert settings.value('inputs/sentinel')=='retained'
        assert 'network TimeoutError' in (base/'updates.log').read_text(encoding='utf8')
        # Restore geometry from another monitor and verify parent-based placement.
        factory('PhaseStudio','JanaSuperflipWrapper').setValue('wizard/windowRect',QRect(5000,5000,1800,1400))
        restored=build();settle();assert available.contains(restored.dialog.frameGeometry())
        restored.dialog.close();settle()
        wrapper=factory('PhaseStudio','JanaSuperflipWrapper');wrapper.remove('wizard/windowRect');wrapper.remove('wizard/windowGeometry');wrapper.sync()
        parent=QDialog();parent.setWindowTitle('Jana2020 — controlled Qt fixture')
        parent.setGeometry(available.adjusted(100,60,-100,-60));parent.show();parent.activateWindow();settle()
        launched=build();settle();assert launched.jana_parent_rect is not None
        assert available.contains(launched.dialog.frameGeometry())
        assert (launched.dialog.frameGeometry().center()-parent.frameGeometry().center()).manhattanLength()<8
        if scale==1:snap('06-jana-parent-fixture',launched.dialog,fixture='Controlled Qt Jana2020-style parent, not real Jana2020')
        launched.dialog.close();parent.close();w.dialog.close();settle()
        # A genuinely smaller work area, rather than only a resized window.
        small_area=QRect(0,0,790,825)
        wrapper.remove('wizard/windowRect');wrapper.remove('wizard/windowGeometry');wrapper.sync()
        with patch.object(QScreen,'availableGeometry',return_value=small_area):
            small=build();settle()
            assert small_area.contains(small.dialog.frameGeometry())
            assert small_area.contains(QRect(small.cancel_button.mapToGlobal(QPoint()),small.cancel_button.size()))
            small.scroll_area.verticalScrollBar().setValue(small.scroll_area.verticalScrollBar().maximum());settle()
            for tile in (small.autosolve_tile,small.professional_mode_tile):
                assert small.scroll_area.viewport().rect().contains(tile.mapTo(small.scroll_area.viewport(),tile.rect().bottomRight()))
            # Exercise the measured breakpoint at the component level.
            small.input_summary_section.setFixedWidth(small.summary_wide_minimum_width-1);settle()
            assert small.input_summary_outer.direction().name=='TopToBottom'
            small.dialog.close()
        assert source.read_bytes()==original
if capture:(OUT/('geometry-dpi-'+str(scale)+'.json')).write_text(json.dumps(records,indent=2),encoding='utf8')
print('PASS Wizard layout, menu, async updates, safe links, persistence/backoff and Jana-style geometry at DPR '+str(scale))
