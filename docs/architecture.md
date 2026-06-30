# Архитектура

Проект использует пакет `api_manager_books` и разделен на HTTP-слой, прикладные сервисы, инфраструктуру базы данных, схемы данных и стартовую инициализацию.

## Текущая структура

Основные части проекта:

- `src/api_manager_books/api/route` - HTTP endpoints FastAPI.
- `src/api_manager_books/api/security` - JWT, FastAPI auth dependencies и TLS helper.
- `src/api_manager_books/api/websocket` - WebSocket-канал уведомлений.
- `src/api_manager_books/application/services` - прикладные сценарии.
- `src/api_manager_books/db/Repository` - SQLAlchemy-репозитории.
- `src/api_manager_books/db/Manager` - менеджер асинхронных сессий и подключения к БД.
- `src/api_manager_books/db/base.py` - базовая metadata SQLAlchemy.
- `src/api_manager_books/db/models.py` - регистрация ORM-моделей в metadata.
- `src/api_manager_books/schemas` - Pydantic DTO, request и response models.
- `src/api_manager_books/config` - чтение, изменение и сохранение настроек.
- `src/api_manager_books/bootstrap` - стартовая инициализация, включая дефолтного админа.
- `src/api_manager_books/security` - общие функции паролей без привязки к FastAPI.

## Направление зависимостей

Зависимости должны идти от внешнего слоя к прикладным сценариям и инфраструктуре:

- `api` собирает зависимости, проверяет HTTP-контракт и вызывает сервисы.
- `application` не зависит от FastAPI, `Request`, `Depends`, HTTP-статусов и роутеров.
- Сервисы принимают зависимости через `Protocol` и поведенческие контракты, а не обязаны импортировать конкретные классы репозиториев.
- Конкретные репозитории и сервисы собираются в `api/dependencies.py`.
- `db` не зависит от `api` и не должен знать о FastAPI.

HTTP-слой может преобразовывать ошибки сервисов в HTTP-ответы. Репозитории и база данных не должны формировать HTTP-ответы, выбирать HTTP-статусы или принимать FastAPI-зависимости.

## Роуты

Роуты отвечают за HTTP-контракт:

- параметры запросов;
- FastAPI dependencies;
- HTTP-статусы;
- преобразование ошибок в HTTP-ответы;
- response models.

Роуты не должны содержать бизнес-сценарии. Их задача - принять HTTP-запрос, вызвать нужный сервис и вернуть корректный HTTP-ответ.

## Сервисы

Сервисы отвечают за сценарии приложения:

- пользователи и авторизация;
- книги и файлы книг;
- избранное;
- главы и файлы глав;
- история чтения;
- настройки.

Сервис координирует репозитории, безопасность и схемы, чтобы выполнить прикладной сценарий. Он не должен зависеть от деталей FastAPI.

## Репозитории и БД

Репозитории отвечают за SQLAlchemy-запросы и работу с хранилищем данных.

Репозитории не знают про FastAPI: они не принимают `Request`, не используют dependencies, не формируют HTTP-ответы и не выбирают HTTP-статусы.

`AsyncDBManager` создает асинхронный engine, session factory и сессии. Схема БД управляется Alembic-миграциями из каталога `migrations/`.

## Запуск приложения

Точка входа Poetry: `api_manager_books.main:main`.

При production-запуске:

- `api_manager_books.main:main` читает `APP_ENV`, `APP_HOST`, `APP_PORT`, `TLS_CERT_FILE`, `TLS_KEY_FILE`;
- при `APP_ENV=prod` проверяется наличие путей к TLS-сертификату и приватному ключу;
- `uvicorn` запускает FastAPI-приложение с `ssl_certfile` и `ssl_keyfile`;
- `FastAPI(lifespan=...)` читает `config.ini`;
- создается `AsyncDBManager`;
- Alembic применяет миграции к текущей БД до `head`;
- если пользователей нет, первый администратор создается из `INITIAL_ADMIN_EMAIL` и `INITIAL_ADMIN_PASSWORD`;
- `db_manager` и `settings_manager` сохраняются в `app.state`;
- при остановке приложения закрываются подключения к БД.

## Runtime-файлы и секреты

Production TLS-сертификат и приватный ключ создаются внешним CA/ACME-инструментом и передаются приложению через `TLS_CERT_FILE` и `TLS_KEY_FILE`.

JWT-ключи хранятся в каталоге из `JWT_KEY_DIR`. Если переменная не задана, используется `var/security/jwt`.

`config.ini`, `.env.prod.local`, TLS-ключи, JWT-ключи и реальные пароли БД не должны храниться в git.

## WebSocket

WebSocket-слой находится в `api/websocket`.

Он отвечает за канал уведомлений и хранение активных подключений. Аутентификация WebSocket использует отдельную FastAPI-зависимость из `api/security`, потому что WebSocket не работает с обычным HTTP `Depends` полностью так же, как REST endpoints.
