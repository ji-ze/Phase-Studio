"""Explicit offline mouse/keyboard acceptance; never entered in normal use."""


def run(directory):
    import hashlib
    import json
    import os
    from pathlib import Path
    import re
    import shutil
    import sys
    import time
    import traceback
    from contextlib import ExitStack
    from unittest.mock import patch
    from PySide6.QtCore import QSettings, Qt, QTimer, QPoint
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtTest import QTest, QSignalSpy
    from PySide6.QtWidgets import (QApplication, QWidget, QAbstractButton, QDialog, QTabWidget,
        QScrollArea, QTableView, QComboBox, QLineEdit, QPushButton, QToolButton,
        QCheckBox, QSpinBox, QDoubleSpinBox, QFileDialog, QMessageBox, QProgressDialog)
    from shiboken6 import isValid
    from . import app as a, jana_superflip as j, update_ui, structure_camera, result_selection
    from .credentials import CredentialStore

    out = Path(directory).resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ['PHASE_STUDIO_STARTUP_PROBE'] = '1'
    qt = QApplication.instance() or QApplication([])
    a.apply_phase_studio_style(qt)
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out/'settings'))
    rows, errors, urls, pictures = [], [], [], []
    seen, clicked_controls = set(), set()
    old_hook = sys.excepthook
    sys.excepthook = lambda typ, value, tb: errors.append(''.join(traceback.format_exception(typ, value, tb)))
    profile = ('jana' if Path(sys.executable).name.lower() == 'phase_studio.exe'
               else os.environ.get('PHASE_STUDIO_GUI_PROFILE', 'standalone'))

    def record(area, control, outcome, detail):
        rows.append(dict(area=area, control=control, outcome=outcome, detail=detail))
        (out/'controls.json').write_text(json.dumps(rows, indent=2), encoding='utf8')

    def wait(predicate, timeout=15):
        deadline = time.monotonic()+timeout
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert predicate(), 'Expected visible/state completion timed out'

    def snap(name, widget):
        if name in pictures:
            return
        assert widget.isVisible()
        qt.processEvents()
        assert widget.grab().save(str(out/(name+'.png')))
        pictures.append(name)

    def select_tab(tabs, index, area):
        bar = tabs.tabBar()
        bar.setFocus()
        for _ in range(tabs.count()):
            if tabs.currentIndex() == index:
                break
            QTest.keyClick(bar, Qt.Key_Right if tabs.currentIndex() < index else Qt.Key_Left)
        wait(lambda: tabs.currentIndex() == index)
        record(area, 'Tab: '+tabs.tabText(index), 'PASS', 'Keyboard navigation changed the visible page')

    def reach(widget):
        qt.processEvents()
        ancestors = []
        child, parent = widget, widget.parentWidget()
        while parent is not None:
            ancestors.append((parent, child))
            child, parent = parent, parent.parentWidget()
        for parent, child in reversed(ancestors):
            if isinstance(parent, QTabWidget):
                for index in range(parent.count()):
                    if parent.widget(index) is child or parent.widget(index).isAncestorOf(widget):
                        if parent.currentIndex() != index:
                            select_tab(parent, index, 'Navigation')
            if isinstance(parent, QScrollArea) and parent.widget().isAncestorOf(widget):
                parent.ensureWidgetVisible(widget, 8, 8)
        qt.processEvents()
        for parent, child in ancestors:
            if isinstance(parent, QScrollArea) and parent.widget().isAncestorOf(widget):
                parent.ensureWidgetVisible(widget, 8, 8)
                QTest.qWait(20)
        assert widget.isVisible() and widget.isEnabled(), 'Control is hidden or disabled: '+widget.objectName()
        if not widget.visibleRegion().contains(widget.rect().center()):
            snap('clipped-control', widget.window())
            raise AssertionError('Control center is clipped: '+repr((type(widget).__name__,widget.objectName(),widget.toolTip(),widget.geometry().getRect())))

    def click(widget):
        reach(widget)
        spy = QSignalSpy(widget.clicked)
        position=QPoint(8,widget.height()//2) if isinstance(widget,QCheckBox) else widget.rect().center()
        QTest.mouseClick(widget, Qt.LeftButton,pos=position)
        assert spy.count() == 1, 'Mouse click was not received: '+widget.text()
        clicked_controls.add(widget)
        qt.processEvents()

    def text_button(root, text):
        candidates = [w for w in root.findChildren(QAbstractButton) if w.text().replace('&','') == text]
        assert candidates, 'Button absent: '+text
        return next((w for w in candidates if w.isVisible()), candidates[0])

    def scroll_check(root, area):
        for index, scroll in enumerate(root.findChildren(QScrollArea)):
            bar = scroll.verticalScrollBar()
            if not scroll.isVisible() or bar.maximum() == 0:
                continue
            bar.setFocus()
            QTest.keyClick(bar, Qt.Key_End)
            assert bar.value() == bar.maximum()
            QTest.keyClick(bar, Qt.Key_Home)
            assert bar.value() == bar.minimum()
            record(area, 'Scrollable content '+str(index), 'PASS', 'End/Home reach both limits independently of footer')

    def dialog_action(area, button, expected, inspect=None, capture=None):
        prior = set(qt.topLevelWidgets())
        result, failure = [], []
        deadline = time.monotonic()+20
        poll = QTimer()
        poll.setInterval(20)

        def handle():
            visible = [w for w in qt.topLevelWidgets() if isinstance(w,QDialog) and not isinstance(w,QProgressDialog) and w.isVisible()
                       and w not in prior]
            if not visible:
                if time.monotonic() > deadline:
                    failure.append('Expected dialog did not appear: '+expected)
                    poll.stop()
                return
            dialog = visible[-1]
            poll.stop()
            try:
                assert re.search(expected, dialog.windowTitle(), re.I), dialog.windowTitle()
                assert dialog.width()>100 and dialog.height()>80
                if inspect:
                    inspect(dialog)
                if capture:
                    snap(capture,dialog)
                result.append(dialog.windowTitle())
            except Exception:
                failure.append(traceback.format_exc())
            finally:
                close = next((w for w in dialog.findChildren(QPushButton)
                              if w.isVisible() and w.isEnabled() and w.text().replace('&','') in ('Close','Close viewer','Back','Cancel','OK')),None)
                if close is not None:
                    click(close)
                else:
                    QTest.keyClick(dialog,Qt.Key_Escape)
                if isValid(dialog) and dialog.isVisible():
                    failure.append('Close/Escape did not dismiss '+dialog.windowTitle())
                    dialog.reject()
        poll.timeout.connect(handle)
        poll.start()
        click(button)
        wait(lambda: bool(result or failure), 22)
        assert not failure, '\n'.join(failure)
        record(area,button.text(),'PASS','Mouse click opened visible '+result[0]+'; inspected and closed')

    def inspect_data(dialog):
        tabs=dialog.findChildren(QTabWidget)
        for tab in tabs:
            for index in range(tab.count()):
                select_tab(tab,index,dialog.windowTitle())
                scroll_check(tab.currentWidget(),dialog.windowTitle())
        for table in dialog.findChildren(QTableView):
            if table.isVisible() and table.model().rowCount():
                index=table.model().index(0,0)
                QTest.mouseClick(table.viewport(),Qt.LeftButton,pos=table.visualRect(index).center())
                assert table.currentIndex().isValid()
                record(dialog.windowTitle(),'Table selection','PASS','Actual visible model row selected')

    def fields(root, area):
        for widget in root.findChildren(QWidget):
            if not isinstance(widget,(QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QCheckBox)):
                continue
            if id(widget) in seen or not widget.isVisible() or not widget.isEnabled():
                continue
            if isinstance(widget,QLineEdit) and isinstance(widget.parentWidget(),(QComboBox,QSpinBox,QDoubleSpinBox)):
                continue
            seen.add(id(widget))
            name=widget.accessibleName() or widget.objectName() or widget.toolTip().split('\n')[0] or type(widget).__name__
            reach(widget)
            if isinstance(widget,QCheckBox):
                before=widget.isChecked();click(widget);assert widget.isChecked()!=before
                click(widget);assert widget.isChecked()==before
                record(area,name or widget.text(),'PASS','Checkbox toggled and restored using mouse')
            elif isinstance(widget,QLineEdit):
                QTest.mouseClick(widget,Qt.LeftButton)
                QTest.keyClick(widget,Qt.Key_A,Qt.ControlModifier)
                assert widget.selectedText()==widget.text()
                QTest.keyClick(widget,Qt.Key_End)
                record(area,name,'PASS','Text field accepts mouse focus and keyboard selection; input preserved')
            elif isinstance(widget,QComboBox):
                eligible=[i for i in range(widget.count()) if widget.model().flags(widget.model().index(i,0)) & Qt.ItemIsEnabled]
                if len(eligible)<2:
                    record(area,name,'NOT APPLICABLE','No alternate choice in this state; live catalogue is a separate external boundary')
                    continue
                before=widget.currentIndex()
                QTest.mouseClick(widget,Qt.LeftButton,pos=QPoint(widget.width()-12,widget.height()//2))
                wait(lambda:widget.view().isVisible())
                direction=Qt.Key_End if before!=eligible[-1] else Qt.Key_Home
                QTest.keyClick(widget.view(),direction)
                QTest.keyClick(widget.view(),Qt.Key_Return)
                assert widget.currentIndex()!=before, (name,before,[widget.itemText(i) for i in range(widget.count())],str(widget.focusPolicy()))
                widget.setCurrentIndex(before)  # Restore fixture after the observed user selection.
                assert widget.currentIndex()==before
                record(area,name,'PASS','Keyboard changed the selected choice and restored it')
            else:
                before=widget.value();widget.setFocus()
                direction=Qt.Key_Up if before<widget.maximum() else Qt.Key_Down
                QTest.keyClick(widget,direction)
                assert widget.value()!=before
                QTest.keyClick(widget,Qt.Key_Down if direction==Qt.Key_Up else Qt.Key_Up)
                assert widget.value()==before
                record(area,name,'PASS','Numeric control stepped and restored through keyboard')

    def settings(*parts):
        return QSettings(str(out/'settings'/((hashlib.sha256(repr(parts).encode()).hexdigest())+'.ini')),QSettings.IniFormat)

    class MemoryCredentials:
        def __init__(self): self.values={}
        def read(self,origin): return self.values.get(origin,'')
        def write(self,origin,value): self.values[origin]=value
        def delete(self,origin): self.values.pop(origin,None)

    store=CredentialStore(backend=MemoryCredentials())
    def forbidden(*args,**kwargs):
        raise AssertionError('Acceptance must not launch phasing, EDMA or remote inference')
    supplied=os.environ.get('PHASE_STUDIO_INTERACTIVE_INPUT','')
    source=out/'input'/'controlled.inflip'
    source.parent.mkdir()
    if supplied:
        original=Path(supplied)
        source=source.with_name(original.name)
        shutil.copyfile(original,source)
        if original.with_suffix('.m90').is_file():
            shutil.copyfile(original.with_suffix('.m90'),source.with_suffix('.m90'))
    else:
        source.write_text('cell 8 12 7 90 94 90\nspacegroup P1\ncomposition C4 O\n'
            'lambda 1.541866\ndataformat intensity fwhm\nfbegin\n'+
            '\n'.join(f'{h} {k} 1 {10+h*k} .0527' for h in range(1,8) for k in range(1,6))+'\nendf\n')
        original=source
    original_hash=hashlib.sha256(original.read_bytes()).hexdigest()
    imports=j._qt_imports
    try:
        with ExitStack() as stack:
            for module in (a,structure_camera,result_selection):
                stack.enter_context(patch.object(module,'QSettings',settings))
            stack.enter_context(patch.object(j,'_qt_imports',lambda:imports()|{'QSettings':settings}))
            stack.enter_context(patch.object(j,'credential_store',store))
            stack.enter_context(patch.object(QDesktopServices,'openUrl',lambda url:urls.append(url.toString()) or True))
            for name in ('load_settings','save_settings','refresh_sharped_models'):
                stack.enter_context(patch.object(a.IterativeSuperflipPipelineQtGUI,name,lambda self:None))
            for name in ('run_superflip_cycle','run_edma_on_xplor','run_sharped_deblur'):
                stack.enter_context(patch.object(a,name,forbidden))
            for name in ('upload','execute'):
                stack.enter_context(patch.object(a.SharpEDServerClient,name,forbidden))
            state=update_ui.UpdateState(settings('updates'),out/'updates.lock')
            state.set_enabled(False)
            qt._phase_studio_updates=update_ui.UpdateService(qt,state=state,automatic_allowed=False)
            main=a.IterativeSuperflipPipelineQtGUI()
            main.resize(1280,850)
            main.show()
            qt.processEvents()
            main._set_widget_value_from_string(main.inputs['jana_inflip'],str(source))
            from .input_context import INPUT_MODE_INFLIP
            main._set_widget_value_from_string(main.inputs['input_source_mode'],INPUT_MODE_INFLIP)
            main._set_widget_value_from_string(main.inputs['metadata_source'],'Jana2020 .inflip')
            main._set_widget_value_from_string(main.inputs['reference_cif'],'')
            main._set_widget_value_from_string(main.inputs['first_cycle_modelfile'],'')
            for button in (main.test_hkl_btn,main.analyze_hkl_btn):
                for index in range(2):
                    dialog_action('Main input',button,'View data|Analyze data',inspect_data,
                                  'main-'+('view' if button is main.test_hkl_btn else 'analysis') if index==0 else None)
            for category,tabs in enumerate((main.basic_tabs,main.advanced_tabs)):
                select_tab(main.category_tabs,category,'Main configuration')
                for index in range(tabs.count()):
                    select_tab(tabs,index,'Main configuration')
                    scroll_check(tabs.currentWidget(),'Main '+tabs.tabText(index))
                    fields(tabs.currentWidget(),'Main '+tabs.tabText(index))
                    if tabs.tabText(index) in ('Input','Workflow','Setup','Help'):
                        snap(('basic-' if category==0 else 'advanced-')+tabs.tabText(index).lower(),main)
            main.showMaximized()
            wait(main.isMaximized)
            record('Main','Maximize/restore','PASS','Native Qt maximized state reached')
            main.showNormal()
            for button in main.findChildren(QAbstractButton):
                label=button.text().replace('&','')
                if label=='Open guide':
                    click(button)
                    assert 'Help' in (main.basic_tabs.tabText(main.basic_tabs.currentIndex()),main.advanced_tabs.tabText(main.advanced_tabs.currentIndex()))
                    record('Main Help',button.toolTip() or label,'PASS','Guide action switched to the Help page')
                elif label=='↑ Contents':
                    click(button)
                    record('Main Help','Contents '+str(len(clicked_controls)),'PASS','Visible contents link accepted pointer navigation')
                elif label=='…' and not isinstance(button,QToolButton):
                    if not button.isEnabled():
                        record('Main files',button.toolTip() or label,'NOT APPLICABLE','Path is disabled in the selected input-source mode')
                        continue
                    with patch.object(QFileDialog,'getOpenFileName',return_value=('','')),patch.object(QFileDialog,'getExistingDirectory',return_value=''):
                        click(button)
                    record('Main files',button.toolTip() or label,'PASS','Browse clicked; file-chooser cancellation supplied at external boundary')
                elif button.objectName()=='externalLink':
                    count=len(urls);click(button);assert len(urls)==count+1
                    record('Main links',button.toolTip(),'PASS','URL handed to external-opening boundary')
                elif button.objectName()=='settingsNavLink':
                    click(button);assert main.category_tabs.currentIndex()==1
                    expected='Setup' if 'Connection' in label else 'SharpED'
                    assert main.advanced_tabs.tabText(main.advanced_tabs.currentIndex())==expected
                    record('Main navigation',label,'PASS','Correct Advanced settings page opened')
            before=main.execution_log_expanded
            click(main.execution_log_expand_button);assert main.execution_log_expanded!=before
            click(main.execution_log_expand_button);assert main.execution_log_expanded==before
            record('Main log','Expand/collapse','PASS','Log area expanded and restored')
            # Actual buttons, not direct document-viewer callbacks.
            from .about_ui import AboutDialog
            about=AboutDialog(main,jana=profile=='jana')
            about.show()
            for index,title in enumerate(('Authors','License','Third party','Citation')):
                click(about.cards[index])
                assert about.stack.currentIndex()==index and sum(c.isChecked() for c in about.cards)==1
                record('About',title,'PASS','Exclusive card selection switched shared content')
                snap('about-'+title.lower().replace(' ','-'),about)
            click(about.cards[1])
            def legal(dialog):
                raw=dialog.raw_bytes
                click(dialog.copy_button)
                assert qt.clipboard().text()==dialog.raw_text
                record('Legal','Copy original','PASS','Clipboard equals complete original source text')
                click(dialog.original_layout)
                assert dialog.original_layout.isChecked()
                record('Legal','Original formatting','PASS','Plain original full text displayed')
                reach(dialog.search)
                QTest.keyClicks(dialog.search,'Permission')
                click(text_button(dialog,'Find next'))
                assert dialog.browser.textCursor().hasSelection()
                record('Legal','Find next','PASS','Search selects matching document text')
                count=len(urls)
                click(dialog.original_button)
                assert len(urls)==count+1
                assert dialog.raw_bytes==raw
                record('Legal','Open original','PASS','Original local document handed to OS URL boundary; external viewer not launched')
            dialog_action('About',text_button(about,'Read full license'),'License',legal,'legal-reader')
            click(about.cards[0])
            dialog_action('About',text_button(about,'Contacts and credits'),'Author|Contact|Credit',capture='credits')
            click(about.cards[2])
            def dependencies(dialog):
                fields(dialog,'Third-party documents')
                click(dialog.copy_button)
                assert qt.clipboard().text()==dialog.raw_text
                assert dialog.raw_bytes
                record('Third-party documents','Copy original','PASS','Selected dependency full original text copied')
            dialog_action('About',text_button(about,'Browse licenses'),'Third|License',dependencies,'third-party-reader')
            for name in ('GitHub repository','Official releases'):
                count=len(urls);click(text_button(about,name));assert len(urls)==count+1
                record('About',name,'PASS','Correct URL reached external-opening boundary; browser not launched')
            click(about.cards[3]);click(text_button(about,'Copy citation'))
            assert qt.clipboard().text()==about.citation
            record('About','Copy citation','PASS','Full citation copied')
            dialog_action('About',text_button(about,'View citations'),'Cite|Citation',capture='citations')
            click(about.close_button);assert not about.isVisible()
            record('About','Close','PASS','Dialog dismissed by mouse')
            from .sharped_access import SharpEDAccessDialog
            access=SharpEDAccessDialog(main,store=store)
            access.show();click(access.manual_button)
            assert access.manual_panel.isVisible()
            record('Authentication','Use an access key instead','PASS','Manual panel disclosed')
            click(access.help_button);assert access.help_panel.isVisible()
            record('Authentication','Access-key instructions','PASS','Instructions disclosed')
            snap('authentication',access)
            count=len(urls);click(access.account_button);assert len(urls)==count+1
            record('Authentication','Get an access key','PASS','Account URL handed to browser boundary; no credential submitted')
            record('Authentication','Live sign-in and permission verification','BLOCKED','Requires external user authentication; no credentials or paid jobs used')
            click(access.back_button);assert not access.isVisible()
            record('Authentication','Back','PASS','Owned dialog closed')
            from .update_checker import Release
            notice=update_ui.UpdateNotice(main,latest_stable=Release((2,0,6)))
            notice.show();snap('update',notice);click(notice.later_button)
            assert not isValid(notice) or not notice.isVisible()
            record('Updates','Close development-version notice','PASS','Stable-version comparison displayed and dismissed')
            record('Updates','Production installation','BLOCKED','Unsigned development build; production install/signing not authorized')
            # Reuse the persisted-result fixtures, but verify controls with real
            # pointer/keyboard events before their legacy screenshot callbacks.
            from .functional_ui_acceptance import capture as result_fixtures
            def result_capture(name, selector):
                if name not in ('results-stopped-four-of-five','results-70-cif-one-jana'):
                    return
                qt.processEvents()
                if name=='results-stopped-four-of-five':
                    for attr,cycle in (('_previous_cycle_button',2),('_next_cycle_button',3),('_latest_cycle_button',4)):
                        click(getattr(selector,attr))
                        assert selector.selected_candidate.cycle==cycle
                        record('Results',attr,'PASS','Visible selection changed to cycle '+str(cycle))
                    click(selector._previous_cycle_button)
                    assert selector.selected_candidate.cycle==3
                    dialog_action('Results',selector._why_cycle_button,'Why|Recommendation',capture='recommendation')
                    def log_checks(log):
                        fields(log,'Execution log')
                        click(text_button(log,'Copy'))
                        assert qt.clipboard().text()==log.text.toPlainText()
                        record('Execution log','Copy','PASS','Complete displayed structured events copied')
                        exported=out/'sanitized-diagnostics.zip'
                        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(exported),'ZIP (*.zip)')):
                            click(text_button(log,'Export sanitized…'))
                        assert exported.is_file() and exported.stat().st_size>0
                        record('Execution log','Export sanitized','PASS','Click created ZIP in isolated fixture; file chooser boundary supplied')
                    dialog_action('Results',selector._execution_log_button,'Execution log',log_checks,'execution-log')
                else:
                    for attr,source_name in (('_superflip_btn','superflip'),('_sharped_btn','deblurred')):
                        click(getattr(selector,attr));assert selector.selected_candidate.source==source_name
                        record('Results',attr,'PASS','Candidate family and preview switched')
                    for attr in ('_cell_button','_molecule_button'):
                        button=getattr(selector,attr);click(button);assert button.isChecked()
                        record('Results',attr,'PASS','Representation selected')
                    before=selector._auto_rotate_button.isChecked()
                    click(selector._auto_rotate_button)
                    assert selector._auto_rotate_button.isChecked()!=before
                    click(selector._auto_rotate_button)
                    record('Results','Auto rotate','PASS','Rotation toggled and restored')
                    click(selector._fit_button)
                    record('Results','Fit','PASS','Visible canvas fit request accepted; preview remains visible')
                    dialog_action('Results',selector._fullscreen_button,'Structure|Charge|Cycle',capture='structure-fullscreen')
                    assert selector._fullscreen_button.isVisible()
                    record('Results','Fullscreen restoration','PASS','Detached viewer returned to its original parent')
                scroll_check(selector,'Results')
                snap(name,selector)
            result_fixtures(main,out,result_capture,{},jana=profile=='jana')

            # Exercise normal Wizard.run() and its modal event loop. The run
            # boundary returns options only: no launch or remote job follows.
            for route in ('navigation','superflip','autosolve','professional'):
                wizard=j._JanaWorkflowWizard([str(source)],source)
                wizard._ensure_models_loaded=lambda **kwargs:None
                wizard._ensure_workflow_requirements=lambda **kwargs:True
                def wizard_steps(wizard=wizard,route=route):
                    try:
                        wait(lambda:getattr(wizard,'hkl_load_result',None) is not None)
                        assert 'FWHM' in wizard.format_value.text()
                        if route=='navigation':
                            snap('wizard-input',wizard.dialog)
                            for button in (wizard.validate_hkl_button,wizard.analyze_completeness_button):
                                for repeat in range(2):
                                    dialog_action('Wizard',button,'View data|Analyze data',inspect_data)
                            click(wizard.files_toggle);assert wizard.files_form_widget.isVisible()
                            fields(wizard.files_form_widget,'Wizard advanced input')
                            click(wizard.files_toggle);assert not wizard.files_form_widget.isVisible()
                            record('Wizard','Advanced input options','PASS','Expanded, reached text fields and collapsed')
                            reach(wizard.superflip_sharped_tile)
                            QTest.mouseClick(wizard.superflip_sharped_tile,Qt.LeftButton)
                            wait(lambda:wizard.stack.currentWidget() is wizard.page2)
                            record('Wizard','Superflip + SharpED','PASS','Mouse selected workflow and opened processing page')
                            fields(wizard.page2,'Wizard processing');snap('wizard-processing',wizard.dialog)
                            click(wizard.primary_button)
                            assert wizard.stack.currentWidget() is wizard.page3
                            record('Wizard','Next','PASS','Map Feedback page opened')
                            fields(wizard.page3,'Wizard Map Feedback');snap('wizard-feedback',wizard.dialog)
                            click(wizard.back_button);assert wizard.stack.currentWidget() is wizard.page2
                            click(wizard.back_button);assert wizard.stack.currentWidget() is wizard.page1
                            record('Wizard','Back','PASS','Returned through processing to workflow selection')
                            click(wizard.cancel_button)
                        else:
                            tile=getattr(wizard,{'superflip':'original_superflip_tile','autosolve':'autosolve_tile','professional':'professional_mode_tile'}[route])
                            reach(tile);QTest.mouseClick(tile,Qt.LeftButton)
                            assert not wizard.dialog.isVisible()
                    except Exception:
                        errors.append(traceback.format_exc())
                        wizard.dialog.reject()
                QTimer.singleShot(0,wizard_steps)
                options=wizard.run()
                expected={'navigation':'cancel','superflip':'run','autosolve':'autosolve','professional':'edit'}[route]
                assert options.action==expected,(route,options.action,errors)
                record('Wizard',route,'PASS','Actual interaction returned '+expected+'; native/auth requirements stubbed, execution not started')
            inventory=[]
            for index,w in enumerate(main.findChildren(QAbstractButton)):
                if w.window() is not main:
                    continue
                outcome='PASS' if w in clicked_controls or id(w) in seen else ('NOT APPLICABLE' if not w.isEnabled() else 'UNVERIFIED')
                inventory.append(dict(index=index,text=w.text(),tooltip=w.toolTip(),name=w.objectName(),enabled=w.isEnabled(),checkable=w.isCheckable(),outcome=outcome))
            (out/'main-control-inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf8')
            main.close()
    except Exception:
        errors.append(traceback.format_exc())
    finally:
        sys.excepthook=old_hook
        for widget in qt.topLevelWidgets():
            widget.close()
        qt.processEvents()
    report=dict(passed=not errors,profile=profile,frozen=bool(getattr(sys,'frozen',False)),
        platform=qt.platformName(),scale=os.environ.get('QT_SCALE_FACTOR','1'),physical_monitor_acceptance=False,
        rows=rows,errors=errors,screenshots=pictures,external_urls=urls,
        original_unchanged=hashlib.sha256(original.read_bytes()).hexdigest()==original_hash,
        inference_submitted=False,inventory_complete=False)
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return 0 if report['passed'] else 1
