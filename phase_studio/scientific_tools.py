"""Bounded, non-calculating identification and safe local-tool installation.

Program identification is a compatibility check, not proof of publisher
authenticity. Downloads require independent package trust before any launch.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProgramValidation:
    state: str
    detail: str = ""
    version: str = ""

    @property
    def ok(self):
        return self.state == "ok"


_verified = {}


def managed_tools_directory() -> Path:
    """Persistent per-user directory; independent of cwd and ONEFILE extraction."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return base / "FZU" / "PhaseStudio" / "scientific_tools"


def _pe_information(data):
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("Not a Windows program")
    pe = struct.unpack_from("<I", data, 60)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Invalid Windows executable header")
    machine, sections = struct.unpack_from("<HH", data, pe + 4)
    optional_size, characteristics = struct.unpack_from("<HH", data, pe + 20)
    if not characteristics & 2 or characteristics & 0x2000:
        raise ValueError("Not an executable application")
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic not in (0x10B, 0x20B):
        raise ValueError("Unsupported Windows executable format")
    directory = optional + (96 if magic == 0x10B else 112)
    import_rva, _size = struct.unpack_from("<II", data, directory + 8)
    section_start = optional + optional_size

    def offset(rva):
        for i in range(sections):
            size, address, raw_size, raw = struct.unpack_from("<IIII", data, section_start + i * 40 + 8)
            if address <= rva < address + max(size, raw_size):
                return raw + rva - address
        raise ValueError("Invalid executable import table")

    imports = []
    if import_rva:
        cursor = offset(import_rva)
        for _ in range(256):
            record = struct.unpack_from("<IIIII", data, cursor)
            if not any(record):
                break
            name_at = offset(record[3])
            end = data.find(b"\0", name_at, name_at + 260)
            if end < 0:
                raise ValueError("Invalid runtime dependency name")
            imports.append(data[name_at:end].decode("ascii"))
            cursor += 20
        else:
            raise ValueError("Too many runtime dependencies")
    return machine, imports


def _dependencies(path, imports):
    """Check local/system DLLs; the launch probe also detects loader failures."""
    result = []
    system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    for name in imports:
        if name.lower().startswith(("api-ms-win-", "ext-ms-win-")):
            continue  # OS API-set contracts are resolved by the Windows loader.
        if Path(name).name != name:
            raise ValueError("Invalid runtime dependency path")
        candidates = [path.parent / name, system / "System32" / name, system / "SysWOW64" / name]
        found = next((p for p in candidates if p.is_file()), None)
        if found is None:
            raise FileNotFoundError("Required runtime dependency is missing: " + name)
        stat = found.stat()
        result.append((str(found), stat.st_size, stat.st_mtime_ns))
    return tuple(result)


def _probe(path, arguments):
    # No project input, no inherited stdin, no visible console, no calculation.
    previous_mode = None
    if os.name == "nt":
        import ctypes
        previous_mode = ctypes.c_uint()
        ctypes.windll.kernel32.SetThreadErrorMode(0x0001 | 0x8000, ctypes.byref(previous_mode))
    try:
        with tempfile.TemporaryDirectory(prefix="phase-studio-identify-") as directory:
            return subprocess.run(
                [str(path), *arguments], cwd=directory, input=b"", capture_output=True,
                timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    finally:
        if previous_mode is not None:
            ctypes.windll.kernel32.SetThreadErrorMode(previous_mode.value, None)


def validate_program(kind, path, *, runner=None, platform=None, dependency_check=None):
    path = Path(path).expanduser().resolve()
    name = getattr(kind, "value", kind)
    if not path.exists():
        return ProgramValidation("not_found")
    if not path.is_file():
        return ProgramValidation("not_a_file")
    if (platform or os.name) != "nt":
        return ProgramValidation("incompatible", "This Windows distribution requires Windows.")
    try:
        stat = path.stat()
        if stat.st_size > 64 * 1024 * 1024:
            return ProgramValidation("wrong_executable", "Unexpected executable size.")
        data = path.read_bytes()
        machine, imports = _pe_information(data)
        if machine not in (0x14C, 0x8664) or (machine == 0x8664 and struct.calcsize("P") == 4):
            return ProgramValidation("incompatible", "Unsupported processor architecture.")
        if name == "superflip":
            identified = b"Superflip version:" in data and b"charge" in data.lower()
            arguments = ["-V"] if b"-V--version" in data else []
        elif name == "edma":
            identified = b"data_structure_from_EDMA" in data and b"edmaatoms" in data
            arguments = []  # Historical Windows EDMA has NO version switch.
        else:
            identified = False
        if not identified:
            return ProgramValidation("wrong_executable", "Program identity could not be verified.")
        dependencies = (dependency_check or _dependencies)(path, imports)
        identity = (name, str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
                    hashlib.sha256(data).hexdigest(), dependencies)
        if runner is None and identity in _verified:
            return _verified[identity]
        completed = (runner or _probe)(path, arguments)
        output = (completed.stdout + completed.stderr).decode("utf-8", "replace")[:16384]
        version = ""
        if name == "superflip" and arguments:
            match = re.search(r"Superflip version:\s*([^\r\n]+)", output)
            successful = completed.returncode == 0 and match is not None
            version = match.group(1).strip() if match else ""
        else:
            expected = "name of your inputfile" if name == "edma" else "name of the input file"
            successful = expected in output and completed.returncode in (0, 2)
        if not successful:
            return ProgramValidation("cannot_launch", "The program did not complete its safe identification check.")
        validated = ProgramValidation("ok", version=version)
        if runner is None:
            if len(_verified) >= 256:
                _verified.clear()
            _verified[identity] = validated
        return validated
    except FileNotFoundError as exc:
        return ProgramValidation("missing_runtime", str(exc))
    except (ValueError, struct.error, UnicodeError):
        return ProgramValidation("wrong_executable", "The executable format could not be verified.")
    except (OSError, subprocess.TimeoutExpired):
        return ProgramValidation("cannot_launch", "The program could not be started safely or did not respond in time.")


@dataclass(frozen=True)
class ApprovedDistribution:
    """Internal release-reviewed trust record; never constructed from a download."""
    url: str
    sha256: str
    licence_reference: str
    permission_reference: str


# No independently authenticated digest / automatic-download rights confirmed.
APPROVED_DISTRIBUTIONS = {}


def install_distribution(kind, destination, *, policy=None, opener=None, validator=None,
                         progress=None, cancelled=None):
    name = getattr(kind, "value", kind)
    policy = policy or APPROVED_DISTRIBUTIONS.get(name)
    if (policy is None or not policy.url.startswith("https://")
            or not re.fullmatch(r"[0-9a-fA-F]{64}", policy.sha256)
            or not policy.licence_reference or not policy.permission_reference):
        raise ValueError("Automatic setup is unavailable: approved licence and independent integrity evidence are required.")
    from urllib.request import urlopen
    report = progress or (lambda *_: None)
    stopped = cancelled or (lambda: False)
    def stage(text):
        if stopped():
            raise InterruptedError("Setup cancelled")
        report(text)
    target_name = "superflip.exe" if name == "superflip" else "EDMA.exe"
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError("An existing installation will not be overwritten.")
    # Deliberately restricted to the app-owned persistent root.
    managed = managed_tools_directory().resolve()
    if managed not in destination.parents:
        raise ValueError("Setup must use the Phase Studio per-user scientific-tools directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage("Preparing download")
    with tempfile.TemporaryDirectory(prefix=".setup-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        archive_path = staging / "download.zip"
        stage("Downloading")
        response = (opener or urlopen)(policy.url, timeout=15)
        digest = hashlib.sha256()
        total = 0
        try:
            with archive_path.open("wb") as stream:
                while True:
                    stage("Downloading")
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > 64 * 1024 * 1024:
                        raise ValueError("The download exceeds the supported package size.")
                    digest.update(chunk)
                    stream.write(chunk)
        finally:
            response.close()
        stage("Verifying downloaded files")
        if digest.hexdigest().lower() != policy.sha256.lower():
            raise ValueError("Package integrity verification failed; no program was installed.")
        stage("Setting up the program")
        extracted = staging / "program"
        extracted.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            if sum(m.file_size for m in archive.infolist()) > 128 * 1024 * 1024:
                raise ValueError("The extracted package exceeds the supported size.")
            for member in archive.infolist():
                stage("Setting up the program")
                relative = Path(member.filename.replace("\\", "/"))
                if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
                    raise ValueError("Unsafe archive path")
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Archive links are not supported")
                target = extracted / relative
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
        matches = [p for p in extracted.rglob("*") if p.name.lower() == target_name.lower() and p.is_file()]
        if len(matches) != 1:
            raise ValueError("The package must contain exactly one expected program.")
        stage("Checking compatibility")
        checked = (validator or validate_program)(kind, matches[0])
        if not checked.ok:
            raise ValueError("The downloaded program failed compatibility verification.")
        stage("Ready to continue")
        # A directory rename publishes executable AND companion files together.
        # No file in an existing or Jana-owned installation is replaced.
        relative_exe = matches[0].relative_to(extracted)
        extracted.rename(destination)
        return destination / relative_exe
