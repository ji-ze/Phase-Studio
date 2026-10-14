"""A genuine local Superflip+EDMA run on generated public synthetic reflections."""
import os,sys,time,json
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ.pop("SHARPED_API_TOKEN",None)
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtGui import QPainter,QColor
from phase_studio import app as engine
from phase_studio.ui_style import apply_phase_studio_style
app=QApplication([]);apply_phase_studio_style(app)
engine.IterativeSuperflipPipelineQtGUI.load_settings=lambda self:None
engine.IterativeSuperflipPipelineQtGUI.save_settings=lambda self:None
engine.IterativeSuperflipPipelineQtGUI.refresh_sharped_models=lambda self:None
w=engine.IterativeSuperflipPipelineQtGUI();w.resize(1600,1000);w.show()
values={"hkl":"docs/tutorials/demo/tutorial_intensity.hkl","reference_cif":"docs/tutorials/demo/tutorial_reference.cif",
        "work_dir":"build/tutorials/local-scientific-run","superflip_exe":"C:/Jana2020/SUPERFLIP/superflip.exe","edma_exe":"C:/Jana2020/SUPERFLIP/EDMA.exe",
        "cycles":"1","maxcycles":"100","repeatmode":"1","voxel":"32 32 32","run_sharped":"false","run_edma_superflip":"true","run_edma_deblurred":"false","normalize":"none","sharped_api_token":""}
for key,value in values.items():w._set_widget_value_from_string(w.inputs[key],value)
w._set_metadata_source("reference")
w._set_widget_value_from_string(w.inputs["input_source_mode"],engine.INPUT_MODE_LABELS[engine.INPUT_MODE_EXTERNAL])
events=lambda:[app.processEvents() for _ in range(8)]
events()
out=ROOT/"docs/tutorials/screenshots/standalone";out.mkdir(parents=True,exist_ok=True)
captured=[]
def capture(name):
    events();pix=w.grab()
    # Redact the diagnostic text area as a whole if it contains local paths.
    # Never alter the running application, its controls or scientific data.
    redacted=[]
    from PySide6.QtWidgets import QPlainTextEdit,QTextEdit
    for widget in w.findChildren(QPlainTextEdit)+w.findChildren(QTextEdit):
        if not widget.isVisible():continue
        text=widget.toPlainText()
        if "Users" in text or "honzi" in text:
            point=widget.mapTo(w,widget.rect().topLeft())
            painter=QPainter(pix);painter.fillRect(point.x(),point.y(),widget.width(),widget.height(),QColor("#f3f5fa"));painter.drawText(point.x()+12,point.y()+25,"Local diagnostic paths redacted");painter.end()
            redacted.append("Diagnostic pane: personal local paths")
    assert pix.save(str(out/(name+".png")))
    captured.append(dict(id=name,path="screenshots/standalone/"+name+".png",captured=True,source_window=type(w).__name__,synthetic=True,fixture="Actual local Superflip / EDMA calculation on public synthetic reflections",redaction=redacted,targets=[]))
try:
    w.start_run()
    until=time.monotonic()+120
    did_capture=False
    while w.worker is not None and w.worker.is_alive() and time.monotonic()<until:
        events();time.sleep(.02)
        if not did_capture:capture("local-run-active");did_capture=True
    for _ in range(15):
        w._poll_queue();events();time.sleep(.02)
    if w.worker is not None and w.worker.is_alive():raise TimeoutError("Local demonstration did not finish in 120 seconds")
    if not w.results:raise RuntimeError("Local demonstration produced no completed result")
    capture("local-run-completed")
    result=w.results[-1]
    data=dict(cycle=result.cycle,map=str(result.superflip_map.relative_to(ROOT)) if result.superflip_map.is_absolute() else str(result.superflip_map),
              structure=str(result.superflip_edma_cif.relative_to(ROOT)) if result.superflip_edma_cif.is_absolute() else str(result.superflip_edma_cif),
              model_source=result.model_source,threshold=result.superflip_edma_sigma,results=len(w.results))
    (ROOT/"build/tutorials/local-run-result.json").write_text(json.dumps(data,indent=2))
finally:
    w.close();w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    (ROOT/"docs/tutorials/sources/local_run_inventory.json").write_text(json.dumps(captured,indent=2))
    import shiboken6
    shiboken6.delete(app)
