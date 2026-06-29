import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _jwt_key_dir() -> Path:
    """Вернуть runtime-директорию JWT-ключей."""
    return Path(os.environ.get("JWT_KEY_DIR", "var/security/jwt"))


def _private_key_path() -> Path:
    """Вернуть путь приватного JWT-ключа."""
    return _jwt_key_dir() / "jwt_private.pem"


def _public_key_path() -> Path:
    """Вернуть путь публичного JWT-ключа."""
    return _jwt_key_dir() / "jwt_public.pem"

def _generate_rsa_key_pair() -> tuple[bytes, bytes]:
    """
    Генерирует пару RSA-ключей и возвращает (private_pem, public_pem) в виде bytes.
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),  # без пароля
    )

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    return private_pem, public_pem


def ensure_jwt_keys() -> tuple[bytes, bytes]:
    """
    Проверяет наличие файлов с ключами.
    Если нет — создаёт директорию keys/ и генерирует новую пару ключей.
    Возвращает (private_pem, public_pem) как bytes.
    """
    key_dir = _jwt_key_dir()
    private_key_path = _private_key_path()
    public_key_path = _public_key_path()

    key_dir.mkdir(parents=True, exist_ok=True)

    if not private_key_path.exists() or not public_key_path.exists():
        private_pem, public_pem = _generate_rsa_key_pair()

        private_key_path.write_bytes(private_pem)
        try:
            private_key_path.chmod(0o600)
        except OSError:
            pass
        public_key_path.write_bytes(public_pem)
    else:
        private_pem = private_key_path.read_bytes()
        public_pem = public_key_path.read_bytes()

    return private_pem, public_pem
