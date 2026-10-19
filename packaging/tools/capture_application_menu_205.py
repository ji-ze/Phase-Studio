"""Actual Qt menu acceptance; all release/account responses are offline fixtures."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch, Mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['PHASE_STUDIO_STARTUP_PROBE'] = '1'
os.environ.pop('SHARPED_API_TOKEN', None)
from PySide6.QtCore import QSettings, QRect, Qt, QTimer, QPoint
from PySide6.QtGui import QScreen, QPainter
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QToolButton, QMessageBox
from PySide6.QtTest import QTest
from phase_studio import jana_superflip as js, update_ui as ui, app as engine
from phase_studio.credentials import CredentialStore
from phase_studio.update_checker import Release, CheckResult, CHECK_INTERVAL
from phase_studio.version import VERSION
from phase_studio.ui_branding import create_phase_studio_brand_header
from test_wizard_text_clipping import write_inflip

scale = float(os.environ.get('QT_SCALE_FACTOR', '1'))
out = ROOT/'build/acceptance-application-menu-2.0.5'/f'scale-{scale}'
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
engine.apply_phase_studio_style(app)
area = QRect(0, 0, int(1920/scale), int(1040/scale))
records = {}


def settle(service=None):
    deadline = time.monotonic()+5
    while True:
        for _ in range(15): app.processEvents()
        if service is None or not service.busy: break
        assert time.monotonic() < deadline
        QTest.qWait(5)


def capture(name, widget, region=None, popup=None):
    settle()
    pixels = widget.grab(region) if region is not None else widget.grab()
    if popup is not None:
        # Offscreen platforms cannot grab the desktop. Preserve actual Qt
        # pixels and live placement; retain a separate uncomposed popup grab.
        painter = QPainter(pixels)
        painter.drawPixmap(popup.mapToGlobal(QPoint())-widget.mapToGlobal(QPoint()),popup.grab())
        painter.end()
    assert pixels.save(str(out/(name+'.png')))
    records[name] = dict(rect=widget.geometry().getRect(), dpr=widget.devicePixelRatioF(),
        fixture='Controlled offline release metadata; no actual newer GitHub release is asserted')
    if popup is not None:
        records[name].update(popup=popup.geometry().getRect(),
            composition='Actual dialog and popup Qt grabs at their live global positions; not a native desktop capture')


with tempfile.TemporaryDirectory() as temporary, patch.object(QScreen, 'availableGeometry', return_value=area):
    base = Path(temporary)
    factory = lambda org, name: QSettings(str(base/(name+'.ini')), QSettings.IniFormat)
    state = ui.UpdateState(factory('PhaseStudio', 'updates'), base/'updates.lock')
    state.set_enabled(False)
    parts = tuple(map(int, VERSION.split('.')))
    future = Release(parts[:2]+(parts[2]+1,))
    response = [Release(parts)]
    now = [1800000000.]
    service = ui.UpdateService(app, state=state, fetcher=lambda: response[0], clock=lambda: now[0], automatic_allowed=False)
    app._phase_studio_updates = service
    source = write_inflip(base)
    original = source.read_bytes()
    jana = base/'Jana'
    (jana/'SUPERFLIP').mkdir(parents=True)
    for name in ('superflip.exe', 'EDMA.exe'):
        (jana/'SUPERFLIP'/name).write_bytes(b'Offline fixture never executed')
    imports = js._qt_imports
    with patch.object(js, '_qt_imports', lambda: imports()|{'QSettings':factory}), \
            patch.object(js, 'credential_store', CredentialStore(backend=None)), \
            patch.object(js, 'application_dir', lambda: jana), \
            patch.object(QDialog, 'exec', lambda self: QDialog.Rejected), \
            patch.object(js.SharpEDServerClient, 'get_models', lambda self: SimpleNamespace(
                models=[js.SHARPED_ONE_CYCLE_MODEL,js.SHARPED_ITERATIVE_MODEL], default_model=js.SHARPED_ITERATIVE_MODEL)):
        w = js._JanaWorkflowWizard([], source)
        w.run();w.dialog.show();settle()
        initial = QRect(w.dialog.geometry())
        button, label = w.update_menu, w.header_controls.version_label
        assert isinstance(button, QToolButton) and isinstance(label, QLabel)
        assert label.text() == 'v'+VERSION and button.text() == ''
        assert label.focusPolicy() == Qt.NoFocus and label.textInteractionFlags() == Qt.NoTextInteraction
        assert 'Science Gothic' not in label.font().family()
        assert button.accessibleName() == 'Phase Studio menu'
        assert 'Updates and application information' in button.toolTip()
        assert button.iconSize().toTuple() == (16,16) and button.size().toTuple() == (30,30)
        assert not button.icon().isNull() and button.arrowType() == Qt.NoArrow
        assert w.header_controls.layout().spacing() == 8
        assert abs(label.mapToGlobal(label.rect().center()).y()-button.mapToGlobal(button.rect().center()).y()) <= 1
        title = w.brand_header.findChild(QLabel,'brandTitle')
        assert abs(title.mapToGlobal(title.rect().center()).y()-button.mapToGlobal(button.rect().center()).y()) <= 1
        assert 'menu-indicator' in button.styleSheet()
        assert not button.update_available
        tree = ET.parse(ROOT/'phase_studio/assets/application_menu.svg')
        circles = tree.findall('.//{*}circle')
        assert len(circles) == 3 and all(c.attrib['cy']=='8' for c in circles)
        capture('01-workflow-closed',w.dialog)
        control_area = QRect(w.header_controls.mapTo(w.brand_header,QPoint()),w.header_controls.size())
        capture('08-control-close-up',w.brand_header,control_area.adjusted(-8,-4,8,4))
        menu = button.menu()
        QTest.mouseClick(label, Qt.LeftButton)
        assert not menu.isVisible() and w.stack.currentWidget() is w.page1
        assert [a.text() for a in menu.actions() if not a.isSeparator()] == [
            'Check for updates','Notify me when new versions are available','About Phase Studio']
        for key in (Qt.Key_Return,Qt.Key_Enter,Qt.Key_Space):
            observed=[]
            def close_menu():
                observed.append(menu.isVisible())
                assert area.contains(menu.frameGeometry())
                QTest.keyClick(menu,Qt.Key_Down)
                assert menu.activeAction() is not None
                QTest.keyClick(menu,Qt.Key_Escape)
            button.setFocus();QTimer.singleShot(40,close_menu);QTest.keyClick(button,key)
            settle();assert observed==[True] and not menu.isVisible()
        # Mouse clicks throughout the hit area open the same single popup.
        for point in (QPoint(2,2),button.rect().center(),button.rect().bottomRight()-QPoint(2,2)):
            observed=[]
            def close_clicked_menu():
                observed.append(menu.isVisible());menu.close()
            QTimer.singleShot(40,close_clicked_menu);QTest.mouseClick(button,Qt.LeftButton,pos=point)
            assert observed==[True]
        for available in (area,QRect(-1280,0,1280,800)):
            with patch.object(QScreen,'availableGeometry',return_value=available):
                w.dialog.move(available.right()-w.dialog.width(),available.top())
                menu.popup(button.mapToGlobal(QPoint(0,button.height())));settle()
                assert available.contains(menu.frameGeometry())
                capture('02-native-menu-popup',menu)
                capture('02-workflow-menu-open',w.dialog,popup=menu)
                menu.close()
        w.dialog.setGeometry(initial);settle()
        preference = next(a for a in menu.actions() if a.isCheckable())
        assert not preference.isChecked()
        preference.trigger();assert state.enabled()
        persisted = ui.UpdateState(factory('PhaseStudio','updates'),base/'updates.lock')
        assert persisted.enabled()
        preference.trigger();assert not persisted.enabled()
        # Only fresh successful checks may light the dot; opening does not clear it.
        service.known_release = future
        temporary_button = ui.wizard_update_menu(w.dialog,automatic=False)
        assert not temporary_button.update_available
        temporary_button.deleteLater();service.known_release=None
        response[0]=future;service.check(w.dialog,manual=True);settle(service)
        assert button.update_available and label.text()=='v'+VERSION
        service.notice.close();settle()
        menu.popup(button.mapToGlobal(QPoint(0,button.height())));settle();menu.close()
        assert button.update_available
        capture('03-verified-newer-release-fixture',w.dialog)
        now[0]+=CHECK_INTERVAL;button.show_release(future);assert not button.update_available
        for reply in (CheckResult(error='network',detail='TimeoutError'),Release(parts)):
            response[0]=reply;service.check(w.dialog,manual=True);settle(service)
            assert not button.update_available
            service.notice.close();settle()
        for tile in (w.original_superflip_tile,w.superflip_sharped_tile,w.autosolve_tile):
            tile._trigger();settle()
            while w.model_cache['inflight']:
                w.refresh_timer.timeout.emit();settle()
            assert w.dialog.geometry()==initial and w.update_menu is button
            assert w.scroll_area.horizontalScrollBar().maximum()==0
            if tile is w.superflip_sharped_tile:
                capture('04-configuration',w.dialog)
                w.primary_button.click();settle();capture('05-map-feedback',w.dialog)
                assert w.dialog.geometry()==initial
                w.back_button.click();settle()
            while w.stack.currentWidget() is not w.page1:
                w.back_button.click();settle()
        # Inspect the actual existing modal About, then dismiss its nested loop.
        def inspect_about():
            dialog=app.activeModalWidget()
            assert isinstance(dialog,QMessageBox) and dialog.parentWidget() is w.dialog
            assert VERSION in dialog.text() and dialog.isVisible()
            capture('09-about-dialog',dialog);dialog.accept()
        QTimer.singleShot(80,inspect_about)
        menu.actions()[-1].trigger();settle()
        assert w.dialog.geometry()==initial
        w.dialog.close();w.dialog.deleteLater();settle()
        # Standalone/Professional reuse exactly the same component.
        with patch.object(engine.IterativeSuperflipPipelineQtGUI,'load_settings',lambda self:None), \
                patch.object(engine.IterativeSuperflipPipelineQtGUI,'save_settings',lambda self:None), \
                patch.object(engine.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None):
            main=engine.IterativeSuperflipPipelineQtGUI();main.show();settle()
            assert main.header_controls.version_label.text()=='v'+VERSION
            assert main.version_menu.accessibleName()=='Phase Studio menu'
            about=Mock();main._open_help_section=about
            main.version_menu.menu().actions()[-1].trigger();about.assert_called_once_with('about')
            capture('06-standalone-header',main.header_controls)
            main.timer.stop();main.close();main.deleteLater();settle()
        plain=create_phase_studio_brand_header()
        assert plain.findChild(QLabel,'versionBadge') is not None and not plain.findChildren(QToolButton)
        plain.deleteLater()
    assert source.read_bytes()==original
(out/'acceptance.json').write_text(json.dumps(records,indent=2),encoding='utf8')
print('PASS separate static version / SVG menu, keys, actions, preferences, verified state and geometry at',scale)
