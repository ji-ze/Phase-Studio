"""Render configuration widgets with a synthetic API catalogue; no scientific run.

Run with QT_SCALE_FACTOR=1, 1.25 or 1.5. Optional first argument labels output
before/after. The fixture never contacts the API or saves application settings.
"""
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog
from phase_studio import jana_superflip as js
from phase_studio.ui_style import apply_phase_studio_style

work = ROOT / "build/configuration-capture"
work.mkdir(parents=True, exist_ok=True)
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(work / "settings"))
QSettings("PhaseStudio", "JanaSuperflipWrapper").clear()
QDialog.exec = lambda self: QDialog.Rejected
js.SharpEDServerClient.get_models = lambda self: SimpleNamespace(
    models=["PEAK A (model prediction)", "UNIVERSAL", "SEED (cyclic CF)", "PEAK B (model prediction)"],
    default_model="UNIVERSAL",
)
app = QApplication([])
apply_phase_studio_style(app)
path = work / "configuration-fixture.inflip"
path.write_text("title configuration_fixture\nperform CF\noutputformat xplor\n"
                "dimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\n"
                "dataformat intensity\nfbegin\n1 0 0 10 2\nendf\n", encoding="utf8")
w = js._JanaWorkflowWizard([], path)
w.run()
w.dialog.show()
for _ in range(20):
    app.processEvents()
w.superflip_sharped_tile._trigger()
for _ in range(20):
    app.processEvents()
    w.refresh_timer.timeout.emit()
    time.sleep(.02)
w._adjust_dialog_size = lambda: None
out = ROOT / "build/configuration-2.0.3" / (sys.argv[1] if len(sys.argv) > 1 else "after") / ("scale-" + os.environ.get("QT_SCALE_FACTOR", "1"))
out.mkdir(parents=True, exist_ok=True)

def capture(name, height=820):
    w.dialog.resize(900, height)
    for _ in range(10):
        app.processEvents()
    w._size_stack_to_current_page(w.dialog.width())
    w.scroll_area.verticalScrollBar().setValue(0)
    for _ in range(10):
        app.processEvents()
    assert w.dialog.grab().save(str(out / (name + ".png")))
    print(name, "logical", w.dialog.size().toTuple(), "DPR", w.dialog.devicePixelRatioF(),
          "scroll", w.scroll_area.verticalScrollBar().maximum(), flush=True)

w.cycles.setValue(1)
capture("01-one-cycle-auto")
w.cycles.setValue(3)
capture("02-three-cycles-auto")
w.model.activated.emit(w.model.currentIndex())
capture("03-three-cycles-seed-manual")
w.model.setCurrentText("PEAK A (model prediction)")
w.model.activated.emit(w.model.currentIndex())
capture("04-three-cycles-peak-manual")
w.restore_automatic_model_button.click()
capture("05-restored-auto")
w.sharped_toggle.setChecked(True)
capture("06-advanced-expanded")
w.sharped_toggle.setChecked(False)
capture("07-height-800", 800)
for height in (750, 850, 1080, 1200):
    capture(f"height-{height}", height)
w.dialog.close()
