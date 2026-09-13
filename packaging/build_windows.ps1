<#
.SYNOPSIS
Build Phase Studio's two public ONEFILE downloads and internal Jana wrapper.
#>
[CmdletBinding()]
param(
    [ValidateSet("All", "Standalone", "JanaInstaller", "JanaWrapper")]
    [string]$Target = "All",
    [string]$DistRoot = "",
    [switch]$Clean = $true
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$defaultDist = Join-Path $RepoRoot "dist"
$distDir = if ($DistRoot) { [IO.Path]::GetFullPath($DistRoot) } else { $defaultDist }
if ($distDir -ne $defaultDist -and -not $distDir.StartsWith($defaultDist + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "DistRoot must be inside the repository dist directory."
}
$buildDir = Join-Path $RepoRoot "build"
$releaseDir = Join-Path $distDir "release"
$PythonExe = (Get-Command python -ErrorAction Stop).Source
& $PythonExe -m PyInstaller --version
if ($LASTEXITCODE -ne 0) { throw "PyInstaller is required in the active Python environment." }

function Remove-SafePath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $allowed = @($distDir, $buildDir) | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') + '\' }
    if (-not ($full.StartsWith($allowed[0], [StringComparison]::OrdinalIgnoreCase) -or
              $full.StartsWith($allowed[1], [StringComparison]::OrdinalIgnoreCase))) {
        throw "Refusing to remove output outside repository build/dist: $full"
    }
    if (Test-Path -LiteralPath $full) { Remove-Item -LiteralPath $full -Recurse -Force }
}

function Invoke-PyInstaller([string]$Spec, [string]$WorkName, [string]$OutputDir) {
    if ($Clean) { Remove-SafePath (Join-Path $buildDir $WorkName) }
    & $PythonExe -m PyInstaller --clean --noconfirm --distpath $OutputDir $Spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for $WorkName." }
}

function Test-OnedirRuntime([string]$Directory, [string]$ManifestName) {
    $manifestPath = Join-Path $buildDir "portable-runtime-$ManifestName.json"
    Assert-PathExists $manifestPath "Portable runtime manifest"
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $internal = Join-Path $Directory "_internal"
    Assert-PathExists $internal "ONEDIR runtime"
    $expected = @()
    foreach ($item in $manifest.msvc_runtime) { $expected += $item.name }
    foreach ($item in $manifest.required_binaries) { $expected += $item }
    foreach ($dll in $expected) {
        if (-not (Get-ChildItem -LiteralPath $internal -Recurse -File -Filter $dll | Select-Object -First 1)) {
            throw "Portable runtime is missing $dll in $Directory"
        }
    }
    $forbidden = @(Get-ChildItem -LiteralPath $internal -Recurse -File | Where-Object {
        $_.Name -eq 'ucrtbase.dll' -or $_.Name -like 'api-ms-win-*.dll'
    })
    if ($forbidden.Count) { throw "App-local UCRT files were found in $Directory" }
    & $PythonExe (Join-Path $PSScriptRoot "tools\audit_dependencies.py") --dist $Directory
    if ($LASTEXITCODE -ne 0) { throw "Native dependency audit failed for $Directory" }
    & $PythonExe (Join-Path $PSScriptRoot "tools\verify_imports.py") --quiet $Directory
    if ($LASTEXITCODE -ne 0) { throw "Frozen import verification failed for $Directory" }
}

$buildWrapper = $Target -in @("All", "JanaInstaller", "JanaWrapper")
$buildStandalone = $Target -in @("All", "Standalone")
$buildInstaller = $Target -in @("All", "JanaInstaller")

Push-Location $RepoRoot
try {
    if ($Target -eq "All" -and $Clean) { Remove-SafePath $releaseDir }
    New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

    if ($buildWrapper) {
        Write-Step "Building authoritative Jana2020 wrapper (ONEDIR)"
        if ($Clean) { Remove-SafePath (Join-Path $distDir "superflip") }
        Invoke-PyInstaller "superflip.spec" "superflip" $distDir
        $wrapperDir = Join-Path $distDir "superflip"
        Assert-PathExists (Join-Path $wrapperDir "superflip.exe") "Jana wrapper"
        Test-OnedirRuntime $wrapperDir "superflip"
        & $PythonExe (Join-Path $PSScriptRoot "tools\check_distribution.py") $wrapperDir --profile wrapper
        if ($LASTEXITCODE -ne 0) { throw "Wrapper boundary check failed." }
    }

    if ($buildStandalone) {
        Write-Step "Building standalone release (ONEFILE)"
        $standaloneExe = Join-Path $releaseDir "PhaseStudio-1.0.9-x64.exe"
        if ($Clean) { Remove-SafePath $standaloneExe }
        Invoke-PyInstaller "packaging\pyinstaller\PhaseStudio.spec" "PhaseStudio" $releaseDir
        Assert-PathExists $standaloneExe "Standalone release"
        & $PythonExe (Join-Path $PSScriptRoot "tools\check_distribution.py") $standaloneExe --profile standalone
        if ($LASTEXITCODE -ne 0) { throw "Standalone boundary check failed." }
        & $standaloneExe --version
        if ($LASTEXITCODE -ne 0) { throw "Standalone smoke test failed." }
    }

    if ($buildInstaller) {
        Write-Step "Building Jana2020 installer (ONEFILE with embedded wrapper)"
        $wrapperDir = Join-Path $distDir "superflip"
        Assert-PathExists (Join-Path $wrapperDir "superflip.exe") "Authoritative Jana wrapper"
        $payloadBundle = Join-Path $buildDir "jana-payload"
        if ($Clean) { Remove-SafePath $payloadBundle }
        & $PythonExe (Join-Path $PSScriptRoot "tools\package_jana_payload.py") $wrapperDir $payloadBundle
        if ($LASTEXITCODE -ne 0) { throw "Could not package the authoritative Jana wrapper." }
        $env:PHASE_STUDIO_WRAPPER_PAYLOAD = $wrapperDir
        try {
            $installerExe = Join-Path $releaseDir "PhaseStudio-Jana2020-Installer-1.0.9-x64.exe"
            if ($Clean) { Remove-SafePath $installerExe }
            Invoke-PyInstaller "packaging\pyinstaller\PhaseStudioJanaInstaller.spec" "PhaseStudioJanaInstaller" $releaseDir
        } finally {
            Remove-Item Env:PHASE_STUDIO_WRAPPER_PAYLOAD -ErrorAction SilentlyContinue
        }
        Assert-PathExists $installerExe "Jana2020 installer release"
        & $PythonExe (Join-Path $PSScriptRoot "tools\check_distribution.py") $installerExe --profile installer --wrapper-source $wrapperDir
        if ($LASTEXITCODE -ne 0) { throw "Installer payload or boundary check failed." }
        & $installerExe --version
        if ($LASTEXITCODE -ne 0) { throw "Installer smoke test failed." }
    }

    $publicFiles = @(Get-ChildItem -LiteralPath $releaseDir -File)
    $unexpected = @($publicFiles | Where-Object { $_.Name -notin @(
        "PhaseStudio-1.0.9-x64.exe", "PhaseStudio-Jana2020-Installer-1.0.9-x64.exe"
    ) })
    if ($unexpected.Count) { throw "Unexpected public release files: $($unexpected.Name -join ', ')" }
    if ($Target -eq "All" -and $publicFiles.Count -ne 2) { throw "All must produce exactly two public EXEs." }
} finally {
    Pop-Location
}
Write-Host "Build complete. Public downloads: $releaseDir" -ForegroundColor Green
