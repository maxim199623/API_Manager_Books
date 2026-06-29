import pytest

from api_manager_books.main import ServerConfigError, build_server_config


def test_prod_requires_explicit_tls_cert_and_key():
    """Проверяет запрет prod без явных TLS-файлов."""
    with pytest.raises(ServerConfigError, match="TLS_CERT_FILE"):
        build_server_config({"APP_ENV": "prod"})


def test_dev_localhost_permits_generated_self_signed_cert():
    """Проверяет dev-запуск на loopback с generated cert."""
    config = build_server_config(
        {
            "APP_ENV": "dev",
            "APP_HOST": "127.0.0.1",
        }
    )

    assert config.host == "127.0.0.1"
    assert config.port == 1408
    assert config.generate_self_signed is True
    assert config.ssl_certfile == "cert.pem"
    assert config.ssl_keyfile == "key.pem"


def test_dev_network_bind_requires_explicit_tls_files():
    """Проверяет запрет generated cert на сетевом bind."""
    with pytest.raises(ServerConfigError, match="non-local"):
        build_server_config(
            {
                "APP_ENV": "dev",
                "APP_HOST": "0.0.0.0",
            }
        )


def test_explicit_tls_paths_are_passed_through_for_network_bind():
    """Проверяет явные TLS-файлы для сетевого bind."""
    config = build_server_config(
        {
            "APP_ENV": "dev",
            "APP_HOST": "0.0.0.0",
            "APP_PORT": "9443",
            "TLS_CERT_FILE": "/etc/app/fullchain.pem",
            "TLS_KEY_FILE": "/etc/app/privkey.pem",
        }
    )

    assert config.host == "0.0.0.0"
    assert config.port == 9443
    assert config.generate_self_signed is False
    assert config.ssl_certfile == "/etc/app/fullchain.pem"
    assert config.ssl_keyfile == "/etc/app/privkey.pem"
