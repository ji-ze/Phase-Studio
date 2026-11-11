"""Complete panel text remains reachable without enlarging scientific panels."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QPlainTextEdit,QPushButton
from phase_studio.viewer_metadata import PanelMetadataLabel

_application=None


def test_truncated_panel_metadata_has_mouse_keyboard_and_exact_copy():
    global _application
    _application=QApplication.instance() or QApplication([])
    owner=QWidget();layout=QVBoxLayout(owner);label=PanelMetadataLabel();label.setMaxLines(2);layout.addWidget(label)
    original='Preview: 70 CIF sites; Jana receives 1 native EDMA-selected site. '+('Complete scientific provenance and original source definitions. '*8)
    label.setText(original);owner.resize(300,100);owner.show();_application.processEvents()
    assert '[Details]' in label.text() and label.accessibleName()==original
    QTest.mouseClick(label,Qt.LeftButton);_application.processEvents()
    first=label._details_dialog
    assert first.isVisible() and first.findChild(QPlainTextEdit).toPlainText()==original
    label.setText('A later rendering must not change the open document copy.')
    copy=next(button for button in first.findChildren(QPushButton) if button.text()=='Copy full text')
    copy.click();assert QApplication.clipboard().text()==original
    first.close();_application.processEvents()
    label.setText(original);label.setFocus();QTest.keyClick(label,Qt.Key_Return);_application.processEvents()
    assert label._details_dialog.isVisible()
    label._details_dialog.close();owner.close();owner.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);_application.processEvents()
