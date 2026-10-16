"""Disclosure, keyboard scrolling and secondary actions at three real Qt scales."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def check_ui():
    from PySide6.QtCore import QPoint, QSettings, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QPushButton, QStyle, QToolTip
    from phase_studio import jana_superflip as js
    from phase_studio.ui_style import apply_phase_studio_style
    from test_wizard_text_clipping import write_inflip

    app = QApplication([])
    apply_phase_studio_style(app)
    with tempfile.TemporaryDirectory() as tmp:
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)
        source = write_inflip(Path(tmp))
        jana = Path(tmp)/'Jana'
        (jana/'SUPERFLIP').mkdir(parents=True)
        for name in ('superflip.exe','EDMA.exe'):
            (jana/'SUPERFLIP'/name).write_bytes(b'fixture executable')
        js.application_dir = lambda: jana
        original = source.read_bytes()
        QDialog.exec = lambda self: QDialog.Rejected
        w = js._JanaWorkflowWizard([], source)
        w.run()
        w._adjust_dialog_size = lambda: None
        w.dialog.show()

        def settle():
            for _ in range(40):
                app.processEvents()

        settle()
        browses = w.files_form_widget.findChildren(QPushButton, 'optionalFileBrowse')
        tiles = [w.original_superflip_tile, w.superflip_sharped_tile, w.autosolve_tile, w.professional_mode_tile]
        assert w.files_toggle.text() == 'Advanced input options (optional)'
        assert not w.files_form_widget.isVisible()
        paths = [str(Path(tmp)/'reference-long-name.cif'), str(Path(tmp)/'initial-model.xplor')]
        for edit, value in zip([w.reference_file, w.model_file], paths):
            edit.setText(value)
            assert value in edit.toolTip()

        def assert_visible(control):
            vp = w.scroll_area.viewport()
            rect = control.rect().translated(control.mapTo(vp, QPoint()))
            assert vp.rect().contains(rect), (control.objectName(), rect, vp.rect())
            assert rect.top() >= 5 and rect.bottom() < vp.height()-5

        for width, height in [(821,780), (821,580), (640,700), (900,850)]:
            w.dialog.resize(width,height)
            settle()
            w.files_toggle.setChecked(False)
            settle()
            collapsed_hint = w.page1.minimumSizeHint().height()
            collapsed_range = w.scroll_area.verticalScrollBar().maximum()
            icon = w.files_toggle.icon().pixmap(16,16).toImage()
            assert icon == w.dialog.style().standardIcon(QStyle.SP_ArrowRight).pixmap(16,16).toImage()
            w.files_toggle.setChecked(True)
            settle()
            assert w.files_toggle.text() == 'Advanced input options (optional)'
            assert w.files_form_widget.isVisible()
            assert all(button.isVisible() for button in browses)
            assert w.page1.minimumSizeHint().height() > collapsed_hint
            assert w.scroll_area.verticalScrollBar().maximum() >= collapsed_range
            assert w.files_toggle.icon().pixmap(16,16).toImage() == w.dialog.style().standardIcon(QStyle.SP_ArrowDown).pixmap(16,16).toImage()
            footer = w.footer.geometry()
            bar = w.scroll_area.verticalScrollBar()
            bar.setValue(bar.maximum())
            settle()
            assert_visible(tiles[-1])
            if w.secondary_actions_row.direction() == QHBoxLayout.LeftToRight:
                assert_visible(tiles[-2])
                assert tiles[-1].height() == tiles[-2].height()
            assert w.footer.geometry() == footer
            assert w.cancel_button.isVisible() and not w.scroll_area.isAncestorOf(w.cancel_button)
            assert w.scroll_area.horizontalScrollBar().maximum() == 0
            if w.dialog.width() < 750:
                assert w.secondary_actions_row.direction() == QHBoxLayout.TopToBottom, (w.dialog.width(),w.secondary_actions.width(),w.secondary_actions.minimum_pair_width())

            sequence = [w.validate_hkl_button, w.analyze_completeness_button, w.files_toggle,
                        w.reference_file,browses[0],w.model_file,browses[1],*tiles,w.cancel_button]
            w.validate_hkl_button.setFocus(Qt.TabFocusReason)
            settle()
            for previous, target in zip(sequence, sequence[1:]):
                QTest.keyClick(previous, Qt.Key_Tab)
                settle()
                assert app.focusWidget() is target, (app.focusWidget(),target)
                if target in tiles:
                    assert_visible(target)
            for previous, target in zip(reversed(sequence), list(reversed(sequence))[1:]):
                QTest.keyClick(previous, Qt.Key_Tab, Qt.ShiftModifier)
                settle()
                assert app.focusWidget() is target
                if target in tiles:
                    assert_visible(target)
            w.files_toggle.setChecked(False)
            settle()
            assert w.page1.minimumSizeHint().height() == collapsed_hint
            assert [w.reference_file.text(),w.model_file.text()] == paths
            assert not any(button.isVisible() for button in browses)
            w.files_toggle.setFocus(Qt.TabFocusReason)
            QTest.keyClick(w.files_toggle, Qt.Key_Tab)
            settle()
            assert app.focusWidget() is tiles[0]
            assert w.scroll_area.verticalScrollBar().maximum() == collapsed_range

        from PySide6.QtGui import QTextDocument
        def tooltip_text(button):
            if not button.toolTip().startswith('<'):
                return button.toolTip()
            document = QTextDocument()
            document.setHtml(button.toolTip())
            return document.toPlainText()
        assert tooltip_text(w.validate_hkl_button) == 'Check reflection data and input format.'
        assert tooltip_text(w.analyze_completeness_button) == 'Show reflection completeness and intensity statistics.'
        calls = []
        class Diagnostics:
            def test_hkl_load_dialog(self): calls.append('validate')
            def open_hkl_completeness_dialog(self): calls.append('analyze')
        w._get_backing_window = lambda: Diagnostics()
        for button in [w.validate_hkl_button,w.analyze_completeness_button]:
            button.click()
            size = button.size()
            button.setFocus(Qt.TabFocusReason)
            QTest.mouseMove(button, button.rect().center())
            settle()
            assert button.size() == size
            assert '#edf3fa' in button.styleSheet() and ':focus' in button.styleSheet()
            QToolTip.showText(w.dialog.mapToGlobal(QPoint(20,100)),button.toolTip(),button)
            settle()
            assert QToolTip.isVisible()
            tooltip = next(t for t in app.topLevelWidgets() if t.windowType() == Qt.ToolTip and t.isVisible())
            assert tooltip.height() < 45 and tooltip.width() < 500, tooltip.size().toTuple()
            QToolTip.hideText()
            QTest.qWait(350)
            assert not QToolTip.isVisible()
        assert calls == ['validate','analyze']
        for tile in tiles:
            tile._on_click = lambda: calls.append('activate')
            count = len(calls)
            tile.setFocus(Qt.TabFocusReason)
            settle()
            assert len(calls) == count  # focus never executes a workflow
            for key in (Qt.Key_Return,Qt.Key_Space):
                QTest.keyClick(tile,key)
            assert len(calls) == count+2
        assert source.read_bytes() == original
        w.dialog.close()
    print('Disclosure, scrolling, Tab/Shift+Tab, activation, tooltips and responsive layout passed.')


def test_wizard_final_dpi():
    for scale in ['1','1.25','1.5']:
        result = subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child'],cwd=ROOT,
            env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},capture_output=True,text=True,timeout=60)
        assert result.returncode == 0, f'Scale {scale}: {result.stdout}\n{result.stderr}'


if __name__ == '__main__':
    check_ui() if '--child' in sys.argv else test_wizard_final_dpi()
