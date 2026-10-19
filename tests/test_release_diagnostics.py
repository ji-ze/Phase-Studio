"""The same offline UI probe is later executed inside both frozen products."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('module', ['phase_studio.standalone', 'phase_studio.jana_superflip'])
def test_release_ui_diagnostic(module, tmp_path):
    output = tmp_path / 'ui-check.json'
    run = subprocess.run([sys.executable, '-m', module, '--release-ui-check', str(output)],
        cwd=Path(__file__).resolve().parents[1], env=os.environ | {'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr + (output.read_text() if output.exists() else '')
    report = json.loads(output.read_text())
    assert report['ok'] and report['parsed_records'] == 2
    assert report['navigation'] and report['account_dialog'] and report['model_policy']
    assert not report['inference_submitted'] and not report['original_superflip_required']
