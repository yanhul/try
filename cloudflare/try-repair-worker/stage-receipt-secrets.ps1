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

$tempDirectory = Join-Path ([IO.Path]::GetTempPath()) ("try-receipt-secrets-" + [Guid]::NewGuid().ToString("N"))
$tempPath = Join-Path $tempDirectory "secrets.json"

function Set-CurrentUserOnlyAcl([string]$Path) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true, $false)

    # A newly created Windows file can carry explicit SYSTEM/logon-session ACEs.
    # Remove every existing ACE; SetAccessRule alone does not guarantee this.
    foreach ($existingRule in @($acl.Access)) {
        [void]$acl.RemoveAccessRuleSpecific($existingRule)
    }

    $rule = New-Object Security.AccessControl.FileSystemAccessRule(
        $identity,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow
    )
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $Path -AclObject $acl

    # Read back the persisted descriptor and fail closed unless it is exact.
    $verified = Get-Acl -LiteralPath $Path
    $entries = @($verified.Access)
    if (-not $verified.AreAccessRulesProtected -or
        $verified.Owner -ne $identity -or
        $entries.Count -ne 1 -or
        $entries[0].IdentityReference.Value -ne $identity -or
        $entries[0].AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
        $entries[0].FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl -or
        $entries[0].IsInherited) {
        throw "ACL verification failed for '$Path'; refusing to write or stage secrets."
    }
}

try {
    # Create and lock the directory before any plaintext secret file exists.
    New-Item -ItemType Directory -Path $tempDirectory -ErrorAction Stop | Out-Null
    Set-CurrentUserOnlyAcl -Path $tempDirectory

    # Create an empty file, lock its ACL, and only then write secret material.
    New-Item -ItemType File -Path $tempPath -ErrorAction Stop | Out-Null
    Set-CurrentUserOnlyAcl -Path $tempPath
    [IO.File]::WriteAllText($tempPath, $payload, (New-Object System.Text.UTF8Encoding($false)))

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
    if (Test-Path -LiteralPath $tempDirectory) {
        Remove-Item -LiteralPath $tempDirectory -Recurse -Force
    }
    $payload = $null
    $privateKeyB64 = $null
    $metadata = $null
    [GC]::Collect()
}
