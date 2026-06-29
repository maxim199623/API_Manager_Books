from pathlib import Path

from api_manager_books.api.security.cert import jwt_keys


def test_jwt_key_dir_env_creates_keys_in_configured_directory(tmp_path, monkeypatch):
    """Проверяет создание JWT-ключей в директории из окружения."""
    key_dir = tmp_path / "jwt-keys"
    monkeypatch.setenv("JWT_KEY_DIR", str(key_dir))

    private_pem, public_pem = jwt_keys.ensure_jwt_keys()

    assert (key_dir / "jwt_private.pem").read_bytes() == private_pem
    assert (key_dir / "jwt_public.pem").read_bytes() == public_pem


def test_jwt_key_dir_fallback_creates_keys_under_var_security(tmp_path, monkeypatch):
    """Проверяет fallback-директорию JWT-ключей."""
    monkeypatch.delenv("JWT_KEY_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    private_pem, public_pem = jwt_keys.ensure_jwt_keys()
    key_dir = tmp_path / "var" / "security" / "jwt"

    assert (key_dir / "jwt_private.pem").read_bytes() == private_pem
    assert (key_dir / "jwt_public.pem").read_bytes() == public_pem


def test_jwt_key_dir_is_not_source_cert_directory(monkeypatch):
    """Проверяет, что runtime-директория не находится внутри package cert."""
    monkeypatch.delenv("JWT_KEY_DIR", raising=False)

    source_cert_dir = Path(jwt_keys.__file__).resolve().parent

    assert jwt_keys._jwt_key_dir().resolve() != source_cert_dir
