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


def no_console_popen_kwargs() -> dict:
    """Extra ``subprocess`` keyword arguments that keep a console child
    process from flashing up its own console window on Windows.

    Phase Studio's GUI executables are built windowed (``console=False``), so
    the process has no console of its own. When such a process starts a
    console-subsystem child (EDMA, Superflip), Windows allocates a brand new
    console *with a visible window* for it -- redirecting stdout/stderr to a
    pipe does not prevent that. ``CREATE_NO_WINDOW`` allocates the console
    without a window, which is what makes the child silent while leaving its
    redirected streams, exit code and termination behaviour untouched.

    ``STARTUPINFO``/``SW_HIDE`` is set as well: ``CREATE_NO_WINDOW`` covers
    the console-subsystem case, and the show-window flag covers a child that
    turns out to be a GUI-subsystem executable instead.

    Returns an empty dict on every non-Windows platform, so callers can
    always splat the result and stay cross-platform.
    """
    if sys.platform != "win32":
        return {}
    import subprocess

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }
