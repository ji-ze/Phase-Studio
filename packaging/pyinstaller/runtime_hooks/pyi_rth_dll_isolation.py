"""Runtime hook: resolve native DLLs from this distribution, never from PATH.

Phase Studio is deployed next to other crystallography software -- most
importantly the Jana2020 tree, where the Superflip wrapper replaces
``superflip.exe`` inside ``C:\\Jana2020\\SUPERFLIP\\``.  By default the Windows
loader searches, for a DLL requested by base name:

    1. modules already loaded in the process (by base name)
    2. the *executable's own directory*
    3. the system directory
    4. ...
    5. every directory on ``PATH``

Steps 2 and 5 are what let a foreign ``Qt6Core.dll``, ``icuuc.dll`` or VC
runtime belonging to some other installed program get loaded into Phase Studio.
When the foreign copy is a different build of the same library, the load
succeeds but an expected export is absent, and Python reports::

    ImportError: DLL load failed while importing QtCore:
    The specified procedure could not be found.

``SetDefaultDllDirectories`` replaces that search order process-wide with an
explicit one.  We keep only the system directory, the directory of the DLL
being loaded, and directories registered with ``AddDllDirectory`` -- then
register this bundle's own directories.  ``PATH`` and the executable's
directory stop contributing entirely.

Notes
-----
* Extension modules are loaded by CPython with an absolute path and
  ``LOAD_WITH_ALTERED_SEARCH_PATH``, so a ``.pyd``'s own directory is still
  searched for its dependencies; ``LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR`` keeps
  that working for Qt plugins loading ``Qt6*.dll`` as well.
* ``System32`` stays in the search order deliberately: Qt 6 links the ICU
  library that ships with Windows (``icuuc.dll``), and that must resolve from
  Windows itself.
* The call is a no-op on non-Windows platforms and degrades to "leave the
  default order alone" if the API is unavailable.
"""

import os
import sys

_LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800
_LOAD_LIBRARY_SEARCH_USER_DIRS = 0x00000400
_LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR = 0x00000100


def _isolate_dll_search_path():
    if sys.platform != "win32":
        return

    bundle_dir = getattr(sys, "_MEIPASS", None)
    if not bundle_dir:
        return

    import ctypes
    from ctypes import wintypes

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetDefaultDllDirectories.restype = wintypes.BOOL
        kernel32.SetDefaultDllDirectories.argtypes = [wintypes.DWORD]
    except (OSError, AttributeError):
        return

    # Register our own directories first: SetDefaultDllDirectories takes effect
    # immediately, so the search path must not be narrowed before the
    # replacements are in place.
    #
    # Qt DLLs live in _internal/PySide6 next to the extension modules; the
    # staged VC runtime lives at the _internal root.
    search_dirs = [
        bundle_dir,
        os.path.join(bundle_dir, "PySide6"),
        os.path.join(bundle_dir, "shiboken6"),
    ]
    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        try:
            # Keep the handle alive for the process lifetime by discarding it:
            # AddDllDirectory entries persist until RemoveDllDirectory.
            os.add_dll_directory(directory)
        except (OSError, AttributeError):
            pass

    flags = (_LOAD_LIBRARY_SEARCH_SYSTEM32
             | _LOAD_LIBRARY_SEARCH_USER_DIRS
             | _LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR)
    kernel32.SetDefaultDllDirectories(flags)

    # Qt must not be told to load plugins from another Qt installation:
    # QT_PLUGIN_PATH inherited from Anaconda, QGIS or another Qt application
    # would point our Qt at foreign, incompatible plugin binaries.
    #
    # PyInstaller's own PySide6 runtime hook sets these to the bundled plugin
    # directory, and hook order is not guaranteed, so only entries that fall
    # *outside* this bundle are discarded -- never the whole variable.
    bundle_prefix = os.path.normcase(os.path.abspath(bundle_dir))
    for variable in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        value = os.environ.get(variable)
        if not value:
            continue
        inside = [
            part for part in value.split(os.pathsep)
            if part and os.path.normcase(os.path.abspath(part)).startswith(bundle_prefix)
        ]
        if inside:
            os.environ[variable] = os.pathsep.join(inside)
        else:
            del os.environ[variable]

    # QTDIR would make Qt look for its own installation tree elsewhere.
    for variable in ("QTDIR", "QT_DIR"):
        os.environ.pop(variable, None)


_isolate_dll_search_path()
