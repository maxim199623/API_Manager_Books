param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

$files = @{
    ".env.prod.local" = @"
APP_ENV=prod
APP_HOST=
APP_PORT=1408
TLS_CERT_FILE=
TLS_KEY_FILE=
INITIAL_ADMIN_EMAIL=
INITIAL_ADMIN_PASSWORD=
"@
    ".env.dev.local" = @"
APP_ENV=dev
APP_HOST=127.0.0.1
APP_PORT=1408
INITIAL_ADMIN_EMAIL=
INITIAL_ADMIN_PASSWORD=
"@
}

foreach ($entry in $files.GetEnumerator()) {
    if ((Test-Path -LiteralPath $entry.Key) -and -not $Force) {
        Write-Host "Skip existing $($entry.Key). Use -Force to overwrite."
        continue
    }

    Set-Content -LiteralPath $entry.Key -Value $entry.Value -Encoding ASCII
    Write-Host "Created $($entry.Key)."
}

Write-Host "Env templates contain placeholders only. Fill real values locally before production start."
