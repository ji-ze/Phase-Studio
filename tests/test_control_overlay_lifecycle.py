"""Native-owned arrow overlays survive repeated Qt dialog collection."""
import os
from pathlib import Path
import subprocess
import sys


def test_control_overlay_lifecycle():
    for scale in ('1','1.25','1.5'):
        result=subprocess.run([sys.executable,__file__,'--child'],cwd=Path(__file__).resolve().parents[1],
            env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},capture_output=True,text=True,timeout=45)
        assert result.returncode==0,result.stdout+result.stderr
        assert 'Error calling Python override' not in result.stderr,result.stderr


def exercise():
    import gc
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QSpinBox,QComboBox
    from phase_studio.ui_style import apply_phase_studio_style
    app=QApplication([]);apply_phase_studio_style(app)
    for _ in range(30):
        dialog=QDialog();layout=QVBoxLayout(dialog)
        spin=QSpinBox();combo=QComboBox();combo.addItems(['First','Second'])
        layout.addWidget(spin);layout.addWidget(combo)
        dialog.show();app.processEvents()
        for control in (spin,combo):
            overlay=control._phase_studio_arrow_overlay
            assert overlay.parentWidget() is control
            # Native parenting is authoritative; no Python back-reference cycle.
            assert 'owner' not in overlay.__dict__
            assert not overlay.grab().isNull()
        dialog.close();dialog.deleteLater()
        del dialog,layout,spin,combo,control,overlay
        gc.collect();app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()


if __name__=='__main__':exercise()
