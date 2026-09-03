"""Small, dependency-free helpers for launching and interoperating with
external Windows processes (Superflip, EDMA, the Jana2020 wrapper).

Deliberately has no PySide6/matplotlib/numpy/gemmi dependency: both
phase_studio.app (the full GUI, heavy imports) and phase_studio.jana_superflip
(which keeps its own import footprint light for the single-pass Jana2020
wrapper path) import from here, so this module must stay importable with
nothing beyond the standard library.
"""

from __future__ import annotations

import locale
import os
import sys


def text_encoding() -> str:
    """Best text encoding for this platform's console/subprocess I/O."""
    if os.name == "nt":
        return "mbcs"
    return locale.getpreferredencoding(False) or "utf-8"


def allow_external_process_foreground(process_id: int) -> bool:
    """Let a newly launched Windows process use normal native foreground rules.

    This grants permission once; it neither activates a window nor polls for
    one. Other platforms deliberately keep their default window-manager
    behaviour. Never raises: a failure here should never interrupt the
    calling workflow.
    """
    if sys.platform != "win32" or int(process_id) <= 0:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        return bool(user32.AllowSetForegroundWindow(int(process_id)))
    except Exception:
        return False
