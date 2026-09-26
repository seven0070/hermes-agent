# Local-only Buzz relay and Hermes preparation. Does not start the gateway.
# Run in PowerShell 7 or Windows PowerShell 5.1 after reading README.md.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$OwnerPubkey,
    [Parameter(Mandatory=$true)][ValidatePattern('^(?:[0-9a-fA-F]{64}|npub1[023456789acdefghjklmnpqrstuvwxyz]{58})$')][string]$AllowedUser,
    [string]$Workspace = (Join-Path $HOME 'buzz-local'),
    [string]$HermesHome = $(if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA 'hermes' })
)
$ErrorActionPreference = 'Stop'
$relay = 'ws://127.0.0.1:3000'
function Need([string]$name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "Missing $name. Install it first, then rerun." }
}
function New-SecretHex {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}
function Save-NewFile([string]$path, [string[]]$lines) {
    if (Test-Path $path) { throw "Existing file $path was not modified. Inspect it and finish manually." }
    $parentDir = Split-Path -Parent $path
    if (-not (Test-Path $parentDir)) { throw "Destination directory does not exist: $parentDir" }
    # Set an owner-only ACL before writing any secret bytes. A failing ACL
    # operation must leave only an empty file, not a readable private key.
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($path, '', $utf8)
    $acl = Get-Acl $path
    $acl.SetAccessRuleProtection($true, $false)
    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new([System.Security.Principal.WindowsIdentity]::GetCurrent().Name, 'FullControl', 'Allow')
    $acl.AddAccessRule($rule)
    try {
        Set-Acl -Path $path -AclObject $acl
        [System.IO.File]::WriteAllLines($path, $lines, $utf8)
    } catch {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        throw
    }
}
Need 'docker'; Need 'git'; Need 'cargo'
& docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop engine is not running.' }
$composeVersion = (& docker compose version --short 2>$null | Select-Object -First 1)
if ($LASTEXITCODE -ne 0 -or -not $composeVersion) { throw 'Docker Compose v2 is unavailable.' }
$versionMatch = [regex]::Match($composeVersion, '^(?:v)?(\d+)\.(\d+)\.(\d+)')
if (-not $versionMatch.Success -or [version]::new([int]$versionMatch.Groups[1].Value, [int]$versionMatch.Groups[2].Value, [int]$versionMatch.Groups[3].Value) -lt [version]'2.24.4') {
    throw 'Docker Compose 2.24.4+ is required for the local-only port override.'
}
& cargo --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Rust/Cargo is not working.' }
$gitBash = Join-Path $env:ProgramFiles 'Git\bin\bash.exe'
if (-not (Test-Path $gitBash)) { Write-Warning 'Git Bash was not found in Program Files. Hermes may have another usable Git Bash location; verify it separately.' }
New-Item -ItemType Directory -Force -Path $Workspace, $HermesHome | Out-Null
$source = Join-Path $Workspace 'buzz'
if (-not (Test-Path (Join-Path $source '.git'))) {
    if (Test-Path $source) { throw "Refusing to replace existing $source." }
    & git clone https://github.com/block/buzz.git $source
    if ($LASTEXITCODE -ne 0) { throw 'Buzz clone failed.' }
}
$compose = Join-Path $source 'deploy\compose'
$template = Join-Path $compose '.env.example'
if (-not (Test-Path $template)) { throw 'Upstream Compose template missing; stop rather than guessing.' }
$localOverride = Join-Path $compose 'compose.local.yml'
if (Test-Path $localOverride) { throw 'Existing compose.local.yml was not modified; inspect it manually.' }
$composeEnv = Join-Path $compose '.env'
$hermesEnv = Join-Path $HermesHome '.env'
if (Test-Path $composeEnv) { throw 'Buzz relay .env already exists. No relay identity or data was overwritten.' }
$existingHermesLines = @(if (Test-Path $hermesEnv) { [System.IO.File]::ReadAllLines($hermesEnv) })
if (@($existingHermesLines | Where-Object { $_ -match '^\s*(BUZZ_[A-Z_]+|RELAY_URL)\s*=' }).Count -gt 0) {
    throw 'Hermes already has Buzz settings. No settings or identity were overwritten; inspect manually.'
}
# Build the Windows CLI before generating/writing any keys.
& cargo build --release -p buzz-cli --manifest-path (Join-Path $source 'Cargo.toml')
if ($LASTEXITCODE -ne 0) { throw 'Windows buzz-cli build failed; no secrets written.' }
$cliPath = Join-Path $source 'target\release\buzz.exe'
if (-not (Test-Path $cliPath)) { throw 'Build returned success, but buzz.exe is missing.' }
# buzz-admin runs in a disposable container. Capture key material in memory; never log it.
$rawKey = & docker run --rm --entrypoint /usr/local/bin/buzz-admin ghcr.io/block/buzz:main generate-key 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Buzz key generator failed; no files written.' }
$keyText = ($rawKey | Out-String)
$pubMatch = [regex]::Match($keyText, '(?im)^\s*Public key:\s*([0-9a-f]{64})\s*$')
$secMatch = [regex]::Match($keyText, '(?im)^\s*Secret key:\s*([0-9a-f]{64})\s*$')
if (-not $pubMatch.Success -or -not $secMatch.Success) { throw 'Unrecognized buzz-admin output. No files written; check upstream format.' }
$agentPubkey = $pubMatch.Groups[1].Value.ToLowerInvariant()
$agentSecret = $secMatch.Groups[1].Value.ToLowerInvariant()
$relaySecret = New-SecretHex
# The upstream template's main image and this source checkout may diverge;
# a live CLI compatibility test is required before relying on the gateway.
$values = @{
    'BUZZ_DOMAIN' = '127.0.0.1'; 'RELAY_URL' = $relay
    'BUZZ_MEDIA_BASE_URL' = 'http://127.0.0.1:3000/media'
    'BUZZ_MEDIA_SERVER_DOMAIN' = '127.0.0.1'
    'BUZZ_CORS_ORIGINS' = 'http://127.0.0.1:3000'
    'RELAY_OWNER_PUBKEY' = $OwnerPubkey.ToLowerInvariant()
    'BUZZ_RELAY_PRIVATE_KEY' = $relaySecret
    'BUZZ_GIT_HOOK_HMAC_SECRET' = (New-SecretHex)
    'POSTGRES_PASSWORD' = (New-SecretHex)
    'REDIS_PASSWORD' = (New-SecretHex)
    'BUZZ_S3_ACCESS_KEY' = (New-SecretHex)
    'BUZZ_S3_SECRET_KEY' = (New-SecretHex)
}
$lines = foreach ($line in [System.IO.File]::ReadAllLines($template)) {
    if ($line -match '^([A-Z][A-Z0-9_]*)=') {
        $name = $Matches[1]
        if ($values.ContainsKey($name)) { "$name=$($values[$name])"; continue }
    }
    $line
}
if (@($lines | Where-Object { $_ -match '^[A-Z][A-Z0-9_]*=.*CHANGE_ME' }).Count -gt 0) { throw 'Upstream added a new placeholder. No files written; review template.' }
$buzzLines = @(
    "BUZZ_RELAY_URL=$relay", "BUZZ_PRIVATE_KEY=$agentSecret", "BUZZ_CLI_PATH=$cliPath",
    'BUZZ_ALLOW_ALL_USERS=false', "BUZZ_ALLOWED_USERS=$AllowedUser",
    'BUZZ_REQUIRE_MENTION=true', 'BUZZ_TRANSPORT=auto'
)
# Preserve unrelated Hermes env entries. Back up before replacing values.
$mergedHermesLines = @($existingHermesLines) + $buzzLines
Save-NewFile $localOverride @(
    'services:',
    '  relay:',
    '    ports: !override',
    '      - "127.0.0.1:3000:3000"'
)
Save-NewFile $composeEnv $lines
if (Test-Path $hermesEnv) {
    $tempEnv = Join-Path $HermesHome ('.env.buzz-' + [guid]::NewGuid().ToString('N'))
    Save-NewFile $tempEnv $mergedHermesLines
    try {
        # Backup existing Hermes env before merge; do not leave credentials in a
        # default-acl plaintext copy. Save-NewFile applies owner-only ACL.
        $backupEnv = Join-Path $HermesHome ('.env.before-buzz-' + [guid]::NewGuid().ToString('N'))
        Save-NewFile $backupEnv $existingHermesLines
        [System.IO.File]::Copy($tempEnv, $hermesEnv, $true)
        # Copy preserves the existing file ACL; Set-Acl ensures the updated env
        # has the same owner-only permissions as the temporary file.
        Set-Acl -Path $hermesEnv -AclObject (Get-Acl $tempEnv)
    }
    finally { if (Test-Path $tempEnv) { Remove-Item -LiteralPath $tempEnv -Force } }
} else {
    Save-NewFile $hermesEnv $mergedHermesLines
}
# Never show secrets. The public key is needed for admission.
Write-Host "New local relay config: $composeEnv (loopback-only override: $localOverride)"
Write-Host "Hermes secret/config env: $hermesEnv"
if ($backupEnv) { Write-Host "Previous Hermes env backup: $backupEnv (owner-only ACL)" }
Write-Host "Agent PUBLIC hex key for relay admission: $agentPubkey"
Write-Host 'Next: inspect README-BuzzLocal.md; start Compose, admit the agent, and enable Buzz in Hermes.'
