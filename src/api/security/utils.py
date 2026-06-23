import uuid

import jwt
from fastapi import Depends, HTTPException, status, WebSocket, WebSocketException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.DB.Repository import User
from src.schemas.enums import UserRole
from src.schemas.users import UserRead
from src.DB.Repository.UserRepository.user_repository import UserRepository
from src.api.dependencies import get_user_repo
from src.api.security.jwt_tokens import decode_access_token

from pathlib import Path
from datetime import datetime, timedelta, UTC

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from ipaddress import IPv4Address


security_bearer = HTTPBearer(auto_error=False)
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    user_repo: UserRepository = Depends(get_user_repo),
) -> User:
    """
    Извлечь текущего пользователя из JWT access token.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    user_id = payload.get("sub")
    token_sid = uuid.UUID(payload.get("sid"))
    if user_id is None or token_sid is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if user.session != token_sid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session replaced",
        )

    return user

async def get_current_user_from_ws(
    websocket: WebSocket,
    token: str = Query(..., alias="token"),
    user_repo: UserRepository = Depends(get_user_repo),
) -> User:
    """
    Версия get_current_user специально для WebSocket.
    Токен берётся из query-параметра ?token=...
    """
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        raise WebSocketException(code=1008)

    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
        token_sid = uuid.UUID(payload.get("sid"))
    except (jwt.PyJWTError, ValueError, KeyError) as e:
        await websocket.close(code=1008, reason="Invalid token")
        raise WebSocketException(code=1008) from e

    user = await user_repo.get_by_id(user_id)
    if user is None:
        await websocket.close(code=1008, reason="User not found")
        raise WebSocketException(code=1008)

    if getattr(user, 'session', None) != token_sid:   # или current_session_id
        await websocket.close(code=4001, reason="Session replaced")
        raise WebSocketException(code=4001, reason="Session replaced")

    return user

async def require_auth(current_user: UserRead = Depends(get_current_user)) -> UserRead:
    """Проверка на авторизацию"""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return current_user


async def require_admin(current_user: UserRead = Depends(get_current_user)) -> UserRead:
    """Проверка на admin"""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user



def ensure_self_signed_cert(
    cert_path: str | Path = "cert.pem",
    key_path: str | Path = "key.pem",
    common_name: str = "localhost",
    ip_address: IPv4Address = IPv4Address("127.0.0.1"),
    days_valid: int = 365,
) -> tuple[str, str]:
    """
    Проверяет наличие cert.pem / key.pem.
    Если их нет — генерирует самоподписанный сертификат и приватный ключ (RSA 2048).
    Возвращает пути к файлам (str).
    """
    cert_path = Path(cert_path)
    key_path = Path(key_path)

    if cert_path.exists() and key_path.exists():
        # Уже есть — ничего не делаем
        return str(cert_path), str(key_path)

    # Генерируем приватный ключ
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Сохраняем приватный ключ в PEM
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),  # без пароля
    )
    key_path.write_bytes(key_pem)

    # Формируем subject/issuer (для self-signed они одинаковые)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Local Dev"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )

    now = datetime.now(UTC)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=days_valid))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(common_name),
                 x509.IPAddress(ip_address)]

            ),
            critical=False,
        )
        .sign(private_key=key, algorithm=hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    cert_path.write_bytes(cert_pem)

    return str(cert_path), str(key_path)
