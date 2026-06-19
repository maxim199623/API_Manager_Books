import uuid
from email import message

from fastapi import APIRouter, Depends, HTTPException, status
from src.DB.Repository.UserRepository.Enums import UserRole
from src.DB.Repository.LogRepository.Shems import LogCreate
from src.DB.Repository.UserRepository.user_repository import UserRepository
from src.DB.Repository.LogRepository.log_repository import LogRepository

from src.api.Shems import AuthRequest, TokenResponse
from src.DB.Repository.UserRepository.Shems import UserCreate, UserRead, UserUpdate
from src.api.Dependencices import get_user_repo, get_log_repo
from src.api.security.jwt_tokens import create_access_token
from src.security.passwords import verify_password
from src.api.security.utils import require_admin, require_auth
from src.api.websocket import manager as ws_manager

router = APIRouter(prefix="/users", tags=["users"])

@router.delete("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: UserRead = Depends(require_auth),
    user_repo: UserRepository = Depends(get_user_repo),
):
    await user_repo.set_session_id(current_user.id, None)
    return


@router.post("/auth", response_model=TokenResponse)
async def login(payload: AuthRequest, user_repo: UserRepository = Depends(get_user_repo),
                log_repo: LogRepository = Depends(get_log_repo)):
        """
        Авторизация пользователя.
        """
        user = await user_repo.get_by_email(payload.email)
        # если нет пользователя или хеши не совпали — 401
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if user.session is not None:
            await ws_manager.send_to_user(user.id, {"type":"re_login", "message":"Сессия закрыта"})

        session = uuid.uuid4()
        await user_repo.set_session_id(user.id, session)
        token = create_access_token(
                {
                    "sub": str(user.id),
                    "sid": str(session),
                    "role": user.role,
                }
            )

            # успешный логин — пишем лог
        await log_repo.log_from_dto(
            LogCreate(
                    user_id=user.id,
                    action="login",
                    entity="users",
                    entity_id=user.id,
                    details="Пользователь успешно авторизовался",
                )
            )
        return TokenResponse(access_token=token)

@router.post("/add_user", status_code=status.HTTP_201_CREATED)
async def add_user(payload: UserCreate, user_repo: UserRepository = Depends(get_user_repo),
                log_repo: LogRepository = Depends(get_log_repo), current_user: UserRead = Depends(require_admin)):
    """Добавления пользователя"""

    existing = await user_repo.get_by_email(payload.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        )

    def_user = await user_repo.get_by_email("default@default.ru")
    if def_user is not None and payload.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="First user must be an admin",
        )

    new_user = await user_repo.create_user(UserCreate(
            email=payload.email,
            password=payload.password,
            role=payload.role))

    await log_repo.log_from_dto(
            LogCreate(
                user_id=current_user.id,
                action="add_user",
                entity="users",
                entity_id=new_user.id,
                details=f"Добавлен пользователь {payload.email}",
            )
        )

    if def_user is not None and payload.role == UserRole.ADMIN:
        await ws_manager.send_to_user(def_user.id, {"type":"re_login", "message":"Сессия закрыта"})
        await user_repo.delete_user(def_user.id)


    return {"message": "User added", "id": new_user.id}

@router.get("/get_users", response_model=list[UserRead])
async def get_users(user_repo: UserRepository = Depends(get_user_repo), current_user: UserRead = Depends(require_admin)):
    """Получение списка пользователей"""
    users = await user_repo.list_users()
    return users


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def dell_users(user_id: uuid.UUID, user_repo: UserRepository = Depends(get_user_repo),
                log_repo: LogRepository = Depends(get_log_repo), current_user: UserRead = Depends(require_admin)):
    """Удаление пользователя"""

    await log_repo.log_action(
        user_id=current_user.id,
        action="delete",
        entity="users",
        entity_id=user_id,
        details="Пользователь удалён"
    )

    deleted = await user_repo.delete_user(user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return

@router.patch("/{user_id}", status_code=status.HTTP_200_OK)
async def patch_user(user_id: uuid.UUID, payload: UserUpdate, user_repo: UserRepository = Depends(get_user_repo),
                log_repo: LogRepository = Depends(get_log_repo), current_user: UserRead = Depends(require_admin)):
    """Обновление пользователя"""
    if not await user_repo.ensure_exists(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    update_user = await user_repo.update_user(user_id=user_id,
                                        password=payload.password,
                                        role=payload.role,
                                        email=payload.email)
    if update_user is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User not update",
        )

    await log_repo.log_from_dto(
        LogCreate(
            user_id=current_user.id,
            action="update_user",
            entity="users",
            entity_id=update_user.id,
            details=f"Обновлен поля пользователь",
        )
    )

    return
