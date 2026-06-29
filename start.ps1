$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
    Write-Error "Poetry is not installed or not available in PATH."
    exit 1
}

function Import-EnvFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) {
            continue
        }

        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = ""
        if ($parts.Count -eq 2) {
            $value = $parts[1]
        }

        if ($name -ne "" -and $value -ne "") {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

$envNames = @(
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "TLS_CERT_FILE",
    "TLS_KEY_FILE",
    "INITIAL_ADMIN_EMAIL",
    "INITIAL_ADMIN_PASSWORD"
)
$previousEnv = @{}
foreach ($name in $envNames) {
    $previousEnv[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

$exitCode = 0
try {
    Import-EnvFile -Path ".env.prod.local"

    if ($env:APP_ENV -ne "prod") {
        throw "APP_ENV must be set to prod."
    }

    if ([string]::IsNullOrWhiteSpace($env:TLS_CERT_FILE)) {
        throw "TLS_CERT_FILE is required for production start."
    }

    if ([string]::IsNullOrWhiteSpace($env:TLS_KEY_FILE)) {
        throw "TLS_KEY_FILE is required for production start."
    }

    poetry install --only main
    if ($LASTEXITCODE -ne 0) {
        $exitCode = $LASTEXITCODE
    }
    else {
        poetry run api-manager-books
        $exitCode = $LASTEXITCODE
    }
}
catch {
    Write-Error $_
    $exitCode = 1
}
finally {
    foreach ($name in $envNames) {
        [Environment]::SetEnvironmentVariable($name, $previousEnv[$name], "Process")
    }
}

exit $exitCode
