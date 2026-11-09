"""Extended contacts use the independent viewer and preserve original credits."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QScreen
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QWidget
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


def test_keyboard_scroll_and_return_from_document(monkeypatch):
    global _application
    _application = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.show()
    def settle():
        for _ in range(10):
            _application.processEvents()
    for width, height in ((480, 520), (640, 360)):
        monkeypatch.setattr(QScreen, 'availableGeometry', lambda self: QRect(0, 0, width, height))
        dialog = AboutDialog(owner, jana=False)
        dialog.show()
        settle()
        geometry = dialog.geometry()
        for index, card in enumerate(dialog.cards):
            card.setFocus(Qt.TabFocusReason)
            QTest.keyClick(card, Qt.Key_Return)
            settle()
            assert dialog.stack.currentIndex() == index
            assert dialog.geometry() == geometry
        dialog.cards[0].click()
        dialog.cards[0].setFocus(Qt.TabFocusReason)
        panel = dialog.stack.widget(0)
        action = next(button for button in panel.findChildren(QPushButton)
                      if button.text() == 'Contacts and credits')
        for _ in range(20):
            QTest.keyClick(_application.focusWidget(), Qt.Key_Tab)
            settle()
            if _application.focusWidget() is action:
                break
        assert _application.focusWidget() is action
        assert panel.viewport().rect().contains(QRect(action.mapTo(panel.viewport(), QPoint()), action.size()))
        QTest.keyClick(action, Qt.Key_Space)
        settle()
        assert dialog.viewer.isVisible()
        QTest.keyClick(dialog.viewer, Qt.Key_Escape)
        settle()
        assert _application.focusWidget() is action
        assert dialog.geometry() == geometry
        dialog.close()
    owner.close()
