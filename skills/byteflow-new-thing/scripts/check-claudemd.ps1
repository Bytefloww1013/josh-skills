#Requires -Version 7
# Usage: check-claudemd.ps1 [path=./CLAUDE.md] [maxLines=200]
param([string]$Path = './CLAUDE.md', [int]$MaxLines = 200)
$failed = 0
if (-not (Test-Path -LiteralPath $Path)) { Write-Output "FAIL: $Path not found"; exit 1 }
$lines = @(Get-Content -LiteralPath $Path)
Write-Output "PASS: $Path exists"

# "under 200 if possible" -> soft limit
if ($lines.Count -le $MaxLines) { Write-Output "PASS: $($lines.Count) lines (<= $MaxLines)" }
else { Write-Output "WARN: $($lines.Count) lines (> $MaxLines) - prune it" }

foreach ($s in 'TOOLS AND COMMANDS', 'WORKFLOWS', 'GOTCHAS') {
    if ($lines -match "^#+\s*$s\b") { Write-Output "PASS: section '$s'" }
    else { Write-Output "FAIL: section '$s' missing"; $failed++ }
}
exit [int]($failed -gt 0)
