#Requires -Version 7
# Reports OS and available shells/runtimes. Run from the project root.
$os = if ($IsWindows) { 'windows' } elseif ($IsMacOS) { 'macos' } else { 'linux' }
Write-Output "INFO: os=$os pwsh=$($PSVersionTable.PSVersion)"
foreach ($t in 'bash', 'python', 'python3', 'node') {
    Write-Output "INFO: $t=$([bool](Get-Command $t -ErrorAction SilentlyContinue))"
}
Write-Output "INFO: script language=$(if ($IsWindows) { 'powershell (.ps1)' } else { 'bash (.sh)' })"

exit 0
