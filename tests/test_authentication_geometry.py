"""Scale-factor child processes guard initial screen clamp, footer and scroll reachability."""
import os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
CHILD=r'''
import os
from PySide6.QtCore import QPoint,QRect,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QLineEdit
from phase_studio.sharped_access import SharpEDAccessDialog
from phase_studio.credentials import CredentialStore
from phase_studio.ui_style import apply_phase_studio_style
from phase_studio import requirements as req
app=QApplication([]);apply_phase_studio_style(app)
d=SharpEDAccessDialog(store=CredentialStore(),verify=lambda key:req.RequirementStatus(req.RequirementKind.SHARPED,req.RequirementState.OK))
for _ in range(8):app.processEvents()
available=d.screen().availableGeometry()
assert available.contains(d.frameGeometry()),(available,d.frameGeometry())
assert d._footer.geometry().bottom()<d.height()
assert d.connect_button.geometry().right()<d._footer.width()
assert d.key_edit.echoMode()==QLineEdit.Password
assert d.key_edit.placeholderText()=='Paste your access key here'
# The shortened high-DPI window yields body height to a scroll area; fixed
# header/footer remain visible. Error feedback can be reached without clipping.
d.show_feedback(req.RequirementStatus(req.RequirementKind.SHARPED,req.RequirementState.SERVER_UNAVAILABLE).message)
for _ in range(8):app.processEvents()
feedback=QRect(d.feedback.mapTo(d._scroll.viewport(),QPoint(0,0)),d.feedback.size())
assert d._scroll.viewport().rect().contains(feedback),(d._scroll.viewport().rect(),feedback)
assert d._footer.isVisible()
assert d.back_button.isVisible()
assert d.findChild(type(d.feedback),'sharpedAccessInstructions') is not None
print('geometry',d.size().toTuple(),'dpr',d.devicePixelRatioF(),'scroll',d._scroll.verticalScrollBar().maximum())
d.close();d.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
import shiboken6
shiboken6.delete(app)
'''

def main():
    count=0;failed=[]
    for scale in ('1','1.25','1.5'):
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_SCALE_FACTOR=scale)
        run=subprocess.run([sys.executable,'-c',CHILD],env=env,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
        ok=run.returncode==0
        print(('PASS' if ok else 'FAIL')+' - scale '+scale+' initial clamp and reachable footer/feedback')
        if not ok:print(run.stdout,run.stderr);failed.append(scale)
        count+=1
    if failed:raise SystemExit(1)
    print('All '+str(count)+' checks passed.')
if __name__=='__main__':main()
