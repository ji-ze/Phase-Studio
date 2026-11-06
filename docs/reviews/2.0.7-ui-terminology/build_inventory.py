"""Read-only UI inventory. Run with repository build Python, offscreen Qt.

Conservative static candidates are explicitly separated from runtime observations;
an extracted literal is not automatically a verified visible message.
"""
import ast
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
OUT=Path(os.environ.get('PHASE_STUDIO_TERMINOLOGY_OUTPUT',str(ROOT/'build/ui-terminology-current')))
OUT.mkdir(parents=True,exist_ok=True)

def write(name,value):
    (OUT/name).write_text(value,encoding='utf8')

def cell(value):
    return str(value).replace('|','\\|').replace('\n','<br>').replace('\r','')

def main():
    import faulthandler
    faulthandler.dump_traceback_later(30,repeat=True)
    literals=[];calls=[];backend=[]
    for path in sorted((ROOT/'phase_studio').glob('*.py')):
        source=path.read_text(encoding='utf8');tree=ast.parse(source);source_lines=source.splitlines(keepends=True)
        def segment(node):
            lines=source_lines[node.lineno-1:node.end_lineno]
            if len(lines)==1:return lines[0].encode('utf8')[node.col_offset:node.end_col_offset].decode('utf8')
            lines[0]=lines[0].encode('utf8')[node.col_offset:].decode('utf8')
            lines[-1]=lines[-1].encode('utf8')[:node.end_col_offset].decode('utf8')
            return ''.join(lines)
        parents={child:node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name=='RunConfig':
                backend.append({'source':str(path.relative_to(ROOT)),'line':node.lineno,'definition':segment(node)})
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr.startswith('_add_'):
                calls.append({'source':str(path.relative_to(ROOT)),'line':node.lineno,'call':segment(node)})
            if not isinstance(node,(ast.Constant,ast.JoinedStr)):continue
            parent=parents.get(node)
            if isinstance(parent,ast.JoinedStr):continue
            if isinstance(node,ast.Constant):
                if not isinstance(node.value,str) or not node.value.strip():continue
                if isinstance(parent,ast.Expr) and any(isinstance(parents.get(parent),t) for t in (ast.FunctionDef,ast.ClassDef,ast.Module)):
                    continue # docstrings, not messages
                text=node.value;dynamic=False
            else:text=segment(node);dynamic=True
            ancestors=[];cur=node
            while cur in parents:
                cur=parents[cur];ancestors.append(cur)
            symbol='.'.join(reversed([a.name for a in ancestors if isinstance(a,(ast.FunctionDef,ast.ClassDef))]))
            context=next((segment(a.func) for a in ancestors if isinstance(a,ast.Call)),'literal')
            # Retain every literal, including uncertain candidates, for completeness
            # accounting; only high-confidence user-facing contexts enter main table.
            visible=bool(re.search(r'(QLabel|QPushButton|QCheckBox|QRadioButton|QAction|QGroupBox|QMessageBox|setText|setToolTip|setWindowTitle|setPlaceholderText|addTab|addAction|addItem|addItems|set_title|set_xlabel|set_ylabel|legend|setHorizontalHeader|_add_|_help|warning|critical|information|self\.log|ValueError|RuntimeError)',context or ''))
            visible=visible or 'TOOLTIP' in source_lines[node.lineno-1] or any(isinstance(a,ast.Assign) and any('TOOLTIP' in ast.unparse(t) for t in a.targets) for a in ancestors)
            entry={'source':str(path.relative_to(ROOT)),'line':node.lineno,'symbol':symbol,'context':context,'text':text,'dynamic':dynamic,
                'classification':'static user-facing candidate' if visible else 'unclassified literal; may be internal',
                'assessment':'Not verified','scientific_meaning':'See enclosing implementation; individual semantic review pending'}
            literals.append(entry)
    print('Static extraction complete',flush=True)
    from PySide6.QtWidgets import QApplication,QWidget,QComboBox,QFormLayout,QLabel,QSpinBox,QDoubleSpinBox,QCheckBox,QTabWidget,QTableWidget
    from PySide6.QtGui import QAction
    from phase_studio import app as a
    from phase_studio.autosolve_window import AutosolveWindow
    import test_jana_completion as fixture
    qt=QApplication.instance() or QApplication([])
    runtime=[];settings=[];presets={};secondary=[];registered=set()
    def inspect(window,screen):
        for obj in [window]+window.findChildren(QWidget)+window.findChildren(QAction):
            if isinstance(obj,(QComboBox,QSpinBox,QDoubleSpinBox,QCheckBox)) and id(obj) not in registered:
                control=dict(screen=screen,control=type(obj).__name__,object_name=obj.objectName(),
                    label=obj.text() if isinstance(obj,QCheckBox) else obj.accessibleName(),
                    tooltip=obj.toolTip(),enabled=obj.isEnabled(),explicitly_hidden=obj.isHidden(),
                    assessment='Not verified; secondary runtime control occurrence, not a unique setting identity')
                if isinstance(obj,QComboBox):control['options']=[dict(text=obj.itemText(i),internal=obj.itemData(i)) for i in range(obj.count())]
                if isinstance(obj,(QSpinBox,QDoubleSpinBox)):
                    control.update(value=obj.value(),minimum=obj.minimum(),maximum=obj.maximum(),step=obj.singleStep(),
                        decimals=obj.decimals() if isinstance(obj,QDoubleSpinBox) else 0,suffix=obj.suffix(),special_value_text=obj.specialValueText())
                secondary.append(control)
            for prop in ('text','title','windowTitle','toolTip','placeholderText','statusTip','accessibleName','accessibleDescription'):
                getter=getattr(obj,prop,None)
                if not callable(getter):continue
                try:value=getter()
                except TypeError:continue
                if isinstance(value,str) and value:
                    runtime.append(dict(screen=screen,element=type(obj).__name__,object_name=obj.objectName(),property=prop,text=value,assessment='Not verified'))
            if isinstance(obj,QComboBox):
                for index in range(obj.count()):runtime.append(dict(screen=screen,element='QComboBox item',property=str(index),text=obj.itemText(index),internal_value=obj.itemData(index),assessment='Not verified'))
            if isinstance(obj,QTabWidget):
                for index in range(obj.count()):runtime.append(dict(screen=screen,element='Tab',property=str(index),text=obj.tabText(index),assessment='Not verified'))
            if isinstance(obj,QTableWidget):
                for index in range(obj.columnCount()):
                    header=obj.horizontalHeaderItem(index)
                    if header:runtime.append(dict(screen=screen,element='Table header',property=str(index),text=header.text(),assessment='Not verified'))
    with patch.multiple(a.IterativeSuperflipPipelineQtGUI,load_settings=lambda self:None,save_settings=lambda self:None,refresh_sharped_models=lambda self:None):
        win,results=fixture.build_window(a);win.results=results;win.timer.stop();print('Main constructed',flush=True)
        registered.update(id(widget) for widget in win.inputs.values())
        inspect(win,'Shared main window / standalone fixture')
        for key,widget in win.inputs.items():
            labels=[]
            for form in win.findChildren(QFormLayout):
                label=form.labelForField(widget)
                if isinstance(label,QLabel):labels.append(label.text())
            if isinstance(widget,QCheckBox):labels=[widget.text()]
            if not labels and key in win.input_labels:labels=[win.input_labels[key].text()]
            entry=dict(key=key,label=' / '.join(labels),control=type(widget).__name__,location='Main configuration; see source helper call',
                application_default=win._setting_origins.records.get(key,{}).get('application_default'),
                displayed_value=win._widget_value_as_string(widget) if not re.search('token|password',key,re.I) else '<not inspected>',
                tooltip=widget.toolTip(),enabled=widget.isEnabled(),explicitly_hidden=widget.isHidden(),
                unit='See label/tooltip; not inferred',persistence='inputs/'+key+' via existing load_settings/save_settings; secret storage is separate',
                scientific_meaning=a.INPUT_TOOLTIPS.get(key,''),backend='get_config + RunConfig + source references in settings-source.json; per-setting verified mapping pending',
                dependencies='Conditional source branches in settings-source.json; not exhaustively exercised',assessment='Not verified')
            if isinstance(widget,QComboBox):entry['options']=[{'text':widget.itemText(i),'internal':widget.itemData(i) if widget.itemData(i) is not None else widget.itemText(i)} for i in range(widget.count())]
            if isinstance(widget,(QSpinBox,QDoubleSpinBox)):
                entry.update(minimum=widget.minimum(),maximum=widget.maximum(),step=widget.singleStep(),decimals=widget.decimals() if isinstance(widget,QDoubleSpinBox) else 0,suffix=widget.suffix(),prefix=widget.prefix(),special_value_text=widget.specialValueText())
            settings.append(entry)
        original={key:win._widget_value_as_string(w) for key,w in win.inputs.items() if not re.search('token|password',key,re.I)}
        for name in ('Recommended','Custom','MOF atomic resolution','MOF medium resolution','small molecule','inorganic'):
            for key,value in original.items():win._set_widget_value_from_string(win.inputs[key],value)
            win._apply_workflow_preset(name)
            presets[name]={key:win._widget_value_as_string(win.inputs[key]) for key in original if win._widget_value_as_string(win.inputs[key])!=original[key]}
        print('Settings captured',flush=True)
        for context in ('standalone','jana'):
            opened=[]
            from PySide6.QtWidgets import QDialog
            with patch.object(a.ResultSelectionDialog,'exec',lambda dialog:opened.append(dialog) or QDialog.Rejected):win.open_result_selector(context)
            if opened:inspect(opened[0],'Result Selection / '+context);opened[0]._rotate_timer.stop();opened[0].close()
        autosolve=AutosolveWindow(win,'A',workflow_name='Superflip + SharpED');autosolve._refresh_timer.stop();autosolve._rotate_timer.stop()
        inspect(autosolve,'SharpED Autosolve / controlled fixture');autosolve.close();win.close()
    visible=[row for row in literals if row['classification']=='static user-facing candidate']
    for index,row in enumerate(visible,1):row['id']=f'S-{index:05}'
    for index,row in enumerate(runtime,1):row['id']=f'R-{index:05}'
    traces={entry['key']:[] for entry in settings}
    for path in sorted((ROOT/'phase_studio').glob('*.py')):
        source=path.read_text(encoding='utf8');tree=ast.parse(source);lines=source.splitlines()
        parents={child:node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            key=node.attr if isinstance(node,ast.Attribute) else node.value if isinstance(node,ast.Constant) and isinstance(node.value,str) else None
            if key not in traces:continue
            ancestors=[];cur=node
            while cur in parents:cur=parents[cur];ancestors.append(cur)
            conditions=[dict(line=a.lineno,condition=ast.unparse(a.test)) for a in ancestors if isinstance(a,ast.If)]
            traces[key].append(dict(source=str(path.relative_to(ROOT)),line=node.lineno,
                symbol='.'.join(reversed([a.name for a in ancestors if isinstance(a,(ast.FunctionDef,ast.ClassDef))])),
                exact_source_line=lines[node.lineno-1].strip(),enclosing_conditions=conditions))
    for name,data in [('static-literals.json',literals),('runtime-widgets.json',runtime),('settings.json',settings),('secondary-controls.json',secondary),('backend-traces.json',traces),('settings-source.json',{'helper_calls':calls,'backend':backend,'presets_relative_to_initial_fixture':presets})]:write(name,json.dumps(data,indent=2,ensure_ascii=False,default=str)+'\n')
    lines=['# UI text inventory','',
        'Exact static literals and dynamic source templates are retained below. Runtime observations follow. A candidate may be an internal argument to a UI helper: extraction is conservative, not a claim of individual semantic verification. All unverified assessments are explicit. See TERMINOLOGY_REVIEW.md for verified priority findings and coverage limits.','',
        '| ID | Screen / source | Element | Exact current text | Scientific meaning | Assessment | Proposed text |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for row in visible:lines.append('| '+' | '.join(map(cell,[row['id'],f"{row['source']}:{row['line']} / {row['symbol']}",row['context'],row['text'],row['scientific_meaning'],row['assessment'],'Pending individual review']))+' |')
    lines+=['','## Runtime observations','','| ID | Screen | Element | Exact current text | Scientific meaning | Assessment | Proposed text |','| --- | --- | --- | --- | --- | --- | --- |']
    for row in runtime:lines.append('| '+' | '.join(map(cell,[row['id'],row['screen'],row['element']+' '+row['property'],row['text'],'See corresponding static implementation',row['assessment'],'Pending individual review']))+' |')
    write('UI_TEXT_INVENTORY.md','\n'.join(lines)+'\n')
    lines=['# Settings inventory','','Initial GUI defaults are captured before persisted settings load. Displayed fixture values are separate. This audit never reads personal saved settings or credentials. Preset differences, exact source helper calls and the complete RunConfig definition are in settings-source.json. The machine inventory carries tooltips, dependencies, persistence and all numerical properties. Backend meanings require the individual verification noted below.','',
        '| Setting | UI location | Options / range | Default | Unit | Actual behavior | Assessment |','| --- | --- | --- | --- | --- | --- | --- |']
    for row in settings:
        options=json.dumps(row.get('options', {k:row[k] for k in ('minimum','maximum','step','decimals','suffix','special_value_text') if k in row}),ensure_ascii=False)
        lines.append('| '+' | '.join(map(cell,[row['key']+' / '+row['label'],row['location'],options,row['application_default'],row['unit'],row['scientific_meaning']+' '+row['backend'],row['assessment']]))+' |')
    write('SETTINGS_INVENTORY.md','\n'.join(lines)+'\n')
    counts=dict(static_literal_occurrences=len(literals),static_user_facing_candidates=len(visible),runtime_text_observations=len(runtime),
        unique_candidate_texts=len({r['text'] for r in visible+runtime}),registered_configuration_settings=len(settings),
        registered_dropdown_options=sum(len(r.get('options',[])) for r in settings),runtime_tooltips=sum(r['property']=='toolTip' for r in runtime),
        secondary_runtime_control_occurrences=len(secondary),
        static_warning_error_candidates=sum(bool(re.search(r'warning|critical|ValueError|RuntimeError',r['context'] or '')) for r in visible),
        individually_unverified_static_candidates=len(visible),individually_unverified_registered_settings=len(settings),
        completeness='NOT certified exhaustive: all Python string literals retained for residual review; runtime branch and external/native text gaps documented')
    write('coverage.json',json.dumps(counts,indent=2)+'\n');print(json.dumps(counts,indent=2))

if __name__=='__main__':main()
