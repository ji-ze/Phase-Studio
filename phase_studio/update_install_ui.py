"""Consent-driven asynchronous update UI shared by both distribution profiles."""
import threading
import time

from PySide6.QtCore import Qt,QTimer,Signal,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QFormLayout,QProgressBar,QPlainTextEdit)

from .version import VERSION
from .update_checker import validated_release_url
from .update_download import DownloadCancelled
from .update_manifest import UpdateVerificationError
from .update_runtime import UpdateSession,fetch_offer


class UpdateInstallDialog(QDialog):
    delivered=Signal(object)
    progressed=Signal(str,int,int)

    def __init__(self,parent,release,*,jana=False,session_factory=None,error_presenter=None):
        super().__init__(parent)
        self.setWindowTitle('Phase Studio update')
        self.setObjectName('phaseStudioInstallUpdateDialog')
        self.release=release;self.jana=bool(jana)
        self.factory=session_factory or UpdateSession
        self.presenter=error_presenter
        self.session=None;self.busy=False;self.phase='offer';self._handed_off=False;self._closed=False;self._cancelled=False
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.delivered.connect(self._delivered,Qt.QueuedConnection)
        self.progressed.connect(self._progress,Qt.QueuedConnection)
        root=QVBoxLayout(self);root.setContentsMargins(12,12,12,12);root.setSpacing(10)
        from .ui_branding import create_phase_studio_brand_header,apply_safe_dialog_geometry
        root.addWidget(create_phase_studio_brand_header())
        heading=QLabel('A new version is available');heading.setStyleSheet('font-size:13pt;font-weight:600;color:#001170;')
        root.addWidget(heading)
        details=QFormLayout();self.installed=QLabel(VERSION);self.available=QLabel(release.label)
        self.package=QLabel('Determining installed profile…');self.published=QLabel('Loading…');self.download_size=QLabel('Loading…')
        for title,value in [('Installed',self.installed),('Available',self.available),('Package',self.package),
                ('Published',self.published),('Download',self.download_size)]:details.addRow(title,value)
        root.addLayout(details)
        self.notes=QPlainTextEdit();self.notes.setReadOnly(True);self.notes.setMaximumHeight(150)
        self.notes.setAccessibleName('Release notes');root.addWidget(self.notes)
        self.status=QLabel('Loading release information…');self.status.setWordWrap(True);self.status.setTextFormat(Qt.PlainText)
        root.addWidget(self.status)
        self.progress=QProgressBar();self.progress.setRange(0,0);root.addWidget(self.progress)
        self.requirement=QLabel('Phase Studio will restart after installation. No scientific calculation is resumed automatically.')
        if self.jana:self.requirement.setText('Direct Jana2020 session: close Phase Studio using Cancel, then exit Jana2020. After installation, reopen Phase Studio from Jana2020. The updater does not complete a scientific handoff.')
        self.requirement.setWordWrap(True);root.addWidget(self.requirement)
        buttons=QHBoxLayout();self.github=QPushButton('View on GitHub');buttons.addWidget(self.github);buttons.addStretch(1)
        self.cancel_button=QPushButton('Later');self.action=QPushButton('Update now');self.action.setObjectName('primaryButton')
        buttons.addWidget(self.cancel_button);buttons.addWidget(self.action);root.addLayout(buttons)
        self.github.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(validated_release_url(release.url,version=release.version))))
        self.cancel_button.clicked.connect(self._cancel)
        self.action.clicked.connect(self._activate)
        self.action.setEnabled(False)
        apply_safe_dialog_geometry(self,620,650)
        self._last_stage=None;self._progress_time=0;self._progress_bytes=0
        QTimer.singleShot(0,self,self._load)

    def _work(self,kind,function):
        if self.busy:return
        self.busy=True;self.action.setEnabled(False);self.cancel_button.setText('Cancel')
        self.progress.setRange(0,0)
        def work():
            try:result=(kind,function(),None)
            except Exception as exc:result=(kind,None,exc)
            try:self.delivered.emit(result)
            except RuntimeError:pass
        threading.Thread(target=work,name='PhaseStudio-update-'+kind,daemon=True).start()

    def _load(self):
        self.phase='offer'
        def load():
            self.session=self.factory(self.release.label,jana=self.jana)
            if self._cancelled:self.session.stop();raise DownloadCancelled()
            offer=fetch_offer(self.release.label) if self.factory is UpdateSession else self.session.load_offer()
            return offer
        self._work('offer',load)

    def _activate(self):
        if self.busy:return
        if self.phase=='offer':
            if self.session is None:self._load();return
            self._work('prepare',lambda:self.session.prepare(self.progressed.emit))
        elif self.phase=='prepared':
            if self._scientific_work_running():
                self._error(UpdateVerificationError('Finish or cancel the active scientific workflow before installing an update.'),retry_prepared=True)
                return
            self._work('helper',self.session.launch_helper)
        elif self.phase=='jana-ready':
            self._handed_off=True;self.accept()

    @staticmethod
    def _scientific_work_running():
        for widget in QApplication.topLevelWidgets():
            backend=getattr(widget,'backend',widget)
            if str(getattr(backend,'_run_status','')).upper() in {'RUNNING','REVIEW'}:return True
        return False

    def _progress(self,stage,done,total):
        if self._closed:return
        now=time.monotonic();self.status.setText(stage)
        if total>0:
            self.progress.setRange(0,1000);self.progress.setValue(min(1000,int(1000*done/total)))
            speed=''
            if stage==self._last_stage and now>self._progress_time and done>=self._progress_bytes:
                speed=f' · {(done-self._progress_bytes)/(now-self._progress_time)/1048576:.1f} MB/s'
            self.progress.setFormat(f'{done/1048576:.1f} / {total/1048576:.1f} MB'+speed)
        else:self.progress.setRange(0,0)
        self._last_stage=stage;self._progress_time=now;self._progress_bytes=done

    def _delivered(self,result):
        if self._closed:return
        self.busy=False;kind,value,error=result
        if error is not None:
            if isinstance(error,DownloadCancelled):
                self.status.setText('Update cancelled. Installation is unchanged.');self.reject();return
            self._error(error);return
        if kind=='offer':
            self.phase='offer';self.action.setText('Update now')
            profile=self.session.current.profile
            self.package.setText('Jana2020 integration' if profile=='jana2020-onedir' else 'Standalone application')
            self.published.setText(value.published.replace('T',' ').replace('Z',' UTC'))
            name=f'PhaseStudio-Jana2020-{value.version}.zip' if profile=='jana2020-onedir' else f'PhaseStudio-{value.version}-x64.exe'
            self.download_size.setText(f'{value.assets[name]["size"]/1048576:.1f} MB')
            self.notes.setPlainText(value.notes)
            self.status.setText('Ready to download and verify. Installation requires a separate confirmation.')
            self.progress.setRange(0,1);self.progress.setValue(0)
        elif kind=='prepare':
            self.phase='prepared';self.action.setText('Prepare Jana update' if self.jana else 'Restart and install')
            self.status.setText('Signature and package verified. Administrator consent is requested only if needed.')
            self.progress.setRange(0,1);self.progress.setValue(1)
        else:
            if not self.jana and self._scientific_work_running():
                self._error(UpdateVerificationError('A scientific workflow started while the updater was preparing. Finish or cancel it, then prepare the update again.'))
                return
            self._handed_off=True
            if self.jana:
                self.phase='jana-ready';self.action.setText('Close these instructions')
                self.status.setText('Updater is waiting. Close Phase Studio with Cancel, then exit Jana2020 within three minutes. Reopen Phase Studio from Jana2020 after the updater reports completion.')
            else:
                self.accept()
                QApplication.closeAllWindows()
                return
        self.action.setEnabled(True);self.cancel_button.setText('Cancel update' if self._handed_off else 'Later')

    def _error(self,error,*,retry_prepared=False):
        self.progress.setRange(0,1);self.progress.setValue(0)
        self.status.setText('Update preparation failed. The existing installation has not been changed.')
        self.action.setText('Retry');self.action.setEnabled(True)
        self.cancel_button.setText('Close')
        if not retry_prepared:
            if self.session is not None:self.session.stop()
            self.phase='offer';self.session=None
        from .error_reporting import ErrorReport,show_phase_studio_error
        message=str(error) if isinstance(error,UpdateVerificationError) else 'The update service is unavailable. Try again later.'
        report=ErrorReport('application_update','Phase Studio update','Update not installed',
            self.status.text(),message,type(error).__name__)
        (self.presenter or show_phase_studio_error)(self,report)

    def _cancel(self):
        if self.session is not None:self.session.stop()
        self._handed_off=False;self.reject()

    def reject(self):
        self._cancelled=True;self._closed=True
        if self.session is not None:self.session.stop()
        self._handed_off=False
        super().reject()

    def closeEvent(self,event):
        self._closed=True
        if self.session is not None and not self._handed_off:self.session.stop()
        super().closeEvent(event)
