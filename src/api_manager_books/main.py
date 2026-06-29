import os
from collections.abc import Mapping
from dataclasses import dataclass
from ipaddress import IPv4Address

import uvicorn

from api_manager_books.api.api import app
from api_manager_books.api.security.utils import ensure_self_signed_cert, is_local_bind_host


class ServerConfigError(RuntimeError):
    """Некорректная TLS/серверная конфигурация."""


@dataclass(frozen=True)
class ServerConfig:
    """Настройки запуска API-сервера."""

    host: str
    port: int
    ssl_certfile: str
    ssl_keyfile: str
    generate_self_signed: bool


def build_server_config(env: Mapping[str, str]) -> ServerConfig:
    """Собирает и проверяет конфигурацию запуска сервера."""
    app_env = env.get("APP_ENV", "dev").strip().lower()
    host = env.get("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(env.get("APP_PORT", "1408"))
    cert_file = env.get("TLS_CERT_FILE", "").strip()
    key_file = env.get("TLS_KEY_FILE", "").strip()
    has_explicit_tls = bool(cert_file and key_file)

    if has_explicit_tls:
        return ServerConfig(
            host=host,
            port=port,
            ssl_certfile=cert_file,
            ssl_keyfile=key_file,
            generate_self_signed=False,
        )

    if app_env == "prod":
        raise ServerConfigError("TLS_CERT_FILE and TLS_KEY_FILE are required in prod")

    if not is_local_bind_host(host):
        raise ServerConfigError("Explicit TLS files are required for non-local bind")

    return ServerConfig(
        host=host,
        port=port,
        ssl_certfile="cert.pem",
        ssl_keyfile="key.pem",
        generate_self_signed=True,
    )


def main():
    """Запускает API-сервер с TLS."""
    config = build_server_config(os.environ)
    cert_file = config.ssl_certfile
    key_file = config.ssl_keyfile
    if config.generate_self_signed:
        cert_file, key_file = ensure_self_signed_cert(
            cert_file,
            key_file,
            common_name="localhost",
            ip_address=IPv4Address("127.0.0.1"),
        )

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        reload=False,
        ssl_certfile=cert_file,
        ssl_keyfile=key_file,
    )


if __name__ == '__main__':
    main()


