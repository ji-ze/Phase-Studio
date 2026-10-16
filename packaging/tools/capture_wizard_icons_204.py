"""Offline Qt capture and interaction assertions; no inference or external navigation."""
import os
from pathlib import Path
import sys
import tempfile
import json
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['PHASE_STUDIO_STARTUP_PROBE']='1'
from PySide6.QtCore import QSettings,QRect,Qt,QPoint
from PySide6.QtGui import QScreen,QFontDatabase,QFontInfo
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog,QLabel,QToolTip
from phase_studio import jana_superflip as js,app as engine
from phase_studio.ui_style import apply_phase_studio_style
from phase_studio.ui_branding import established_icon
from phase_studio.credentials import CredentialStore
from test_wizard_text_clipping import write_inflip

qt=QApplication([])
if os.name=='nt':
    # The offscreen backend does not enumerate the Windows platform fonts.
    for name in ('segoeui.ttf','segoeuib.ttf','seguisym.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name))
apply_phase_studio_style(qt)
scale=float(os.environ.get('QT_SCALE_FACTOR','1'))
out=ROOT/'build/acceptance-wizard-icons-2.0.4'/f'dpi-{round(scale*100)}'
out.mkdir(parents=True,exist_ok=True)
records=[]
def settle():
    for _ in range(30):qt.processEvents()
def capture(w,name):
    settle();QToolTip.hideText()
    assert w.scroll_area.horizontalScrollBar().maximum()==0
    assert w.cancel_button.isVisible()
    assert w.dialog.grab().save(str(out/(name+'.png')))
    records.append(dict(name=name,size=w.dialog.size().toTuple(),dpi=scale,scroll=w.scroll_area.verticalScrollBar().maximum()))

with tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp);QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
    js.credential_store=CredentialStore()
    original=js._qt_imports
    js._qt_imports=lambda:original()|{'QSettings':lambda org,app:QSettings(str(base/(app+'.ini')),QSettings.IniFormat)}
    engine.IterativeSuperflipPipelineQtGUI.refresh_sharped_models=lambda self:None
    jana=base/'Jana';(jana/'SUPERFLIP').mkdir(parents=True)
    for name in ('superflip.exe','EDMA.exe'):(jana/'SUPERFLIP'/name).write_bytes(b'UI fixture only')
    js.application_dir=lambda:jana
    inflip=write_inflip(base);input_bytes=inflip.read_bytes()
    with patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(2560/scale),int(1400/scale))),patch.object(QDialog,'exec',lambda self:QDialog.Rejected):
        w=js._JanaWorkflowWizard([],inflip);w.run();w.dialog.show();settle()
        selected=w.workflow_state['key']
        capture(w,'01-default-compact')
        assert 960<=w.dialog.width()<=1040
        assert w.dialog.height()<=780
        assert w.scroll_area.verticalScrollBar().maximum()==0
        for label in w.page1.findChildren(QLabel):
            assert 'Science Gothic' not in QFontInfo(label.font()).family()
        tiles=[w.original_superflip_tile,w.superflip_sharped_tile,w.autosolve_tile,w.professional_mode_tile]
        for i,tile in enumerate(tiles):
            icon=tile.icon_label.pixmap()
            assert icon and not icon.isNull()
            assert abs(icon.devicePixelRatio()-scale)<.01
            rendered=icon.toImage()
            assert rendered.pixelColor(0,0).alpha()==0
            assert sum(rendered.pixelColor(x,y).alpha()>0 for x in range(rendered.width()) for y in range(rendered.height()))>20
            asset=ROOT/'phase_studio/assets'/('workflow_'+('superflip','sharped','autosolve','settings')[i]+'.svg')
            renderer=QSvgRenderer(str(asset));assert renderer.isValid() and renderer.viewBox().width()==48
            tile.setFocus(Qt.TabFocusReason);w.scroll_area.ensureWidgetVisible(tile,8,8)
            capture(w,f'0{i+2}-focused')
        assert w.workflow_state['key']==selected
        w.reference_file.setText('reference-fixture.cif');w.model_file.setText('initial-fixture.xplor')
        w.files_toggle.setChecked(True);w.scroll_area.verticalScrollBar().setValue(0);capture(w,'06-advanced-expanded')
        w.scroll_area.verticalScrollBar().setValue(w.scroll_area.verticalScrollBar().maximum());capture(w,'06b-advanced-workflows-visible')
        w.files_toggle.setChecked(False);w.files_toggle.setChecked(True)
        assert w.reference_file.text()=='reference-fixture.cif' and w.model_file.text()=='initial-fixture.xplor'
        assert tiles[0].height()==tiles[1].height()
        assert tiles[2].height()==tiles[3].height()
        # Every event hits the tile once; rapid repeat activation is suppressed.
        for tile in tiles:
            calls=[];tile._on_click=lambda:calls.append(True)
            tile._last_activation=0;QTest.mouseClick(tile,Qt.LeftButton)
            QTest.mouseClick(tile,Qt.LeftButton);assert len(calls)==1
            QTest.qWait(360);QTest.keyClick(tile,Qt.Key_Space);assert len(calls)==2
            QTest.qWait(360);QTest.keyClick(tile,Qt.Key_Return);assert len(calls)==3
            QTest.qWait(360);QTest.mouseClick(tile.chevron_label,Qt.LeftButton);assert len(calls)==4
            assert tile.testAttribute(Qt.WA_Hover) and tile.focusPolicy()==Qt.StrongFocus
        with patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(1366/scale),int(768/scale))):
            w._adjust_dialog_size();settle();capture(w,'07-constrained-scroll')
            assert w.scroll_area.verticalScrollBar().maximum()>0
            w.scroll_area.verticalScrollBar().setValue(w.scroll_area.verticalScrollBar().maximum())
            capture(w,'08-constrained-workflows')
        original_count=w.reflections_value.text()
        w.reflections_value.setText('12,345,678 parsed / 10,987,654 literal unique HKL')
        w.dialog.resize(720,540);settle()
        assert w.reflections_value.wordWrap()
        assert w.reflections_value.height()>=w.reflections_value.heightForWidth(w.reflections_value.width())
        w.reflections_value.setText(original_count)
        w.refresh_timer.stop();w.dialog.close();QTest.qWait(400)
    assert inflip.read_bytes()==input_bytes
(out/'checks.json').write_text(json.dumps(records,indent=2),encoding='utf8')
print('PASS: real SVG rendering, activation, retention, geometry and input immutability',scale,flush=True)
