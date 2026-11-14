"""Exercise the script namespace used by the actual Jana PyInstaller entry."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('kind', ['view', 'analyze'])
def test_script_entry_mouse_click_opens_owned_diagnostic_and_reopens(tmp_path, kind):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name('jana_script_entry_probe_207.py')),
         str(tmp_path), kind],
        env=os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': '1'},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
