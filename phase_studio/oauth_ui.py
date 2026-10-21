"""Qt delivery for one OAuth worker and serialized in-workflow reauthorization."""
from __future__ import annotations
import threading
import time
from PySide6.QtCore import QObject, QRunnable, Signal, Qt, QThread
from PySide6.QtWidgets import QApplication
from phase_studio.oauth import OAuthAttempt, OAuthError


class OAuthSignals(QObject):
    ready = Signal(str)
    progress = Signal(str)
    finished = Signal(object, object)


class OAuthWorker(QRunnable):
    def __init__(self, attempt=None):
        super().__init__()
        self.attempt = attempt or OAuthAttempt()
        self.signals = OAuthSignals()

    def run(self):
        try:
            result = self.attempt.run(self.signals.ready.emit, self.signals.progress.emit)
            self.signals.finished.emit(result, None)
        except OAuthError as exc:
            self.signals.finished.emit(None, exc)
        except Exception:
            self.signals.finished.emit(None, OAuthError("response"))


class ReauthorizationBridge(QObject):
    requested = Signal(object)
    cancelled = Signal(object)

    def __init__(self, store):
        super().__init__(QApplication.instance())
        self.store = store
        self.requested.connect(self._show, Qt.QueuedConnection)
        self.cancelled.connect(self._cancel, Qt.QueuedConnection)

    def renew(self, stop_event=None):
        if QThread.currentThread() == self.thread():
            # Network operations should be on workers; never block the GUI.
            raise OAuthError("exchange")
        request = {"event": threading.Event(), "credential": None, "cancelled": False}
        self.requested.emit(request)
        deadline = time.monotonic() + 150
        while not request["event"].wait(.1):
            stopped = stop_event is not None and stop_event.is_set()
            if stopped or time.monotonic() >= deadline:
                request["cancelled"] = True
                self.cancelled.emit(request)
                raise OAuthError("cancelled" if stopped else "timeout")
        return request["credential"]

    def _cancel(self, request):
        dialog = request.get("dialog")
        if dialog is not None and request.get('owns_dialog', False):
            dialog.reject()

    def _show(self, request):
        if request["cancelled"] or not self.store._oauth_selected:
            request["event"].set()
            return
        from phase_studio.sharped_access import SharpEDAccessDialog
        active = getattr(self.store, '_active_access_dialog', None)
        if active is not None:
            request['dialog'] = active
            def share_result(_result):
                if not request['cancelled'] and active.selected_key and self.store.is_oauth(active.selected_key):
                    request['credential'] = self.store._oauth
                request['event'].set()
                request['dialog'] = None
            active.finished.connect(share_result)
            return
        dialog = SharpEDAccessDialog(QApplication.activeWindow(), store=self.store)
        self.store._active_access_dialog = dialog
        request["dialog"] = dialog
        request['owns_dialog'] = True
        from PySide6.QtCore import QTimer
        dialog.show_feedback("Your SharpED connection needs to be renewed. Continue with Jana2020 sign-in.")
        QTimer.singleShot(0, dialog, dialog._start_oauth)
        try:
            dialog.exec()
        finally:
            self.store._active_access_dialog = None
        if not request["cancelled"] and dialog.selected_key and self.store.is_oauth(dialog.selected_key):
            request["credential"] = self.store._oauth
        request["event"].set()
        request["dialog"] = None
        dialog.deleteLater()


def install_reauthorization(store):
    if not hasattr(store, "_oauth_bridge"):
        store._oauth_bridge = ReauthorizationBridge(store)
        store.reauthorize = store._oauth_bridge.renew
