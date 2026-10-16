"""The actual About HTML must cite the runtime version, including future updates."""
import ast
from pathlib import Path

from phase_studio.version import VERSION


def test_about_citation_uses_runtime_version():
    tree = ast.parse((Path(__file__).parents[1] / 'phase_studio' / 'app.py').read_text(encoding='utf-8'))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == '_add_help_section'
             and len(node.args) >= 4 and isinstance(node.args[1], ast.Constant)
             and node.args[1].value == 'about']
    assert len(calls) == 1
    expression = ast.Expression(calls[0].args[3])
    for version in (VERSION, '9.8.7'):
        html = eval(compile(expression, '<About HTML>', 'eval'), {'__version__': version})
        assert f'Phase Studio, version {version},' in html
        assert 'version 2.0.2' not in html
