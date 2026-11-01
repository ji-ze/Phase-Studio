import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def test_diagnostics_and_metadata_at_all_scales():
    for scale in ('1','1.25','1.5','2'):
        p=subprocess.run([sys.executable,__file__,'--child'],cwd=ROOT,
            env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_SCALE_FACTOR':scale},capture_output=True,text=True,timeout=60)
        assert p.returncode==0,scale+': '+p.stdout+p.stderr


def exercise():
    sys.path.insert(0,str(ROOT))
    import tempfile,json,csv
    from unittest.mock import patch
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QScreen
    from PySide6.QtWidgets import QApplication,QWidget,QHBoxLayout,QFileDialog
    from phase_studio.feedback_diagnostics import save_report,load_summaries,compare_stage
    from phase_studio.feedback_diagnostics_ui import FeedbackDiagnosticsDialog
    from phase_studio.viewer_metadata import PanelMetadataLabel
    from phase_studio import app as a
    qt=QApplication([]);a.apply_phase_studio_style(qt)
    scale=float(os.environ.get('QT_SCALE_FACTOR','1'))
    with tempfile.TemporaryDirectory() as tmp,patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(1920/scale),int(1140/scale))):
        root=Path(tmp);owner=QWidget();layout=QHBoxLayout(owner);labels=[PanelMetadataLabel() for _ in range(3)]
        for label in labels:layout.addWidget(label,1)
        for text in ('','70 atoms shown','EDMA asymmetric-unit composition: '+'C26 H32 N4 O4 S1 '*30):
            for label in labels:label.setText(text)
            owner.resize(700,100);owner.show();qt.processEvents()
            for label in labels:
                from PySide6.QtGui import QTextDocument
                assert label.accessibleName()==text
                tip=QTextDocument();tip.setHtml(label.toolTip())
                assert tip.toPlainText().split()==text.split()
                assert len(label.text().splitlines())<=3
                assert all(label.fontMetrics().horizontalAdvance(line)<=label.width()-8 for line in label.text().splitlines())
            assert all(left.geometry().right()<right.geometry().left() for left,right in zip(labels,labels[1:]))
        before=[a.Reflection(1,0,0,10,.1),a.Reflection(2,0,0,20,.1)]
        after=[a.Reflection(1,0,0,7.5,.1),a.Reflection(2,0,0,22.5,.1)]
        op=compare_stage(before,after,a.REFLECTION_DATA_MODE_INTENSITY_FWHM,eligible={(1,0,0),(2,0,0)},groups={(1,0,0):1,(2,0,0):1})
        op.update(operation='powder',status='Applied',reason='Controlled fixture')
        report=dict(source_cycle=5,target_cycle=6,operations=[op],errors=[],definitions='Controlled fixture; changed finite records only.')
        save_report(root,report);summaries=load_summaries(root)
        dialog=FeedbackDiagnosticsDialog(owner,summaries,root);dialog.show();qt.processEvents()
        assert dialog.cycle.currentData()==5 and 'input for cycle 6' in dialog.cycle.currentText()
        assert dialog.model.rowCount()==2 and len(dialog.figure.axes[0].lines)==1
        assert list(dialog.figure.axes[0].lines[0].get_xdata())==[5]
        target=root/'export.json'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'JSON')):dialog.export_json()
        assert json.loads(target.read_text())['operations'][0]['mean_absolute_delta']==2.5
        target=root/'export.csv'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'CSV')):dialog.export_cycle_csv()
        records=list(csv.DictReader(target.open()));assert len(records)==2 and records[0]['source_cycle']=='5'
        dialog.refresh(summaries);assert dialog.cycle.currentData()==5
        dialog.refresh([]);assert dialog.report is None and dialog.table.model() is None
        out=ROOT/'build/palette-feedback207/ui-tests';out.mkdir(parents=True,exist_ok=True)
        dialog.refresh(summaries);qt.processEvents();dialog.grab().save(str(out/f'diagnostics-{scale}.png'))
        owner.grab().save(str(out/f'metadata-{scale}.png'))
        dialog.close();owner.close()


if __name__=='__main__':exercise()
