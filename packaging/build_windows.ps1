<#
.SYNOPSIS
    Developer/testing build: PhaseStudio and the JanaIntegration (Superflip
    wrapper) payload, both PyInstaller ONEDIR, output under dist\.

.DESCRIPTION
    This is the plain developer build -- it does NOT produce an MSIX. Use
    packaging\build_store_msix.ps1 for the Microsoft Store package.

    Output:
        dist\PhaseStudio\PhaseStudio.exe
        dist\PhaseStudio\_internal\...
        dist\JanaIntegration\superflip.exe
        dist\JanaIntegration\_internal\...

    dist\JanaIntegration is exactly where phase_studio.jana_integration's
    resolve_bundled_jana_payload_dir() looks for a locally built payload when
    running Phase Studio from a normal (non-frozen) Python environment, so a
    developer build here is directly usable by "Install to Jana2020" without
    any extra copying.

.PARAMETER Clean
    Remove prior PyInstaller build\/dist\ staging for these two specs before
    building (recommended; on by default).

.EXAMPLE
    powershell -File packaging\build_windows.ps1
#>
[CmdletBinding()]
param(
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-PathExists($Path, $Description) {
    if (-not (Test-Path $Path)) {
        throw "$Description was not found: $Path"
    }
}

Write-Step "Checking source assets"
Assert-PathExists (Join-Path $RepoRoot "phase_studio\app.py") "Main application entry point"
Assert-PathExists (Join-Path $RepoRoot "phase_studio\jana_superflip.py") "Jana2020 wrapper entry point"
Assert-PathExists (Join-Path $RepoRoot "phase_studio\assets\phase_studio.ico") "Application icon"

$pyInstallerSpecDir = Join-Path $PSScriptRoot "pyinstaller"
$phaseStudioSpec = Join-Path $pyInstallerSpecDir "PhaseStudio.spec"
$janaSpec = Join-Path $pyInstallerSpecDir "JanaSuperflip.spec"
Assert-PathExists $phaseStudioSpec "PhaseStudio PyInstaller spec"
Assert-PathExists $janaSpec "Jana2020 wrapper PyInstaller spec"

$buildDir = Join-Path $RepoRoot "build"
$distDir = Join-Path $RepoRoot "dist"

if ($Clean) {
    Write-Step "Cleaning prior PyInstaller staging"
    foreach ($name in @("PhaseStudio", "JanaIntegration")) {
        $workPath = Join-Path $buildDir $name
        if (Test-Path $workPath) { Remove-Item -Recurse -Force $workPath }
        $distPath = Join-Path $distDir $name
        if (Test-Path $distPath) { Remove-Item -Recurse -Force $distPath }
    }
}

function Invoke-PyInstaller($SpecPath, $Label) {
    Write-Step "Building $Label (PyInstaller ONEDIR)"
    & pyinstaller --noconfirm --distpath $distDir --workpath $buildDir $SpecPath
    if ($LASTEXITCODE -ne 0) {
        throw "$Label build failed (PyInstaller exit code $LASTEXITCODE)."
    }
}

Invoke-PyInstaller $phaseStudioSpec "PhaseStudio"
Invoke-PyInstaller $janaSpec "JanaIntegration (Superflip wrapper)"

Write-Step "Verifying generated executables"
$phaseStudioExe = Join-Path $distDir "PhaseStudio\PhaseStudio.exe"
$janaExe = Join-Path $distDir "JanaIntegration\superflip.exe"
Assert-PathExists $phaseStudioExe "Generated PhaseStudio.exe"
Assert-PathExists $janaExe "Generated JanaIntegration\superflip.exe"

Write-Host ""
Write-Host "Developer build complete." -ForegroundColor Green
Write-Host "  PhaseStudio:      $phaseStudioExe"
Write-Host "  JanaIntegration:  $janaExe"
Write-Host ""
Write-Host "Run 'python -m phase_studio' or dist\PhaseStudio\PhaseStudio.exe directly." -ForegroundColor DarkGray
