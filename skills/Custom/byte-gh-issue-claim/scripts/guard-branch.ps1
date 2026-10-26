#Requires -Version 7
# Usage: guard-branch.ps1 <branch> <issue#> [base]
# Run before every commit and push: HEAD must be on <branch>, the issue's own branch, and never on the base branch.
param([Parameter(Mandatory)][string]$Branch, [Parameter(Mandatory)][int]$Issue, [string]$Base)
$failed = 0
if (-not $Base) { $Base = (git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>$null) -replace '^origin/', '' }
if (-not $Base) { $Base = 'main' }
$cur = git branch --show-current
if (-not $cur) { Write-Output "FAIL: HEAD is detached - check out $Branch"; $failed++ }
elseif ($cur -ceq $Branch) { Write-Output "PASS: on $Branch" }
else { Write-Output "FAIL: on '$cur', not $Branch - switch back before committing"; $failed++ }
if ($Branch -cmatch "^[a-z]+/[a-z]+-issue$Issue-") { Write-Output "PASS: $Branch is issue #$Issue's branch" }
else { Write-Output "FAIL: $Branch doesn't match */*-issue$Issue-*"; $failed++ }
if (@($Base, 'main', 'master') -ccontains $Branch) { Write-Output "FAIL: $Branch is a base branch - never commit or push there"; $failed++ }
else { Write-Output "PASS: not the base branch ($Base)" }
exit [int]($failed -gt 0)
