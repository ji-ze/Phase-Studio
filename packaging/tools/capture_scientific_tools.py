"""Actual Qt captures; approved installation screens use explicit mock fixtures."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from threading import Event
import time
from unittest.mock import patch
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool, Qt, QPoint
from PySide6.QtWidgets import QApplication, QDialog, QWidget, QPushButton
from phase_studio import requirements as reqs, scientific_tools as tools
from phase_studio.scientific_tools_setup import ScientificToolsSetupDialog
from phase_studio.ui_style import apply_phase_studio_style
from scientific_tool_fixtures import program_bytes

app = QApplication([])
apply_phase_studio_style(app)
scale = os.environ.get("QT_SCALE_FACTOR", "1")
out = ROOT / "docs" / "screenshots" / "2.0.3-scientific-tools" / ("scale-" + scale)
out.mkdir(parents=True, exist_ok=True)
parent = QWidget()
parent.resize(740, 700)
parent.show()
windows = []
K, S = reqs.RequirementKind, reqs.RequirementState

def dialog(kinds=(K.SUPERFLIP,), found=False, **kwargs):
    statuses = [reqs.RequirementStatus(k, S.OK if found else S.NOT_FOUND, path=Path(k.value + ".exe") if found else None) for k in kinds]
    d = ScientificToolsSetupDialog(parent, statuses, **kwargs)
    windows.append(d)
    d.show()
    return d

def events():
    for _ in range(12): app.processEvents()

def capture(name, d, **metadata):
    events()
    image = d.grab()
    assert image.save(str(out / (name + ".png")))
    data = dict(source_runtime=True, scale=float(scale), logical_size=d.size().toTuple(),
                device_pixel_ratio=image.devicePixelRatio(), **metadata)
    if isinstance(d, ScientificToolsSetupDialog):
        assert d._scroll.horizontalScrollBar().maximum() == 0
        for button in (d.back_button, d.continue_button):
            pos = button.mapTo(d, QPoint())
            assert pos.y() + button.height() <= d.height()
        assert not d.windowFlags() & Qt.WindowStaysOnTopHint
        data.update(scroll_maximum=d._scroll.verticalScrollBar().maximum(),
                    production_automatic_setup_available=False)
    (out / (name + ".json")).write_text(json.dumps(data, indent=2), encoding="utf-8")

try:
    # The saved previous UI is used only for a source-layout comparison.
    baseline = ROOT / "build" / "scientific-tools-before-ui.py"
    if baseline.exists():
        spec = importlib.util.spec_from_file_location("before_scientific_tools", baseline)
        before = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(before)
        def old_exec(d):
            d.show()
            capture("00-before-edma-setup", d, layout_baseline=True)
            d.reject()
            return QDialog.Rejected
        with patch.object(QDialog, "exec", old_exec):
            before.show_requirement_remediation_dialog(parent, reqs.RequirementStatus(K.EDMA, S.NOT_FOUND))
    d = dialog((K.EDMA,)); capture("01-edma-missing", d); d.close()
    d = dialog(); capture("02-superflip-missing", d); d.close()
    d = dialog((K.SUPERFLIP, K.EDMA)); capture("03-both-missing", d); d.close()
    d = dialog((K.EDMA,), found=True); capture("04-existing-edma-found", d, status_fixture=True); d.close()
    d = dialog(found=True); capture("05-existing-superflip-found", d, status_fixture=True); d.close()
    d = dialog(); capture("06-manual-only", d); d.close()
    policy = tools.ApprovedDistribution("https://official.example.test/mock.zip", "0" * 64, "mock licence", "mock permission")
    d = dialog((K.SUPERFLIP, K.EDMA), distributions={"superflip": policy})
    capture("07-approved-automatic-setup-fixture", d, mocked=True, not_a_production_source=True)
    gate = Event()
    def mock_install(report, stopped):
        report("Downloading")
        gate.wait(3)
        if stopped(): raise InterruptedError("Cancelled")
        status = reqs.RequirementStatus(K.SUPERFLIP, S.OK, path=Path("mock-superflip.exe"))
        return str(status.path), status
    d._start(K.SUPERFLIP, mock_install)
    until = time.monotonic() + 2
    while d.feedback.text() != "Downloading" and time.monotonic() < until:
        events(); time.sleep(.005)
    capture("08-download-in-progress-fixture", d, mocked=True, not_a_production_download=True)
    gate.set()
    while d._task is not None: events(); time.sleep(.005)
    capture("09-installation-completed-fixture", d, mocked=True, not_a_production_installation=True)
    d.close()
    d = dialog((K.SUPERFLIP, K.EDMA), distributions={"superflip": policy})
    def invalid_package(report, stopped):
        report("Verifying downloaded files")
        raise ValueError("Package integrity verification failed")
    d._start(K.SUPERFLIP, invalid_package)
    while d._task is not None: events(); time.sleep(.005)
    capture("10-failed-verification-fixture", d, mocked=True)
    d.close()
    d = dialog((K.SUPERFLIP, K.EDMA))
    d.resize(650, 390)
    capture("11-reduced-height-top", d)
    d._scroll.verticalScrollBar().setValue(d._scroll.verticalScrollBar().maximum())
    capture("12-reduced-height-bottom", d)
finally:
    QThreadPool.globalInstance().waitForDone(4000)
    for d in windows: d.close(); d.deleteLater()
    parent.close(); parent.deleteLater()
    events()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    import shiboken6
    shiboken6.delete(app)
