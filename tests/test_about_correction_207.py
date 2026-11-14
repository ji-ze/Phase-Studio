"""Real-widget font, responsive reader, source integrity and CFF regressions."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('scale', ['1', '1.25', '1.5', '2'])
def test_about_font_and_reader_matrix(scale, tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / ('about-' + scale)
    result = subprocess.run([sys.executable, '-m', 'phase_studio', '--packaging-acceptance', str(output)],
        cwd=root, env=os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': scale,
            'PHASE_STUDIO_ABOUT_UI_ACCEPTANCE': '1'}, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output / 'report.json').read_text(encoding='utf8'))
    assert report['passed'] and len(report['profiles']) == 2
    for profile in report['profiles']:
        assert profile['body_font']['family'] != 'Science Gothic'
        assert profile['reader_font']['family'] != 'Science Gothic'
        assert profile['brand_font']['family'] == 'Science Gothic'
        assert profile['geometry'][2:] == [720, 390]
        assert profile['reader_font']['point_size'] >= 10
    assert report['narrow']['geometry'][2] <= 480
    assert len(report['screenshots']) == 28


def test_about_resolves_ui_font_without_application_styles(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-m', 'phase_studio', '--packaging-acceptance', str(tmp_path)],
        cwd=root, env=os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': '1',
            'PHASE_STUDIO_ABOUT_UI_ACCEPTANCE': '1', 'PHASE_STUDIO_ABOUT_UNSTYLED': '1'},
        capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / 'report.json').read_text(encoding='utf8'))
    assert report['passed']
    assert all(profile['body_font']['family'] != 'Science Gothic' for profile in report['profiles'])


def test_citation_uses_authoritative_person_fields(monkeypatch):
    from phase_studio import legal_content
    cff = ('title: Example software\nauthors:\n'
           '  - family-names: Lovelace\n    given-names: Ada\n'
           '  - name: Example Research Group\n'
           'repository-code: https://example.org/project\n')
    monkeypatch.setattr(legal_content, 'source_text', lambda name: cff)
    assert legal_content.citation_text('9.8.7') == (
        'Ada Lovelace; Example Research Group, Example software, version 9.8.7, https://example.org/project')


def test_dependency_license_is_not_mislabeled_as_project_mit():
    from phase_studio.about_ui import _document_title
    path = Path('dependencies/example/example-1.2.dist-info/licenses/LICENSE')
    assert _document_title(path) == 'example-1.2 · License'


def test_reader_renders_bundled_html_and_avoids_duplicate_mit_heading():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from phase_studio import about_ui
    app = QApplication.instance() or QApplication([])
    mit = about_ui.DocumentDialog(None, 'LICENSE')
    mit.show(); app.processEvents()
    assert not mit.title_label.isVisible()
    assert mit.browser.toPlainText().startswith('MIT License')
    mit.copy_button.click()
    assert app.clipboard().text() == mit.raw_text
    mit.close()
    viewer = about_ui.DocumentDialog(None, 'THIRD_PARTY_NOTICES.md', third_party=True)
    index = next(i for i, path in enumerate(viewer.paths) if path.name == 'Qt-third-party-notices.html')
    viewer.selector.setCurrentIndex(index)
    raw = viewer.path.read_bytes()
    plain = viewer.browser.toPlainText()
    assert 'Third-Party Code Used in Qt' in plain and '<html' not in plain.lower()
    assert viewer.raw_bytes == raw
    viewer.copy_button.click()
    assert app.clipboard().text() == raw.decode('utf8')
    viewer.original_layout.setChecked(True)
    assert viewer.browser.toPlainText() == raw.decode('utf8').replace('\r\n', '\n')
    assert viewer.path.read_bytes() == raw
    viewer.close()


def test_reader_unicode_extended_paths_raw_copy_and_markdown_safety(tmp_path, monkeypatch):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices, QFontInfo
    from PySide6.QtWidgets import QApplication
    from phase_studio import about_ui

    app = QApplication.instance() or QApplication([])
    root = tmp_path / 'žluťoučký-密度'
    if os.name == 'nt':
        root = Path('\\\\?\\' + str(root))
    nested = root / 'third_party_licenses'
    for _ in range(5):
        nested /= 'unicode-notice-' + 'x' * 36
    nested.mkdir(parents=True)
    original = nested / 'licence-密度.txt'
    raw = 'Copyright © Example\r\n\r\nUnicode: žluťoučký 密度.\r\nAll original terms remain.\r\n'.encode('utf8')
    original.write_bytes(raw)
    (root / 'THIRD_PARTY_NOTICES.md').write_text(
        '# Notices\n\n- outer\n  - nested\n\n![local](file:///private.png)\n![remote](https://example.org/image.png)\n', encoding='utf8')
    monkeypatch.setattr(about_ui, 'legal_directory', lambda: root)
    viewer = about_ui.DocumentDialog(None, 'THIRD_PARTY_NOTICES.md', third_party=True)
    viewer.show()
    app.processEvents()
    assert 'nested' in viewer.browser.toPlainText()
    assert viewer.browser.loadResource(2, QUrl('file:///private.png')) is None
    assert viewer.browser.loadResource(2, QUrl('https://example.org/image.png')) is None
    viewer.selector.setCurrentIndex(1)
    app.processEvents()
    assert len(str(viewer.path)) > 260
    assert viewer.raw_bytes == raw
    assert QFontInfo(viewer.browser.font()).family() != 'Science Gothic'
    # Switching from Markdown must not carry a heading font into the notice.
    cursor = viewer.browser.textCursor()
    cursor.setPosition(1)
    assert cursor.charFormat().fontPointSize() == 10.5
    viewer.copy_button.click()
    assert QApplication.clipboard().text() == raw.decode('utf8')
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url) or True)
    viewer.original_button.click()
    assert opened == [QUrl.fromLocalFile(str(original))]
    viewer.original_layout.setChecked(True)
    assert viewer.browser.toPlainText() == raw.decode('utf8').replace('\r\n', '\n')
    viewer.search.setText('original terms')
    viewer.find_next()
    assert viewer.browser.textCursor().selectedText() == 'original terms'
    assert original.read_bytes() == raw
    viewer.paths[1] = root / 'outside.txt'
    viewer.load_document()
    assert not viewer.available and not viewer.original_button.isEnabled()
    viewer.close()
