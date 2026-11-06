param([Parameter(Mandatory=$true)][string]$File)
$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path -LiteralPath $File).Path
$signature = Get-AuthenticodeSignature -LiteralPath $resolved
function Test-CertificateChain($Certificate) {
    if ($null -eq $Certificate) { return $false }
    $chain = New-Object Security.Cryptography.X509Certificates.X509Chain
    try {
        $chain.ChainPolicy.RevocationMode = [Security.Cryptography.X509Certificates.X509RevocationMode]::Online
        $chain.ChainPolicy.RevocationFlag = [Security.Cryptography.X509Certificates.X509RevocationFlag]::ExcludeRoot
        $chain.ChainPolicy.UrlRetrievalTimeout = [TimeSpan]::FromSeconds(30)
        return $chain.Build($Certificate)
    } finally { $chain.Dispose() }
}
$timestampEku = $false
if ($null -ne $signature.TimeStamperCertificate) {
    foreach ($extension in $signature.TimeStamperCertificate.Extensions) {
        if ($extension -is [Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]) {
            foreach ($usage in $extension.EnhancedKeyUsages) {
                if ($usage.Value -eq '1.3.6.1.5.5.7.3.8') { $timestampEku = $true }
            }
        }
    }
}
$record = [ordered]@{
    sha256 = (Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash.ToLowerInvariant()
    status = $signature.Status.ToString()
    signature_type = $signature.SignatureType.ToString()
    signer_subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { $null }
    signer_thumbprint = if ($signature.SignerCertificate) { $signature.SignerCertificate.Thumbprint } else { $null }
    signer_chain_valid = (Test-CertificateChain $signature.SignerCertificate)
    timestamp_present = ($null -ne $signature.TimeStamperCertificate)
    timestamp_chain_valid = (Test-CertificateChain $signature.TimeStamperCertificate)
    timestamp_eku_valid = $timestampEku
    product_version = (Get-Item -LiteralPath $resolved).VersionInfo.ProductVersion
}
$record | ConvertTo-Json -Compress
