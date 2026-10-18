"""Configuration geometry, selection and navigation against real Qt widgets."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def probe(scale):
    from PySide6.QtCore import QPoint, QSettings, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog
    from phase_studio import jana_superflip as js
    from phase_studio.ui_style import apply_phase_studio_style
    with tempfile.TemporaryDirectory() as folder:
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, folder)
        QDialog.exec = lambda self: QDialog.Rejected
        js.SharpEDServerClient.get_models = lambda self: SimpleNamespace(
            models=["PEAK A (model prediction)", "SEED (cyclic CF)", "Extra API model"], default_model="Extra API model")
        app = QApplication([])
        apply_phase_studio_style(app)
        # No scientific run or actual project writes; deliberately long name.
        source = Path(folder) / ("long_input_name_" * 10 + ".inflip")
        source.write_text("title config_fixture\nperform CF\noutputformat xplor\ndimension 3\n"
                          "cell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\n"
                          "dataformat intensity\nfbegin\n1 0 0 10 2\nendf\n", encoding="utf8")
        w = js._JanaWorkflowWizard([], source)
        w.run()
        w.dialog.show()
        for _ in range(20):
            app.processEvents()
        w.superflip_sharped_tile._trigger()
        for _ in range(20):
            app.processEvents()
            w.refresh_timer.timeout.emit()
            time.sleep(.01)
        assert w.model.count() == 3
        assert not w.model_user_picked["value"]
        assert w.inflip_path == source and str(source) in w.inflip_info.toolTip(), repr(w.inflip_info.toolTip())
        assert w.inflip_info.accessibleName().endswith(source.name)
        w._adjust_dialog_size = lambda: None

        def settle(height):
            w.dialog.resize(900, height)
            for _ in range(10):
                app.processEvents()
            w._size_stack_to_current_page(w.dialog.width())
            for _ in range(10):
                app.processEvents()

        def box(widget):
            from PySide6.QtCore import QRect
            return QRect(widget.mapTo(w.dialog, QPoint()), widget.size())

        for height in (750, 800, 850, 1080, 1200):
            for expanded in (False, True):
                w.sharped_toggle.setChecked(expanded)
                settle(height)
                assert w.dialog.height() == height
                assert 120 <= w.cycles.width() <= 140
                assert 340 <= w.model.width() <= 420
                assert box(w.refresh_models_button).left() > box(w.model).right()
                assert abs(box(w.refresh_models_button).center().y() - box(w.model).center().y()) <= 3
                assert box(w.warning_text).bottom() < box(w.primary_button).top()
                if not expanded: assert w.scroll_area.verticalScrollBar().maximum() == 0
                assert w.scroll_area.horizontalScrollBar().maximum() == 0
                assert box(w.processing_heading).top()>box(w.inflip_info).bottom()
                assert box(w.cycles).top() - box(w.processing_heading).bottom() <= 12
                gap = box(w.inflip_info).top() - box(w.context_banner).bottom()
                assert 12 <= gap <= 24, (gap, height, expanded)
                assert box(w.validation_group).bottom() < 650, "extra height must stay below the compact form"
                assert w.primary_button.isVisible() and w.back_button.isVisible()
                assert w.warning_text.height() >= w.warning_text.heightForWidth(w.warning_text.width())
                assert w.dialog.devicePixelRatioF() == float(scale)
        w.sharped_toggle.setChecked(False)
        for value, help_text, model in (
            (1, "Single pass · Fastest option", "PEAK A (model prediction)"),
            (3, "Iterative processing · Balanced runtime", "SEED (cyclic CF)"),
            (4, "Extended iterative processing · Longer runtime", "SEED (cyclic CF)"),
        ):
            w.cycles.setValue(value)
            assert w.cycles_recommendation.text() == 'Each cycle processes a charge-flipping map with SharpED. Additional cycles increase processing time and may improve the iterative solution.'
            assert w.model.currentText() == model
        w.cycles.setValue(3)
        w.model.activated.emit(w.model.currentIndex())
        assert w.model_user_picked["value"]
        assert "Matches recommended model" in w.manual_model_indicator.text()
        assert w.model_recommendation.isHidden()
        w.refresh_models_button.click()
        for _ in range(20):
            app.processEvents()
            w.refresh_timer.timeout.emit()
            time.sleep(.01)
        assert w.model_user_picked["value"] and w.model.currentText() == "SEED (cyclic CF)"
        w.cycles.setValue(1)
        assert w.model.currentText() == "SEED (cyclic CF)"
        assert w.manual_model_indicator.text() == "Manually selected"
        w.restore_automatic_model_button.setFocus()
        QTest.keyClick(w.restore_automatic_model_button, Qt.Key_Space)
        assert not w.model_user_picked["value"]
        assert w.model.currentText() == "PEAK A (model prediction)"
        w.model.setCurrentText("Extra API model")
        w.model.activated.emit(w.model.currentIndex())
        w.primary_button.click()
        assert w.stack.currentWidget() is w.page3
        w.back_button.click()
        assert w.stack.currentWidget() is w.page2
        assert w.model_user_picked["value"] and w.model.currentText() == "Extra API model"
        w.back_button.click()
        assert w.stack.currentWidget() is w.page1
        w.superflip_sharped_tile._trigger()
        assert w.model.currentText() == "Extra API model" and w.model_user_picked["value"]
        w.cancel_button.click()
        assert w.result["action"] == "cancel"
        assert not w.dialog.isVisible()
        assert not getattr(w, "backing_window", None)
        print(f"Configuration matrix passed at {scale}: 10 height/advanced states and selection/navigation")


class ConfigurationUI(unittest.TestCase):
    def run_scale(self, scale):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=scale)
        run = subprocess.run([sys.executable, __file__, "--probe", scale], env=env,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_scale_100(self):
        self.run_scale("1")

    def test_scale_125(self):
        self.run_scale("1.25")

    def test_scale_150(self):
        self.run_scale("1.5")


if __name__ == "__main__":
    if "--probe" in sys.argv:
        probe(sys.argv[-1])
    else:
        unittest.main()
