#!/usr/bin/env sh
set -eu

cd "$(CDPATH= cd "$(dirname "$0")" && pwd)"

if ! command -v poetry >/dev/null 2>&1; then
    echo "Poetry is not installed or not available in PATH." >&2
    exit 1
fi

if [ -f ".env.prod.local" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ""|\#*) continue ;;
        esac

        name=${line%%=*}
        value=${line#*=}
        if [ "$name" != "$line" ] && [ -n "$name" ] && [ -n "$value" ]; then
            export "$name=$value"
        fi
    done < ".env.prod.local"
fi

if [ "${APP_ENV:-}" != "prod" ]; then
    echo "APP_ENV must be set to prod." >&2
    exit 1
fi

if [ -z "${TLS_CERT_FILE:-}" ]; then
    echo "TLS_CERT_FILE is required for production start." >&2
    exit 1
fi

if [ -z "${TLS_KEY_FILE:-}" ]; then
    echo "TLS_KEY_FILE is required for production start." >&2
    exit 1
fi

poetry install --only main
poetry run api-manager-books
