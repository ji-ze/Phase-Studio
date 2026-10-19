"""Explicit offline frozen-UI acceptance; never runs scientific executables."""
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch


def run_release_ui_check(output_path):
    os.environ['PHASE_STUDIO_STARTUP_PROBE'] = '1'
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QDialog
    from phase_studio import jana_superflip as js, update_ui
    from phase_studio.credentials import CredentialStore
    from phase_studio.sharped_access import SharpEDAccessDialog
    from phase_studio.ui_style import apply_phase_studio_style
    from phase_studio.version import VERSION
    report = {'version': VERSION, 'offline': True, 'inference_submitted': False}
    app = QApplication.instance() or QApplication([])
    apply_phase_studio_style(app)
    try:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / 'release-check.inflip'
            source.write_text('title offline_release_fixture\nperform CF\noutputformat xplor\n'
                'dimension 3\ncell 10 11 12 90 90 90\nspacegroup P1\ncomposition C2\n'
                'dataformat intensity\nfbegin\n1 0 0 10\n0 1 0 20\nendf\n', encoding='utf8')
            original = source.read_bytes()
            programs = base / 'Jana' / 'SUPERFLIP'
            programs.mkdir(parents=True)
            for name in ('superflip.exe', 'EDMA.exe'):
                (programs / name).write_bytes(b'Offline fixture; never execute')
            factory = lambda org, name: QSettings(str(base / (name + '.ini')), QSettings.IniFormat)
            state = update_ui.UpdateState(factory('PhaseStudio', 'updates'), base / 'updates.lock')
            state.set_enabled(False)
            app._phase_studio_updates = update_ui.UpdateService(app, state=state, automatic_allowed=False)
            store = CredentialStore(backend=None)
            imports = js._qt_imports
            models = [js.SHARPED_ONE_CYCLE_MODEL, js.SHARPED_ITERATIVE_MODEL]
            with patch.object(js, '_qt_imports', lambda: imports() | {'QSettings': factory}), \
                    patch.object(js, 'credential_store', store), \
                    patch.object(js, 'application_dir', lambda: programs.parent), \
                    patch.object(QDialog, 'exec', lambda self: QDialog.Rejected), \
                    patch.object(js.SharpEDServerClient, 'get_models',
                        lambda self: SimpleNamespace(models=models, default_model=models[0])):
                wizard = js._JanaWorkflowWizard([], source)
                wizard.run()
                wizard.dialog.show()
                for _ in range(25): app.processEvents()
                assert wizard.reflections_value.text() == '2 HKL records · 2 unique indices'
                geometry = wizard.dialog.geometry()
                wizard.superflip_sharped_tile._trigger()
                deadline = time.monotonic() + 5
                while wizard.model_cache['inflight']:
                    app.processEvents()
                    wizard.refresh_timer.timeout.emit()
                    assert time.monotonic() < deadline
                wizard.cycles.setValue(1)
                assert wizard.model.currentText() == models[0]
                wizard.cycles.setValue(3)
                assert wizard.model.currentText() == models[1]
                wizard.primary_button.click()
                assert wizard.stack.currentWidget() is wizard.page3
                assert wizard.dialog.geometry() == geometry
                assert wizard.update_menu.menu().actions()
                access = SharpEDAccessDialog(wizard.dialog, store=store)
                access.show()
                app.processEvents()
                assert access.isVisible()
                access.close()
                assert js.resolve_active_jana_superflip(programs) == programs / 'superflip.exe'
                assert not (programs / 'superflip_original.exe').exists()
                assert source.read_bytes() == original
                report.update(ok=True, parsed_records=2, navigation=True, model_policy=True,
                    account_dialog=True, update_menu=True, original_superflip_required=False,
                    context='Isolated synthetic project and executable-path fixtures; no native Jana acceptance')
                wizard.dialog.close()
    except Exception as error:
        report.update(ok=False, error_type=type(error).__name__)
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf8')
    return 0 if report.get('ok') else 1
