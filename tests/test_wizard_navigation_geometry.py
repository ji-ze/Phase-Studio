"""Exercise actual stacked Wizard navigation at real Qt device-pixel ratios."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).parents[1]


def test_stable_wizard_navigation_at_three_scales():
    for scale in ('1', '1.25', '1.5'):
        result = subprocess.run([sys.executable, 'packaging/tools/capture_wizard_geometry_204.py'], cwd=ROOT,
            env=os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': scale},
            capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, scale + '\n' + result.stdout + result.stderr
