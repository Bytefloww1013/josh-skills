#Requires -Version 7
# Reports OS/shells and whether hooks (which /goal needs) are disabled. Run from the project root.
$os = if ($IsWindows) { 'windows' } elseif ($IsMacOS) { 'macos' } else { 'linux' }
Write-Output "INFO: os=$os pwsh=$($PSVersionTable.PSVersion)"
foreach ($t in 'bash', 'python', 'python3', 'node') {
    Write-Output "INFO: $t=$([bool](Get-Command $t -ErrorAction SilentlyContinue))"
}
Write-Output "INFO: script language=$(if ($IsWindows) { 'powershell (.ps1)' } else { 'bash (.sh)' })"

$managed = if ($IsWindows) { 'C:\Program Files\ClaudeCode\managed-settings.json' }
           elseif ($IsMacOS) { '/Library/Application Support/ClaudeCode/managed-settings.json' }
           else { '/etc/claude-code/managed-settings.json' }
$files = @((Join-Path $HOME '.claude/settings.json'), '.claude/settings.json', '.claude/settings.local.json', $managed)
$hits = @(foreach ($f in $files) {
    if ((Test-Path -LiteralPath $f) -and
        (Select-String -LiteralPath $f -Pattern '"(disableAllHooks|allowManagedHooksOnly)"\s*:\s*true' -Quiet)) { $f }
})
if ($hits) { Write-Output "FAIL: hooks restricted in $($hits -join ', ') - /goal unavailable"; exit 1 }
Write-Output 'PASS: hooks not disabled - /goal available'
exit 0
