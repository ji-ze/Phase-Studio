<#
.SYNOPSIS
    Build a Microsoft Store-ready Phase Studio MSIX package.

.DESCRIPTION
    Reproducible pipeline:
      1. clean prior Store staging (build\store\, dist\store\),
      2. build PhaseStudio and the Jana2020 wrapper by running
         packaging\build_windows.ps1 -- the exact same known-working
         "python -m PyInstaller --clean --noconfirm superflip.spec" build
         used for plain developer builds. That script also stages the Jana
         wrapper into dist\PhaseStudio\JanaIntegration\ (a plain post-build
         file copy of dist\superflip\, never a second PyInstaller build), so
         this script does not reimplement a second, separately frozen Jana
         wrapper: the payload staged into the MSIX below is bit-for-bit what
         build_windows.ps1 already produced,
      3. copy the already-staged dist\PhaseStudio\ (JanaIntegration\
         included) -> MSIX layout PhaseStudio\ as a single directory copy,
      4. generate the MSIX staging layout,
      5. generate AppxManifest.xml from the template + store identity + the
         single Phase Studio version source (phase_studio\version.py),
      6. validate required visual assets exist,
      7. optionally Authenticode-sign PhaseStudio\JanaIntegration\superflip.exe
         (it is copied OUT of the MSIX package later by Phase Studio itself,
         so the MSIX package signature alone does not cover it -- see
         phase_studio\jana_integration.py and Part I of the integration
         design notes),
      8. call MakeAppx.exe,
      9. produce the final .msix under dist\store\.

    This script produces an UNSIGNED .msix by default, suitable for direct
    Microsoft Store submission (the Store re-signs the package after
    certification). For local sideload testing, sign the produced .msix
    afterward with packaging\sign_test_msix.ps1 (or pass
    -TestCertificatePath/-TestCertificatePassword here). Never commit a
    .pfx, private key, or password anywhere in this repository.

.PARAMETER StoreIdentityPath
    Path to a local store_identity.json (see
    packaging\msix\store_identity.example.json). Defaults to
    packaging\msix\store_identity.json, which is expected to be created
    locally and is NOT committed (placeholder Partner Center values only
    live in the .example.json).

.PARAMETER Version
    Override the package version (format A.B.C.D). Defaults to
    phase_studio\version.py's VERSION with a trailing ".0" component
    (e.g. "1.0.8" -> "1.0.8.0") -- the single source of truth for the
    application version.

.PARAMETER JanaSigningCertificate
    Optional path to a .pfx used to Authenticode-sign
    PhaseStudio\JanaIntegration\superflip.exe before it is added to the MSIX
    payload. If omitted, the wrapper is left unsigned and this is reported
    clearly (never silently).

.PARAMETER JanaSigningPassword
    Password for -JanaSigningCertificate, as a SecureString. Never pass a
    plain-text password on the command line in a shared/scripted context;
    prefer Read-Host -AsSecureString interactively.

.PARAMETER TimestampUrl
    RFC 3161 timestamp server used for both the optional Jana wrapper
    signing and (if requested) test-signing the MSIX itself.

.PARAMETER TestCertificatePath / TestCertificatePassword
    Optional: also sign the produced MSIX package itself with a local test
    certificate (for sideload testing on a dev machine). Equivalent to
    running packaging\sign_test_msix.ps1 afterward.

.EXAMPLE
    powershell -File packaging\build_store_msix.ps1

.EXAMPLE
    powershell -File packaging\build_store_msix.ps1 `
        -JanaSigningCertificate C:\secure\phase_studio_codesign.pfx `
        -JanaSigningPassword (Read-Host -AsSecureString "Cert password") `
        -TimestampUrl "http://timestamp.digicert.com"
#>
[CmdletBinding()]
param(
    [string]$StoreIdentityPath = (Join-Path $PSScriptRoot "msix\store_identity.json"),
    [string]$Version,
    [string]$JanaSigningCertificate,
    [System.Security.SecureString]$JanaSigningPassword,
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$TestCertificatePath,
    [System.Security.SecureString]$TestCertificatePassword
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

# ---------------------------------------------------------------------------
# 1. Version (single source of truth: phase_studio\version.py)
# ---------------------------------------------------------------------------
if (-not $Version) {
    $versionPy = Get-Content (Join-Path $RepoRoot "phase_studio\version.py") -Raw
    if ($versionPy -notmatch 'VERSION\s*=\s*"([^"]+)"') {
        throw "Could not read VERSION from phase_studio\version.py"
    }
    $appVersion = $Matches[1]
    $Version = "$appVersion.0"
}
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

# ---------------------------------------------------------------------------
# 4. Build PhaseStudio + the Jana2020 wrapper by delegating to the canonical
#    developer build (packaging\build_windows.ps1). That script builds the
#    Jana wrapper with the exact known-working
#    "python -m PyInstaller --clean --noconfirm superflip.spec" command
#    against the repository's root-level superflip.spec -- the same command
#    already verified against a real Jana2020 installation -- and then
#    stages a complete copy of its dist\superflip\ output into
#    dist\PhaseStudio\JanaIntegration\ itself (a plain file copy, not a
#    second PyInstaller build). This script never gives PyInstaller a
#    different spec or a different output name for that build; it only
#    copies the already-staged dist\PhaseStudio\ directory below.
# ---------------------------------------------------------------------------
Write-Step "Building PhaseStudio and the Jana2020 wrapper (packaging\build_windows.ps1)"
& (Join-Path $PSScriptRoot "build_windows.ps1")

$builtPhaseStudioDir = Join-Path $RepoRoot "dist\PhaseStudio"
Assert-PathExists (Join-Path $builtPhaseStudioDir "PhaseStudio.exe") "Built PhaseStudio.exe"
Assert-PathExists (Join-Path $builtPhaseStudioDir "JanaIntegration\superflip.exe") "Built (staged) PhaseStudio\JanaIntegration\superflip.exe"

Write-Step "Staging build output into the MSIX layout"
Copy-Item $builtPhaseStudioDir (Join-Path $layoutDir "PhaseStudio") -Recurse -Force

Assert-PathExists (Join-Path $layoutDir "PhaseStudio\PhaseStudio.exe") "Staged PhaseStudio.exe"
Assert-PathExists (Join-Path $layoutDir "PhaseStudio\JanaIntegration\superflip.exe") "Staged PhaseStudio\JanaIntegration\superflip.exe"
Assert-PathExists (Join-Path $layoutDir "PhaseStudio\JanaIntegration\_internal") "Staged PhaseStudio\JanaIntegration\_internal"

# ---------------------------------------------------------------------------
# 5. Optional: Authenticode-sign the Jana wrapper BEFORE it goes into the
#    MSIX payload. The MSIX package signature does not cover this file once
#    Phase Studio later copies it out to a Jana2020 installation.
# ---------------------------------------------------------------------------
$janaExePath = Join-Path $layoutDir "PhaseStudio\JanaIntegration\superflip.exe"
if ($JanaSigningCertificate) {
    Write-Step "Signing PhaseStudio\JanaIntegration\superflip.exe"
    Assert-PathExists $JanaSigningCertificate "Jana wrapper signing certificate"
    $signTool = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\x64\\" } | Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $signTool) {
        throw "SignTool.exe was not found under Windows Kits. Install the Windows SDK, or omit -JanaSigningCertificate to build unsigned."
    }
    $signArgs = @("sign", "/fd", "SHA256", "/f", $JanaSigningCertificate)
    if ($JanaSigningPassword) {
        $plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($JanaSigningPassword))
        $signArgs += @("/p", $plainPassword)
    }
    if ($TimestampUrl) {
        $signArgs += @("/tr", $TimestampUrl, "/td", "SHA256")
    }
    $signArgs += $janaExePath
    & $signTool.FullName @signArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Signing PhaseStudio\JanaIntegration\superflip.exe failed (SignTool exit code $LASTEXITCODE)."
    }
    Write-Host "PhaseStudio\JanaIntegration\superflip.exe signed." -ForegroundColor Green
} else {
    Write-Host "Jana integration wrapper is unsigned." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# 6. Integration payload marker (informational; the real per-install marker
#    is written at install time by phase_studio.jana_integration).
# ---------------------------------------------------------------------------
$payloadMarker = @{
    product  = "Phase Studio"
    version  = $Version.Substring(0, $Version.LastIndexOf("."))
    wrapper  = "superflip.exe"
} | ConvertTo-Json
Set-Content -Path (Join-Path $layoutDir "PhaseStudio\JanaIntegration\phase_studio_integration_payload.json") -Value $payloadMarker -Encoding utf8

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
