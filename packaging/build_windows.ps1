<#
.SYNOPSIS
    Developer/testing build: PhaseStudio (this repo's own packaging spec) and
    the known-working Jana2020 Superflip wrapper (the repository's root-level
    superflip.spec), both PyInstaller ONEDIR, output under dist\.

.DESCRIPTION
    This is the plain developer build -- it does NOT produce an MSIX. Use
    packaging\build_store_msix.ps1 for the Microsoft Store package.

    The Jana2020 wrapper is built with the EXACT known-working command,
    unmodified, from the repository root:

        python -m PyInstaller --clean --noconfirm superflip.spec

    <RepoRoot>\superflip.spec is the authoritative Jana2020 wrapper
    specification (already verified against a real Jana2020 installation).
    This script does not maintain a second, separately frozen Jana wrapper.

    Output:
        dist\PhaseStudio\PhaseStudio.exe
        dist\PhaseStudio\_internal\...
        dist\PhaseStudio\JanaIntegration\superflip.exe       (staged copy)
        dist\PhaseStudio\JanaIntegration\_internal\...        (staged copy)
        dist\superflip\superflip.exe                          (authoritative)
        dist\superflip\_internal\...                           (authoritative)

    dist\superflip\ remains the authoritative Jana wrapper build (produced
    directly by the repository's root superflip.spec). This script then
    stages a complete copy of it into dist\PhaseStudio\JanaIntegration\, which
    is where the running standalone PhaseStudio.exe (frozen,
    phase_studio.jana_integration.resolve_bundled_jana_payload_dir()) looks
    for it -- directly beside itself, matching the MSIX-installed layout too.

.PARAMETER Clean
    Remove the two specific output directories below before building
    (recommended; on by default). This never touches the rest of dist\/build\
    (see "Output directory design" in packaging\README_STORE.md) -- the two
    builds below never delete each other's output.

.EXAMPLE
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File packaging\build_windows.ps1

    Works from any current directory, and from an activated Conda/venv
    environment -- every path below is resolved from $PSScriptRoot, never
    from Get-Location or a hard-coded drive path.
#>
[CmdletBinding()]
param(
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "common.ps1")

function Test-ExeRunningFrom($ExeName, $ExpectedPath) {
    # $true only if a currently running process named $ExeName has its
    # executable located at exactly $ExpectedPath (case-insensitive path
    # comparison). Matching by name alone would risk flagging (or, if this
    # were ever extended to kill anything, terminating) an unrelated
    # PhaseStudio.exe/superflip.exe running from a different checkout or a
    # real Jana2020\SUPERFLIP installation -- this never kills a process, it
    # only refuses to delete out from under one still running the exact
    # previous build output.
    if (-not (Test-Path $ExpectedPath)) { return $false }
    $expectedFull = (Resolve-Path $ExpectedPath).Path
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name = '$ExeName'" -ErrorAction Stop
    } catch {
        # WMI/CIM unavailable for some reason -- fail open (report nothing
        # locked) rather than blocking every build; the UnauthorizedAccess/
        # IOException catch around Remove-Item below is the real backstop.
        return $false
    }
    foreach ($proc in $procs) {
        if ($proc.ExecutablePath -and ($proc.ExecutablePath -ieq $expectedFull)) {
            return $true
        }
    }
    return $false
}

function Remove-BuildOutputDir($Path) {
    if (-not (Test-Path $Path)) { return }
    try {
        Remove-Item -Recurse -Force $Path -ErrorAction Stop
    } catch [System.UnauthorizedAccessException], [System.IO.IOException] {
        # Empirically, a file locked by another running process raises
        # System.IO.IOException ("...because it is being used by another
        # process"), not UnauthorizedAccessException -- both are caught here
        # since either can surface depending on exactly which handle Windows
        # is holding (a loaded DLL/PYD vs. a permissions-style denial).
        throw @"
Could not remove $Path
  $($_.Exception.GetType().Name): $($_.Exception.Message)

A DLL or .pyd from a previous build may still be loaded by a running Phase
Studio (or Jana2020 Superflip wrapper) process, even one not detected by
name above. Close Phase Studio and any Jana2020 session using the Superflip
wrapper, then retry the build.
"@
    }
}

# ---------------------------------------------------------------------------
# Resolve every path from $PSScriptRoot (this script's own directory), never
# from the caller's current directory. packaging\build_windows.ps1 lives at
# <RepoRoot>\packaging\build_windows.ps1, so the repo root is exactly one
# level up -- not two. (This exact off-by-one, one level too many, was the
# root cause of the first real build's "script ...\phase_studio\app.py not
# found": the repo root resolved one directory ABOVE the actual checkout.)
# ---------------------------------------------------------------------------
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PhaseStudioSource = Join-Path $RepoRoot "phase_studio\app.py"
$JanaWrapperSource = Join-Path $RepoRoot "phase_studio\jana_superflip.py"
$JanaWrapperSpec = Join-Path $RepoRoot "superflip.spec"
$PhaseStudioSpec = Join-Path $PSScriptRoot "pyinstaller\PhaseStudio.spec"
$PhaseStudioIcon = Join-Path $RepoRoot "phase_studio\assets\phase_studio.ico"
$distDir = Join-Path $RepoRoot "dist"
$buildDir = Join-Path $RepoRoot "build"

Write-Step "Resolved paths"
Write-Host "Repository root:"
Write-Host "  $RepoRoot"
Write-Host "Packaging directory:"
Write-Host "  $PSScriptRoot"
Write-Host "Phase Studio source:"
Write-Host "  $PhaseStudioSource"
Write-Host "Phase Studio spec (packaging, ONEDIR):"
Write-Host "  $PhaseStudioSpec"
Write-Host "Jana2020 wrapper source:"
Write-Host "  $JanaWrapperSource"
Write-Host "Jana2020 wrapper spec (repo root, known-working, authoritative):"
Write-Host "  $JanaWrapperSpec"
Write-Host "Output directory:"
Write-Host "  $distDir"

# ---------------------------------------------------------------------------
# Fail BEFORE invoking PyInstaller if anything is missing -- a clear message
# naming the resolved root and the exact expected file, not an opaque
# PyInstaller "script not found" three steps later.
# ---------------------------------------------------------------------------
Write-Step "Verifying source paths"
foreach ($pair in @(
    @{ Path = $PhaseStudioSource; Label = "phase_studio/app.py" },
    @{ Path = $JanaWrapperSource; Label = "phase_studio/jana_superflip.py" },
    @{ Path = $JanaWrapperSpec;   Label = "superflip.spec (repository root)" },
    @{ Path = $PhaseStudioSpec;   Label = "packaging/pyinstaller/PhaseStudio.spec" },
    @{ Path = $PhaseStudioIcon;   Label = "Phase Studio icon" }
)) {
    if (Test-Path $pair.Path) {
        Write-Host "[OK] $($pair.Label)"
    } else {
        throw @"
Missing required file: $($pair.Label)
  Expected at: $($pair.Path)
  Resolved repository root: $RepoRoot

If the repository root above looks wrong, this script is being run from an
unexpected location -- it must live at <RepoRoot>\packaging\build_windows.ps1.
"@
    }
}

# ---------------------------------------------------------------------------
# Resolve the ACTIVE Python explicitly (works correctly inside an activated
# Conda/venv environment) and invoke PyInstaller through it as
# "python -m PyInstaller" -- never a bare "pyinstaller" command, which can
# silently resolve to a different environment's entry-point shim.
# ---------------------------------------------------------------------------
Write-Step "Checking the active Python environment"
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    throw "No 'python' was found on PATH. Activate the intended Conda/venv environment first (e.g. 'conda activate phase-build')."
}
$PythonExe = $pythonCommand.Source
Write-Host "Python executable:"
Write-Host "  $PythonExe"
& $PythonExe --version
& $PythonExe -m PyInstaller --version 2>&1 | ForEach-Object {
    if ($_ -match "No module named") {
        throw "PyInstaller is not installed in the active Python environment ($PythonExe). Install it there first (pip install pyinstaller)."
    }
    Write-Host "PyInstaller: $_"
}
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed in the active Python environment ($PythonExe). Install it there first (pip install pyinstaller)."
}

# ---------------------------------------------------------------------------
# Clean ONLY the two specific output directories this script produces --
# never a blanket removal of dist\/build\, and never between the two builds
# below (each --clean only clears its own spec's prior output/work cache).
#
# Before deleting, check whether the PREVIOUS build's own executables are
# still running from those exact directories. This never kills a process --
# Jana2020/Superflip may legitimately still be using the previously staged
# wrapper -- it only stops with a clear message so the developer can close
# it themselves before the old build output is removed out from under it.
# ---------------------------------------------------------------------------
if ($Clean) {
    Write-Step "Checking for locked previous build artifacts"
    $lockedTargets = @(
        @{ Exe = "PhaseStudio.exe"; Path = Join-Path $distDir "PhaseStudio\PhaseStudio.exe" },
        @{ Exe = "superflip.exe";   Path = Join-Path $distDir "superflip\superflip.exe" },
        @{ Exe = "superflip.exe";   Path = Join-Path $distDir "PhaseStudio\JanaIntegration\superflip.exe" }
    )
    foreach ($target in $lockedTargets) {
        if (Test-ExeRunningFrom $target.Exe $target.Path) {
            throw @"
$($target.Exe) is still running from the previous build:
  $($target.Path)

Close Phase Studio and retry the build.
"@
        }
    }
    Write-Host "[OK] No previous build executables are running"

    Write-Step "Cleaning prior output for PhaseStudio and superflip"
    foreach ($name in @("PhaseStudio", "superflip")) {
        Remove-BuildOutputDir (Join-Path $distDir $name)
        Remove-BuildOutputDir (Join-Path $buildDir $name)
    }
}

# ---------------------------------------------------------------------------
# Build from the repository root (Push-Location, exception-safe): the
# repository's own root-level superflip.spec resolves its entry point as a
# path RELATIVE to the current directory ("phase_studio/jana_superflip.py"),
# exactly matching how it has already been verified to work
# ("python -m PyInstaller --clean --noconfirm superflip.spec" run from the
# repo root) -- this script must reproduce that exact invocation, not a
# reimplementation of it.
# ---------------------------------------------------------------------------
Push-Location $RepoRoot
try {
    Write-Step "Building PhaseStudio (PyInstaller ONEDIR, packaging\pyinstaller\PhaseStudio.spec)"
    & $PythonExe -m PyInstaller --clean --noconfirm --distpath $distDir --workpath $buildDir $PhaseStudioSpec
    if ($LASTEXITCODE -ne 0) {
        throw "PhaseStudio build failed (PyInstaller exit code $LASTEXITCODE)."
    }

    Write-Step "Building the Jana2020 Superflip wrapper (known-working: python -m PyInstaller --clean --noconfirm superflip.spec)"
    & $PythonExe -m PyInstaller --clean --noconfirm superflip.spec
    if ($LASTEXITCODE -ne 0) {
        throw "Jana2020 wrapper build failed (PyInstaller exit code $LASTEXITCODE)."
    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# Verify generated executables -- do not claim success merely because
# PyInstaller returned exit code 0.
# ---------------------------------------------------------------------------
Write-Step "Verifying generated executables"
$phaseStudioExe = Join-Path $distDir "PhaseStudio\PhaseStudio.exe"
$janaExe = Join-Path $distDir "superflip\superflip.exe"
$janaRuntime = Join-Path $distDir "superflip\_internal"
Assert-PathExists $phaseStudioExe "Generated PhaseStudio.exe"
Assert-PathExists $janaExe "Generated superflip.exe"
Assert-PathExists $janaRuntime "Generated superflip runtime (_internal)"

# ---------------------------------------------------------------------------
# Stage the Jana2020 wrapper INTO the standalone PhaseStudio distribution so
# "Install to Jana2020" can find it (phase_studio.jana_integration's
# resolve_bundled_jana_payload_dir() looks for a sibling JanaIntegration\
# folder next to PhaseStudio.exe) without any separate manual step. This is
# a plain file copy performed after both PyInstaller builds above have
# already completed -- it does not change either build.
# ---------------------------------------------------------------------------
Write-Step "Staging the Jana2020 wrapper into dist\PhaseStudio\JanaIntegration"
$stagedJanaDir = Join-Path $distDir "PhaseStudio\JanaIntegration"
if (Test-Path $stagedJanaDir) { Remove-Item -Recurse -Force $stagedJanaDir }
Copy-Item (Join-Path $distDir "superflip") $stagedJanaDir -Recurse -Force

$stagedJanaExe = Join-Path $stagedJanaDir "superflip.exe"
$stagedJanaRuntime = Join-Path $stagedJanaDir "_internal"
Assert-PathExists $stagedJanaExe "Staged dist\PhaseStudio\JanaIntegration\superflip.exe"
Assert-PathExists $stagedJanaRuntime "Staged dist\PhaseStudio\JanaIntegration\_internal"

Write-Host ""
Write-Host "Developer build complete." -ForegroundColor Green
Write-Host "  PhaseStudio: $phaseStudioExe"
Write-Host "  Jana wrapper (dist\superflip\, ONEDIR, authoritative build): $janaExe"
Write-Host "  Staged into the standalone app: $stagedJanaExe"
Write-Host ""
Write-Host "Run dist\PhaseStudio\PhaseStudio.exe directly, or 'python -m phase_studio'." -ForegroundColor DarkGray
Write-Host "dist\superflip\ (superflip.exe + _internal\) remains the authoritative Jana" -ForegroundColor DarkGray
Write-Host "wrapper build; dist\PhaseStudio\JanaIntegration\ is a staged copy of it for" -ForegroundColor DarkGray
Write-Host "the standalone application to find and install from." -ForegroundColor DarkGray
