
from fastapi import APIRouter, Depends, HTTPException, status, Request

from src.DB.Repository.UserRepository.Shems import UserRead
from src.api.dependencies import get_settings_service
from src.api.Shems import SettingsResponse, SettingsUpdate
from src.api.security.utils import require_admin
from src.application.services.settings_service import SettingsMigrationError, SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/", response_model=SettingsResponse)
async def get_current_settings(
    settings_service: SettingsService = Depends(get_settings_service),
    current_user: UserRead = Depends(require_admin)
):
    """
    Получить текущие настройки приложения (backend, echo, пути и пр.).
    """
    return settings_service.get_current_settings()

@router.patch("/", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdate,
    request: Request,
    settings_service: SettingsService = Depends(get_settings_service),
    current_user = Depends(require_admin),
):
    try:
        result = await settings_service.update_settings(
            payload,
            request.app.state.db_manager,
        )
    except SettingsMigrationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database migration failed: {e}",
        ) from e

    request.app.state.db_manager = result.new_db_manager
    return result.response
