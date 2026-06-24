from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_DIR = Path(__file__).resolve().parent
PRIVATE_KEY_PATH = KEY_DIR / "jwt_private.pem"
PUBLIC_KEY_PATH = KEY_DIR / "jwt_public.pem"

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
    KEY_DIR.mkdir(parents=True, exist_ok=True)

    if not PRIVATE_KEY_PATH.exists() or not PUBLIC_KEY_PATH.exists():
        private_pem, public_pem = _generate_rsa_key_pair()

        PRIVATE_KEY_PATH.write_bytes(private_pem)
        PUBLIC_KEY_PATH.write_bytes(public_pem)
    else:
        private_pem = PRIVATE_KEY_PATH.read_bytes()
        public_pem = PUBLIC_KEY_PATH.read_bytes()

    return private_pem, public_pem
