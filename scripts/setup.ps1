<#
.SYNOPSIS
    Vertex: put the project on a Windows machine and start it, in one command.

.DESCRIPTION
    Checks Python, fetches the project, builds a virtual environment, installs
    what the demo needs, starts the API and opens the measurements page.
    Safe to run again: an existing checkout is reused and updated.

    git is optional. When it is missing the branch is fetched as a zip from
    GitHub instead, which needs nothing beyond PowerShell itself.

    Run it straight from GitHub, no download step and no execution policy to change:

        irm https://raw.githubusercontent.com/Batmanchik/Vertex/main/scripts/setup.ps1 | iex

    Or, if the file is already on disk:

        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

.PARAMETER Path
    Where to put the project. Defaults to Vertex in the user folder.

.PARAMETER Branch
    Branch to check out. Defaults to main.

.PARAMETER Port
    Port for the interface. Defaults to 8501, and one address carries
    everything: the measurements page is a page inside it.

.PARAMETER WithApi
    Also start the API on port 8000, for the scoring endpoints.

.PARAMETER SkipStart
    Install everything but do not start the server.
#>
[CmdletBinding()]
param(
    [string]$Path = (Join-Path $env:USERPROFILE "Vertex"),
    [string]$Branch = "main",
    [int]$Port = 8501,
    [switch]$WithApi,
    [switch]$SkipStart
)

# Not "Stop": git writes progress to stderr, and under Stop a redirected native
# stderr line is raised as a terminating error. Exit codes are checked by hand
# instead, right after each call that can fail.
$ErrorActionPreference = "Continue"
$RepoUrl = "https://github.com/Batmanchik/Vertex.git"

# Everything the interface, the API and the ladder run need. mlflow and
# elasticsearch are left out on purpose: nothing in this demo imports them, and
# they are the two that most often turn a five-minute install into a failed one.
$Packages = @(
    "streamlit>=1.42",
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
function Update-PathFromRegistry {
    # A console keeps the PATH it was born with, so a Python installed a minute
    # ago is invisible until a new window is opened. The authoritative value
    # lives in the registry, and reading it back removes that whole class of
    # "но я же только что поставил".
    try {
        $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $user = [Environment]::GetEnvironmentVariable("Path", "User")
        $merged = @($machine, $user) | Where-Object { $_ }
        if ($merged) {
            $env:PATH = ($merged -join ";")
        }
    } catch {
        # Not fatal: the search below also looks at fixed locations.
    }
}

function Get-GitCommand {
    # Git for Windows can be installed with PATH integration switched off, which
    # leaves a perfectly good git.exe that no command finds. Same treatment as
    # Python: reload PATH, then look where the installer actually puts things.
    Update-PathFromRegistry

    $onPath = Get-Command git -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }

    $roots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA, "C:\Program Files") |
             Where-Object { $_ }
    foreach ($root in $roots) {
        foreach ($tail in @("Git\cmd\git.exe", "Programs\Git\cmd\git.exe")) {
            $path = Join-Path $root $tail
            if (Test-Path $path) { return $path }
        }
    }
    return $null
}

function Get-ProjectZip {
    <#
        Fetch the branch as a zip and unpack it into $Target.

        GitHub names the top folder after the repo and the branch, with slashes
        turned into dashes, so the archive is unpacked to a temporary place and
        the single directory inside it is moved into position.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$BranchName
    )

    $url = "https://github.com/Batmanchik/Vertex/archive/refs/heads/$BranchName.zip"
    $temp = Join-Path $env:TEMP ("vertex-" + [Guid]::NewGuid().ToString("N"))
    $zip = "$temp.zip"

    Write-Host "скачиваю архив ветки $BranchName"
    try {
        # Progress rendering makes Invoke-WebRequest crawl on large files.
        $previous = $ProgressPreference
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        $ProgressPreference = $previous
    } catch {
        Write-Fail "не удалось скачать архив: $($_.Exception.Message)"
        return $false
    }

    try {
        Expand-Archive -Path $zip -DestinationPath $temp -Force
    } catch {
        Write-Fail "архив скачался, но не распаковался: $($_.Exception.Message)"
        return $false
    }

    $inner = Get-ChildItem -Path $temp -Directory | Select-Object -First 1
    if (-not $inner) {
        Write-Fail "в архиве нет папки проекта."
        return $false
    }

    if (Test-Path $Target) {
        # Обновление поверх: файлы проекта перезаписываются, .venv и artifacts,
        # которых нет в архиве, остаются на месте.
        Copy-Item -Path (Join-Path $inner.FullName "*") -Destination $Target -Recurse -Force
    } else {
        Move-Item -Path $inner.FullName -Destination $Target
    }

    Remove-Item $zip, $temp -Recurse -Force -ErrorAction SilentlyContinue
    return $true
}

function Get-PythonCandidates {
    $candidates = @(
        @{ File = "py";          Args = @("-3.13") },
        @{ File = "py";          Args = @("-3.12") },
        @{ File = "py";          Args = @("-3.11") },
        @{ File = "py";          Args = @("-3") },
        @{ File = "python";      Args = @() },
        @{ File = "python3";     Args = @() },
        @{ File = "python3.13";  Args = @() },
        @{ File = "python3.12";  Args = @() },
        @{ File = "python3.11";  Args = @() }
    )

    # Store Python lands in WindowsApps as python3.12.exe and friends. The bare
    # python.exe next to them can be the stub that opens the Store instead of
    # running anything, so the versioned names are tried first.
    $windowsApps = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"
    if (Test-Path $windowsApps) {
        $apps = Get-ChildItem -Path $windowsApps -Filter "python3*.exe" -File -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending
        foreach ($app in $apps) {
            $candidates += @{ File = $app.FullName; Args = @() }
        }
    }

    # The real Store package, in case the alias is switched off in Settings.
    $storeRoot = if ($env:ProgramW6432) {
        Join-Path $env:ProgramW6432 "WindowsApps"
    } else {
        "C:\Program Files\WindowsApps"
    }
    if (Test-Path $storeRoot) {
        $packages = Get-ChildItem -Path $storeRoot -Filter "PythonSoftwareFoundation.Python.3*" `
                        -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        foreach ($package in $packages) {
            $exe = Join-Path $package.FullName "python.exe"
            if (Test-Path $exe) { $candidates += @{ File = $exe; Args = @() } }
        }
    }

    # An installer run without "Add to PATH" leaves a working interpreter that
    # none of the names above reach. Newest version first.
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
            if (Test-Path $exe) { $candidates += @{ File = $exe; Args = @() } }
        }
    }

    return $candidates
}

function Get-PythonCommand {
    param([switch]$Explain)

    Update-PathFromRegistry
    $tried = @()

    foreach ($candidate in Get-PythonCandidates) {
        $shown = (@($candidate.File) + $candidate.Args) -join " "
        try {
            $output = & $candidate.File @($candidate.Args + @("--version")) 2>&1
        } catch {
            $tried += "$shown -> нет такой команды"
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
            $tried += "$shown -> $text, слишком старый"
        } else {
            $short = ($text -split "`n")[0]
            if (-not $short) { $short = "молчит, похоже на заглушку Microsoft Store" }
            $tried += "$shown -> $short"
        }
    }

    if ($Explain) {
        Write-Host ""
        Write-Host "Что я пробовал:" -ForegroundColor Yellow
        foreach ($line in $tried) { Write-Host "  $line" }
    }
    return $null
}

# ---------------------------------------------------------------- checks
Write-Step "Проверяю, что установлено"

$git = Get-GitCommand
if ($git) {
    Write-Host "git: $((& $git --version) -join '')"
} else {
    # Not fatal. GitHub serves the branch as a zip, and Expand-Archive is built
    # into PowerShell, so the project can be fetched without git at all.
    Write-Host "git не найден, возьму архивом с GitHub." -ForegroundColor Yellow
}

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
            if ($LASTEXITCODE -ne 0) {
                # A broken winget source (0x8a15000f and friends) is common and
                # has nothing to do with this project. Say so instead of
                # reporting a success that did not happen.
                Write-Host ""
                Write-Host "winget не справился, код $LASTEXITCODE." -ForegroundColor Yellow
                Write-Host "Иногда чинится командой:  winget source reset --force"
                Write-Host "Ниже способы поставить Python без winget."
            } else {
                # winget puts Python on PATH for new processes only, so the
                # search relies on the install directories, not on PATH.
                $python = Get-PythonCommand
            }
        }
    }
}

if (-not $python) {
    # Second pass, this time printing every candidate and what it answered.
    $python = Get-PythonCommand -Explain
}

if (-not $python) {
    Write-Fail "не найден Python 3.10 или новее."
    Write-Host ""
    Write-Host "Если Python из Microsoft Store уже стоит, проверьте псевдонимы:"
    Write-Host "  Параметры -> Приложения -> Дополнительные параметры приложений ->"
    Write-Host "  Псевдонимы выполнения приложения. Переключатели python.exe и"
    Write-Host "  python3.exe должны быть включены." -ForegroundColor White
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
$alreadyHere = (Test-Path $pyprojectHere) -and
               ((Get-Content $pyprojectHere -Raw) -match 'name\s*=\s*"apris"')

if ($alreadyHere) {
    # Уже стоим внутри проекта: ничего не скачиваем.
    $Path = (Get-Location).Path
    Write-Host "уже в папке проекта: $Path"
} elseif ($git -and -not (Test-Path (Join-Path $Path "pyproject.toml"))) {
    Write-Host "скачиваю в $Path"
    & $git clone $RepoUrl $Path
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "не удалось скачать проект. Проверьте интернет и попробуйте ещё раз."
        return
    }
} elseif (Test-Path (Join-Path $Path ".git")) {
    Write-Host "проект уже есть: $Path"
} else {
    # Папка есть, но без истории git: её положил сюда прошлый запуск архивом,
    # и обновлять её надо тем же способом, а не клоном поверх непустой папки.
    if (-not (Get-ProjectZip -Target $Path -BranchName $Branch)) { return }
    Write-Host "проект в $Path"
}

Set-Location $Path

if ($git -and (Test-Path (Join-Path $Path ".git"))) {
    & $git fetch origin $Branch 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        & $git checkout $Branch 2>$null | Out-Null
        & $git pull origin $Branch 2>$null | Out-Null
        Write-Host "ветка: $Branch"
    } else {
        Write-Host "ветки $Branch нет на сервере, остаюсь на текущей" -ForegroundColor Yellow
    }
} elseif (-not $alreadyHere) {
    Write-Host "ветка: $Branch (архивом, без истории)"
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
    Write-Host "Установка закончена. Запуск:"
    Write-Host "  .venv\Scripts\python.exe -m streamlit run app.py --server.port $Port"
    return
}

# ---------------------------------------------------------------- старт
Write-Step "Запускаю интерфейс на порту $Port"

$healthUrl = "http://127.0.0.1:$Port/_stcore/health"
$pageUrl = "http://127.0.0.1:$Port/"

if (Test-HttpOk -Url $healthUrl) {
    Write-Host "на этом порту уже что-то работает, открываю страницу"
} else {
    Start-Process -FilePath $VenvPython `
        -ArgumentList @("-m", "streamlit", "run", "app.py",
                        "--server.address", "127.0.0.1", "--server.port", "$Port",
                        "--server.headless", "true") `
        -WorkingDirectory $Path | Out-Null

    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        if (Test-HttpOk -Url $healthUrl) { $ready = $true; break }
    }
    if (-not $ready) {
        Write-Fail "интерфейс запустился, но не отвечает. Посмотрите на второе окно, которое открылось."
        return
    }
}

# API нужен только для запросов к /api/..., сама витрина без него работает.
if ($WithApi) {
    Write-Step "Запускаю API на порту 8000"
    if (-not (Test-HttpOk -Url "http://127.0.0.1:8000/api/v1/health")) {
        Start-Process -FilePath $VenvPython `
            -ArgumentList @("-m", "uvicorn", "apris.api.main:app",
                            "--host", "127.0.0.1", "--port", "8000") `
            -WorkingDirectory $Path | Out-Null
        for ($i = 0; $i -lt 40; $i++) {
            Start-Sleep -Seconds 1
            if (Test-HttpOk -Url "http://127.0.0.1:8000/api/v1/health") { break }
        }
    }
}

Start-Process $pageUrl | Out-Null

Write-Host ""
Write-Host "Готово." -ForegroundColor Green
Write-Host "  Адрес:          $pageUrl" -ForegroundColor White
Write-Host "  Папка проекта:  $Path"
if ($WithApi) { Write-Host "  API:            http://127.0.0.1:8000/" }
Write-Host ""
Write-Host "Всё на одном адресе: витрина измерений — первая страница в меню слева."
Write-Host "Сервер работает во втором окне. Чтобы остановить, закройте его или нажмите там Ctrl+C."
Write-Host "Порядок показа на защите: docs\DEFENCE.md"
