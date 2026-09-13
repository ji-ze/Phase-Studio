<#
.SYNOPSIS
    Shared helpers for packaging/build_windows.ps1 and packaging/build_store_msix.ps1.

.DESCRIPTION
    Dot-source this file (". (Join-Path $PSScriptRoot 'common.ps1')") rather
    than copy-pasting these two small functions into every packaging script.
    Keep this file limited to genuinely shared, packaging-generic helpers --
    Store/MSIX-specific logic (manifest generation, MakeAppx, Authenticode
    signing) and developer-build-specific logic (locked-process detection,
    build-output cleanup) belong in their own scripts, not here.
#>

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-PathExists($Path, $Description) {
    if (-not (Test-Path $Path)) {
        throw "$Description not found: $Path"
    }
}
