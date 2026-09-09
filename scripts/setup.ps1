<#
.SYNOPSIS
    Vertex: put the project on a Windows machine and start it, in one command.

.DESCRIPTION
    Checks Python, fetches the project, builds a virtual environment, installs
    what the demo needs, starts the API and opens the measurements page.
    Safe to run again: an existing checkout is reused and updated.

    Run it straight from GitHub, no download step and no execution policy to change:

        irm https://raw.githubusercontent.com/Batmanchik/Vertex/claude/documentation-review-improve-w17t1u/scripts/setup.ps1 | iex

    Or, if the file is already on disk:

        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

.PARAMETER Path
    Where to put the project. Defaults to Vertex in the user folder.

.PARAMETER Branch
    Branch to check out. Falls back to main when the branch is not on the remote.

.PARAMETER Port
    Port for the API and the measurements page. Defaults to 8000.

.PARAMETER SkipStart
    Install everything but do not start the server.
#>
[CmdletBinding()]
param(
    [string]$Path = (Join-Path $env:USERPROFILE "Vertex"),
    [string]$Branch = "claude/documentation-review-improve-w17t1u",
    [int]$Port = 8000,
    [switch]$SkipStart
)

# Not "Stop": git writes progress to stderr, and under Stop a redirected native
# stderr line is raised as a terminating error. Exit codes are checked by hand
# instead, right after each call that can fail.
$ErrorActionPreference = "Continue"
$RepoUrl = "https://github.com/Batmanchik/Vertex.git"

# Everything the measurements page, the API and the ladder run need. streamlit,
# mlflow and elasticsearch are left out on purpose: nothing in this demo imports
# them, and they are the three that most often turn a five-minute install into
# a failed one.
$Packages = @(
    "fastapi>=0.104",
    "uvicorn[standard]>=0.24",
    "jinja2>=3.1",
    "scikit-learn>=1.3",
    "pandas>=2.1",
    "numpy>=1.26",
    "networkx>=3.2",
    "joblib>=1.3",
    "lightgbm>=4.0",
    "matplotlib>=3.8",
    "requests>=2.31"
)

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Fail {
    param([string]$Text)
    Write-Host ""
    Write-Host "ОШИБКА: $Text" -ForegroundColor Red
}

function Test-HttpOk {
    param([string]$Url)
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400)
    } catch {
        return $false
    }
}

# ---------------------------------------------------------------- python
function Get-PythonCommand {
    # The Windows Store stub called python.exe exits without printing a version,
    # so a candidate counts only when it actually answers --version.
    $candidates = @(
        @{ File = "py";      Args = @("-3.13") },
        @{ File = "py";      Args = @("-3.12") },
        @{ File = "py";      Args = @("-3.11") },
        @{ File = "py";      Args = @("-3") },
        @{ File = "python";  Args = @() },
        @{ File = "python3"; Args = @() }
    )

    # An installer run without "Add to PATH" leaves a working interpreter that
    # none of the names above reach, so the usual install directories are
    # searched as well. Newest version first.
    $roots = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        "$env:ProgramFiles",
        "C:\"
    )
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $found = Get-ChildItem -Path $root -Filter "Python3*" -Directory -ErrorAction SilentlyContinue |
                 Sort-Object Name -Descending
        foreach ($dir in $found) {
            $exe = Join-Path $dir.FullName "python.exe"
            if (Test-Path $exe) {
                $candidates += @{ File = $exe; Args = @() }
            }
        }
    }

    foreach ($candidate in $candidates) {
        try {
            $output = & $candidate.File @($candidate.Args + @("--version")) 2>&1
        } catch {
            continue
        }

        # The version line is the test, not the exit code: a candidate that is
        # missing prints an error instead, and the Store stub prints nothing.
        $text = ($output | Out-String).Trim()
        if ($text -match "Python\s+(\d+)\.(\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -eq 3 -and $minor -ge 10) {
                return @{ File = $candidate.File; Args = $candidate.Args; Version = $text }
            }
        }
    }
    return $null
}

# ---------------------------------------------------------------- checks
Write-Step "Проверяю, что установлено"

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    Write-Host "git не найден." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Могу поставить его сам через winget."
        $answer = Read-Host "Ставить? [Y/n]"
        if ($answer -eq "" -or $answer -match "^[YyДд]") {
            Write-Step "Ставлю git"
            & winget install --id Git.Git -e --source winget `
                --accept-package-agreements --accept-source-agreements
            Write-Host ""
            Write-Host "git установлен. Он появится в PATH только в новом окне." -ForegroundColor Yellow
            Write-Host "Закройте это окно, откройте новое и запустите команду ещё раз."
            return
        }
    }
    Write-Fail "не найден git."
    Write-Host "Поставьте его одной командой:"
    Write-Host "    winget install --id Git.Git -e --source winget" -ForegroundColor White
    Write-Host "или скачайте с https://git-scm.com/download/win, галочки по умолчанию."
    Write-Host "Потом закройте это окно, откройте новое и запустите команду ещё раз."
    return
}
Write-Host "git: $((& git --version) -join '')"

$python = Get-PythonCommand
if (-not $python) {
    Write-Host "Python 3.10 или новее не найден." -ForegroundColor Yellow

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "Могу поставить его сам через winget (Python 3.12, примерно минута)."
        $answer = Read-Host "Ставить? [Y/n]"
        if ($answer -eq "" -or $answer -match "^[YyДд]") {
            Write-Step "Ставлю Python 3.12"
            & winget install --id Python.Python.3.12 -e --source winget `
                --accept-package-agreements --accept-source-agreements
            # winget adds Python to PATH for new processes only, so the search
            # below relies on the install directories rather than on PATH.
            $python = Get-PythonCommand
        }
    }
}

if (-not $python) {
    Write-Fail "не найден Python 3.10 или новее."
    Write-Host ""
    Write-Host "Способ 1, через браузер:"
    Write-Host "  открыть https://www.python.org/downloads/ , нажать большую кнопку"
    Write-Host "  Download Python, запустить файл и на первом экране установщика"
    Write-Host "  отметить галочку 'Add python.exe to PATH'." -ForegroundColor White
    Write-Host "  Без этой галочки Python поставится, но команды его не увидят."
    Write-Host ""
    Write-Host "Способ 2, через магазин приложений:"
    Write-Host "  открыть Microsoft Store, найти Python 3.12 и нажать Install."
    Write-Host "  Эта версия прописывается в PATH сама."
    Write-Host ""
    Write-Host "Потом закройте это окно, откройте новое и запустите команду ещё раз."
    return
}
Write-Host "python: $($python.Version)"

# ---------------------------------------------------------------- checkout
Write-Step "Проект"

$pyprojectHere = Join-Path (Get-Location).Path "pyproject.toml"
if ((Test-Path $pyprojectHere) -and ((Get-Content $pyprojectHere -Raw) -match 'name\s*=\s*"apris"')) {
    # Уже стоим внутри проекта: ничего не скачиваем.
    $Path = (Get-Location).Path
    Write-Host "уже в папке проекта: $Path"
} elseif (Test-Path (Join-Path $Path ".git")) {
    Write-Host "проект уже есть: $Path"
} else {
    Write-Host "скачиваю в $Path"
    & git clone $RepoUrl $Path
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "не удалось скачать проект. Проверьте интернет и попробуйте ещё раз."
        return
    }
}

Set-Location $Path

& git fetch origin $Branch 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    & git checkout $Branch 2>$null | Out-Null
    & git pull origin $Branch 2>$null | Out-Null
    Write-Host "ветка: $Branch"
} else {
    Write-Host "ветки $Branch нет на сервере, остаюсь на текущей" -ForegroundColor Yellow
}

# ---------------------------------------------------------------- venv
$VenvPython = Join-Path $Path ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Step "Создаю окружение (.venv)"
    & $python.File @($python.Args + @("-m", "venv", ".venv"))
    if (-not (Test-Path $VenvPython)) {
        Write-Fail "не удалось создать .venv."
        return
    }
} else {
    Write-Step "Окружение .venv уже есть"
}

Write-Step "Ставлю зависимости, первый раз это несколько минут"
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet @Packages
if ($LASTEXITCODE -ne 0) {
    Write-Fail "не удалось поставить зависимости. Прокрутите вывод выше, там написана причина."
    return
}
& $VenvPython -m pip install --quiet --no-deps -e .
if ($LASTEXITCODE -ne 0) {
    Write-Fail "не удалось зарегистрировать пакет apris."
    return
}
Write-Host "готово"

# ---------------------------------------------------------------- проверка
Write-Step "Проверяю, что всё импортируется"
& $VenvPython -c "import apris.api.main; print('apris ok')"
if ($LASTEXITCODE -ne 0) {
    Write-Fail "пакет поставился, но не импортируется. Причина в выводе выше."
    return
}

if ($SkipStart) {
    Write-Host ""
    Write-Host "Установка закончена. Запуск: .venv\Scripts\python.exe -m uvicorn apris.api.main:app --port $Port"
    return
}

# ---------------------------------------------------------------- старт
Write-Step "Запускаю сервер на порту $Port"

$healthUrl = "http://127.0.0.1:$Port/api/v1/health"
$pageUrl = "http://127.0.0.1:$Port/"

if (Test-HttpOk -Url $healthUrl) {
    Write-Host "на этом порту уже что-то работает, открываю страницу"
} else {
    Start-Process -FilePath $VenvPython `
        -ArgumentList @("-m", "uvicorn", "apris.api.main:app", "--host", "127.0.0.1", "--port", "$Port") `
        -WorkingDirectory $Path | Out-Null

    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 1
        if (Test-HttpOk -Url $healthUrl) { $ready = $true; break }
    }
    if (-not $ready) {
        Write-Fail "сервер запустился, но не отвечает. Посмотрите на второе окно, которое открылось."
        return
    }
}

Start-Process $pageUrl | Out-Null

Write-Host ""
Write-Host "Готово." -ForegroundColor Green
Write-Host "  Витрина измерений:  $pageUrl"
Write-Host "  Папка проекта:      $Path"
Write-Host ""
Write-Host "Сервер работает во втором окне. Чтобы остановить, закройте его или нажмите там Ctrl+C."
Write-Host "Порядок показа на защите: docs\DEMO.md"
