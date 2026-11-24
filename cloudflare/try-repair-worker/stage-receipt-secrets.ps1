param(
    [string]$KeyDirectory = (Join-Path $HOME ".aios-secure-keys"),
    [string]$WorkerName = "try-aios-repair-provider",
    [switch]$Stage
)

$ErrorActionPreference = "Stop"

if (-not $Stage) {
    throw "No changes made. Re-run with -Stage to upload a staged Worker version (this script never deploys it)."
}

$privatePath = Join-Path $KeyDirectory "try-operation-private.pk8.der.b64"
$metadataPath = Join-Path $KeyDirectory "key-metadata.json"

foreach ($path in @($privatePath, $metadataPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required local key material is missing: $path"
    }
}

$privateKeyB64 = (Get-Content -LiteralPath $privatePath -Raw).Trim()
$metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
$keyId = [string]$metadata.try_receipt_key_id
$publicKeyB64 = [string]$metadata.try_receipt_public_key_base64

if ([string]::IsNullOrWhiteSpace($privateKeyB64) -or
    [string]::IsNullOrWhiteSpace($keyId) -or
    [string]::IsNullOrWhiteSpace($publicKeyB64)) {
    throw "Key metadata or private key is incomplete."
}

$decoded = $null
$publicDecoded = $null
try {
    $decoded = [Convert]::FromBase64String($privateKeyB64)
    $publicDecoded = [Convert]::FromBase64String($publicKeyB64)
    if ($decoded.Length -lt 48 -or $publicDecoded.Length -ne 32) {
        throw "Unexpected Ed25519 key encoding length."
    }
}
catch {
    throw "Local TRY key encoding validation failed."
}
finally {
    if ($decoded) { [Array]::Clear($decoded, 0, $decoded.Length) }
    if ($publicDecoded) { [Array]::Clear($publicDecoded, 0, $publicDecoded.Length) }
}

$payload = @{
    TRY_OPERATION_RECEIPT_PRIVATE_KEY = $privateKeyB64
    TRY_OPERATION_RECEIPT_KEY_ID = $keyId
} | ConvertTo-Json -Compress

$tempPath = Join-Path ([IO.Path]::GetTempPath()) ("try-receipt-secrets-" + [Guid]::NewGuid().ToString("N") + ".json")

try {
    [IO.File]::WriteAllText($tempPath, $payload, (New-Object System.Text.UTF8Encoding($false)))

    # Restrict the temporary plaintext secret file to the current Windows identity.
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl = Get-Acl -LiteralPath $tempPath
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object Security.AccessControl.FileSystemAccessRule(
        $identity,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow
    )
    $acl.SetAccessRule($rule)
    Set-Acl -LiteralPath $tempPath -AclObject $acl

    Write-Host "Staging TRY receipt signing secrets for Worker '$WorkerName'..."
    Write-Host "The secret values are not placed in command-line arguments."
    & npx wrangler versions secret bulk $tempPath --name $WorkerName
    if ($LASTEXITCODE -ne 0) {
        throw "Wrangler staging failed with exit code $LASTEXITCODE."
    }

    Write-Host "STAGED_ONLY: a Worker version was created; no deployment was requested."
    Write-Host "Review the returned version ID. Do not deploy until all required secrets and runtime checks pass."
}
finally {
    if (Test-Path -LiteralPath $tempPath) {
        Remove-Item -LiteralPath $tempPath -Force
    }
    $payload = $null
    $privateKeyB64 = $null
    $metadata = $null
    [GC]::Collect()
}
