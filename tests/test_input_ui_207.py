"""Exercise actual styled widgets, effective fonts and legal bytes at four scales."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('scale',['1','1.25','1.5','2'])
def test_input_about_and_splash_acceptance(scale,tmp_path):
    root=Path(__file__).resolve().parents[1]
    output=tmp_path/'ui'
    result=subprocess.run([sys.executable,'-m','phase_studio','--packaging-acceptance',str(output)],
        cwd=root,env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale,
            'PHASE_STUDIO_INPUT_UI_ACCEPTANCE':'1'},capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
    report=json.loads((output/'report.json').read_text())
    assert report['passed'] and report['splash_font']['family']=='Science Gothic'
    assert len(report['profiles'])==2
    for profile in report['profiles']:
        assert profile['legal_exact']
        assert len(profile['tabs'])==2 and all(row['unchanged'] for row in profile['tabs'])
