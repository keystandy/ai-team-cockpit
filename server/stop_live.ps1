$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PidFile = Join-Path $Root "runtime\server.pid"
if (Test-Path -LiteralPath $PidFile) {
    $ServerPid = [int](Get-Content -LiteralPath $PidFile -Raw)
    $Process = Get-Process -Id $ServerPid -ErrorAction SilentlyContinue
    if ($Process) {
        Stop-Process -Id $ServerPid
    }
    Remove-Item -LiteralPath $PidFile -Force
}

