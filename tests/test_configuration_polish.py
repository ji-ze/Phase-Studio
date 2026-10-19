"""Run the real offline Wizard acceptance at three Qt device pixel ratios."""
import os
from pathlib import Path
import subprocess
import sys


def test_configuration_polish_three_scales():
    root=Path(__file__).resolve().parents[1]
    for scale in ('1','1.25','1.5'):
        result=subprocess.run([sys.executable,'packaging/tools/capture_configuration_polish_205.py'],cwd=root,
            env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},capture_output=True,text=True,timeout=90)
        assert result.returncode==0,scale+'\n'+result.stdout+result.stderr
