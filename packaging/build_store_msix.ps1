<#
.SYNOPSIS
Build and package ONLY standalone Phase Studio for Microsoft Store.
The dedicated Jana installer and its wrapper payload are never included.
#>
[CmdletBinding()]
param(
    # Resolved below, not here: $PSScriptRoot is not reliably populated yet
    # while parameter defaults are being evaluated in every PowerShell
    # context (confirmed empty here even for a plain `-File` invocation with
    # no arguments -- this previously made the script fail immediately,
    # before printing anything, exactly when run per its own .EXAMPLE).
    [string]$StoreIdentityPath = "",
    [string]$Version,
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$TestCertificatePath,
    [System.Security.SecureString]$TestCertificatePassword
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "common.ps1")

# Plain string (not a PathInfo), matching build_windows.ps1's convention.
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $StoreIdentityPath) {
    $StoreIdentityPath = Join-Path $PSScriptRoot "msix\store_identity.json"
}

# ---------------------------------------------------------------------------
# 1. Version (single source of truth: phase_studio\version.py)
# ---------------------------------------------------------------------------
$versionPy = Get-Content (Join-Path $RepoRoot "phase_studio\version.py") -Raw
if ($versionPy -notmatch 'VERSION\s*=\s*"([^"]+)"') { throw "Cannot read canonical VERSION." }
$canonicalVersion = "$($Matches[1]).0"
if ($Version -and $Version -ne $canonicalVersion) { throw "MSIX version must match $canonicalVersion." }
$Version = $canonicalVersion
Write-Host "Phase Studio version: $Version (MSIX package version)"

# ---------------------------------------------------------------------------
# 2. Store identity (never hard-coded; must be supplied locally)
# ---------------------------------------------------------------------------
Write-Step "Loading Store identity"
if (-not (Test-Path $StoreIdentityPath)) {
    throw @"
Store identity file not found: $StoreIdentityPath

Create it from packaging\msix\store_identity.example.json with your real
Partner Center Package Identity Name/Publisher (this file is intentionally
not committed to the repository).
"@
}
$identity = Get-Content $StoreIdentityPath -Raw | ConvertFrom-Json
foreach ($field in @("name", "publisher", "publisher_display_name")) {
    if (-not $identity.$field -or $identity.$field -like "REPLACE_WITH_*") {
        throw "store_identity.json field '$field' is still a placeholder. Fill in the real Partner Center value."
    }
}

# ---------------------------------------------------------------------------
# 3. Clean prior Store staging
# ---------------------------------------------------------------------------
Write-Step "Cleaning prior Store staging"
$storeBuildDir = Join-Path $RepoRoot "build\store"
$storeDistDir = Join-Path $RepoRoot "dist\store"
if (Test-Path $storeBuildDir) { Remove-Item -Recurse -Force $storeBuildDir }
if (Test-Path $storeDistDir) { Remove-Item -Recurse -Force $storeDistDir }
$layoutDir = Join-Path $storeBuildDir "layout"
New-Item -ItemType Directory -Force -Path $layoutDir | Out-Null
New-Item -ItemType Directory -Force -Path $storeDistDir | Out-Null

Write-Step "Building standalone PhaseStudio"
& python -m PyInstaller --clean --noconfirm (Join-Path $PSScriptRoot "pyinstaller\PhaseStudioStore.spec")
if ($LASTEXITCODE -ne 0) { throw "Store ONEDIR build failed." }
$builtPhaseStudioDir = Join-Path $RepoRoot "dist\PhaseStudio"
Assert-PathExists (Join-Path $builtPhaseStudioDir "PhaseStudio.exe") "Built standalone"
if (Test-Path (Join-Path $builtPhaseStudioDir "JanaIntegration")) {
    throw "Store packaging refuses a Jana installation payload."
}
Copy-Item -LiteralPath $builtPhaseStudioDir -Destination (Join-Path $layoutDir "PhaseStudio") -Recurse -Force
Assert-PathExists (Join-Path $layoutDir "PhaseStudio\PhaseStudio.exe") "Staged standalone"
& python (Join-Path $PSScriptRoot "tools\check_distribution.py") (Join-Path $layoutDir "PhaseStudio") --profile store
if ($LASTEXITCODE -ne 0) { throw "Store layout failed standalone boundary checks." }

# ---------------------------------------------------------------------------
# 7. Assets
# ---------------------------------------------------------------------------
Write-Step "Validating Store visual assets"
$assetsSourceDir = Join-Path $PSScriptRoot "msix\Assets"
$assetsDestDir = Join-Path $layoutDir "Assets"
New-Item -ItemType Directory -Force -Path $assetsDestDir | Out-Null
$requiredAssets = @(
    "StoreLogo.png", "Square44x44Logo.png", "Square150x150Logo.png",
    "Square71x71Logo.png", "Square310x310Logo.png", "Wide310x150Logo.png", "SplashScreen.png"
)
$missingAssets = @()
foreach ($assetName in $requiredAssets) {
    $sourcePath = Join-Path $assetsSourceDir $assetName
    if (Test-Path $sourcePath) {
        Copy-Item $sourcePath (Join-Path $assetsDestDir $assetName) -Force
    } else {
        $missingAssets += $assetName
    }
}
if ($missingAssets.Count -gt 0) {
    throw @"
Missing required MSIX visual assets: $($missingAssets -join ', ')

Generate them first:
    python packaging\generate_store_assets.py

This renders each asset directly from Phase Studio's own vector brand mark
(see packaging\README_STORE.md, "Store assets") -- the same navy/blue
Phase Studio identity, not a new one, and not manually duplicated.
"@
}

# ---------------------------------------------------------------------------
# 8. AppxManifest.xml
# ---------------------------------------------------------------------------
Write-Step "Generating AppxManifest.xml"
$manifestTemplate = Get-Content (Join-Path $PSScriptRoot "msix\AppxManifest.template.xml") -Raw
$manifest = $manifestTemplate `
    -replace "\{\{IDENTITY_NAME\}\}", [System.Security.SecurityElement]::Escape($identity.name) `
    -replace "\{\{IDENTITY_PUBLISHER\}\}", [System.Security.SecurityElement]::Escape($identity.publisher) `
    -replace "\{\{PACKAGE_VERSION\}\}", $Version `
    -replace "\{\{PACKAGE_DISPLAY_NAME\}\}", [System.Security.SecurityElement]::Escape($identity.package_display_name) `
    -replace "\{\{PUBLISHER_DISPLAY_NAME\}\}", [System.Security.SecurityElement]::Escape($identity.publisher_display_name) `
    -replace "\{\{PACKAGE_DESCRIPTION\}\}", [System.Security.SecurityElement]::Escape($identity.description)
$manifestOutDir = Join-Path $storeDistDir "manifest"
New-Item -ItemType Directory -Force -Path $manifestOutDir | Out-Null
$manifestPath = Join-Path $layoutDir "AppxManifest.xml"
Set-Content -Path $manifestPath -Value $manifest -Encoding utf8
Copy-Item $manifestPath (Join-Path $manifestOutDir "AppxManifest.xml") -Force

# ---------------------------------------------------------------------------
# 9. Locate MakeAppx.exe (never hard-code one SDK version)
# ---------------------------------------------------------------------------
Write-Step "Locating MakeAppx.exe"
$makeAppx = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter "makeappx.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "\\x64\\" } | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $makeAppx) {
    throw @"
MakeAppx.exe was not found under any installed Windows Kits (Windows SDK).
Install the Windows 10/11 SDK (App Installer/Windows App SDK components
include it) and re-run this script.
"@
}
Write-Host "Using $($makeAppx.FullName)"

# ---------------------------------------------------------------------------
# 10. Build the MSIX
# ---------------------------------------------------------------------------
Write-Step "Packaging MSIX"
$appVersionPart = $Version.Substring(0, $Version.LastIndexOf("."))
$msixName = "PhaseStudio-$appVersionPart-x64.msix"
$msixPath = Join-Path $storeDistDir $msixName
& $makeAppx.FullName pack /d $layoutDir /p $msixPath /overwrite
if ($LASTEXITCODE -ne 0) {
    throw "MakeAppx packaging failed (exit code $LASTEXITCODE). See the log above for the specific validation failure."
}
Assert-PathExists $msixPath "Generated MSIX package"

# ---------------------------------------------------------------------------
# 11. Optional local test signing (see also sign_test_msix.ps1)
# ---------------------------------------------------------------------------
if ($TestCertificatePath) {
    Write-Step "Test-signing the MSIX package (local sideload use only)"
    & (Join-Path $PSScriptRoot "sign_test_msix.ps1") -MsixPath $msixPath -TestCertificatePath $TestCertificatePath -TestCertificatePassword $TestCertificatePassword -TimestampUrl $TimestampUrl
}

Write-Host ""
Write-Host "Store MSIX build complete." -ForegroundColor Green
Write-Host "  Package:   $msixPath"
Write-Host "  Manifest:  $(Join-Path $manifestOutDir 'AppxManifest.xml')"
Write-Host ""
if (-not $TestCertificatePath) {
    Write-Host "This package is UNSIGNED, which is correct for direct Microsoft Store" -ForegroundColor DarkGray
    Write-Host "submission (the Store signs it after certification). For local sideload" -ForegroundColor DarkGray
    Write-Host "testing, run packaging\sign_test_msix.ps1 against $msixName." -ForegroundColor DarkGray
}
