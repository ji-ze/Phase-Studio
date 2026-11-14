"""Mouse-event regression in a real modal loop; no callback/exec replacement."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['PHASE_STUDIO_STARTUP_PROBE'] = '1'
from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog, QTabWidget, QTableView

directory, kind = Path(sys.argv[1]), sys.argv[2]
source = directory / 'controlled.inflip'
source.write_text('cell 8 12 7 90 94 90\nspacegroup P1\ncomposition C4 O\n'
                  'lambda 1.541866\ndataformat intensity fwhm\nfbegin\n'
                  '1 0 0 10 .05\n0 1 0 20 .06\n0 0 1 30 .07\nendf\n')
original = source.read_bytes()
entry = Path(os.environ.get('PS207_JANA_ENTRY_SOURCE', ROOT / 'phase_studio/jana_superflip.py'))
spec = importlib.util.spec_from_file_location('jana_frozen_script_entry', entry)
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)
assert not launcher.__package__  # This is what ordinary package-import tests missed.
qt = QApplication([])
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(directory / 'settings'))
errors = []
sys.excepthook = lambda typ, value, tb: errors.append(''.join(traceback.format_exception(typ, value, tb)))
imports = launcher._qt_imports
with patch.object(launcher, '_qt_imports', lambda: imports() | {
    'QSettings': lambda org, name: QSettings(str(directory / (name + '.ini')), QSettings.IniFormat)
}):
    wizard = launcher._JanaWorkflowWizard([str(source)], source)
wizard._ensure_models_loaded = lambda **kwargs: None  # No remote model catalogue in this test.
button = wizard.validate_hkl_button if kind == 'view' else wizard.analyze_completeness_button
clicked = QSignalSpy(button.clicked)
completed = QSignalSpy(wizard.diagnostic_loader.completed)
stage, reopened = 'click', 0
deadline = time.monotonic() + 20


def tick():
    global stage, reopened
    try:
        assert not errors, '\n'.join(errors)
        assert time.monotonic() < deadline, 'Visible diagnostic completion timed out'
        if stage == 'click':
            if not wizard.dialog.isVisible() or not button.isEnabled():
                return
            assert 'FWHM' in wizard.format_value.text()
            assert button.visibleRegion().contains(button.rect().center())
            QTest.mouseClick(button, Qt.LeftButton)
            stage = 'result'
        else:
            dialog = getattr(wizard, '_diagnostic_dialog', None)
            if dialog is None or not dialog.isVisible():
                return
            assert dialog.parentWidget() is wizard.dialog
            assert qt.activeModalWidget() is dialog
            assert dialog.windowModality() == Qt.WindowModal
            assert Path(dialog._phase_studio_hkl_request.jana_text) == source
            assert clicked.count() == completed.count() == reopened + 1
            if kind == 'view':
                table = dialog.findChildren(QTableView)[0]
                assert table.model().rowCount() == 3
                index = table.model().index(1, 0)
                QTest.mouseClick(table.viewport(), Qt.LeftButton, pos=table.visualRect(index).center())
                assert table.currentIndex().row() == 1
            else:
                tabs = dialog.findChildren(QTabWidget)[0]
                assert tabs.count() == 7
                for index in range(tabs.count()):
                    QTest.mouseClick(tabs.tabBar(), Qt.LeftButton, pos=tabs.tabBar().tabRect(index).center())
                    assert tabs.currentIndex() == index
            QTest.keyClick(dialog, Qt.Key_Escape)
            assert not dialog.isVisible()
            assert wizard._diagnostic_dialog is None
            reopened += 1
            stage = 'click'
            if reopened == 2:
                assert source.read_bytes() == original
                assert wizard.backing_window_holder['win'] is None
                QTest.mouseClick(wizard.cancel_button, Qt.LeftButton)
                timer.stop()
    except Exception:
        errors.append(traceback.format_exc())
        timer.stop()
        for widget in qt.topLevelWidgets():
            if isinstance(widget, QDialog):
                widget.reject()


timer = QTimer()
timer.setInterval(20)
timer.timeout.connect(tick)
timer.start()
wizard.run()
print(json.dumps(dict(kind=kind,opens=reopened,clicked=clicked.count(),completed=completed.count(),errors=errors)))
raise SystemExit(0 if reopened == 2 and not errors else 1)
