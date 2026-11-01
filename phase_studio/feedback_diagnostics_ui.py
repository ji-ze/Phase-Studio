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
    def __init__(self,parent,reports,directory):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint,True)
        self.setWindowTitle('Map Feedback diagnostics');self.resize(1120,780)
        self.directory=directory;self.reports=reports;self.report=None
        layout=QVBoxLayout(self);top=QHBoxLayout()
        self.cycle=QComboBox();self.operation=QComboBox()
        self.operation.addItem('All operations',None)
        for name in OPERATIONS:self.operation.addItem(TITLES[name],name)
        top.addWidget(self.cycle,1);top.addWidget(self.operation,1)
        reopen=QPushButton('Open recorded run…');reopen.clicked.connect(self.open_run);top.addWidget(reopen)
        layout.addLayout(top)
        self.notes=QPlainTextEdit();self.notes.setReadOnly(True);self.notes.setMaximumHeight(110);layout.addWidget(self.notes)
        tabs=QTabWidget();layout.addWidget(tabs,1)
        self.summary=QTableWidget();tabs.addTab(self.summary,'Operation summaries')
        self.figure=Figure(figsize=(9,4));self.canvas=FigureCanvasQTAgg(self.figure);tabs.addTab(self.canvas,'Change by source cycle')
        self.table=QTableView();self.table.setAlternatingRowColors(True);self.table.setSortingEnabled(True)
        tabs.addTab(self.table,'Reflection changes')
        buttons=QHBoxLayout()
        for text,slot in [('Export cycle JSON',self.export_json),('Export cycle CSV',self.export_cycle_csv)]:
            button=QPushButton(text);button.clicked.connect(slot);buttons.addWidget(button)
        buttons.addStretch();close=QPushButton('Close');close.clicked.connect(self.close);buttons.addWidget(close);layout.addLayout(buttons)
        self.cycle.currentIndexChanged.connect(self.select_cycle);self.operation.currentIndexChanged.connect(self.select_cycle)
        self.refresh(reports)
        from .ui_branding import fit_dialog_to_available_screen
        fit_dialog_to_available_screen(self,QSize(1120,780))

    def refresh(self,reports):
        selected=self.cycle.currentData();self.reports=reports
        self.cycle.blockSignals(True);self.cycle.clear()
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
        self.summary.setRowCount(0);self.table.setModel(None)
        for model in (getattr(self,'proxy',None),getattr(self,'model',None)):
            if model is not None:model.deleteLater()
        self.proxy=None;self.model=None
        summary=next((r for r in self.reports if r['source_cycle']==self.cycle.currentData()),None)
        if summary is None:
            self.notes.setPlainText('No recorded feedback diagnostics. Legacy means may exist in metrics.csv; missing reflection-level history is unavailable.')
            self.report=None;return
        try:self.report=load_report(summary)
        except (OSError,ValueError) as exc:
            self.notes.setPlainText('Recorded diagnostics unavailable: '+str(exc));self.report=None;return
        written=self.report.get('written_reflections')
        output=self.report.get('next_cycle_reflection_file')
        file_note=(f'Written next-cycle reflections: {written}; file: {output}\n' if written is not None else '')
        self.notes.setPlainText(file_note+self.report['definitions']+'\n'+'\n'.join(self.report.get('errors',[])))
        ops=self.report['operations'];choice=self.operation.currentData()
        visible=[op for op in ops if choice is None or op['operation']==choice]
        metrics=['status','reason','input_reflections','eligible_reflections','significance_eligible',
            'modified_reflections','unchanged_eligible','overlap_groups','eligible_groups','modified_groups',
            'mean_absolute_delta','median_absolute_delta','maximum_absolute_delta',
            'mean_absolute_relative_percent','relative_population','conservation','maximum_group_conservation_error','unavailable_conservation_groups',
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
