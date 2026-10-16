"""Capture actual Wizard widgets before/after the focused UI correction."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QToolTip
from phase_studio import jana_superflip as js
from phase_studio import ui_style

phase = sys.argv[1]
if phase == 'before':
    # The snapshot is the dirty working tree immediately before this task,
    # not HEAD (which predates the existing 2.0.4 UI).
    exec(compile((ROOT/'build/wizard-final/ui_style_before.py').read_bytes(), ui_style.__file__, 'exec'), ui_style.__dict__)
    exec(compile((ROOT/'build/wizard-final/jana_superflip_before.py').read_bytes(), js.__file__, 'exec'), js.__dict__)
app = QApplication([])
ui_style.apply_phase_studio_style(app)
settings = tempfile.TemporaryDirectory()
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, settings.name)
QDialog.exec = lambda self: QDialog.Rejected
js.application_dir = lambda: Path('C:/Jana2020/SharpED')
source = ROOT/'build/oauth-2.0.4-ochlor-run/ochlor.inflip'
w = js._JanaWorkflowWizard([], source)
w.run()
w._adjust_dialog_size = lambda: None
w.dialog.show()
out = ROOT/'docs/screenshots/2.0.4-wizard-final'/phase/('scale-'+os.environ.get('QT_SCALE_FACTOR', '1'))
out.mkdir(parents=True, exist_ok=True)
records = {}

def settle():
    for _ in range(30):
        app.processEvents()
    QTest.qWait(20)

def capture(name, width=None, height=None, bottom=False):
    settle()
    if width:
        w.dialog.resize(width, height)
    settle()
    if bottom:
        w.scroll_area.verticalScrollBar().setValue(w.scroll_area.verticalScrollBar().maximum())
        settle()
    viewport = w.scroll_area.viewport()
    tiles = (w.original_superflip_tile, w.superflip_sharped_tile, w.autosolve_tile, w.professional_mode_tile)
    rects = [t.rect().translated(t.mapTo(viewport, QPoint())) for t in tiles]
    records[name] = dict(size=w.dialog.size().toTuple(), viewport=viewport.size().toTuple(),
                         scroll=w.scroll_area.verticalScrollBar().value(), maximum=w.scroll_area.verticalScrollBar().maximum(),
                         horizontal=w.scroll_area.horizontalScrollBar().maximum(),
                         cards=[r.getRect() for r in rects], fully_visible=[viewport.rect().contains(r) for r in rects],
                         footer=w.footer.geometry().getRect(), focus=app.focusWidget().objectName() if app.focusWidget() else None)
    assert w.dialog.grab().save(str(out/(name+'.png')))

capture('01-normal-collapsed', 821, 780)
w.files_toggle.setChecked(True)
capture('02-normal-expanded')
capture('03-reduced-expanded-top', 821, 580)
capture('04-reduced-expanded-bottom', bottom=True)
w.scroll_area.verticalScrollBar().setValue(0)
w.autosolve_tile.setFocus(Qt.TabFocusReason)
QTest.keyClick(w.autosolve_tile, Qt.Key_Tab)
capture('05-last-card-keyboard-focus')
w.files_toggle.setChecked(False)
w.dialog.resize(821, 780)
settle()
for name, button in [('06-validate-tooltip', w.validate_hkl_button), ('07-completeness-tooltip', w.analyze_completeness_button)]:
    QTest.mouseMove(button, button.rect().center())
    QToolTip.showText(button.mapToGlobal(QPoint(0, button.height()+3)), button.toolTip(), button)
    settle()
    capture(name)
    # Tooltip is a native top-level Qt widget, outside dialog.grab().
    for widget in app.topLevelWidgets():
        if widget.isVisible() and widget.windowType() == Qt.ToolTip:
            widget.grab().save(str(out/(name+'-tooltip.png')))
    QToolTip.hideText()
w.files_toggle.setChecked(True)
capture('08-narrow-expanded-bottom', 640, 700, bottom=True)
(out/'geometry.json').write_text(json.dumps(records, indent=2), encoding='utf8')
print(str(out))
w.dialog.close()
