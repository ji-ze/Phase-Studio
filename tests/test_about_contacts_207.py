"""Extended contacts use the independent viewer and preserve original credits."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from phase_studio.about_ui import AboutDialog
from phase_studio.legal_content import legal_directory
_application = None

def test_contacts_original_credits_and_stable_geometry():
    global _application
    _application = QApplication.instance() or QApplication([])
    dialog = AboutDialog(None, jana=False)
    dialog.show()
    _application.processEvents()
    viewer = dialog.open_document('AUTHORS.md', contacts=True)
    _application.processEvents()
    text = viewer.browser.toPlainText()
    for value in ('Scientific collaboration', 'Na Slovance 1999/2', '182 00 Prague 8', 'Czech Republic'):
        assert value in text
    expected = {'https://github.com/ji-ze/Phase-Studio', 'https://sharped.fzu.cz/',
        'mailto:sharped@fzu.cz', 'mailto:rohlicek@fzu.cz', 'mailto:zelenka@fzu.cz',
        'mailto:kucerakova@fzu.cz', 'mailto:buk@fzu.cz',
        'mailto:sharped@fzu.cz?subject=SharpED%20scientific%20collaboration', 'https://www.fzu.cz/en'}
    links = set()
    block = viewer.browser.document().begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.charFormat().isAnchor():
                links.add(fragment.charFormat().anchorHref())
            iterator += 1
        block = block.next()
    assert links == expected
    raw = (legal_directory() / 'AUTHORS.md').read_bytes()
    assert viewer.raw_bytes == raw
    viewer.copy_button.click()
    assert QApplication.clipboard().text() == raw.decode('utf8')
    viewer.original_authors.click()
    viewer.original_layout.click()
    assert viewer.browser.toPlainText() == raw.decode('utf8').replace('\r\n', '\n')
    viewer.close()
    geometry = dialog.geometry()
    for card in dialog.cards:
        card.click()
        _application.processEvents()
        assert sum(item.isChecked() for item in dialog.cards) == 1
        assert dialog.geometry() == geometry
    dialog.close()
