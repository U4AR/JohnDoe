$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    python -m venv .venv
}

& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$stdout = Join-Path $root "app_run.log"
$stderr = Join-Path $root "app_run.err.log"
$app = Start-Process -FilePath $python -ArgumentList "app.py" -WorkingDirectory $root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest "http://127.0.0.1:7860" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { break }
    } catch {}
} while ((Get-Date) -lt $deadline -and -not $app.HasExited)

if ($app.HasExited) {
    Get-Content $stderr -Tail 50 -ErrorAction SilentlyContinue
    exit $app.ExitCode
}

Write-Host "Opening Phantom Grid at http://127.0.0.1:7860"
Start-Process "http://127.0.0.1:7860"
Wait-Process -Id $app.Id
