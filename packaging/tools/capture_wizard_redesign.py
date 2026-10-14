"""Render 2.0.3 Wizard acceptance states using a display-only metadata fixture.

Run separately with QT_SCALE_FACTOR=1, 1.25 and 1.5; these are offscreen Qt
renders, not certification of real Windows multi-monitor behavior.
"""
import os, sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from phase_studio.ui_style import apply_phase_studio_style
import phase_studio.jana_superflip as js
app = QApplication([])
apply_phase_studio_style(app)
QDialog.exec = lambda self: QDialog.Rejected
w = js._JanaWorkflowWizard([], None)
w.run()
w._adjust_dialog_size = lambda: None
w.dialog.show()
app.processEvents()
# Display-only fixture: no altered input parser or scientific calculation.
w.reflections_value.setText('631 parsed · 631 unique')
w.format_value.setText('h k l · I · FWHM')
w.cell_value.setText('8.2512 × 18.844 × 6.7032 Å\n90° × 92.58° × 90°')
w.spacegroup_value.setText('P2₁/n (#14)')
w.composition_value.setText('C₃₆ O₄ N₄ H₇₂ Cl₄')
out = ROOT / 'build/wizard-2.0.3' / (sys.argv[1] if len(sys.argv) > 1 else 'after')
out.mkdir(parents=True, exist_ok=True)
def capture(name, width=900, height=820):
    w.dialog.resize(width, height)
    app.processEvents()
    w._size_stack_to_current_page(w.dialog.width())
    app.processEvents()
    w.scroll_area.verticalScrollBar().setValue(0)
    app.processEvents()
    assert w.dialog.grab().save(str(out / (name + '.png')))
    print(name, 'size', w.dialog.size().toTuple(), 'scroll', w.scroll_area.verticalScrollBar().maximum(), 'cards', [(t.width(), t.height()) for t in [w.original_superflip_tile, w.superflip_sharped_tile, w.autosolve_tile, w.professional_mode_tile]])
capture('normal')
w.files_toggle.setChecked(True)
capture('expanded')
w.files_toggle.setChecked(False)
for name, tile in [('hover-superflip', w.original_superflip_tile), ('hover-sharped', w.superflip_sharped_tile)]:
    QTest.mouseMove(tile, tile.rect().center())
    capture(name)
QTest.mouseMove(w.brand_header)
w.original_superflip_tile.setFocus(Qt.TabFocusReason)
capture('keyboard-focus')
capture('short', height=580)
capture('narrow', width=640, height=820)
w.dialog.close()
