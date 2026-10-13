"""Public developer archive boundaries and byte-verified extraction."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
import io
from contextlib import redirect_stdout
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("release_archive", ROOT / "packaging/tools/package_release.py")
archive_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive_module)
spec = importlib.util.spec_from_file_location("release_legal", ROOT / "packaging/pyinstaller/release_legal.py")
legal_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legal_module)


class PublicReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.developer = self.root / "PhaseStudio-Jana2020-2.0.2"
        (self.developer / "_internal").mkdir(parents=True)
        (self.developer / "Phase_studio.exe").write_bytes(b"test executable fixture")
        (self.developer / "_internal/runtime.dll").write_bytes(b"test runtime fixture")
        self.release = self.root / "release"

    def test_complete_runtime_archive_and_hashes(self):
        self.release.mkdir()
        exe = self.release / "PhaseStudio-2.0.2-x64.exe"
        exe.write_bytes(b"standalone fixture")
        output = archive_module.package_release(self.developer, self.release)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read("PhaseStudio-Jana2020-2.0.2/_internal/runtime.dll"), b"test runtime fixture")
            self.assertNotIn("superflip.exe", archive.namelist())
        checksums = (self.release / "SHA256SUMS.txt").read_text()
        self.assertIn(archive_module.digest(exe), checksums)
        self.assertIn(archive_module.digest(output), checksums)
        self.assertNotIn("Installer", checksums)

    def test_missing_runtime_rejected(self):
        (self.developer / "_internal/runtime.dll").unlink()
        (self.developer / "_internal").rmdir()
        with self.assertRaises(ValueError):
            archive_module.package_release(self.developer, self.release)

    def test_wrong_executable_name_rejected(self):
        (self.developer / "Phase_studio.exe").rename(self.developer / "superflip.exe")
        with self.assertRaises(ValueError):
            archive_module.package_release(self.developer, self.release)

    def test_wrong_archive_root_rejected(self):
        wrong = self.root / "unrelated"
        with self.assertRaises(ValueError):
            archive_module.package_release(wrong, self.release)

    def test_unused_optional_plugins_excluded_required_qt_retained(self):
        entries = [(name, name, "BINARY") for name in
                   ("Qt6Core.dll", "Qt6Widgets.dll", "Qt6VirtualKeyboard.dll", "qpdf.dll")]
        result = legal_module.exclude_unused_qt_plugins(entries)
        self.assertEqual([entry[0] for entry in result], ["Qt6Core.dll", "Qt6Widgets.dll"])

    def test_jana_version_diagnostic_does_not_open_wizard(self):
        from phase_studio import jana_superflip
        output = io.StringIO()
        with patch.object(jana_superflip, "_qt_imports", side_effect=AssertionError("Unexpected GUI")), redirect_stdout(output):
            self.assertEqual(jana_superflip.main(["Phase_studio.exe", "--version"]), 0)
        self.assertEqual(output.getvalue().strip(), "2.0.2")


if __name__ == "__main__":
    unittest.main()
