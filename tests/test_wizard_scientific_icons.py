"""Approved scientific SVG family and real Wizard presentation at three scales."""
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_svg_contract():
    for name in ('superflip', 'sharped', 'autosolve', 'settings'):
        svg = ROOT/'phase_studio/assets'/f'workflow_{name}.svg'
        tree = ET.parse(svg)
        assert tree.getroot().attrib['viewBox'] == '0 0 48 48'
        assert tree.getroot().attrib['width'] == tree.getroot().attrib['height'] == '48'
        assert not any(node.tag.rsplit('}', 1)[-1] in {'image', 'text', 'linearGradient', 'filter'} for node in tree.iter())
    root = ET.parse(ROOT/'phase_studio/assets/workflow_autosolve.svg').getroot()
    circles = root.findall('.//{*}circle')
    assert [(int(c.attrib['cx']), int(c.attrib['cy'])) for c in circles] == [(17,25),(24,16),(33,26),(24,33)]
    assert root.find('.//{*}path').attrib['d'].count('M') == 4
    for spec in ('superflip.spec', 'packaging/pyinstaller/PhaseStudio.spec'):
        text = (ROOT/spec).read_text(encoding='utf8')
        assert '"PySide6.QtSvg"' in text and '"phase_studio/assets"' in text


def test_wizard_scientific_icons_three_scales():
    for scale in ('1', '1.25', '1.5'):
        result = subprocess.run([sys.executable, str(ROOT/'packaging/tools/capture_wizard_icons_204.py'), '--test'],
            cwd=ROOT, env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},
            capture_output=True, text=True, timeout=80)
        assert result.returncode == 0, result.stdout+result.stderr
