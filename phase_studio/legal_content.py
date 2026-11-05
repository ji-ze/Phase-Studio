"""Shared legal authorities for Help and About; source files remain authoritative."""
from pathlib import Path
import sys
from html import escape


def legal_directory():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'PhaseStudioLegal'
    return Path(__file__).resolve().parents[1]


def source_text(name):
    path = legal_directory() / name
    return path.read_text(encoding='utf8') if path.is_file() else 'Bundled notice unavailable: ' + name


def citation_fields():
    # CFF is YAML. Read the supported scalar fields without a runtime YAML dependency;
    # schema validation belongs to the release checks, not this presentation layer.
    fields = {}
    for line in source_text('CITATION.cff').splitlines():
        if line and not line[0].isspace() and ':' in line:
            key, value = line.split(':', 1)
            fields[key] = value.strip().strip('"\'')
    return fields


def citation_text(runtime_version):
    fields = citation_fields()
    return f'Jiří Zelenka, {fields.get("title", "Phase Studio")}, version {runtime_version}, {fields.get("repository-code", "")}'


def overview_html(runtime_version):
    from PySide6.QtGui import QTextDocument
    document = QTextDocument()
    document.setMarkdown(source_text('AUTHORS.md'), QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML)
    return document.toHtml() + '<p>MIT license. Scientific attribution is separate from license terms.</p><p>' + escape(citation_text(runtime_version)) + '</p>'
