<#
.SYNOPSIS
Build independent portable Windows targets from one shared source tree.
.EXAMPLE
powershell -File packaging\build_windows.ps1 -Target All
.EXAMPLE
powershell -File packaging\build_windows.ps1 -Target Standalone
.EXAMPLE
powershell -File packaging\build_windows.ps1 -Target JanaInstaller
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
$PythonExe = (Get-Command python -ErrorAction Stop).Source
& $PythonExe -m PyInstaller --version
if ($LASTEXITCODE -ne 0) { throw "PyInstaller is required in the active Python environment." }

function Remove-TargetOutput([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $allowed = @($distDir, $buildDir) | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') + '\' }
    if (-not ($full.StartsWith($allowed[0], [StringComparison]::OrdinalIgnoreCase) -or
              $full.StartsWith($allowed[1], [StringComparison]::OrdinalIgnoreCase))) {
        throw "Refusing to remove output outside repository build/dist: $full"
    }
    if (Test-Path -LiteralPath $full) {
        Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction Stop
    }
}

function Test-PortableRuntime($DistName, $DistPath, $ManifestName) {
    $internal = Join-Path $DistPath "_internal"
    $manifestPath = Join-Path $buildDir "portable-runtime-$ManifestName.json"

    Write-Host ""
    Write-Host "$DistName"

    if (-not (Test-Path $manifestPath)) {
        Write-Host "  portable-runtime manifest not found: $manifestPath" -ForegroundColor Red
        return $false
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

    $ok = $true
    # NB: PowerShell variable names are case-insensitive -- a loop variable
    # named $DistName/$Name here would clobber this function's parameters.
    $expected = @()
    foreach ($item in $manifest.msvc_runtime) { $expected += $item.name }
    foreach ($qtLib in $manifest.required_binaries) { $expected += $qtLib }

    Write-Host "  Portable runtime:"
    foreach ($dllName in $expected) {
        $found = Get-ChildItem -LiteralPath $internal -Recurse -File -Filter $dllName -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($found) {
            Write-Host ("    {0,-24} OK" -f $dllName)
        } else {
            Write-Host ("    {0,-24} MISSING" -f $dllName) -ForegroundColor Red
            $ok = $false
        }
    }

    # An app-local Universal CRT must NOT be shipped: the UCRT belongs to
    # Windows 10/11, and a private older copy is a portability hazard.
    # (-Include needs a wildcard path in PowerShell 5.1; filter on Name.)
    $allFiles = @(Get-ChildItem -LiteralPath $internal -Recurse -File -ErrorAction SilentlyContinue)
    $ucrt = @($allFiles | Where-Object {
        $_.Name -like 'ucrtbase.dll' -or $_.Name -like 'api-ms-win-*.dll'
    })
    if ($ucrt.Count -eq 0) {
        Write-Host ("    {0,-24} OK (Windows provides the UCRT)" -f "no app-local UCRT")
    } else {
        Write-Host ("    {0,-24} {1} file(s) present" -f "app-local UCRT", $ucrt.Count) -ForegroundColor Red
        $ok = $false
    }

    # Windows keeps one module per base name per process, so two different
    # builds of e.g. MSVCP140.dll in different subdirectories cannot coexist.
    $runtimeFiles = @($allFiles | Where-Object {
        $_.Name -like 'vcruntime*.dll' -or $_.Name -like 'msvcp140*.dll' -or $_.Name -like 'Qt6*.dll'
    })
    $dupes = @($runtimeFiles |
        Group-Object { $_.Name.ToLowerInvariant() } |
        Where-Object { $_.Count -gt 1 -and (@($_.Group.Length | Sort-Object -Unique).Count -gt 1) })
    if ($dupes.Count -eq 0) {
        Write-Host ("    {0,-24} OK" -f "no duplicate runtime")
    } else {
        foreach ($dupe in $dupes) {
            Write-Host ("    {0,-24} {1} differing copies" -f $dupe.Name, $dupe.Count) -ForegroundColor Red
        }
        $ok = $false
    }

    # Full native-dependency and symbol-level audits.
    $auditor = Join-Path $PSScriptRoot "tools\audit_dependencies.py"
    $verifier = Join-Path $PSScriptRoot "tools\verify_imports.py"

    if (Test-Path $auditor) {
        $auditOutput = & $PythonExe $auditor --dist $DistPath 2>&1
        $auditFailed = ($LASTEXITCODE -ne 0)
        $auditOutput | Where-Object { $_ -match 'Result:|PORTABLE|UNRESOLVED|OUTSIDE THE DIST|Windows 10 1903' } |
            ForEach-Object { Write-Host "    $_" }
        if ($auditFailed) { $ok = $false }
    }

    if (Test-Path $verifier) {
        $verifyOutput = & $PythonExe $verifier $DistPath --quiet 2>&1
        $verifyFailed = ($LASTEXITCODE -ne 0)
        $verifyOutput | Where-Object { $_ -match 'Result:|UNSATISFIED|MISSING DLL|DUPLICATE DLL' } |
            ForEach-Object { Write-Host "    $_" }
        if ($verifyFailed) { $ok = $false }
    }

    if ($ok) {
        Write-Host "  -> PORTABLE" -ForegroundColor Green
    } else {
        Write-Host "  -> NOT PORTABLE" -ForegroundColor Red
    }
    return $ok
}

$targets = switch ($Target) {
    "All" { @("PhaseStudio", "superflip", "PhaseStudioJanaInstaller") }
    "Standalone" { @("PhaseStudio") }
    "JanaInstaller" { @("superflip", "PhaseStudioJanaInstaller") }
    "JanaWrapper" { @("superflip") }
}
Push-Location $RepoRoot
try {
    foreach ($product in $targets) {
        Write-Step "Building $product"
        $exePath = Join-Path $distDir "$product\$product.exe"
        $running = @(Get-Process -Name $product -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exePath })
        if ($running.Count) { throw "Close the running build at $exePath before rebuilding." }
        if ($Clean) {
            Remove-TargetOutput (Join-Path $distDir $product)
            Remove-TargetOutput (Join-Path $buildDir $product)
        }
        $spec = if ($product -eq "superflip") { "superflip.spec" } else { "packaging\pyinstaller\$product.spec" }
        if ($distDir -eq $defaultDist) {
            & $PythonExe -m PyInstaller --clean --noconfirm $spec
        } else {
            & $PythonExe -m PyInstaller --clean --noconfirm --distpath $distDir $spec
        }
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for $product." }
        Assert-PathExists $exePath "Built $product"
        if (-not (Test-PortableRuntime $product (Join-Path $distDir $product) $product)) {
            throw "$product failed portable dependency audits."
        }
    }
    if ($targets -contains "PhaseStudio") {
        # Even -Clean:$false must never retain an old installation payload.
        $oldPayload = Join-Path $distDir "PhaseStudio\JanaIntegration"
        Remove-TargetOutput $oldPayload
        if (Test-Path $oldPayload) { throw "Standalone must not contain an installation payload." }
    }
    if ($targets -contains "PhaseStudioJanaInstaller") {
        $staged = Join-Path $distDir "PhaseStudioJanaInstaller\JanaIntegration"
        Remove-TargetOutput $staged
        Copy-Item -LiteralPath (Join-Path $distDir "superflip") -Destination $staged -Recurse -Force
        Assert-PathExists (Join-Path $staged "superflip.exe") "Installer wrapper payload"
        Assert-PathExists (Join-Path $staged "_internal") "Installer complete wrapper runtime"
        if (-not (Test-PortableRuntime "Installer payload" $staged "superflip")) { throw "Staged payload audit failed." }
    }
    foreach ($product in $targets) {
        $profile = switch ($product) {
            "PhaseStudio" { "standalone" }
            "superflip" { "wrapper" }
            "PhaseStudioJanaInstaller" { "installer" }
        }
        $boundaryArgs = @((Join-Path $PSScriptRoot "tools\check_distribution.py"),
                         (Join-Path $distDir $product), "--profile", $profile)
        if ($profile -eq "installer") { $boundaryArgs += @("--wrapper-source", (Join-Path $distDir "superflip")) }
        & $PythonExe @boundaryArgs
        if ($LASTEXITCODE -ne 0) { throw "$product failed distribution boundary checks." }
    }
} finally { Pop-Location }
Write-Host "Build complete: $($targets -join ', ')" -ForegroundColor Green
