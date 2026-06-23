
from fastapi import APIRouter, Depends, HTTPException, status, Request

from src.DB.Manager.manager import AsyncDBManager
from src.DB.Repository.UserRepository.Shems import UserRead
from src.DB.base import Base
from src.api.dependencies import get_settings_manager
from src.api.Shems import SettingsResponse, SettingsUpdate
from src.api.security.utils import require_admin
from src.core.config import SettingsManager

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/", response_model=SettingsResponse)
async def get_current_settings(
    settings_manager: SettingsManager = Depends(get_settings_manager),
    current_user: UserRead = Depends(require_admin)
):
    """
    Получить текущие настройки приложения (backend, echo, пути и пр.).
    """
    db = settings_manager.settings.database # или settings_manager.settings.database, как у тебя

    return SettingsResponse(
        backend=db.backend,
        echo=db.echo,
        sqlite_path=db.sqlite.path if db.backend == "sqlite" else None,
        postgres_host=db.postgres.host if db.backend == "postgres" else db.postgres.host,
        postgres_port=db.postgres.port if db.backend == "postgres" else db.postgres.port,
        postgres_user=db.postgres.user if db.backend == "postgres" else db.postgres.user,
        postgres_name=db.postgres.name if db.backend == "postgres" else db.postgres.name,
    )

@router.patch("/", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdate,
    request: Request,
    settings_manager: SettingsManager = Depends(get_settings_manager),
    current_user = Depends(require_admin),
):
    old_backend = settings_manager.db.backend
    old_db_manager: AsyncDBManager = request.app.state.db_manager

    # применяем изменения к settings_manager
    if payload.backend is not None:
        settings_manager.set_backend(payload.backend)
    if payload.echo is not None:
        settings_manager.set_echo(payload.echo)
    if payload.sqlite_path is not None:
        settings_manager.set_sqlite_path(payload.sqlite_path)
    if (
        payload.postgres_host is not None
        or payload.postgres_port is not None
        or payload.postgres_user is not None
        or payload.postgres_password is not None
        or payload.postgres_name is not None
    ):
        settings_manager.set_postgres(
            host=payload.postgres_host,
            port=payload.postgres_port,
            user=payload.postgres_user,
            password=payload.postgres_password,
            name=payload.postgres_name,
        )

    new_backend = settings_manager.db.backend

    # создаём новый менеджер с обновлёнными настройками
    new_db_manager = AsyncDBManager(settings_manager.db, Base)
    await new_db_manager.create_schema()

    # если backend поменялся — мигрируем данные
    if old_backend != new_backend:
        try:
            await old_db_manager.migrate_to(new_db_manager)
        except Exception as e:
            await new_db_manager.dispose()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database migration failed: {e}",
            )

    # переключаемся на новый менеджер, старый закрываем
    await old_db_manager.dispose()
    request.app.state.db_manager = new_db_manager

    # сохраняем настройки в config.ini
    settings_manager.save()

    # возвращаем актуальные настройки
    db = settings_manager.db
    sqlite_cfg = settings_manager.sqlite
    pg = settings_manager.postgres

    return SettingsResponse(
        backend=db.backend,
        echo=db.echo,
        sqlite_path=sqlite_cfg.path if sqlite_cfg is not None else None,
        postgres_host=pg.host if pg is not None else None,
        postgres_port=pg.port if pg is not None else None,
        postgres_user=pg.user if pg is not None else None,
        postgres_name=pg.name if pg is not None else None,
    )
