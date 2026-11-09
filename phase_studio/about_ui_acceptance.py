"""Opt-in source/frozen About diagnostics using real widgets, never network jobs."""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch


def run(directory):
    from PySide6.QtCore import QRect, Qt, QUrl
    from PySide6.QtGui import QDesktopServices, QFontDatabase, QFontInfo, QScreen
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QTabWidget, QWidget
    from .about_ui import AboutDialog, LegalBrowser, show_about_dialog
    from .legal_content import legal_directory, source_text
    from .ui_branding import create_phase_studio_brand_header
    from .ui_style import apply_phase_studio_style

    output = Path(directory).absolute()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    report = dict(offline=True, controlled_fixtures=True, physical_display=False,
                  platform=app.platformName(), profiles=[], screenshots=[])
    # Reproduce the previously broken initialization order before resolving UI
    # fonts. The backend may initially know only the application branding face.
    first_header = create_phase_studio_brand_header()
    report['fonts_before_ui'] = QFontDatabase.families()
    if os.environ.get('PHASE_STUDIO_ABOUT_UNSTYLED') != '1':
        apply_phase_studio_style(app)

    def settle():
        for _ in range(8):
            app.processEvents()

    def snap(name, widget):
        settle()
        assert widget.isVisible()
        assert widget.grab().save(str(output / (name + '.png')))
        report['screenshots'].append(name)

    def font_info(widget):
        info = QFontInfo(widget.font())
        return dict(requested=widget.font().family(), family=info.family(),
                    point_size=info.pointSizeF(), weight=int(info.weight()))

    def check_fonts(dialog):
        ordinary = [widget for widget in dialog.findChildren(QWidget)
                    if isinstance(widget, (QLabel, LegalBrowser))
                    and widget.objectName() not in ('brandTitle', 'brandSubtitle', 'brandLogo')]
        for widget in ordinary:
            assert QFontInfo(widget.font()).family() not in ('', 'Science Gothic'), widget.objectName()
        brand = dialog.findChild(QLabel, 'brandTitle')
        if brand:
            assert QFontInfo(brand.font()).family() == 'Science Gothic'

    scale = float(os.environ.get('QT_SCALE_FACTOR', '1'))
    viewport = QRect(0, 0, int(1920 / scale), int(1040 / scale))
    report.update(scale=scale, screen_logical=viewport.getRect())
    with patch.object(QScreen, 'availableGeometry', return_value=viewport):
        owner = QWidget()
        owner.setWindowTitle('Controlled About acceptance owner')
        owner.show()
        for jana in (False, True):
            prefix = 'jana' if jana else 'standalone'
            dialog = show_about_dialog(owner, jana=jana)
            settle()
            assert show_about_dialog(owner, jana=jana) is dialog
            assert len(dialog.cards) == 4 and not dialog.findChildren(QTabWidget)
            assert dialog.cards[0].isChecked() and dialog.stack.currentIndex() == 0
            geometry = dialog.geometry()
            assert viewport.contains(dialog.frameGeometry())
            assert 390 <= dialog.height() <= 460 or viewport.height() < 480
            check_fonts(dialog)
            profile = dict(profile=prefix, geometry=geometry.getRect(), dpr=dialog.devicePixelRatioF(),
                           body_font=font_info(dialog.findChild(QLabel, 'aboutCardTitle')),
                           brand_font=font_info(dialog.findChild(QLabel, 'brandTitle')),
                           content_height=dialog.stack.height())
            for index, label in enumerate(('authors', 'license', 'third-party', 'citation')):
                dialog.cards[index].setFocus(Qt.TabFocusReason)
                QTest.keyClick(dialog.cards[index], Qt.Key_Space)
                settle()
                assert dialog.stack.currentIndex() == index
                assert sum(card.isChecked() for card in dialog.cards) == 1
                assert dialog.geometry() == geometry
                snap(prefix + '-' + label, dialog)
            dialog.cards[0].setFocus(Qt.TabFocusReason)
            snap(prefix + '-focus-versus-selection', dialog)
            assert dialog.cards[3].isChecked() and not dialog.cards[0].isChecked()
            # Test the actual citation action, including clipboard content.
            from PySide6.QtWidgets import QPushButton
            next(b for b in dialog.stack.currentWidget().findChildren(QPushButton)
                 if b.text() == 'Copy citation').click()
            assert QApplication.clipboard().text() == dialog.citation
            for name, third in (('LICENSE', False), ('THIRD_PARTY_NOTICES.md', True)):
                viewer = dialog.open_document(name, third_party=third)
                settle()
                assert viewer.parentWidget() is dialog and viewer.isModal()
                assert viewer.raw_bytes == (legal_directory() / name).read_bytes()
                assert viewer.raw_text.replace('\r\n', '\n') == source_text(name)
                check_fonts(viewer)
                if not third:
                    viewer.search.setText('permission')
                    viewer.find_next()
                    assert 'permission' in viewer.browser.textCursor().selectedText().lower()
                    viewer.copy_button.click()
                    assert QApplication.clipboard().text() == viewer.raw_text
                    with patch.object(QDesktopServices, 'openUrl', return_value=True) as opened:
                        viewer.original_button.click()
                        opened.assert_called_once_with(QUrl.fromLocalFile(str(legal_directory() / name)))
                    snap(prefix + '-mit-viewer', viewer)
                    profile['reader_font'] = font_info(viewer.browser)
                    viewer.original_layout.setChecked(True)
                    assert viewer.browser.toPlainText() == viewer.raw_text.replace('\r\n', '\n')
                    viewer.original_layout.setChecked(False)
                else:
                    selected = next((i for i, path in enumerate(viewer.paths) if path.name == 'GFDL-1.3.txt'),
                                    min(1, len(viewer.paths) - 1))
                    viewer.selector.setCurrentIndex(selected)
                    settle()
                    assert viewer.raw_bytes == viewer.path.read_bytes()
                    assert viewer.browser.toPlainText().strip()
                    # Reader reflow changes whitespace only for plain notices.
                    if viewer.path.suffix.lower() != '.md':
                        assert ''.join(viewer.raw_text.split()) == ''.join(viewer.browser.toPlainText().split())
                    assert viewer.browser.geometry().top() - viewer.source_label.geometry().bottom() < 20
                    snap(prefix + '-third-party-viewer', viewer)
                    profile['selected_notice'] = viewer.source
                    profile['notice_count'] = len(viewer.paths)
                QTest.keyClick(viewer, Qt.Key_Escape)
                settle()
                assert not viewer.isVisible() and dialog.isVisible()
                assert dialog.geometry() == geometry
            QTest.keyClick(dialog, Qt.Key_Escape)
            settle()
            assert not dialog.isVisible()
            report['profiles'].append(profile)

        with patch.object(QScreen, 'availableGeometry', return_value=QRect(0, 0, 480, 520)):
            narrow = AboutDialog(owner, jana=False)
            narrow.show()
            settle()
            assert QRect(0, 0, 480, 520).contains(narrow.frameGeometry())
            assert narrow.rect().contains(narrow.close_button.geometry())
            check_fonts(narrow)
            snap('narrow-authors', narrow)
            profile = dict(geometry=narrow.geometry().getRect(),
                           content_scroll=narrow.stack.currentWidget().verticalScrollBar().maximum())
            for label in narrow.findChildren(QLabel, 'aboutCardTitle'):
                bounds = label.fontMetrics().boundingRect(label.rect(), Qt.TextWordWrap, label.text())
                assert bounds.height() <= label.height() + 2, label.text()
            report['narrow'] = profile
            from PySide6.QtWidgets import QPushButton
            action = next(b for b in narrow.stack.currentWidget().findChildren(QPushButton)
                          if b.text() == 'View original authors')
            action.setFocus(Qt.TabFocusReason)
            narrow.stack.currentWidget().ensureWidgetVisible(action)
            snap('narrow-authors-action', narrow)
            narrow.close()
        with patch.object(QScreen, 'availableGeometry', return_value=QRect(0, 0, 640, 360)):
            short = AboutDialog(owner, jana=True)
            short.show()
            settle()
            assert QRect(0, 0, 640, 360).contains(short.frameGeometry())
            assert short.rect().contains(short.close_button.geometry())
            report['short'] = dict(geometry=short.geometry().getRect(), content_height=short.stack.height())
            snap('short-screen-authors', short)
            short.close()
        owner.close()
    first_header.deleteLater()
    originals = ('LICENSE', 'AUTHORS.md', 'CITATION.cff', 'THIRD_PARTY_NOTICES.md')
    report['legal_sha256'] = {name: hashlib.sha256((legal_directory() / name).read_bytes()).hexdigest()
                              for name in originals}
    report['passed'] = True
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    return 0
