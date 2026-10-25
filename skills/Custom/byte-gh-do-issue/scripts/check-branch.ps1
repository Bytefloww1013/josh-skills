#Requires -Version 7
# Usage: check-branch.ps1 <branch> <issue#>
# Format: <descriptor>/<action>-issue<N>-<description>, e.g. feature/build-issue30-docs-context-system
param([Parameter(Mandatory)][string]$Branch, [Parameter(Mandatory)][int]$Issue)
$failed = 0
$descriptors = 'feature', 'bug', 'refactor', 'doc', 'chore', 'test', 'ci'
$actions = 'add', 'build', 'change', 'delete', 'fix', 'install', 'move', 'remove', 'rename', 'update', 'upgrade'
if ($Branch -cmatch '^[a-z]+/[a-z]+-issue[0-9]+-[a-z0-9]+(-[a-z0-9]+){1,2}$') { Write-Output 'PASS: format <descriptor>/<action>-issue<N>-<2-3 word description>' }
else { Write-Output "FAIL: '$Branch' does not match <descriptor>/<action>-issue<N>-<2-3 lower-case kebab words>"; $failed++ }
$d = ($Branch -split '/', 2)[0]; $a = ((($Branch -split '/', 2)[-1]) -split '-', 2)[0]
if ($descriptors -ccontains $d) { Write-Output "PASS: descriptor $d" } else { Write-Output "FAIL: '$d' is not a descriptor ($($descriptors -join ', '))"; $failed++ }
if ($actions -ccontains $a) { Write-Output "PASS: action $a" } else { Write-Output "FAIL: '$a' is not an action ($($actions -join ', '))"; $failed++ }
if ($Branch -match "-issue$Issue-") { Write-Output "PASS: issue number $Issue" } else { Write-Output "FAIL: issue number is not $Issue"; $failed++ }
if ($Branch.Length -le 60) { Write-Output "PASS: $($Branch.Length) chars (<= 60)" } else { Write-Output "WARN: $($Branch.Length) chars (> 60) - shorten the description" }
git check-ref-format --branch $Branch *> $null
if ($LASTEXITCODE -eq 0) { Write-Output 'PASS: valid git ref' } else { Write-Output 'FAIL: invalid git ref'; $failed++ }
git show-ref --verify --quiet "refs/heads/$Branch"
if ($LASTEXITCODE -eq 0) { Write-Output 'WARN: local branch already exists - resume or pick another name' }
git ls-remote --exit-code --heads origin $Branch *> $null
if ($LASTEXITCODE -eq 0) { Write-Output 'WARN: remote branch already exists - resume or pick another name' }
exit [int]($failed -gt 0)
