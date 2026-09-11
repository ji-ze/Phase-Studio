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


def ensure_visible_console(title: str = "") -> bool:
    """Give this process one visible console window and bind stdout/stderr to it.

    Used only by the wrapper-only Jana2020 workflows (Superflip only,
    Superflip + SharpED), where the console IS the user's live execution
    feedback because no Phase Studio main window opens.

    The wrapper is built windowed, so it normally has no console at all. That
    is why the console the user used to see was empty: it belonged to the
    Superflip child process, whose stdout/stderr were redirected into a pipe
    for logging, leaving its window with nothing to print. Allocating a
    console here -- and launching the child hidden with its output teed back
    into this console -- keeps exactly one visible window and puts the real
    output in it.

    Returns True when a console is available afterwards. Never raises: losing
    the console must never take down a calculation.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if not kernel32.GetConsoleWindow():
            if not kernel32.AllocConsole():
                return False
        if title:
            try:
                kernel32.SetConsoleTitleW(str(title))
            except Exception:
                pass
    except Exception:
        return False

    # A windowed build starts with sys.stdout/sys.stderr as None (or detached),
    # so bind them to the console device explicitly; otherwise every print()
    # into the freshly allocated console would silently do nothing.
    for name, device, mode in (
        ("stdout", "CONOUT$", "w"),
        ("stderr", "CONOUT$", "w"),
    ):
        stream = getattr(sys, name, None)
        try:
            if stream is not None and stream.fileno() >= 0:
                continue
        except Exception:
            pass
        try:
            handle = open(device, mode, buffering=1, encoding=text_encoding(), errors="replace")
            setattr(sys, name, handle)
        except Exception:
            pass
    return True
