# Third-party notices

Phase Studio's MIT license applies to its own source, not to the separate
runtime components, fonts, scientific executables or hosted SharpED service.
Release packages contain `PhaseStudioLegal` resources (under `_internal` for
ONEDIR), including license texts collected from the exact installed wheels.
Science Gothic's original SIL OFL notice remains beside the font asset.

| Component | Applicable notice/license | Upstream |
| --- | --- | --- |
| Python | PSF license and incorporated third-party notices | https://www.python.org/ |
| PySide6 / Shiboken6 / required Qt libraries | LGPLv3 alternative; separate embedded third-party terms | https://doc.qt.io/qtforpython-6/licenses.html |
| NumPy, bundled numerical libraries | BSD and bundled component notices | https://numpy.org/ |
| Matplotlib and bundled fonts | Matplotlib license and individual font/component notices | https://matplotlib.org/ |
| Gemmi | MPL-2.0 | https://github.com/project-gemmi/gemmi |
| QtVSCodeStyle | MIT | https://github.com/5yutan5/QtVSCodeStyle |
| truststore | MIT | https://github.com/sethmlarson/truststore |
| Pillow / fontTools / contourpy / kiwisolver / cycler / python-dateutil / pyparsing / six / packaging | Individual license texts included from their distributions | See bundled notices |
| PyInstaller bootloader | GPL with the bootloader distribution exception | https://pyinstaller.org/en/stable/license.html |
| Science Gothic | SIL Open Font License 1.1 | https://github.com/googlefonts/science-gothic |
| OpenSSL runtime | Apache-2.0 and included notices | https://www.openssl.org/ |
| Microsoft Visual C++ runtime | Microsoft proprietary redistribution terms; not MIT | https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files |

SciPy is not installed in the release environment or intentionally collected.
If a future build introduces it, its license and dependencies must be audited.
Superflip, EDMA and Jana2020 are external programs, not included in these
packages. SharpED server code, architecture and model weights are not shipped.
Windows Segoe UI is used from the operating system, not bundled as a font asset.

## Qt/PySide source, replacement and notices

The collected Qt libraries are used dynamically. The unused virtual-keyboard
plugin (a GPL-only/commercial option) and unused PDF image plugin are excluded
from both public profiles. No commercial Qt license is asserted. Consult the
exact module's licensing and third-party notices; the PySide wheel metadata
offers LGPL-3.0-only as one alternative.

Users may inspect and modify these libraries, including reverse engineering
needed to debug modifications. ONEDIR exposes replaceable library files.
For ONEFILE, the published Phase Studio source and build specifications allow
rebuilding with modified libraries; no signatures or application checks prevent
this. Instructions are in packaging/README_RELEASE.md.

Corresponding upstream sources for the Qt/PySide 6.11.1 build:

- https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.1-src/
- https://download.qt.io/official_releases/qt/6.11/6.11.1/submodules/
- https://code.qt.io/cgit/pyside/pyside-setup.git/?h=v6.11.1
- https://code.qt.io/cgit/qt/qtbase.git/?h=v6.11.1
- https://code.qt.io/cgit/qt/qtdeclarative.git/?h=v6.11.1
- https://code.qt.io/cgit/qt/qtsvg.git/?h=v6.11.1
- https://code.qt.io/cgit/qt/qtimageformats.git/?h=v6.11.1

Full LGPLv3/GPLv3 texts and an official Qt third-party notice snapshot are
included. Upstream binaries are unmodified except for selection of unused
plugins; Phase Studio patches to Qt/PySide are not present. Distributors must
keep corresponding-source access and all applicable license obligations
available alongside their binary distribution; links alone are not a blanket
compliance certification. Source availability/rebuild instructions and runtime
license rights remain release-publication gates.

Microsoft runtime DLLs are taken from the PySide6 wheel, never from System32
or arbitrary PATH locations. Redistribution is governed by Microsoft's terms
for licensed Visual Studio users. Possessing a DLL or an MIT Phase Studio
license alone does not grant redistribution rights.

## Update verification dependencies

Ed25519 verification uses cryptography (Apache-2.0 OR BSD-3-Clause), with cffi and pycparser. Windows PE validation uses pefile. Their upstream license notices are collected from the installed distributions into PhaseStudioLegal/dependencies in both application packages and the independent updater. Private signing keys are not distributed.
