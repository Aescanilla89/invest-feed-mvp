# Migra la BD de Neon (o cualquier Postgres) a Supabase sin tocar el código.
#
# El backend usa SQLAlchemy + psycopg2 con una URL estándar postgresql://,
# así que la migración es solo de datos: pg_dump de origen -> psql a destino.
#
# Uso:
#   .\migrate_to_supabase.ps1 -NeonUrl "postgresql://..." -SupabaseUrl "postgresql://..."
#   # o por variables de entorno NEON_DATABASE_URL / SUPABASE_DATABASE_URL
#   # o sin argumentos: te los pide por consola.
#
# Requisitos: pg_dump y psql en el PATH (PostgreSQL instalado; p.ej. choco install postgresql).
#
# Importante: importar a una BD de Supabase VACÍA. El backend ejecuta init_db()
# en el arranque (create_all + ALTER TABLE IF NOT EXISTS), así que si apuntas el
# backend a Supabase ANTES de importar, las tablas se autocrean y el CREATE TABLE
# del dump fallará. Orden correcto: importar primero, luego cambiar DATABASE_URL.

param(
    [string]$NeonUrl = $env:NEON_DATABASE_URL,
    [string]$SupabaseUrl = $env:SUPABASE_DATABASE_URL
)

$ErrorActionPreference = "Stop"

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Normalize-Url([string]$Url) {
    # Railway/Neon a veces entregan postgres:// (legacy); psql acepta ambos,
    # pero normalizamos a postgresql:// para consistencia con config.py.
    return $Url -replace '^postgres://', 'postgresql://'
}

if (-not $NeonUrl) { $NeonUrl = Read-Host "URL de origen (Neon)" }
if (-not $SupabaseUrl) { $SupabaseUrl = Read-Host "URL de destino (Supabase, pooler puerto 5432)" }

$NeonUrl = Normalize-Url $NeonUrl
$SupabaseUrl = Normalize-Url $SupabaseUrl

foreach ($cmd in @("pg_dump", "psql")) {
    if (-not (Test-Command $cmd)) {
        Write-Host "Falta '$cmd'. Instala PostgreSQL (choco install postgresql) y añade su carpeta bin al PATH." -ForegroundColor Red
        exit 1
    }
}

$Backup = Join-Path $PWD "backup.sql"

Write-Host "1/2 Exportando datos de origen a '$Backup'..."
& pg_dump --no-owner --no-privileges $NeonUrl -f $Backup
if ($LASTEXITCODE -ne 0) { Write-Host "pg_dump falló (código $LASTEXITCODE)." -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "2/2 Importando en Supabase..."
& psql -v ON_ERROR_STOP=1 $SupabaseUrl -f $Backup
if ($LASTEXITCODE -ne 0) { Write-Host "psql falló (código $LASTEXITCODE)." -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "Migración completa. Actualiza DATABASE_URL en Railway y en los secrets de GitHub Actions." -ForegroundColor Green
