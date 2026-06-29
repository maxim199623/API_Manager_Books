import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api_manager_books.api.dependencies import get_user_service
from api_manager_books.api.security.utils import require_admin, require_auth
from api_manager_books.application.services.user_service import (
    CannotDemoteLastAdminError,
    CannotRemoveLastAdminError,
    FirstUserMustBeAdminError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UserAlreadyExistsError,
    UserNotFoundInServiceError,
    UserService,
    UserUpdateFailedError,
)
from api_manager_books.schemas.api import AuthRequest, RefreshTokenRequest, TokenResponse
from api_manager_books.schemas.users import UserCreate, UserRead, UserUpdate
from api_manager_books.security.auth_throttle import TooManyAuthAttemptsError

router = APIRouter(prefix="/users", tags=["users"])


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


@router.delete("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: UserRead = Depends(require_auth),
    user_service: UserService = Depends(get_user_service),
):
    """Завершает текущую сессию пользователя."""
    await user_service.logout(current_user.id)
    return


@router.post("/auth", response_model=TokenResponse)
async def login(
    payload: AuthRequest,
    request: Request,
    user_service: UserService = Depends(get_user_service),
):
    """
    Авторизация пользователя.
    """
    try:
        token = await user_service.login(payload.email, payload.password, client_ip=_client_ip(request))
    except TooManyAuthAttemptsError as err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts",
        ) from err
    except InvalidCredentialsError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from err
    return TokenResponse(
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        token_type=token.token_type,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshTokenRequest,
    request: Request,
    user_service: UserService = Depends(get_user_service),
):
    """Обновляет пару access/refresh токенов."""
    try:
        token = await user_service.refresh(payload.refresh_token, client_ip=_client_ip(request))
    except TooManyAuthAttemptsError as err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts",
        ) from err
    except InvalidRefreshTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from err
    return TokenResponse(
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        token_type=token.token_type,
    )


@router.get("/me", response_model=UserRead)
async def me(current_user: UserRead = Depends(require_auth)):
    """Возвращает текущего пользователя из БД."""
    return current_user

@router.post("/add_user", status_code=status.HTTP_201_CREATED)
async def add_user(
    payload: UserCreate,
    user_service: UserService = Depends(get_user_service),
    current_user: UserRead = Depends(require_admin),
):
    """Добавления пользователя"""
    try:
        return await user_service.add_user(payload, current_user)
    except UserAlreadyExistsError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        ) from err
    except FirstUserMustBeAdminError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="First user must be an admin",
        ) from err

@router.get("/get_users", response_model=list[UserRead])
async def get_users(
    user_service: UserService = Depends(get_user_service),
    current_user: UserRead = Depends(require_admin),
):
    """Получение списка пользователей"""
    return await user_service.list_users()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def dell_users(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
    current_user: UserRead = Depends(require_admin),
):
    """Удаление пользователя"""
    try:
        deleted = await user_service.delete_user(user_id, current_user)
    except UserNotFoundInServiceError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from err
    except CannotRemoveLastAdminError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove the last admin",
        ) from err

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return

@router.patch("/{user_id}", status_code=status.HTTP_200_OK)
async def patch_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    user_service: UserService = Depends(get_user_service),
    current_user: UserRead = Depends(require_admin),
):
    """Обновление пользователя"""
    try:
        await user_service.update_user(user_id, payload, current_user)
    except UserNotFoundInServiceError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from err
    except UserUpdateFailedError as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User not update",
        ) from err
    except CannotDemoteLastAdminError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot demote the last admin",
        ) from err

    return
