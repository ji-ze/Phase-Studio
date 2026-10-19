"""Final actual-Qt acceptance runs in isolated per-DPI processes."""
import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('scale', ['1', '1.25', '1.5'])
def test_final_wizard_release_acceptance(scale):
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run([sys.executable, 'packaging/tools/capture_final_wizard_release_205.py'],
        cwd=root, env=os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': scale},
        capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stdout + run.stderr
