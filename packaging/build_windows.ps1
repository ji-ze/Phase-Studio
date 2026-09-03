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
        dist\superflip\superflip.exe
        dist\superflip\_internal\...

    dist\superflip is exactly where phase_studio.jana_integration's
    resolve_bundled_jana_payload_dir() looks for a locally built payload when
    running Phase Studio from a normal (non-frozen) Python environment, so a
    developer build here is directly usable by "Install to Jana2020" without
    any extra copying.

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

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-PathExists($Path, $Description) {
    if (-not (Test-Path $Path)) {
        throw "$Description not found: $Path"
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
# ---------------------------------------------------------------------------
if ($Clean) {
    Write-Step "Cleaning prior output for PhaseStudio and superflip"
    foreach ($name in @("PhaseStudio", "superflip")) {
        $distPath = Join-Path $distDir $name
        if (Test-Path $distPath) { Remove-Item -Recurse -Force $distPath }
        $workPath = Join-Path $buildDir $name
        if (Test-Path $workPath) { Remove-Item -Recurse -Force $workPath }
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

Write-Host ""
Write-Host "Developer build complete." -ForegroundColor Green
Write-Host "  PhaseStudio: $phaseStudioExe"
Write-Host "  Jana wrapper (dist\superflip\, ONEDIR): $janaExe"
Write-Host ""
Write-Host "Run dist\PhaseStudio\PhaseStudio.exe directly, or 'python -m phase_studio'." -ForegroundColor DarkGray
Write-Host "The complete dist\superflip\ directory (superflip.exe + _internal\) is the" -ForegroundColor DarkGray
Write-Host "Jana2020 integration payload; copy the whole directory, not just the .exe." -ForegroundColor DarkGray
