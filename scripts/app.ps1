param(
    [Parameter(Mandatory = $false, Position = 0)]
    [ValidateSet("start", "stop", "status", "open")]
    [string]$Command = "status"
)

# Один процесс, один адрес. Раньше здесь поднимались два — API и интерфейс на
# Streamlit, — и половина этого файла занималась тем, чтобы их согласовать:
# два pid-файла, две проверки здоровья, два способа не запуститься. Интерфейс
# переехал на ту же страницу, что отдаёт API, и всё это стало не нужно.

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RunDir = Join-Path $ProjectRoot ".run"
$PidFile = Join-Path $RunDir "api.pid"
$OutLog = Join-Path $RunDir "api.out.log"
$ErrLog = Join-Path $RunDir "api.err.log"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$HealthUrl = "http://127.0.0.1:8000/api/v1/health"
$SiteUrl = "http://127.0.0.1:8000/"

function Test-HttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $false)][int]$TimeoutSec = 2
    )
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec $TimeoutSec -UseBasicParsing
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    } catch {
        return $false
    }
}

function Get-RunningPid {
    if (-not (Test-Path $PidFile)) { return $null }
    $value = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $value) { return $null }
    $processId = 0
    if (-not [int]::TryParse($value.Trim(), [ref]$processId)) { return $null }
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    return $processId
}

function Invoke-Start {
    if (-not (Test-Path $PythonExe)) {
        Write-Host "Нет виртуального окружения. Запустите scripts\setup.ps1" -ForegroundColor Red
        return
    }
    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

    if (Test-HttpOk -Url $HealthUrl) {
        Write-Host "Уже работает: $SiteUrl"
        return
    }

    Write-Host "Собираю очередь аналитика…"
    & $PythonExe (Join-Path $ProjectRoot "scripts\run_pipeline.py") --preset full | Out-Null

    Write-Host "Поднимаю сайт…"
    $process = Start-Process -FilePath $PythonExe `
        -ArgumentList @("-m", "uvicorn", "apris.api.main:app",
                        "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog `
        -PassThru -WindowStyle Hidden
    $process.Id | Out-File -FilePath $PidFile -Encoding ascii

    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 1
        if (Test-HttpOk -Url $HealthUrl) {
            Write-Host "Готово: $SiteUrl" -ForegroundColor Green
            return
        }
    }
    Write-Host "Не отвечает. Смотрите $ErrLog" -ForegroundColor Red
}

function Invoke-Stop {
    $processId = Get-RunningPid
    if ($null -ne $processId) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        Write-Host "Остановлен (pid $processId)"
    } else {
        Write-Host "Не запущен"
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}

function Invoke-Status {
    $processId = Get-RunningPid
    $alive = Test-HttpOk -Url $HealthUrl
    Write-Host "pid:     $(if ($null -ne $processId) { $processId } else { '—' })"
    Write-Host "адрес:   $SiteUrl"
    Write-Host "здоров:  $(if ($alive) { 'да' } else { 'нет' })"
}

switch ($Command) {
    "start"  { Invoke-Start }
    "stop"   { Invoke-Stop }
    "status" { Invoke-Status }
    "open"   { Start-Process $SiteUrl | Out-Null }
}
