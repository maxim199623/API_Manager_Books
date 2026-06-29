#!/usr/bin/env sh
set -eu

cd "$(CDPATH= cd "$(dirname "$0")/.." && pwd)"

force=0
if [ "${1:-}" = "--force" ]; then
    force=1
fi

write_file() {
    path="$1"
    content="$2"

    if [ -f "$path" ] && [ "$force" -ne 1 ]; then
        echo "Skip existing $path. Use --force to overwrite."
        return
    fi

    printf "%s\n" "$content" > "$path"
    echo "Created $path."
}

write_file ".env.prod.local" "APP_ENV=prod
APP_HOST=
APP_PORT=1408
TLS_CERT_FILE=
TLS_KEY_FILE=
INITIAL_ADMIN_EMAIL=
INITIAL_ADMIN_PASSWORD="

write_file ".env.dev.local" "APP_ENV=dev
APP_HOST=127.0.0.1
APP_PORT=1408
INITIAL_ADMIN_EMAIL=
INITIAL_ADMIN_PASSWORD="

echo "Env templates contain placeholders only. Fill real values locally before production start."
