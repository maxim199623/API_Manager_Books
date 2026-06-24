from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from src.schemas.api import SettingsResponse, SettingsUpdate
from src.schemas.config import DatabaseSettings, PostgresSettings, SQLiteSettings
from src.core.config import AppSettings


class DBManager(Protocol):
    async def create_schema(self) -> None:
        ...

    async def migrate_to(self, target: "DBManager") -> None:
        ...

    async def dispose(self) -> None:
        ...


class SettingsStore(Protocol):
    @property
    def settings(self) -> AppSettings:
        ...

    def replace_settings(self, settings: AppSettings) -> None:
        ...

    def save(self) -> None:
        ...


class SettingsMigrationError(Exception):
    """Ошибка миграции базы данных при смене backend."""


@dataclass(frozen=True)
class SettingsUpdateResult:
    response: SettingsResponse
    new_db_manager: DBManager


class SettingsService:
    """Сценарии чтения и обновления настроек приложения."""

    def __init__(
        self,
        settings_manager: SettingsStore,
        db_manager_factory: Callable[[DatabaseSettings], DBManager],
    ):
        self._settings_manager = settings_manager
        self._db_manager_factory = db_manager_factory

    def get_current_settings(self) -> SettingsResponse:
        return self._build_response(
            self._settings_manager.settings,
            only_active_sqlite=True,
        )

    async def update_settings(
        self,
        payload: SettingsUpdate,
        current_db_manager: DBManager,
    ) -> SettingsUpdateResult:
        old_settings = self._settings_manager.settings
        draft_settings = old_settings.model_copy(deep=True)
        old_backend = old_settings.database.backend

        self._apply_payload(draft_settings, payload)
        new_backend = draft_settings.database.backend

        new_db_manager = self._db_manager_factory(draft_settings.database)

        try:
            await new_db_manager.create_schema()
            if old_backend != new_backend:
                try:
                    await current_db_manager.migrate_to(new_db_manager)
                except Exception as exc:
                    raise SettingsMigrationError(str(exc)) from exc

            self._settings_manager.replace_settings(draft_settings)
            self._settings_manager.save()
        except Exception:
            if self._settings_manager.settings is draft_settings:
                self._settings_manager.replace_settings(old_settings)
            await new_db_manager.dispose()
            raise

        await current_db_manager.dispose()

        return SettingsUpdateResult(
            response=self._build_response(draft_settings),
            new_db_manager=new_db_manager,
        )

    def _apply_payload(self, settings: AppSettings, payload: SettingsUpdate) -> None:
        db = settings.database

        if payload.backend is not None:
            db.backend = payload.backend
        if payload.echo is not None:
            db.echo = payload.echo
        if payload.sqlite_path is not None:
            if db.sqlite is None:
                db.sqlite = SQLiteSettings(path=payload.sqlite_path)
            else:
                db.sqlite.path = payload.sqlite_path

        if (
            payload.postgres_host is not None
            or payload.postgres_port is not None
            or payload.postgres_user is not None
            or payload.postgres_password is not None
            or payload.postgres_name is not None
        ):
            if db.postgres is None:
                db.postgres = PostgresSettings(
                    host=payload.postgres_host or "localhost",
                    port=payload.postgres_port or 5432,
                    user=payload.postgres_user or "postgres",
                    password=payload.postgres_password or "postgres",
                    name=payload.postgres_name or "postgres",
                )
            else:
                pg = db.postgres
                if payload.postgres_host is not None:
                    pg.host = payload.postgres_host
                if payload.postgres_port is not None:
                    pg.port = payload.postgres_port
                if payload.postgres_user is not None:
                    pg.user = payload.postgres_user
                if payload.postgres_password is not None:
                    pg.password = payload.postgres_password
                if payload.postgres_name is not None:
                    pg.name = payload.postgres_name

    def _build_response(
        self,
        settings: AppSettings,
        *,
        only_active_sqlite: bool = False,
    ) -> SettingsResponse:
        db = settings.database
        sqlite_cfg = db.sqlite
        pg = db.postgres
        sqlite_path = sqlite_cfg.path if sqlite_cfg is not None else None
        if only_active_sqlite and db.backend != "sqlite":
            sqlite_path = None

        return SettingsResponse(
            backend=db.backend,
            echo=db.echo,
            sqlite_path=sqlite_path,
            postgres_host=pg.host if pg is not None else None,
            postgres_port=pg.port if pg is not None else None,
            postgres_user=pg.user if pg is not None else None,
            postgres_name=pg.name if pg is not None else None,
        )
