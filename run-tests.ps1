# Quick Docker-based test runner for COD Commerce Platform
# Usage: .\run-tests.ps1

param(
    [switch]$help,
    [switch]$up,
    [switch]$down,
    [switch]$clean,
    [switch]$logs,
    [string]$test = "tests"  # Default test path
)

if ($help) {
    Write-Host "COD Commerce Platform - Docker Test Runner"
    Write-Host ""
    Write-Host "Usage: .\run-tests.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -up           Start Docker containers and run tests"
    Write-Host "  -down         Stop and remove Docker containers"
    Write-Host "  -clean        Remove containers and volumes (complete cleanup)"
    Write-Host "  -logs         Show Docker container logs"
    Write-Host "  -test PATH    Run specific test path (default: tests)"
    Write-Host "  -help         Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\run-tests.ps1 -up                          # Start Docker and run all tests"
    Write-Host "  .\run-tests.ps1 -test tests/core -up         # Start Docker and run core tests"
    Write-Host "  .\run-tests.ps1 -down                        # Stop Docker containers"
    Write-Host "  .\run-tests.ps1 -clean                       # Remove Docker containers and volumes"
    exit 0
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"

Write-Host "🐳 COD Commerce Platform - Docker Test Suite" -ForegroundColor Cyan
Write-Host ""

# Check if docker-compose exists
try {
    $dockerVersion = docker --version 2>&1
    Write-Host "✓ Docker found: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker not found. Please install Docker Desktop." -ForegroundColor Red
    exit 1
}

try {
    $composeVersion = docker-compose --version 2>&1
    Write-Host "✓ Docker Compose found: $composeVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker Compose not found. Please install Docker Desktop." -ForegroundColor Red
    exit 1
}

Write-Host ""

# Show logs command
if ($logs) {
    Write-Host "📋 Docker Container Logs" -ForegroundColor Yellow
    Write-Host ""
    docker-compose -f "$projectRoot/docker-compose.yml" logs -f
    exit 0
}

# Cleanup command
if ($clean) {
    Write-Host "🧹 Cleaning up Docker containers and volumes..." -ForegroundColor Yellow
    docker-compose -f "$projectRoot/docker-compose.yml" down -v
    Write-Host "✓ Cleanup complete" -ForegroundColor Green
    exit 0
}

# Down command
if ($down) {
    Write-Host "🛑 Stopping Docker containers..." -ForegroundColor Yellow
    docker-compose -f "$projectRoot/docker-compose.yml" down
    Write-Host "✓ Containers stopped" -ForegroundColor Green
    exit 0
}

# Up and test command
if ($up) {
    Write-Host "⬆️  Starting Docker containers..." -ForegroundColor Yellow
    docker-compose -f "$projectRoot/docker-compose.yml" up -d

    # Wait for services to be ready
    Write-Host "⏳ Waiting for PostgreSQL to be ready..." -ForegroundColor Yellow
    $attempts = 0
    $maxAttempts = 30
    while ($attempts -lt $maxAttempts) {
        try {
            $result = docker-compose -f "$projectRoot/docker-compose.yml" exec -T postgres pg_isready -U cod_user -d cod_platform_test 2>&1
            if ($result -match "accepting connections") {
                Write-Host "✓ PostgreSQL is ready" -ForegroundColor Green
                break
            }
        } catch {
            $attempts++
            if ($attempts -lt $maxAttempts) {
                Start-Sleep -Seconds 1
            }
        }
    }

    Write-Host "⏳ Waiting for Redis to be ready..." -ForegroundColor Yellow
    $attempts = 0
    while ($attempts -lt $maxAttempts) {
        try {
            $result = docker-compose -f "$projectRoot/docker-compose.yml" exec -T redis redis-cli ping 2>&1
            if ($result -match "PONG") {
                Write-Host "✓ Redis is ready" -ForegroundColor Green
                break
            }
        } catch {
            $attempts++
            if ($attempts -lt $maxAttempts) {
                Start-Sleep -Seconds 1
            }
        }
    }

    Write-Host ""
    Write-Host "🔧 Running Prisma migrations..." -ForegroundColor Yellow
    
    # Load environment variables from .env.test
    $envFile = Join-Path $backendDir ".env.test"
    if (Test-Path $envFile) {
        Get-Content $envFile | foreach {
            $line = $_
            if ($line -and -not $line.StartsWith("#")) {
                $parts = $line -split "=", 2
                if ($parts.Count -eq 2) {
                    $env:($parts[0].Trim()) = $parts[1].Trim()
                }
            }
        }
        Write-Host "✓ Loaded environment from .env.test" -ForegroundColor Green
    }

    # Run migrations
    Set-Location $projectRoot
    prisma migrate deploy 2>&1 | Out-Null
    Write-Host "✓ Migrations completed" -ForegroundColor Green

    Write-Host ""
    Write-Host "🧪 Running tests..." -ForegroundColor Yellow
    Write-Host ""

    # Change to backend directory and run tests
    Set-Location $backendDir
    python -m pytest $test -v

    $testExitCode = $LASTEXITCODE

    Write-Host ""
    Write-Host "📊 Test run complete" -ForegroundColor Cyan
    
    if ($testExitCode -eq 0) {
        Write-Host "✓ All tests passed!" -ForegroundColor Green
    } else {
        Write-Host "✗ Some tests failed (exit code: $testExitCode)" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "💡 Containers are still running. To stop them, run: .\run-tests.ps1 -down" -ForegroundColor Cyan
    
    Set-Location $projectRoot
    exit $testExitCode
}

# If no command specified, show help
if (-not $up -and -not $down -and -not $clean -and -not $logs) {
    Write-Host "No command specified. Use -up to start Docker and run tests." -ForegroundColor Yellow
    Write-Host "For help, run: .\run-tests.ps1 -help" -ForegroundColor Yellow
    exit 1
}
