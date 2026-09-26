# Optional local Buzz setup after Hermes install. May also be run later.
[CmdletBinding()]
param(
    [string]$HermesHome = $(if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA 'hermes' })
)
$ErrorActionPreference = 'Stop'
$setup = Join-Path $PSScriptRoot 'Setup-BuzzLocal.ps1'
$guide = Join-Path $PSScriptRoot 'README-BuzzLocal.md'
if (-not (Test-Path $setup) -or -not (Test-Path $guide)) { throw 'Buzz setup files are missing.' }
Write-Host 'Buzz runs locally alongside Hermes. This setup builds the Buzz CLI and creates a private relay identity.'
Write-Host 'Docker Desktop and Rust are required. The relay will be reachable only on this PC.'
Write-Host "Read the guide before proceeding: $guide"
$answer = Read-Host 'Set up Buzz now? [y/N]'
if ($answer -notmatch '^(?i:y|yes)$') { Write-Host "Skipped. Run this file later: $PSCommandPath"; return }
Write-Host 'In Buzz Desktop, create or open your identity, then copy its public hex key and npub.'
$owner = Read-Host 'Your 64-character public hex key (not your private key)'
$allowed = Read-Host 'Your public npub or hex key (allowed to command Hermes)'
if ($owner -notmatch '^[0-9a-fA-F]{64}$' -or $allowed -notmatch '^(?:[0-9a-fA-F]{64}|npub1[023456789acdefghjklmnpqrstuvwxyz]{58})$') {
    throw 'Public keys are missing or invalid. No Buzz setup started.'
}
& $setup -OwnerPubkey $owner -AllowedUser $allowed -HermesHome $HermesHome
Write-Host "Continue with the relay start, membership and gateway steps in $guide"
