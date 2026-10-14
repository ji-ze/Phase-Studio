"""Local discovery, package trust, cancellation and workflow continuation guards."""
import hashlib
import io
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scientific_tool_fixtures import program_bytes, identification_process
from phase_studio import requirements as reqs, scientific_tools as tools

K, S = reqs.RequirementKind, reqs.RequirementState


class LocalToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.empty = self.root / "empty"
        self.empty.mkdir()
        self.cache = patch.dict(tools._verified, {}, clear=True)
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.standalone = patch.object(reqs, "DEFAULT_JANA_SUPERFLIP_DIR", self.empty)
        self.standalone.start()
        self.addCleanup(self.standalone.stop)
        self.path = patch.object(reqs.shutil, "which", return_value=None)
        self.path.start()
        self.addCleanup(self.path.stop)
        self.process = patch.object(tools, "_probe", identification_process)
        self.process.start()
        self.addCleanup(self.process.stop)
        self.managed = patch.object(tools, "managed_tools_directory", return_value=self.root / "managed")
        self.managed.start()
        self.addCleanup(self.managed.stop)

    def program(self, name="superflip.exe", directory=None):
        target = (directory or self.root) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(program_bytes(name))
        return target

    def test_configured_superflip(self):
        self.assertTrue(reqs.check_superflip(self.program()).ok)

    def test_configured_edma(self):
        self.assertTrue(reqs.check_edma(self.program("EDMA.exe")).ok)

    def test_actual_jana_priority(self):
        active = self.program(directory=self.root / "different-jana" / "SUPERFLIP")
        self.program(directory=tools.managed_tools_directory() / "superflip")
        self.assertEqual(reqs.check_superflip("", active.parent).suggested_path, active)

    def test_configured_before_jana(self):
        explicit = self.program(directory=self.root / "explicit")
        jana = self.program(directory=self.root / "jana")
        self.assertEqual(reqs.check_superflip(explicit, jana.parent).path, explicit)

    def test_bare_default_does_not_put_path_before_active_jana(self):
        active = self.program(directory=self.root / "active-jana")
        on_path = self.program(directory=self.root / "path-program")
        with patch.object(reqs.shutil, "which", return_value=str(on_path)):
            checked = reqs.check_superflip("superflip.exe", active.parent)
        self.assertEqual(checked.suggested_path, active)

    def test_standalone_managed_before_known(self):
        managed = self.program(directory=tools.managed_tools_directory() / "superflip")
        self.program(directory=self.empty)
        self.assertEqual(reqs.check_superflip("").suggested_path, managed)

    def test_path_last(self):
        target = self.program()
        with patch.object(reqs.shutil, "which", return_value=str(target)):
            self.assertEqual(reqs.check_superflip("").suggested_path, target)

    def test_path_invalid_rejected(self):
        target = self.program("unrelated.exe")
        with patch.object(reqs.shutil, "which", return_value=str(target)):
            self.assertEqual(reqs.check_superflip("").state, S.WRONG_EXECUTABLE)

    def test_missing_path(self):
        self.assertEqual(reqs.check_superflip(self.root / "gone.exe").state, S.NOT_FOUND)

    def test_directory_rejected(self):
        self.assertEqual(reqs.check_edma(self.empty).state, S.NOT_A_FILE)

    def test_expected_filename_insufficient(self):
        p = self.program()
        p.write_bytes(b"MZ arbitrary bytes")
        self.assertFalse(reqs.check_superflip(p).ok)

    def test_wrong_program(self):
        self.assertEqual(reqs.check_superflip(self.program("EDMA.exe")).state, S.WRONG_EXECUTABLE)

    def test_missing_runtime(self):
        p = self.program()
        with patch.object(tools, "_dependencies", side_effect=FileNotFoundError("missing library")):
            self.assertEqual(reqs.check_superflip(p).state, S.MISSING_RUNTIME)

    def test_machine_incompatible(self):
        p = self.program()
        data = bytearray(p.read_bytes())
        struct.pack_into("<H", data, 0x84, 0x9999)
        p.write_bytes(data)
        self.assertEqual(reqs.check_superflip(p).state, S.INCOMPATIBLE)

    def test_other_os_incompatible(self):
        self.assertEqual(tools.validate_program(K.SUPERFLIP, self.program(), platform="posix").state, "incompatible")

    def test_timeout(self):
        with patch.object(tools, "_probe", side_effect=subprocess.TimeoutExpired("program", 5)):
            self.assertEqual(reqs.check_superflip(self.program()).state, S.CANNOT_LAUNCH)

    def test_loader_failure(self):
        with patch.object(tools, "_probe", side_effect=OSError("cannot load")):
            self.assertEqual(reqs.check_edma(self.program("EDMA.exe")).state, S.CANNOT_LAUNCH)

    def test_probe_identity_not_filename(self):
        with patch.object(tools, "_probe", return_value=SimpleNamespace(returncode=0, stdout=b"other app", stderr=b"")):
            self.assertEqual(reqs.check_superflip(self.program()).state, S.CANNOT_LAUNCH)

    def test_no_edma_version_switch(self):
        p = self.program("EDMA.exe")
        calls = []
        def run(path, args):
            calls.append(args)
            return identification_process(path, args)
        self.assertTrue(tools.validate_program(K.EDMA, p, runner=run).ok)
        self.assertEqual(calls, [[]])

    def test_revalidate_modified_file(self):
        p = self.program()
        self.assertTrue(reqs.check_superflip(p).ok)
        p.write_bytes(program_bytes("unrelated.exe"))
        self.assertFalse(reqs.check_superflip(p).ok)

    def test_revalidate_deleted_file(self):
        p = self.program()
        self.assertTrue(reqs.check_superflip(p).ok)
        p.unlink()
        self.assertEqual(reqs.check_superflip(p).state, S.NOT_FOUND)

    def test_revalidate_companion_changes(self):
        p = self.program()
        count = []
        with patch.object(tools, "_dependencies", side_effect=[(("runtime", 1, 1),), (("runtime", 1, 2),)]), patch.object(tools, "_probe", side_effect=lambda p, a: (count.append(1), identification_process(p, a))[1]):
            self.assertTrue(reqs.check_superflip(p).ok)
            self.assertTrue(reqs.check_superflip(p).ok)
        self.assertEqual(len(count), 2)

    def test_successful_validation_cached(self):
        p = self.program()
        with patch.object(tools, "_probe", side_effect=identification_process) as run:
            self.assertTrue(reqs.check_superflip(p).ok)
            self.assertTrue(reqs.check_superflip(p).ok)
            self.assertEqual(run.call_count, 1)

    def test_unrelated_legacy_original_not_discovered(self):
        self.program("superflip_original.exe", self.empty)
        self.assertIsNone(reqs.check_superflip("", self.empty).suggested_path)

    def test_active_jana_root(self):
        from phase_studio.jana_superflip import resolve_jana_installation_root
        installation = self.root / "Jana2020"
        self.assertEqual(resolve_jana_installation_root(installation / "SharpED"), installation)
        self.assertEqual(resolve_jana_installation_root(installation / "SharpED" / "_internal"), installation)

    def test_managed_directory_outside_onefile(self):
        self.managed.stop()
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "local")}), patch.object(sys, "_MEIPASS", str(self.root / "unpack"), create=True):
            self.assertEqual(tools.managed_tools_directory(), self.root / "local" / "FZU" / "PhaseStudio" / "scientific_tools")
        self.managed.start()

    def package(self, payload=None):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("package/superflip.exe", payload or program_bytes("superflip.exe"))
            z.writestr("package/companion.dat", "keep companion")
        return stream.getvalue()

    def install(self, payload=None, **kwargs):
        payload = payload if payload is not None else self.package()
        policy = tools.ApprovedDistribution("https://official.example.test/package.zip", hashlib.sha256(payload).hexdigest(),
                                            "mock licence authority", "mock automated-download permission")
        return tools.install_distribution(K.SUPERFLIP, tools.managed_tools_directory() / "superflip", policy=policy,
                                          opener=lambda *_a, **_k: io.BytesIO(payload), **kwargs)

    def test_approved_mock_install(self):
        stages = []
        installed = self.install(progress=stages.append)
        self.assertTrue(reqs.check_superflip(installed).ok)
        self.assertEqual((installed.parent / "companion.dat").read_text(), "keep companion")
        self.assertEqual(list(dict.fromkeys(stages)), ["Preparing download", "Downloading", "Verifying downloaded files",
                         "Setting up the program", "Checking compatibility", "Ready to continue"])

    def test_unapproved_no_network(self):
        with patch("urllib.request.urlopen") as network:
            with self.assertRaises(ValueError):
                tools.install_distribution(K.SUPERFLIP, self.root / "not-installed")
            network.assert_not_called()

    def test_invalid_checksum_no_launch(self):
        policy = tools.ApprovedDistribution("https://official.example.test/file", "0" * 64, "licence", "permission")
        with patch.object(tools, "validate_program") as validate:
            with self.assertRaisesRegex(ValueError, "integrity"):
                tools.install_distribution(K.SUPERFLIP, tools.managed_tools_directory() / "superflip", policy=policy,
                                           opener=lambda *_a, **_k: io.BytesIO(self.package()))
            validate.assert_not_called()
        self.assertFalse((tools.managed_tools_directory() / "superflip").exists())

    def test_interrupted_download_cleanup(self):
        class Interrupted(io.BytesIO):
            def read(self, _size):
                raise ConnectionError("interrupted")
        policy = tools.ApprovedDistribution("https://official.example.test/file", "0" * 64, "licence", "permission")
        with self.assertRaises(ConnectionError):
            tools.install_distribution(K.SUPERFLIP, tools.managed_tools_directory() / "superflip", policy=policy,
                                       opener=lambda *_a, **_k: Interrupted())
        self.assertEqual(list(tools.managed_tools_directory().glob(".setup-*")), [])

    def test_bad_archive(self):
        with self.assertRaises(zipfile.BadZipFile):
            self.install(b"not zip")

    def test_extraction_traversal_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("../outside.exe", program_bytes("superflip.exe"))
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.install(stream.getvalue())
        self.assertFalse((tools.managed_tools_directory() / "outside.exe").exists())

    def test_downloaded_unsupported_program(self):
        with self.assertRaisesRegex(ValueError, "compatibility"):
            self.install(self.package(b"MZ not a program"))

    def test_failed_validation_not_published(self):
        with self.assertRaisesRegex(ValueError, "compatibility"):
            self.install(validator=lambda *_: tools.ProgramValidation("cannot_launch"))
        self.assertFalse((tools.managed_tools_directory() / "superflip").exists())

    def test_cancel_during_download(self):
        stopped = []
        with self.assertRaises(InterruptedError):
            self.install(progress=lambda text: stopped.append(text) if text == "Downloading" else None,
                         cancelled=lambda: bool(stopped))
        self.assertFalse((tools.managed_tools_directory() / "superflip").exists())

    def test_existing_install_never_overwritten(self):
        existing = self.program(directory=tools.managed_tools_directory() / "superflip")
        before = existing.read_bytes()
        with self.assertRaises(FileExistsError):
            self.install()
        self.assertEqual(existing.read_bytes(), before)

    def test_jana_install_never_modified(self):
        existing = self.program(directory=self.root / "jana" / "SUPERFLIP")
        before = existing.read_bytes()
        policy = tools.ApprovedDistribution("https://official.example.test/file", "0" * 64, "licence", "permission")
        with self.assertRaises(ValueError):
            tools.install_distribution(K.SUPERFLIP, existing.parent / "new", policy=policy)
        self.assertEqual(existing.read_bytes(), before)

    def test_https_required(self):
        policy = tools.ApprovedDistribution("http://official.example.test/file", "0" * 64, "licence", "permission")
        with self.assertRaises(ValueError):
            tools.install_distribution(K.SUPERFLIP, tools.managed_tools_directory() / "superflip", policy=policy)

    def test_only_required_tools(self):
        p = self.program()
        result = reqs.run_preflight(reqs.RequirementSet(superflip=True), superflip_path=p, jana_dir=self.empty)
        self.assertTrue(result.ok)
        self.assertEqual([s.kind for s in result.statuses], [K.SUPERFLIP])

    def test_both_missing(self):
        result = reqs.run_preflight(reqs.RequirementSet(superflip=True, edma=True), jana_dir=self.empty)
        self.assertEqual([s.kind for s in result.failures], [K.SUPERFLIP, K.EDMA])

    def test_both_found_silent(self):
        self.program(directory=self.empty)
        self.program("EDMA.exe", self.empty)
        result = reqs.run_preflight(reqs.RequirementSet(superflip=True, edma=True), jana_dir=self.empty)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.repaired), 2)


class SetupDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.owns_app = QApplication.instance() is None
        cls.app = QApplication.instance() or QApplication([])
        from phase_studio.ui_style import apply_phase_studio_style
        apply_phase_studio_style(cls.app)

    @classmethod
    def tearDownClass(cls):
        if cls.owns_app:
            from PySide6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            import shiboken6
            shiboken6.delete(cls.app)

    def dialog(self, kinds=(K.SUPERFLIP,), **kwargs):
        from phase_studio.scientific_tools_setup import ScientificToolsSetupDialog
        dialog = ScientificToolsSetupDialog(None, [reqs.RequirementStatus(k, S.NOT_FOUND) for k in kinds], **kwargs)
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)
        return dialog

    def finish(self, d):
        until = time.monotonic() + 5
        while d._task is not None and time.monotonic() < until:
            self.app.processEvents()
            time.sleep(.005)
        self.assertIsNone(d._task)

    def test_edma_only_title(self):
        self.assertEqual(self.dialog((K.EDMA,)).windowTitle(), "Set up EDMA")

    def test_superflip_terminology(self):
        from PySide6.QtWidgets import QLabel
        labels = " ".join(l.text() for l in self.dialog().findChildren(QLabel))
        self.assertIn("Required for charge-flipping structure solution", labels)
        self.assertNotIn("phase retrieval", labels)
        self.assertNotIn("neural", labels)

    def test_combined_title(self):
        d = self.dialog((K.SUPERFLIP, K.EDMA))
        self.assertEqual(d.windowTitle(), "Set up scientific tools")
        self.assertEqual(set(d.locate_buttons), {K.SUPERFLIP, K.EDMA})

    def test_manual_only_no_silent_skip(self):
        from PySide6.QtWidgets import QPushButton, QLineEdit
        d = self.dialog()
        buttons = [b.text() for b in d.findChildren(QPushButton)]
        self.assertIn("Official download page", buttons)
        self.assertIn("Locate existing Superflip", buttons)
        self.assertNotIn("Skip for now", buttons)
        self.assertEqual(d.install_buttons, {})
        self.assertEqual(d.findChildren(QLineEdit), [])
        self.assertFalse(d.continue_button.isEnabled())

    def test_invalid_selection_not_saved(self):
        d = self.dialog(validator=lambda *_: tools.ProgramValidation("wrong_executable"))
        d.verify_path(K.SUPERFLIP, "invalid.exe")
        self.finish(d)
        self.assertFalse(d.selected_paths)
        self.assertIn("could not be verified", d.feedback.text())

    def test_manual_selection_resumes(self):
        d = self.dialog(validator=lambda *_: tools.ProgramValidation("ok"))
        d.verify_path(K.SUPERFLIP, "selected.exe")
        self.finish(d)
        self.assertEqual(d.result(), 1)
        self.assertEqual(d.selected_paths[K.SUPERFLIP], str(Path("selected.exe").resolve()))

    def test_combined_requires_both(self):
        d = self.dialog((K.SUPERFLIP, K.EDMA), validator=lambda *_: tools.ProgramValidation("ok"))
        d.verify_path(K.SUPERFLIP, "selected.exe")
        self.finish(d)
        self.assertFalse(d.continue_button.isEnabled())
        d.verify_path(K.EDMA, "EDMA.exe")
        self.finish(d)
        self.assertTrue(d.continue_button.isEnabled())
        d.continue_button.click()
        self.assertEqual(d.result(), 1)

    def test_back_ignores_late_response(self):
        d = self.dialog()
        d.reject()
        d._complete(K.SUPERFLIP, ("late.exe", reqs.RequirementStatus(K.SUPERFLIP, S.OK)), None)
        self.assertFalse(d.selected_paths)

    def test_no_always_on_top(self):
        from PySide6.QtCore import Qt
        d = self.dialog()
        self.assertTrue(d.isModal())
        self.assertFalse(d.windowFlags() & Qt.WindowStaysOnTopHint)

    def test_official_page_exact(self):
        d = self.dialog()
        from PySide6.QtWidgets import QPushButton
        with patch("phase_studio.scientific_tools_setup.QDesktopServices.openUrl") as open_url:
            next(b for b in d.findChildren(QPushButton) if b.text() == "Official download page").click()
            self.assertEqual(open_url.call_args.args[0].toString(), "https://superflip.fzu.cz/")

    def test_separate_verified_licence_links(self):
        from PySide6.QtWidgets import QPushButton
        for kind, expected in [(K.SUPERFLIP, reqs.SUPERFLIP_LICENSE_URL), (K.EDMA, reqs.EDMA_LICENSE_URL)]:
            d = self.dialog((kind,))
            with patch("phase_studio.scientific_tools_setup.QDesktopServices.openUrl") as open_url:
                next(b for b in d.findChildren(QPushButton) if b.text() == "View licence information").click()
                self.assertEqual(open_url.call_args.args[0].toString(), expected)

    def test_combined_loop_preserves_workflow(self):
        from phase_studio.requirements_ui import run_remediation_loop
        config = {"cycles": 5, "model": "SEED", "automatic": False, "threshold": .50,
                  "feedback": .4, "reflection": "powder", "inflip": "project.inflip"}
        before = config.copy()
        paths = {}
        def check():
            return reqs.PreflightResult([reqs.RequirementStatus(k, S.OK if k in paths else S.NOT_FOUND,
                                            path=Path(paths[k]) if k in paths else None) for k in (K.SUPERFLIP, K.EDMA)])
        with patch("phase_studio.scientific_tools_setup.show_scientific_tools_setup",
                   return_value={K.SUPERFLIP: "superflip.exe", K.EDMA: "EDMA.exe"}) as show:
            self.assertTrue(run_remediation_loop(None, check, lambda k: paths.get(k, ""), lambda k, p, _: paths.update({k:p})))
            self.assertEqual(show.call_count, 1)
        self.assertEqual(config, before)

    def test_no_dialog_if_available(self):
        from phase_studio.requirements_ui import run_remediation_loop
        with patch("phase_studio.requirements_ui.show_requirement_remediation_dialog") as show:
            self.assertTrue(run_remediation_loop(None, lambda: reqs.PreflightResult(), lambda _: "", lambda *_: None))
            show.assert_not_called()

    def test_back_returns_original_action(self):
        from phase_studio.requirements_ui import run_remediation_loop
        with patch("phase_studio.scientific_tools_setup.show_scientific_tools_setup", return_value=None):
            persist = unittest.mock.Mock()
            check = lambda: reqs.PreflightResult([reqs.RequirementStatus(k, S.NOT_FOUND) for k in (K.SUPERFLIP, K.EDMA)])
            self.assertFalse(run_remediation_loop(None, check, lambda _: "", persist))
            persist.assert_not_called()

    def test_real_wizard_browser_back_and_setup_preserve_all_controls(self):
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QDialog, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QRadioButton, QPushButton
        from phase_studio import jana_superflip as js
        from phase_studio.scientific_tools_setup import show_scientific_tools_setup
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inflip = root / "setup-fixture.inflip"
            inflip.write_text("title setup_fixture\nperform CF\ndimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\ndataformat intensity\nfbegin\n1 0 0 10 2\nendf\n")
            original = js._qt_imports
            def imports():
                qt = original()
                qt["QSettings"] = lambda org, app: QSettings(str(root / (app + ".ini")), QSettings.IniFormat)
                return qt
            catalog = SimpleNamespace(models=["PEAK A (model prediction)", "SEED (cyclic CF)"], default_model="PEAK A (model prediction)")
            with patch.object(js, "_qt_imports", imports), patch.object(js.SharpEDServerClient, "get_models", return_value=catalog):
                with patch.object(QDialog, "exec", return_value=QDialog.Rejected):
                    wizard = js._JanaWorkflowWizard([], inflip)
                    wizard.run()
                self.addCleanup(wizard.dialog.deleteLater)
                self.addCleanup(wizard.dialog.close)
                self.addCleanup(wizard.refresh_timer.stop)
                wizard.workflow_state["key"] = js.WORKFLOW_PHASE_RECYCLING
                wizard._workflow_changed()
                wizard.cycles.setValue(3)
                wizard.model.clear()
                wizard.model.addItems(catalog.models)
                wizard.model.setCurrentText("SEED (cyclic CF)")
                wizard.model.activated.emit(wizard.model.currentIndex())
                controls = []
                for kind in (QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QRadioButton):
                    controls.extend(wizard.dialog.findChildren(kind))
                def snapshot():
                    def value(w):
                        if isinstance(w, QLineEdit): return w.text()
                        if isinstance(w, QComboBox): return w.currentText(), w.currentData()
                        if isinstance(w, (QSpinBox, QDoubleSpinBox)): return w.value()
                        return w.isChecked()
                    return [value(w) for w in controls]
                before = snapshot()
                statuses = [reqs.RequirementStatus(k, S.NOT_FOUND) for k in (K.SUPERFLIP, K.EDMA)]
                def inspect(dialog):
                    next(b for b in dialog.findChildren(QPushButton) if b.text() == "Official download page").click()
                    self.assertIs(dialog.parentWidget(), wizard.dialog)
                    dialog.reject()
                    return QDialog.Rejected
                with patch.object(QDialog, "exec", inspect), patch("phase_studio.scientific_tools_setup.QDesktopServices.openUrl") as browser, patch.object(js, "launch_phase_studio_from_jana") as launch, patch.object(js, "launch_autosolve_from_jana") as autosolve:
                    self.assertIsNone(show_scientific_tools_setup(wizard.dialog, statuses))
                    self.assertEqual(browser.call_args.args[0].toString(), "https://superflip.fzu.cz/")
                    launch.assert_not_called()
                    autosolve.assert_not_called()
                self.assertEqual(snapshot(), before)
                self.assertEqual(wizard.inflip_path, inflip)
                self.assertEqual(wizard.workflow_state["key"], js.WORKFLOW_PHASE_RECYCLING)


if __name__ == "__main__":
    unittest.main()
