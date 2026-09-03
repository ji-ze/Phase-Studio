<#
.SYNOPSIS
    Locally sign an already-built Phase Studio MSIX with a development/test
    certificate, for sideload testing on a machine that trusts it.

.DESCRIPTION
    Store submission does not need this: Microsoft Store re-signs the
    package with its own production signing after certification (see
    packaging\README_STORE.md, "Store vs local distribution"). This script
    is only for installing the MSIX directly (sideloading) on a development
    or test machine.

    Never commit a .pfx, private key, or password to this repository.

.PARAMETER MsixPath
    Path to the .msix produced by build_store_msix.ps1.

.PARAMETER TestCertificatePath
    Path to a local .pfx test certificate (e.g. created with
    New-SelfSignedCertificate + Export-PfxCertificate). Its Subject must
    exactly match the MSIX Package Identity Publisher field.

.PARAMETER TestCertificatePassword
    Password for the .pfx, as a SecureString.

.PARAMETER TimestampUrl
    Optional RFC 3161 timestamp server.

.EXAMPLE
    powershell -File packaging\sign_test_msix.ps1 `
        -MsixPath dist\store\PhaseStudio-1.0.7-x64.msix `
        -TestCertificatePath C:\dev\phase_studio_test.pfx `
        -TestCertificatePassword (Read-Host -AsSecureString "Cert password")
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MsixPath,
    [Parameter(Mandatory = $true)]
    [string]$TestCertificatePath,
    [Parameter(Mandatory = $true)]
    [System.Security.SecureString]$TestCertificatePassword,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $MsixPath)) { throw "MSIX package not found: $MsixPath" }
if (-not (Test-Path $TestCertificatePath)) { throw "Test certificate not found: $TestCertificatePath" }

$signTool = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "\\x64\\" } | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signTool) {
    throw "SignTool.exe was not found under any installed Windows Kits (Windows SDK)."
}

$plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($TestCertificatePassword))
$signArgs = @("sign", "/fd", "SHA256", "/a", "/f", $TestCertificatePath, "/p", $plainPassword)
if ($TimestampUrl) {
    $signArgs += @("/tr", $TimestampUrl, "/td", "SHA256")
}
$signArgs += $MsixPath

Write-Host "Signing $MsixPath for local sideload testing..." -ForegroundColor Cyan
& $signTool.FullName @signArgs
if ($LASTEXITCODE -ne 0) {
    throw "Signing failed (SignTool exit code $LASTEXITCODE). Check that the certificate Subject matches the MSIX Package Identity Publisher."
}

Write-Host "Test-signed: $MsixPath" -ForegroundColor Green
Write-Host "Trust the test certificate on the target machine (Local Machine \ Trusted People) before installing." -ForegroundColor DarkGray
