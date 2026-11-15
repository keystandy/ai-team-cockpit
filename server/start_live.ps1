$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runtime = Join-Path $Root "runtime"
$Temp = Join-Path $Runtime "tmp"
$PidFile = Join-Path $Runtime "server.pid"
$LogFile = Join-Path $Runtime "server.log"
$Port = 8765

New-Item -ItemType Directory -Force -Path $Temp | Out-Null

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
    if ($health.ok) {
        Start-Process "http://127.0.0.1:$Port"
        exit 0
    }
} catch {}

$env:TEMP = $Temp
$env:TMP = $Temp
$env:PYTHONPYCACHEPREFIX = Join-Path $Runtime "python-cache"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$env:NO_PROXY = "localhost,127.0.0.1,::1"
$env:no_proxy = $env:NO_PROXY

$PythonArgs = @(
    "-B",
    "-m",
    "server.main"
)
$Process = Start-Process `
    -FilePath "python" `
    -ArgumentList $PythonArgs `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError (Join-Path $Runtime "server-error.log") `
    -PassThru

Set-Content -LiteralPath $PidFile -Value $Process.Id -Encoding ascii

for ($Index = 0; $Index -lt 30; $Index++) {
    Start-Sleep -Milliseconds 300
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        if ($health.ok) {
            Start-Process "http://127.0.0.1:$Port"
            exit 0
        }
    } catch {}
}

throw "AI Team server failed to start. Check $LogFile"

