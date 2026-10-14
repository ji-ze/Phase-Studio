"""Capture actual public web pages in a fresh, off-record Qt browser profile."""
import os,sys,json,time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
ROOT=Path(__file__).resolve().parents[2]
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
app=QApplication([])
profile=QWebEngineProfile(app)
assert profile.isOffTheRecord()
window=QWebEngineView()
page=QWebEnginePage(profile,window)
window.setPage(page);window.resize(1440,1050);window.show()
out=ROOT/"docs/tutorials/screenshots/web";out.mkdir(parents=True,exist_ok=True)
records=[]
for name,url in [("github-release","https://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.2"),("jana-login","https://jana.fzu.cz/login")]:
    state={"loaded":None}
    def loaded(ok):state["loaded"]=ok
    window.loadFinished.connect(loaded);window.load(QUrl(url))
    until=time.monotonic()+35
    while state["loaded"] is None and time.monotonic()<until:app.processEvents();time.sleep(.01)
    text={"value":None};page.toPlainText(lambda value:text.update(value=value))
    until=time.monotonic()+5
    while text["value"] is None and time.monotonic()<until:app.processEvents();time.sleep(.01)
    valid=bool(state["loaded"] and text["value"] and ("PhaseStudio-2.0.2" in text["value"] if name=="github-release" else "Password" in text["value"] or "password" in text["value"]))
    if valid:
        for _ in range(50):app.processEvents();time.sleep(.01)
        assert window.grab().save(str(out/(name+".png")))
    records.append(dict(id=name,url=url,captured=valid,source_window="QWebEngineView / live public website",authenticated=False,privacy="Fresh in-memory profile; no supplied credentials or cookies",missing_reason="" if valid else "Public page did not load or could not be verified"))
    window.loadFinished.disconnect(loaded)
(ROOT/"docs/tutorials/sources/web_screenshot_inventory.json").write_text(json.dumps(records,indent=2))
window.close();page.deleteLater();app.processEvents();profile.deleteLater();app.processEvents()
