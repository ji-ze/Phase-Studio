"""Opt-in frozen-runtime checks. Reports contain no credentials or codes."""
from pathlib import Path
import json
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen


def run_credential_check(output_path, phase):
    """Opt-in cross-process WinCred check; never access production targets."""
    from phase_studio.credentials import CredentialStore, WindowsCredentialBackend
    from phase_studio.version import VERSION

    class TestBackend(WindowsCredentialBackend):
        @staticmethod
        def target(origin):
            return "FZU/PhaseStudio/SelfTest/CredentialPersistence"

    backend = TestBackend()
    store = CredentialStore(backend)
    mock = "SYNTHETIC-PERSISTENCE-SELF-CHECK-NOT-A-REAL-KEY"
    existing = store.get()
    report = dict(version=VERSION, phase=phase, isolated_test_target=True, success=False)
    if phase == "write" and existing in ("", mock):
        store.set(mock)
        report["success"] = CredentialStore(backend).get() == mock
    elif phase == "read":
        report["success"] = existing == mock
    elif phase == "remove" and existing == mock:
        store.remove()
        report["success"] = not CredentialStore(backend).get()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(report, indent=2), encoding="utf8")
    return 0 if report["success"] else 1


def run_oauth_check(output_path, *, interactive=False):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog
    from phase_studio.version import VERSION
    from phase_studio.credentials import CredentialStore
    from phase_studio.oauth import OAuthAttempt, OAuthError, ISSUER, AUTHORIZE, TOKEN, SCOPE, pkce_challenge
    from phase_studio.oauth_ui import OAuthWorker
    from phase_studio.ui_style import apply_phase_studio_style
    app = QApplication.instance() or QApplication([])
    apply_phase_studio_style(app)
    report = dict(version=VERSION, interactive=interactive, inference_submitted=False,
                  api_access_verified=False, callback_ok=False)
    if interactive:
        from phase_studio.sharped_access import SharpEDAccessDialog
        store = CredentialStore()  # Never read/write the user's saved credentials.
        dialog = SharpEDAccessDialog(store=store)
        accepted = dialog.exec() == QDialog.Accepted
        credential = store._oauth
        report.update(accepted=accepted, method=store.authentication_method(),
                      callback_ok=bool(accepted and credential),
                      oauth_token_received=credential is not None,
                      granted_scope=credential.scope if credential else None,
                      remaining_lifetime_seconds=round(credential.expires_at-time.monotonic()) if credential else None)
        dialog.close()
        import shiboken6
        shiboken6.delete(dialog)
    else:
        class LocalTransport:
            authorization = None
            def json(self, url, form=None):
                if url.endswith("openid-configuration"):
                    return dict(issuer=ISSUER, authorization_endpoint=AUTHORIZE, token_endpoint=TOKEN,
                                response_types_supported=["code"], scopes_supported=[SCOPE],
                                code_challenge_methods_supported=["S256"], token_endpoint_auth_methods_supported=["none"])
                if (url != TOKEN or "client_secret" in form or form.get("client_id") != "phase-studio" or
                        form.get("redirect_uri") != self.authorization["redirect_uri"] or
                        pkce_challenge(form["code_verifier"]) != self.authorization["code_challenge"]):
                    raise OAuthError("exchange")
                time.sleep(.1)  # Let the Qt responsiveness timer execute.
                return dict(access_token="FROZEN-SELF-CHECK-NOT-A-CREDENTIAL", token_type="Bearer",
                            expires_in=3600, scope=SCOPE)
        transport = LocalTransport()
        worker = OAuthWorker(OAuthAttempt(transport, timeout=5))
        threads = []
        ticks = [0]
        timer = QTimer();timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.__setitem__(0,ticks[0]+1));timer.start()
        def ready(url):
            transport.authorization = {k:v[0] for k,v in parse_qs(urlsplit(url).query).items()}
            uri = transport.authorization["redirect_uri"]
            report["loopback_host"] = urlsplit(uri).hostname
            report["callback_path"] = urlsplit(uri).path
            def callback():
                try:
                    with urlopen(uri+"?"+urlencode(dict(code="frozen-self-check-code",state=transport.authorization["state"])),timeout=3) as r:
                        report["callback_ok"] = r.status == 200
                except OSError:
                    report["callback_ok"] = False
            thread=threading.Thread(target=callback);threads.append(thread);thread.start()
        def finished(credential,error):
            report.update(mocked=True, system_browser_tested=False, exchange_ok=credential is not None,
                          error_kind=getattr(error,"kind",None), qt_responsive=ticks[0]>0)
            app.quit()
        worker.signals.ready.connect(ready)
        worker.signals.finished.connect(finished)
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(worker)
        app.exec()
        timer.stop()
        for thread in threads:thread.join(3)
        QThreadPool.globalInstance().waitForDone(3000)
    Path(output_path).parent.mkdir(parents=True,exist_ok=True)
    Path(output_path).write_text(json.dumps(report,indent=2),encoding="utf8")
    success = report["callback_ok"] and (interactive or report.get("exchange_ok") and report.get("qt_responsive"))
    import shiboken6
    shiboken6.delete(app)
    return 0 if success else 1
