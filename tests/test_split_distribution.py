"""Distribution boundaries and transactional Jana lifecycle; no real installation touched."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from phase_studio import jana_integration as ji
from phase_studio.version import VERSION


class SplitDistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "Jana2020"
        self.target = self.root / "SUPERFLIP"
        self.target.mkdir(parents=True)
        (self.target / "superflip.exe").write_bytes(b"original-superflip")
        (self.target / "EDMA.exe").write_bytes(b"unchanged-edma")
        self.payload = Path(self.temp.name) / "payload"
        (self.payload / "_internal").mkdir(parents=True)
        (self.payload / "superflip.exe").write_bytes(b"wrapper")
        (self.payload / "_internal/runtime.dll").write_bytes(b"runtime")

    def install(self, version=VERSION):
        result = ji.install_or_update_integration(self.target, self.payload, bundled_version=version)
        self.assertTrue(result.success, result.message)
        self.assertEqual((self.target / "EDMA.exe").read_bytes(), b"unchanged-edma")

    def snapshot(self):
        return {str(p.relative_to(self.target)): p.read_bytes() for p in self.target.rglob("*") if p.is_file()}

    def test_canonical_version(self):
        self.assertEqual(VERSION, "1.0.9")
        self.assertEqual(ji.bundled_integration_version(), VERSION)
        import phase_studio.app as app, phase_studio.jana_superflip as wizard
        self.assertEqual(app.__version__, VERSION)
        self.assertEqual(wizard.__version__, VERSION)
        self.assertIn('version = { attr = "phase_studio.version.VERSION" }', (ROOT / "pyproject.toml").read_text())

    def test_installer_import_does_not_load_scientific_gui(self):
        code = "import sys; import phase_studio.jana_installer; assert 'phase_studio.app' not in sys.modules; assert 'phase_studio.jana_superflip' not in sys.modules"
        subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)

    def test_onefile_installer_uses_private_embedded_payload(self):
        bundle = Path(self.temp.name) / "onefile-temp"
        payload_package = bundle / "JanaIntegrationPayload"
        package_payload = __import__("runpy").run_path(
            str(ROOT / "packaging/tools/package_jana_payload.py")
        )["package_payload"]
        package_payload(self.payload, payload_package)
        adjacent = Path(self.temp.name) / "public"
        adjacent.mkdir()
        import shutil
        shutil.copytree(self.payload, adjacent / "JanaIntegration")
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "_MEIPASS", str(bundle), create=True), \
             patch.object(sys, "executable", str(adjacent / "installer.exe")):
            extracted = ji.resolve_bundled_jana_payload_dir()
            self.assertIsNotNone(extracted)
            self.assertNotEqual(extracted, adjacent / "JanaIntegration")
            self.assertEqual(self.snapshot_payload(extracted), self.snapshot_payload(self.payload))
            installed = ji.install_or_update_integration(self.target, extracted)
            self.assertTrue(installed.success, installed.message)
        ji._cleanup_embedded_payload()
        self.assertTrue((self.target / "superflip.exe").is_file())
        self.assertTrue((self.target / "_internal/runtime.dll").is_file())

    @staticmethod
    def snapshot_payload(root):
        return {str(path.relative_to(root)): path.read_bytes()
                for path in Path(root).rglob("*") if path.is_file()}

    def test_embedded_payload_rejects_path_escape(self):
        import zipfile
        package = Path(self.temp.name) / "unsafe"
        package.mkdir()
        archive = package / "jana-wrapper.zip"
        manifest = package / "jana-wrapper-manifest.json"
        data = b"escape"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("../escape.exe", data)
        import hashlib
        manifest.write_text(json.dumps({"format": 1, "files": [{
            "path": "../escape.exe", "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }]}))
        with self.assertRaisesRegex(ValueError, "unsafe path"):
            ji._extract_verified_payload(archive, manifest)
        self.assertFalse((package.parent / "escape.exe").exists())

    def test_entrypoint_versions(self):
        for module in ("phase_studio", "phase_studio.jana_installer"):
            output = subprocess.check_output([sys.executable, "-m", module, "--version"], cwd=ROOT, text=True)
            self.assertEqual(output.strip(), VERSION)

    def test_detection_install_and_remove(self):
        with patch.object(ji, "default_jana_root_candidates", return_value=[]):
            self.assertEqual(ji.detect_jana_root([self.target / "EDMA.exe"]), self.root)
        self.install()
        self.assertEqual((self.target / "superflip_original.exe").read_bytes(), b"original-superflip")
        marker, error = ji.read_marker(self.target)
        self.assertFalse(error)
        self.assertEqual(marker.version, VERSION)
        self.assertEqual(marker.payload_hash, ji._sha256_file(self.target / "superflip.exe"))
        self.assertTrue(ji.remove_integration(self.target).success)
        self.assertEqual(self.snapshot(), {"superflip.exe": b"original-superflip", "EDMA.exe": b"unchanged-edma"})

    def test_108_update_and_repair(self):
        self.install("1.0.8")
        self.assertEqual(ji.classify_install_state(ji.inspect_jana_superflip_dir(self.target)), ji.IntegrationState.UPDATE_AVAILABLE)
        (self.payload / "superflip.exe").write_bytes(b"new-wrapper")
        self.install()
        (self.target / "superflip.exe").unlink()
        self.assertEqual(ji.classify_install_state(ji.inspect_jana_superflip_dir(self.target)), ji.IntegrationState.REPAIR_REQUIRED)
        self.install()
        self.assertEqual((self.target / "superflip.exe").read_bytes(), b"new-wrapper")

    def test_unknown_files_and_marker_are_not_overwritten(self):
        (self.target / "_internal").mkdir()
        (self.target / "_internal/foreign.dll").write_bytes(b"foreign")
        before = self.snapshot()
        self.assertFalse(ji.install_or_update_integration(self.target, self.payload).success)
        self.assertEqual(before, self.snapshot())

    def test_wrapper_hash_conflict_blocks_update_and_remove(self):
        self.install()
        (self.target / "superflip.exe").write_bytes(b"unknown-replacement")
        before = self.snapshot()
        self.assertFalse(ji.install_or_update_integration(self.target, self.payload).success)
        self.assertFalse(ji.remove_integration(self.target).success)
        self.assertEqual(before, self.snapshot())

    def test_foreign_marker_blocks_update_and_remove(self):
        self.install()
        path = self.target / ji.MARKER_FILENAME
        marker = json.loads(path.read_text())
        marker["product"] = "Unrelated program"
        path.write_text(json.dumps(marker))
        before = self.snapshot()
        self.assertFalse(ji.install_or_update_integration(self.target, self.payload).success)
        self.assertFalse(ji.remove_integration(self.target).success)
        self.assertEqual(before, self.snapshot())

    def test_install_rollback_after_wrapper_swap(self):
        before = self.snapshot()
        real_move = ji.shutil.move
        def fail_runtime(source, dest, *args, **kwargs):
            if Path(source).parent.name == ji.STAGING_DIR_NAME and Path(source).name == "_internal":
                raise OSError("synthetic runtime swap failure")
            return real_move(source, dest, *args, **kwargs)
        with patch.object(ji.shutil, "move", side_effect=fail_runtime):
            self.assertFalse(ji.install_or_update_integration(self.target, self.payload).success)
        self.assertEqual(before, self.snapshot())

    def test_update_rollback_before_backup_move(self):
        self.install("1.0.8")
        before = self.snapshot()
        real_move = ji.shutil.move
        def fail_backup(source, dest, *args, **kwargs):
            if str(dest).endswith(ji.BACKUP_EXE_SUFFIX):
                raise OSError("synthetic locked original wrapper")
            return real_move(source, dest, *args, **kwargs)
        with patch.object(ji.shutil, "move", side_effect=fail_backup):
            self.assertFalse(ji.install_or_update_integration(self.target, self.payload).success)
        self.assertEqual(before, self.snapshot())

    def test_remove_rollback_preserves_previous_installation(self):
        self.install()
        before = self.snapshot()
        real_move = ji.shutil.move
        def fail_restore(source, dest, *args, **kwargs):
            if Path(source).name == ji.ORIGINAL_EXE_NAME:
                raise OSError("synthetic restore failure")
            return real_move(source, dest, *args, **kwargs)
        with patch.object(ji.shutil, "move", side_effect=fail_restore):
            self.assertFalse(ji.remove_integration(self.target).success)
        self.assertEqual(before, self.snapshot())

    def test_missing_original_prevents_removal(self):
        self.install()
        (self.target / ji.ORIGINAL_EXE_NAME).unlink()
        before = self.snapshot()
        self.assertFalse(ji.remove_integration(self.target).success)
        self.assertEqual(before, self.snapshot())

    def test_installer_dialog_drives_lifecycle(self):
        from PySide6.QtWidgets import QApplication, QLabel, QMessageBox
        from phase_studio.jana_installer import create_integration_dialog
        app = QApplication.instance() or QApplication([])
        self.install("1.0.8")
        with patch.object(ji, "default_jana_root_candidates", return_value=[self.root]), \
             patch.object(ji, "resolve_bundled_jana_payload_dir", return_value=self.payload), \
             patch.object(ji, "authenticode_signature_status", return_value="unsigned"), \
             patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            dialog = create_integration_dialog()
            self.assertIn(VERSION, dialog.windowTitle())
            self.assertEqual(dialog.path_edit.text(), str(self.root))
            status_text = " ".join(label.text() for label in dialog.status_group.findChildren(QLabel))
            self.assertIn("SUPERFLIP directory detected", status_text)
            self.assertIn("Original Superflip detected", status_text)
            self.assertIn("EDMA detected", status_text)
            self.assertIn("Integration package: Ready", dialog.signature_label.text())
            self.assertIn("Package integrity:", dialog.signature_label.text())
            self.assertIn("Digital signature: Not present", dialog.signature_label.text())
            self.assertEqual(dialog.primary_button.text(), "Update integration")
            dialog.primary_button.click()
            self.assertEqual(dialog.primary_button.text(), "Repair integration")
            (self.target / "superflip.exe").unlink()
            dialog.refresh_status(self.root)
            dialog.primary_button.click()
            self.assertTrue((self.target / "superflip.exe").is_file())
            dialog.remove_button.click()
            self.assertEqual(dialog.primary_button.text(), "Install integration")
            dialog.primary_button.click()
            self.assertTrue((self.target / ji.MARKER_FILENAME).is_file())
            dialog.deleteLater()
            app.processEvents()

    def test_standalone_has_result_export_action_but_no_management_action(self):
        from PySide6.QtWidgets import QApplication, QPushButton
        from phase_studio.app import IterativeSuperflipPipelineQtGUI
        app = QApplication.instance() or QApplication([])
        with patch.object(IterativeSuperflipPipelineQtGUI, "load_settings"), \
             patch.object(IterativeSuperflipPipelineQtGUI, "save_settings"), \
             patch.object(IterativeSuperflipPipelineQtGUI, "refresh_sharped_models"):
            win = IterativeSuperflipPipelineQtGUI()
            self.assertFalse(win.jana_action_btn.isHidden())
            self.assertEqual(win.jana_action_btn.text(), "Save map and model")
            self.assertFalse(win.jana_action_btn.isEnabled())
            self.assertFalse(hasattr(win, "open_install_to_jana_dialog"))
            self.assertFalse(any("Install" in button.text() or "Repair" in button.text()
                                 for button in win.findChildren(QPushButton)))
            win.timer.stop()
            win.close()
            win.deleteLater()
            app.processEvents()

    def test_store_selects_only_standalone(self):
        script = (ROOT / "packaging/build_store_msix.ps1").read_text()
        self.assertIn('PhaseStudioStore.spec', script)
        self.assertIn('--profile store', script)
        self.assertNotIn('JanaSigningCertificate', script)
        self.assertIn('Store packaging refuses a Jana installation payload', script)
        self.assertIn('$Version = $canonicalVersion', script)

    def test_public_release_contract_is_two_onefile_executables(self):
        build = (ROOT / "packaging/build_windows.ps1").read_text()
        spec = (ROOT / "packaging/pyinstaller/PhaseStudio.spec").read_text()
        self.assertIn('PhaseStudio-1.0.9-x64.exe', build)
        self.assertIn('PhaseStudio-Jana2020-Installer-1.0.9-x64.exe', build)
        self.assertIn('$publicFiles.Count -ne 2', build)
        self.assertIn('a.binaries, a.datas', spec)
        self.assertIn('"JanaIntegrationPayload"', spec)
        self.assertIn('Splash(', spec)
        self.assertIn('phase_studio_splash.png', spec)
        self.assertIn('splash, splash.binaries, a.binaries, a.datas', spec)
        self.assertIn('PHASE_STUDIO_STARTUP_PROBE', (ROOT / "phase_studio/app.py").read_text(encoding="utf-8"))
        self.assertIn('PHASE_STUDIO_STARTUP_PROBE', (ROOT / "phase_studio/jana_installer.py").read_text(encoding="utf-8"))
        self.assertTrue((ROOT / "phase_studio/assets/phase_studio_splash.png").is_file())
        self.assertTrue((ROOT / "packaging/pyinstaller/PhaseStudioStore.spec").is_file())

    def test_portable_distribution_manifest_schema_is_stable(self):
        portable = __import__("runpy").run_path(
            str(ROOT / "packaging/pyinstaller/portable_runtime.py")
        )
        manifest_path = Path(self.temp.name) / "portable-runtime.json"
        portable["write_portable_manifest"](
            manifest_path,
            app="PhaseStudio",
            staged_runtime=[{"name": "vcruntime140.dll", "version": "14.0", "source": "wheel"}],
            qt_report={"pyside6_version": "6.x", "shiboken6_version": "6.x", "pyside6_path": "Qt"},
            removed_ucrt=["ucrtbase.dll"],
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(set(manifest), {
            "app", "python", "python_prefix", "qt", "msvc_runtime",
            "removed_app_local_ucrt", "required_binaries",
        })
        self.assertEqual(manifest["app"], "PhaseStudio")
        self.assertEqual(manifest["qt"], {
            "pyside6_version": "6.x", "shiboken6_version": "6.x", "pyside6_path": "Qt",
        })
        self.assertEqual(manifest["msvc_runtime"], [
            {"name": "vcruntime140.dll", "version": "14.0", "source": "wheel"},
        ])
        self.assertEqual(manifest["removed_app_local_ucrt"], ["ucrtbase.dll"])
        self.assertEqual(
            manifest["required_binaries"],
            ["Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll"],
        )

    def test_scientific_functions_match_integrated_baseline(self):
        git = r"C:\Program Files\Git\cmd\git.exe" if os.name == "nt" else "git"
        for filename in ("app.py", "jana_superflip.py", "sharped_server_client.py", "sharped_map_scaling.py"):
            baseline = subprocess.check_output([git, "show", f"main:phase_studio/{filename}"], cwd=ROOT).decode()
            current = (ROOT / "phase_studio" / filename).read_text(encoding="utf-8")
            def functions(text):
                return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(text).body
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
            old, new = functions(baseline), functions(current)
            excluded = {"create_phase_studio_logo_pixmap", "create_phase_studio_app_icon", "apply_phase_studio_app_icon",
                        "create_phase_studio_brand_header", "create_phase_studio_context_banner", "apply_safe_dialog_geometry",
                        "fitted_dialog_client_size", "fit_dialog_to_available_screen", "classify_log_record",
                        # Explicitly extended for immutable validation holdouts;
                        # the existing correction formula remains unchanged.
                        "apply_map_feedback_to_reflections", "compute_rfree", "atom_recall_precision",
                        # Explicit profile-aware per-cycle/source reporting.
                        "write_metrics_csv"}
            if filename == "app.py":
                # API orchestration is pinned by test_sharped_api_contract.py;
                # DEFAULT resolution here was restored from commit 396270c.
                # Performance-only wrappers and in-memory FFT reuse are pinned
                # by test_performance.py; the numerical outputs remain covered
                # by the golden scientific suite.
                excluded |= {"run_sharped_deblur", "assess_xplor_map",
                             "run_superflip_cycle", "run_superflip_symmetrize_map",
                             "run_edma_on_xplor", "run_command",
                             "xplor_fft_predictions", "compose_fobs_phicalc_map",
                             # Moved byte-for-byte policies are pinned by
                             # test_scientific_core.py and inflip_io.py.
                             "split_inflip_line", "inflip_first_token",
                             "insert_before_fbegin", "without_inflip_keywords",
                             "inflip_header_for_m80", "define_m80_inflip_from_model"}
                # Uncalled legacy Authenticode warning chain; current
                # requirement/error dialogs own executable guidance.
                excluded |= {"resolve_executable_for_validation", "warn_if_windows_unsigned_exe"}
                # Moved unchanged with the workflow-metrics presentation.
                excluded |= {"robust_detail_range"}
                # Presentation aliases accepted by the metadata-source combo;
                # authoritative resolution is covered by test_final_ui.py.
                excluded |= {"normalize_metadata_source"}
                # Startup-only handoff from PyInstaller's extraction splash to
                # the existing Qt splash; no scientific code is involved.
                excluded |= {"main"}
            elif filename == "jana_superflip.py":
                # UI-only requirement routing: the former generic token warning
                # became unreachable once the shared dedicated remediation dialog
                # was connected, so its removal is intentional and non-scientific.
                excluded |= {"launch_phase_studio_from_jana", "main", "_show_missing_token_warning",
                             "extract_embedded_hkl",
                             "deblur_with_sharped", "split_inline_comment", "split_inflip_line",
                             "first_token", "line_has_xplor_output", "insert_before_fbegin",
                             "ensure_xplor_output", "without_keywords", "add_modelseed_modelfile",
                             "apply_reference_override", "inflip_header_for_m80", "define_m80_inflip"}
            elif filename == "sharped_server_client.py":
                # These split-catalog helpers postdate the restored historical
                # client. The one-host behavior is pinned by its contract test.
                excluded |= {"normalize_server_url", "model_selection", "current_model_catalog",
                             "model_catalog_status", "apply_model_catalog", "sync_model_catalog",
                             "resolve_effective_model"}
            for name in old.keys() - excluded:
                self.assertEqual(old[name], new.get(name), f"{filename}:{name}")
            if filename == "app.py":
                metrics_ui = (ROOT / "phase_studio" / "workflow_metrics_ui.py").read_text(encoding="utf-8")
                moved = functions(metrics_ui)
                self.assertEqual(old["robust_detail_range"], moved.get("robust_detail_range"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
