import os
from pathlib import Path
import subprocess
import sys


def test_wizard_update_acceptance_three_dpi_scales():
    root=Path(__file__).resolve().parents[1]
    for factor in ('1','1.25','1.5'):
        result=subprocess.run([sys.executable,'packaging/tools/capture_wizard_updates_205.py'],cwd=root,
            env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':factor},capture_output=True,text=True,timeout=70)
        assert result.returncode==0,factor+'\n'+result.stdout+result.stderr
