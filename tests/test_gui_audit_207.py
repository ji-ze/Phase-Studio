"""Actual Qt capability, provenance and automatic-value presentation checks."""
import os
from pathlib import Path
import subprocess
import sys


def test_presentation_in_isolated_qt_process():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / 'packaging/tools/capture_gui_audit_207.py'), 'test'], cwd=root,
        env=os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'PHASE_STUDIO_STARTUP_PROBE': '1', 'PHASE_STUDIO_AUDIT_ASSERT': '1'}, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
