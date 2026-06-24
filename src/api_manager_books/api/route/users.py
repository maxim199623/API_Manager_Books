import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from api_manager_books.schemas.api import AuthRequest, TokenResponse
from api_manager_books.schemas.users import UserCreate, UserRead, UserUpdate
from api_manager_books.api.dependencies import get_user_service
from api_manager_books.api.security.utils import require_admin, require_auth
from api_manager_books.application.services.user_service import (
    FirstUserMustBeAdminError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserNotFoundInServiceError,
    UserService,
    UserUpdateFailedError,
)

router = APIRouter(prefix="/users", tags=["users"])

@router.delete("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: UserRead = Depends(require_auth),
    user_service: UserService = Depends(get_user_service),
):
    await user_service.logout(current_user.id)
    return


@router.post("/auth", response_model=TokenResponse)
async def login(
    payload: AuthRequest,
    user_service: UserService = Depends(get_user_service),
):
    """
    Авторизация пользователя.
    """
    try:
        token = await user_service.login(payload.email, payload.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return TokenResponse(access_token=token)

@router.post("/add_user", status_code=status.HTTP_201_CREATED)
async def add_user(
    payload: UserCreate,
    user_service: UserService = Depends(get_user_service),
    current_user: UserRead = Depends(require_admin),
):
    """Добавления пользователя"""
    try:
        return await user_service.add_user(payload, current_user)
    except UserAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        )
    except FirstUserMustBeAdminError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="First user must be an admin",
        )

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
    deleted = await user_service.delete_user(user_id, current_user)
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
    except UserNotFoundInServiceError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except UserUpdateFailedError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User not update",
        )

    return
