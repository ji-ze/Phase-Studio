"""DPI regression checks for SharpED/EDMA requirement-remediation dialogs."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCALES = ("1", "1.25", "1.5")

CHILD = r'''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QWidget
from phase_studio import requirements as reqs
from phase_studio.requirements_ui import show_requirement_remediation_dialog
from phase_studio.ui_style import apply_phase_studio_style

app = QApplication([sys.argv[0]])
apply_phase_studio_style(app)
parent = QWidget()
parent.resize(820, 780)
parent.show()
app.processEvents()
problems = []

def inspect(dialog):
    dialog.show()
    app.processEvents()
    screen = dialog.screen().availableGeometry()
    frame = dialog.frameGeometry()
    if not screen.contains(frame):
        problems.append("dialog frame leaves available screen")
    for button in dialog.findChildren(QPushButton):
        top_left = button.mapTo(dialog, QPoint(0, 0))
        if top_left.x() < 0 or top_left.y() < 0:
            problems.append(f"{button.text()} starts outside client")
        if top_left.x() + button.width() > dialog.width() or top_left.y() + button.height() > dialog.height():
            problems.append(f"{button.text()} ends outside client")
        if button.width() < button.sizeHint().width() or button.height() < button.sizeHint().height():
            problems.append(f"{button.text()} is clipped")
    dialog.reject()
    return QDialog.Rejected

QDialog.exec = inspect
show_requirement_remediation_dialog(
    parent,
    reqs.RequirementStatus(reqs.RequirementKind.SHARPED, reqs.RequirementState.TOKEN_MISSING),
)
show_requirement_remediation_dialog(
    parent,
    reqs.RequirementStatus(reqs.RequirementKind.EDMA, reqs.RequirementState.NOT_CONFIGURED),
)
for problem in problems:
    print("PROBLEM", problem)
print("DONE")
'''


def main() -> int:
    results = []
    for scale in SCALES:
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=scale, PYTHONIOENCODING="utf-8")
        run = subprocess.run(
            [sys.executable, "-c", CHILD, str(ROOT)],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=60,
        )
        tag = f"{float(scale) * 100:.0f}%"
        checks = [
            (f"{tag}: modal checks completed", run.returncode == 0 and "DONE" in run.stdout),
            (f"{tag}: SharpED/EDMA buttons and frames are not clipped", "PROBLEM" not in run.stdout),
        ]
        for name, ok in checks:
            results.append((name, ok))
            print(("PASS" if ok else "FAIL") + " - " + name)
        if run.returncode or "PROBLEM" in run.stdout:
            print(run.stdout)
            print(run.stderr)
    failures = [name for name, ok in results if not ok]
    if failures:
        print(f"\n{len(failures)} of {len(results)} checks FAILED")
        return 1
    print(f"\nAll {len(results)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
