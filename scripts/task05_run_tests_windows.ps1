$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repoRoot ".env.test"

if (-not (Test-Path $envFile)) {
    throw "No se encontró .env.test en la raíz del proyecto."
}

Push-Location $repoRoot
$previousEnvFile = $env:ENV_FILE

try {
    # Hace que Settings cargue .env.test en lugar de .env.
    $env:ENV_FILE = ".env.test"

    Write-Host "Aplicando migraciones sobre la base de testing..."
    python -m alembic upgrade head

    Write-Host "Ejecutando tests de la Task 05..."
    python -m pytest -v -s
}
finally {
    if ($null -eq $previousEnvFile) {
        Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue
    }
    else {
        $env:ENV_FILE = $previousEnvFile
    }

    Pop-Location
}
