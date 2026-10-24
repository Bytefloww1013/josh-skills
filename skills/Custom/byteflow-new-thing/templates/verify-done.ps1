#Requires -Version 7
# Definition of Done check. Contract: one PASS/FAIL line per check; exit 0 only if all pass.
$ErrorActionPreference = 'Stop'
$failed = 0; $ran = 0

function Check([string]$Name, [scriptblock]$Test) {
    $script:ran++
    # Only the block's last output decides, so stray command output can't make a FAIL look like a PASS.
    try { $ok = [bool](& $Test | Select-Object -Last 1) } catch { $ok = $false }
    if ($ok) { Write-Output "PASS: $Name" } else { Write-Output "FAIL: $Name"; $script:failed++ }
}

# Examples - replace with one Check per scripted DoD item / checkable guardrail:
# Check 'tests pass'          { npm test --silent *> $null; $LASTEXITCODE -eq 0 }
# Check 'template unchanged'  { git diff --quiet HEAD -- templates/base.html; $LASTEXITCODE -eq 0 }
# Check 'output file exists'  { Test-Path 'dist/report.json' }

if ($ran -eq 0) { Write-Output 'FAIL: no checks defined'; $failed++ }
if ($failed) { Write-Output "RESULT: FAIL ($failed)"; exit 1 }
Write-Output 'RESULT: PASS'; exit 0
