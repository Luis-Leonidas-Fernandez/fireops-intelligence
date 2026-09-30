$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$envTest = Join-Path $repoRoot ".env.test"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $envTest)) {
    throw "Falta .env.test en la raíz del proyecto."
}

if (-not (Test-Path $python)) {
    throw "Falta el entorno virtual .venv. Crealo e instalá las dependencias del proyecto."
}

Push-Location $repoRoot
try {
    $dbName = & $python -c "from pathlib import Path; from urllib.parse import urlsplit; line=next((x for x in Path('.env.test').read_text(encoding='utf-8').splitlines() if x.startswith('DATABASE_URL=')), ''); print(urlsplit(line.split('=', 1)[1]).path.lstrip('/') if line else '')"
    if ($LASTEXITCODE -ne 0 -or $dbName.Trim() -ne "fireassets_test") {
        throw "Por seguridad, .env.test debe apuntar a fireassets_test. No se inició el servidor."
    }

    $previousEnvFile = $env:ENV_FILE
    try {
        $env:ENV_FILE = ".env.test"
        Write-Host "Iniciando Fire Control con fireassets_test. Detené el servidor con Ctrl+C."
        & $python -m uvicorn app.main:app --reload
        if ($LASTEXITCODE -ne 0) {
            throw "Uvicorn terminó con código $LASTEXITCODE."
        }
    }
    finally {
        if ($null -eq $previousEnvFile) {
            Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue
        }
        else {
            $env:ENV_FILE = $previousEnvFile
        }
    }
}
finally {
    Pop-Location
}
