"""Inspection of recorded feedback stages, separate from quality/ranking metrics."""
import json
import math
from pathlib import Path
from PySide6.QtCore import Qt,QSize,QAbstractTableModel,QSortFilterProxyModel
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QPushButton,
    QLabel,QTableView,QTableWidget,QTableWidgetItem,QTabWidget,QPlainTextEdit,QFileDialog,QMessageBox)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .feedback_diagnostics import TITLES,OPERATIONS,load_report,load_summaries,export_csv

FIELDS=[('h','h'),('k','k'),('l','l'),('before','I before'),('after','I after'),
    ('delta','ΔI'),('absolute_delta','|ΔI|'),('relative_percent','|ΔI| / I before (%)'),
    ('signed_relative_percent','ΔI / I before (%)'),
    ('group','Overlap group'),('operation','Operation'),('source_cycle','After cycle'),('target_cycle','Input cycle')]


class ReflectionChanges(QAbstractTableModel):
    def __init__(self,rows,parent):
        super().__init__(parent);self.rows=rows
    def rowCount(self,parent=None):return len(self.rows)
    def columnCount(self,parent=None):return len(FIELDS)
    def headerData(self,section,orientation,role=Qt.DisplayRole):
        if role==Qt.DisplayRole:return FIELDS[section][1] if orientation==Qt.Horizontal else str(section+1)
    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid():return None
        value=self.rows[index.row()].get(FIELDS[index.column()][0])
        if role==Qt.UserRole:return value
        if role==Qt.TextAlignmentRole:return int(Qt.AlignRight|Qt.AlignVCenter)
        if role in (Qt.DisplayRole,Qt.ToolTipRole):
            if value is None:return 'Unavailable'
            return f'{value:.10g}' if isinstance(value,float) and role==Qt.DisplayRole else str(value)


class FeedbackDiagnosticsDialog(QDialog):
    def __init__(self,parent,reports,directory,*,historical=False):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint,True)
        self.setWindowTitle('Map Feedback diagnostics');self.resize(1120,780)
        self.directory=directory;self.reports=reports;self.report=None;self.historical=historical
        layout=QVBoxLayout(self);top=QHBoxLayout()
        self.provenance=QLabel();self.provenance.setWordWrap(True);layout.addWidget(self.provenance)
        self.cycle=QComboBox();self.operation=QComboBox()
        self.operation.addItem('All operations',None)
        for name in OPERATIONS:self.operation.addItem(TITLES[name],name)
        top.addWidget(self.cycle,1);top.addWidget(self.operation,1)
        reopen=QPushButton('Open recorded run…');reopen.clicked.connect(self.open_run);top.addWidget(reopen)
        layout.addLayout(top)
        self.notes=QPlainTextEdit();self.notes.setReadOnly(True);self.notes.setMaximumHeight(110);layout.addWidget(self.notes)
        tabs=QTabWidget();self.tabs=tabs;layout.addWidget(tabs,1)
        self.summary=QTableWidget();tabs.addTab(self.summary,'Operation summaries')
        self.figure=Figure(figsize=(9,4));self.canvas=FigureCanvasQTAgg(self.figure);tabs.addTab(self.canvas,'Change by source cycle')
        self.table=QTableView();self.table.setAlternatingRowColors(True);self.table.setSortingEnabled(True)
        tabs.addTab(self.table,'Reflection changes')
        from PySide6.QtWidgets import QWidget
        cumulative_page=QWidget();cumulative_layout=QVBoxLayout(cumulative_page)
        self.cumulative_label=QLabel();self.cumulative_label.setWordWrap(True)
        self.cumulative_table=QTableView();self.cumulative_table.setSortingEnabled(True)
        cumulative_layout.addWidget(self.cumulative_label);cumulative_layout.addWidget(self.cumulative_table,1)
        tabs.addTab(cumulative_page,'Cumulative input vs original')
        written_page=QWidget();written_layout=QVBoxLayout(written_page)
        self.written_label=QLabel();self.written_label.setWordWrap(True)
        self.written_table=QTableView();self.written_table.setSortingEnabled(True)
        self.written_export=QPushButton('Export actual written-input CSV')
        self.written_export.clicked.connect(self.export_written_csv)
        written_layout.addWidget(self.written_label);written_layout.addWidget(self.written_export)
        written_layout.addWidget(self.written_table,1);tabs.addTab(written_page,'Actual written inputs')
        buttons=QHBoxLayout()
        self.cycle_exports=[]
        for text,slot in [('Export cycle JSON',self.export_json),('Export cycle CSV',self.export_cycle_csv)]:
            button=QPushButton(text);button.clicked.connect(slot);buttons.addWidget(button);self.cycle_exports.append(button)
        self.cumulative_export=QPushButton('Export cumulative CSV')
        self.cumulative_export.clicked.connect(self.export_cumulative_csv);buttons.addWidget(self.cumulative_export)
        buttons.addStretch();close=QPushButton('Close');close.clicked.connect(self.close);buttons.addWidget(close);layout.addLayout(buttons)
        self.cycle.currentIndexChanged.connect(self.select_cycle);self.operation.currentIndexChanged.connect(self.select_cycle)
        self.refresh(reports)
        from .ui_branding import fit_dialog_to_available_screen
        fit_dialog_to_available_screen(self,QSize(1000,660) if reports else QSize(620,240))
        self.setMinimumSize(min(420,self.width()),min(240,self.height()))

    def refresh(self,reports):
        selected=self.cycle.currentData();self.reports=reports
        available=bool(reports)
        self.tabs.setVisible(available)
        self.cycle.setVisible(available);self.operation.setVisible(available)
        for button in self.cycle_exports+[self.cumulative_export]:button.setVisible(available)
        runs=sorted({str(report.get('run_id') or 'unavailable') for report in reports})
        self.provenance.setText(('Recorded run' if self.historical else 'Current run') + ': ' +
            (', '.join(runs) if runs else 'No observations available') + ' · Source: ' + Path(self.directory).name)
        self.provenance.setToolTip(str(Path(self.directory).resolve()))
        self.cycle.blockSignals(True);self.cycle.clear()
        if any(r.get('source_cycle')==1 and r.get('cycle_input') for r in reports):
            self.cycle.addItem('Original input for cycle 1 · no preceding Map Feedback',0)
        for report in sorted(reports,key=lambda r:r['source_cycle']):
            target=report['target_cycle']
            self.cycle.addItem(f'Map Feedback after cycle {report["source_cycle"]} → '+(f'input for cycle {target}' if target else 'no next cycle'),report['source_cycle'])
        index=self.cycle.findData(selected)
        self.cycle.setCurrentIndex(index if index>=0 else self.cycle.count()-1);self.cycle.blockSignals(False)
        self.select_cycle()
        self.figure.clear();axis=self.figure.subplots()
        for name in OPERATIONS:
            data=[(r['source_cycle'],next((op.get('mean_absolute_relative_percent') for op in r['operations'] if op['operation']==name),None)) for r in sorted(reports,key=lambda r:r['source_cycle'])]
            if any(value is not None for _,value in data):
                axis.plot([n for n,_ in data],[value if value is not None else math.nan for _,value in data],'o-',label=TITLES[name])
        axis.set_xlabel('Feedback after source cycle N → input N+1')
        axis.set_ylabel('Mean |ΔI| / I before (%)\nchanged finite records, I before > 1e-12')
        if axis.lines:axis.legend(fontsize=8)
        else:axis.text(.5,.5,'No measured change statistics available',ha='center',transform=axis.transAxes)
        self.figure.tight_layout();self.canvas.draw_idle()

    def select_cycle(self,*_):
        for button in self.cycle_exports:button.setEnabled(False)
        self.summary.setRowCount(0);self.table.setModel(None);self.cumulative_table.setModel(None)
        self.cumulative_label.setText('Cumulative comparison unavailable: original or actual input observations were not recorded.')
        self.cumulative_export.setEnabled(False);self._cumulative_report=None
        self.written_table.setModel(None);self.written_label.setText('Actual consecutive written-input comparison unavailable.')
        self.written_export.setEnabled(False);self._written_report=None
        for model in (getattr(self,'proxy',None),getattr(self,'model',None),
                      getattr(self,'cumulative_proxy',None),getattr(self,'cumulative_model',None),
                      getattr(self,'written_proxy',None),getattr(self,'written_model',None)):
            if model is not None:model.deleteLater()
        self.proxy=None;self.model=None;self.cumulative_proxy=None;self.cumulative_model=None
        self.written_proxy=None;self.written_model=None
        initial=self.cycle.currentData()==0
        summary=next((r for r in self.reports if r['source_cycle']==(1 if initial else self.cycle.currentData())),None)
        if summary is None:
            self.notes.setPlainText('No recorded feedback diagnostics. Legacy means may exist in metrics.csv; missing reflection-level history is unavailable.')
            self.report=None;return
        try:self.report=load_report(summary)
        except (OSError,ValueError) as exc:
            self.notes.setPlainText('Recorded diagnostics unavailable: '+str(exc));self.report=None;return
        self.cycle_exports[0].setEnabled(True)
        self.cycle_exports[1].setEnabled(any(operation.get('rows') for operation in self.report.get('operations',[])))
        if initial:
            self.report=self.report|dict(source_cycle=0,target_cycle=1,operations=[],
                target_input=self.report['cycle_input'],written_reflections=None,next_cycle_reflection_file=None,
                written_input_difference=None,
                definitions='Original input for cycle 1; no preceding Map Feedback operation. '+self.report['definitions'])
        written=self.report.get('written_reflections')
        output=self.report.get('next_cycle_reflection_file')
        file_note=(f'Written next-cycle reflections: {written}; file: {output}\n' if written is not None else '')
        self.notes.setPlainText(file_note+self.report['definitions']+'\n'+'\n'.join(self.report.get('errors',[])))
        ops=self.report['operations'];choice=self.operation.currentData()
        visible=[op for op in ops if choice is None or op['operation']==choice]
        metrics=['status','reason','input_reflections','eligible_reflections','significance_eligible',
            'modified_reflections','unchanged_eligible','overlap_groups','eligible_groups','modified_groups',
            'mean_absolute_delta','median_absolute_delta','maximum_absolute_delta',
            'mean_absolute_relative_percent','maximum_absolute_relative_percent','relative_population','conservation','maximum_group_conservation_error','unavailable_conservation_groups',
            'proposed_reflections','added_reflections','percentage_increase','legacy_mean_percent']
        self.summary.setColumnCount(len(visible)+1);self.summary.setRowCount(len(metrics))
        self.summary.setHorizontalHeaderLabels(['Quantity']+[TITLES[op['operation']] for op in visible])
        for row,key in enumerate(metrics):
            self.summary.setItem(row,0,QTableWidgetItem(key.replace('_',' ')))
            for col,op in enumerate(visible,1):
                value=op.get(key);item=QTableWidgetItem('Unavailable' if value is None else str(value))
                item.setToolTip(self.report['definitions']+'\n'+op.get('reason',''));self.summary.setItem(row,col,item)
        self.summary.setEditTriggers(QTableWidget.NoEditTriggers);self.summary.resizeColumnsToContents()
        rows=[row|dict(operation=op['operation'],source_cycle=self.report['source_cycle'],target_cycle=self.report['target_cycle']) for op in visible for row in op.get('rows',[])]
        self.model=ReflectionChanges(rows,self)
        self.proxy=QSortFilterProxyModel(self);self.proxy.setSourceModel(self.model);self.proxy.setSortRole(Qt.UserRole)
        self.table.setModel(self.proxy);self.table.sortByColumn(6,Qt.DescendingOrder);self.table.resizeColumnsToContents()
        data=self.report.get('target_input') or self.report.get('cycle_input') or {}
        comparison=data.get('cumulative')
        if comparison:
            cycle=self.report['target_cycle'] or self.report['source_cycle']
            mean=comparison.get('mean_absolute_relative_percent')
            maximum=comparison.get('maximum_absolute_relative_percent')
            self.cumulative_label.setText(f'Written input for cycle {cycle} vs original measured observations. '
                f'{comparison["modified_reflections"]} changed matched HKLs; {comparison["added_reflections"]} added; '
                f'{comparison["removed_reflections"]} absent (not zero). Mean/max absolute relative change: '
                f'{mean if mean is not None else "Unavailable"}% / {maximum if maximum is not None else "Unavailable"}%.\n'
                +data.get('reason','')+'\nInput: '+data.get('file','Unavailable'))
            self._cumulative_report=dict(source_cycle=0,target_cycle=cycle,
                operations=[comparison|dict(operation='cumulative input vs original')])
            rows=[r|dict(operation='cumulative input vs original',source_cycle=0,target_cycle=cycle)
                  for r in comparison.get('rows',[])]
            self.cumulative_model=ReflectionChanges(rows,self)
            self.cumulative_proxy=QSortFilterProxyModel(self);self.cumulative_proxy.setSourceModel(self.cumulative_model)
            self.cumulative_proxy.setSortRole(Qt.UserRole);self.cumulative_table.setModel(self.cumulative_proxy)
            self.cumulative_table.sortByColumn(6,Qt.DescendingOrder);self.cumulative_table.resizeColumnsToContents()
            self.cumulative_export.setEnabled(True)
        written=self.report.get('written_input_difference') or {}
        if written.get('status')=='Available':
            self.written_label.setText(f'Actual written input {self.report["source_cycle"]} → {self.report["target_cycle"]}: '
                f'{written["modified_reflections"]}/{written["input_reflections"]} changed matched reflections, '
                f'{written["added_reflections"]} added, {written["removed_reflections"]} absent. '+written['reason'])
            self._written_report=dict(source_cycle=self.report['source_cycle'],target_cycle=self.report['target_cycle'],
                operations=[written|dict(operation='net written-input difference')])
            rows=[r|dict(operation='net written-input difference',source_cycle=self.report['source_cycle'],
                         target_cycle=self.report['target_cycle']) for r in written.get('rows',[])]
            self.written_model=ReflectionChanges(rows,self)
            self.written_proxy=QSortFilterProxyModel(self);self.written_proxy.setSourceModel(self.written_model)
            self.written_proxy.setSortRole(Qt.UserRole);self.written_table.setModel(self.written_proxy)
            self.written_table.sortByColumn(6,Qt.DescendingOrder);self.written_table.resizeColumnsToContents()
            self.written_export.setEnabled(True)

    def open_run(self):
        folder=QFileDialog.getExistingDirectory(self,'Open recorded run',str(self.directory))
        if folder:
            try:self.directory=folder;self.refresh(load_summaries(folder))
            except (OSError,ValueError) as exc:QMessageBox.warning(self,'Diagnostics unavailable',str(exc))

    def export_json(self):
        if self.report is not None:
            name,_=QFileDialog.getSaveFileName(self,'Export cycle diagnostics','','JSON (*.json)')
            if name:Path(name).write_text(json.dumps(self.report,indent=2,allow_nan=False),encoding='utf8')

    def export_cycle_csv(self):
        if self.report is not None:
            name,_=QFileDialog.getSaveFileName(self,'Export reflection changes','','CSV (*.csv)')
            if name:export_csv(name,self.report)

    def export_cumulative_csv(self):
        if self._cumulative_report is not None:
            name,_=QFileDialog.getSaveFileName(self,'Export cumulative input differences','','CSV (*.csv)')
            if name:export_csv(name,self._cumulative_report)

    def export_written_csv(self):
        if self._written_report is not None:
            name,_=QFileDialog.getSaveFileName(self,'Export actual written-input differences','','CSV (*.csv)')
            if name:export_csv(name,self._written_report)
