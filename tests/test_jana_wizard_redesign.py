"""Presentation guards for the 2.0.3 Wizard; no workflow is executed."""
import os
import sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtWidgets import QApplication, QDialog
    from PySide6.QtTest import QTest
    from phase_studio.ui_style import apply_phase_studio_style
    from phase_studio import jana_superflip as js
    app = QApplication.instance() or QApplication([])
    apply_phase_studio_style(app)
    QDialog.exec = lambda self: QDialog.Rejected
    wizard = js._JanaWorkflowWizard([], None)
    wizard.run()
    wizard._adjust_dialog_size = lambda: None
    wizard.dialog.show()
    checks = 0
    def check(condition):
        nonlocal checks
        assert condition
        checks += 1
    check(wizard.backing_window_holder['win'] is None)
    wizard.dialog.resize(900, 820)
    for _ in range(10): app.processEvents()
    before_size = wizard.dialog.size()
    before_scroll = wizard.scroll_area.verticalScrollBar().maximum()
    wizard.files_toggle.setChecked(True)
    for _ in range(10): app.processEvents()
    check(wizard.files_form_widget.isVisible())
    wizard.files_toggle.setChecked(False)
    for _ in range(10): app.processEvents()
    check(not wizard.files_form_widget.isVisible())
    check(wizard.dialog.size() == before_size)
    check(wizard.scroll_area.verticalScrollBar().maximum() == before_scroll)
    for width, height in [(900, 820), (740, 580)]:
        wizard.dialog.resize(width, height)
        for _ in range(10): app.processEvents()
        wizard._size_stack_to_current_page(wizard.dialog.width())
        for _ in range(10): app.processEvents()
        primary = (wizard.original_superflip_tile, wizard.superflip_sharped_tile)
        secondary = (wizard.autosolve_tile, wizard.professional_mode_tile)
        for pair in (primary, secondary):
            check(pair[0].height() == pair[1].height())
            check(abs(pair[0].width() - pair[1].width()) <= 1)
            check(pair[0].subtitle_label.geometry().top() == pair[1].subtitle_label.geometry().top())
            for tile in pair:
                check(tile.rect().contains(tile.chevron_label.geometry()))
                check(tile.rect().contains(tile.icon_label.geometry()))
        for tile in (wizard.superflip_sharped_tile, wizard.autosolve_tile):
            status_top = tile.secondary_label.mapTo(tile, QPoint())
            check(status_top.y() >= 0 and status_top.y() + tile.secondary_label.height() <= tile.height())
        check(not wizard.scroll_area.isAncestorOf(wizard.cancel_button))
        check(wizard.cancel_button.isVisible())
    tile = wizard.original_superflip_tile
    calls = []
    tile._on_click = lambda: calls.append(True)
    tile.setEnabled(False)
    tile.click()
    check(not calls)
    tile.setEnabled(True)
    tile.setFocus()
    QTest.keyClick(tile, Qt.Key_Space)
    check(len(calls) == 1)
    check(wizard.backing_window_holder['win'] is None)
    wizard.dialog.close()
    print(f'All {checks} checks passed.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
