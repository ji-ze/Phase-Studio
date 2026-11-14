import os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget
from phase_studio.about_ui import AboutDialog, DocumentDialog
from phase_studio.legal_content import legal_directory, source_text


def test_four_cards_viewers_and_stable_geometry():
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    dialog = AboutDialog(owner, jana=False)
    dialog.show()
    app.processEvents()
    geometry = dialog.geometry()
    assert len(dialog.cards) == 4 and not dialog.findChildren(QTabWidget)
    assert dialog.cards[0].isChecked()
    for index, card in enumerate(dialog.cards):
        card.click()
        app.processEvents()
        assert dialog.stack.currentIndex() == index
        assert sum(c.isChecked() for c in dialog.cards) == 1
        assert dialog.geometry() == geometry
    viewer = DocumentDialog(dialog, 'LICENSE')
    assert viewer.raw_bytes == (legal_directory() / 'LICENSE').read_bytes()
    viewer = DocumentDialog(dialog, 'THIRD_PARTY_NOTICES.md', third_party=True)
    assert viewer.raw_text.replace('\r\n', '\n') == source_text('THIRD_PARTY_NOTICES.md')
    if viewer.selector.count() > 1:
        viewer.selector.setCurrentIndex(1)
        assert viewer.raw_text and viewer.path.name in viewer.source_label.text()
    with pytest.raises(ValueError):
        DocumentDialog(dialog, "../README.md")
    viewer.paths[0] = Path(__file__)
    viewer.selector.setCurrentIndex(0)
    viewer.load_document()
    assert viewer.raw_text == "Bundled notice unavailable."
    dialog.close()
