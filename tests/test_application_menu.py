"""Semantic and actual Qt interaction checks in separate DPI processes."""
import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('scale',['1','1.25','1.5'])
def test_application_menu(scale):
    root=Path(__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'packaging/tools/capture_application_menu_205.py'],cwd=root,
        env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},
        capture_output=True,text=True,timeout=90)
    assert run.returncode==0,run.stdout+run.stderr
