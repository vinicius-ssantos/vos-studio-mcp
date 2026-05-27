param(
    [switch]$SkipDocker,
    [switch]$SkipMigrations,
    [switch]$NoWorker
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Celery = Join-Path $ProjectRoot ".venv\Scripts\celery.exe"
$LogsDir = Join-Path $ProjectRoot "logs"
$PostgresContainer = "vos-studio-mcp-postgres-15432"
$PostgresImage = "postgres:16-alpine"
$PostgresPort = "15432"
$RedisService = "redis"
$HealthUrl = "http://localhost:8000/health"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Command {
    param([string]$Name)
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Wait-Until {
    param(
        [scriptblock]$Condition,
        [int]$TimeoutSeconds,
        [string]$FailureMessage
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (& $Condition) {
            return
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    throw $FailureMessage
}

function Stop-ProjectProcesses {
    Write-Step "Stopping existing local API/worker processes"
    $escapedRoot = [regex]::Escape($ProjectRoot.Path)
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and (
                (
                    $_.CommandLine -match $escapedRoot -and (
                        $_.CommandLine -match "uvicorn vos_studio_mcp.server:app" -or
                        $_.CommandLine -match "vos_studio_mcp.tasks.celery_app"
                    )
                ) -or
                $_.CommandLine -match "\.venv\\Scripts\\python\.exe`"?\s+-m\s+uvicorn\s+vos_studio_mcp\.server:app" -or
                $_.CommandLine -match "\.venv\\Scripts\\celery\.exe`"?.*vos_studio_mcp\.tasks\.celery_app" -or
                $_.CommandLine -match "cmd\.exe.*set DATABASE_URL=.*vos_studio_mcp\.server:app"
            )
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }

    Start-Sleep -Seconds 1
}

function Ensure-Docker {
    if ($SkipDocker) {
        Write-Step "Skipping Docker startup"
        return
    }

    if (-not (Test-Command "docker")) {
        throw "Docker CLI not found. Install Docker Desktop or run with -SkipDocker if services are already running."
    }

    Write-Step "Checking Docker engine"
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
        if (Test-Path $dockerDesktop) {
            Write-Host "Starting Docker Desktop..."
            Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
        }
    }

    Wait-Until `
        -TimeoutSeconds 180 `
        -FailureMessage "Docker engine did not become ready within 180 seconds." `
        -Condition {
            docker info *> $null
            $LASTEXITCODE -eq 0
        }
}

function Ensure-Redis {
    if ($SkipDocker) {
        return
    }

    Write-Step "Starting Redis"
    Push-Location $ProjectRoot
    try {
        docker compose up -d $RedisService
    } finally {
        Pop-Location
    }

    Wait-Until `
        -TimeoutSeconds 60 `
        -FailureMessage "Redis did not become healthy within 60 seconds." `
        -Condition {
            docker exec vos-studio-mcp-redis-1 redis-cli ping 2>$null | Select-String -Quiet "PONG"
        }
}

function Ensure-Postgres {
    if ($SkipDocker) {
        return
    }

    Write-Step "Starting Postgres on localhost:$PostgresPort"
    $exists = docker ps -a --format "{{.Names}}" | Select-String -Quiet "^$PostgresContainer$"
    if ($exists) {
        docker start $PostgresContainer *> $null
    } else {
        docker run `
            -d `
            --name $PostgresContainer `
            -e POSTGRES_USER=postgres `
            -e POSTGRES_PASSWORD=password `
            -e POSTGRES_DB=postgres `
            -p "${PostgresPort}:5432" `
            $PostgresImage *> $null
    }

    Wait-Until `
        -TimeoutSeconds 60 `
        -FailureMessage "Postgres did not become ready within 60 seconds." `
        -Condition {
            docker exec $PostgresContainer pg_isready -U postgres *> $null
            $LASTEXITCODE -eq 0
        }
}

function Run-Migrations {
    if ($SkipMigrations) {
        Write-Step "Skipping migrations"
        return
    }

    Write-Step "Running Alembic migrations"
    Push-Location $ProjectRoot
    try {
        & $Python -m alembic upgrade head
    } finally {
        Pop-Location
    }
}

function Start-Api {
    Write-Step "Starting API on http://localhost:8000"
    $stdout = Join-Path $LogsDir "uvicorn.local.out.log"
    $stderr = Join-Path $LogsDir "uvicorn.local.err.log"
    Start-Process `
        -FilePath $Python `
        -ArgumentList @("-m", "uvicorn", "vos_studio_mcp.server:app", "--host", "0.0.0.0", "--port", "8000") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr
}

function Start-Worker {
    if ($NoWorker) {
        Write-Step "Skipping Celery worker"
        return
    }

    Write-Step "Starting Celery worker"
    $stdout = Join-Path $LogsDir "celery.local.out.log"
    $stderr = Join-Path $LogsDir "celery.local.err.log"
    Start-Process `
        -FilePath $Celery `
        -ArgumentList @("-A", "vos_studio_mcp.tasks.celery_app:celery_app", "worker", "--loglevel=info", "--pool=solo") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr
}

function Check-Health {
    Write-Step "Checking health"
    Wait-Until `
        -TimeoutSeconds 40 `
        -FailureMessage "API did not respond on $HealthUrl within 40 seconds." `
        -Condition {
            try {
                $response = Invoke-RestMethod $HealthUrl -TimeoutSec 5
                $script:LastHealth = $response
                $true
            } catch {
                $false
            }
        }

    $LastHealth | ConvertTo-Json -Depth 8
}

if (-not (Test-Path $Python)) {
    throw "Virtualenv Python not found at $Python. Create dependencies first with the project setup command."
}

if (-not (Test-Path $Celery)) {
    throw "Celery executable not found at $Celery. Install dev dependencies first."
}

if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    throw ".env not found. Copy .env.example to .env and configure local values first."
}

New-Item -ItemType Directory -Path $LogsDir -Force *> $null

Stop-ProjectProcesses
Ensure-Docker
Ensure-Redis
Ensure-Postgres
Run-Migrations
Start-Worker
Start-Api
Check-Health

Write-Host ""
Write-Host "Local VOS Studio MCP is running." -ForegroundColor Green
Write-Host "API:        http://localhost:8000"
Write-Host "Docs:       http://localhost:8000/docs"
Write-Host "MCP:        http://localhost:8000/mcp/"
Write-Host "Bearer:     local-dev-token"
Write-Host "API logs:   logs\uvicorn.local.err.log"
Write-Host "Worker logs: logs\celery.local.err.log"
