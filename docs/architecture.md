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

`AsyncDBManager` создает асинхронный engine, session factory, сессии и схему БД. Модели регистрируются через импорт `api_manager_books.db.models`.

## Запуск приложения

Точка входа Poetry: `api_manager_books.main:main`.

При запуске:

- создается или переиспользуется self-signed TLS-сертификат;
- `uvicorn` запускает FastAPI-приложение на `0.0.0.0:1408`;
- `FastAPI(lifespan=...)` читает `config.ini`;
- создается `AsyncDBManager`;
- создаются таблицы базы данных;
- если пользователей нет, создается дефолтный администратор;
- `db_manager` и `settings_manager` сохраняются в `app.state`;
- при остановке приложения закрываются подключения к БД.

## WebSocket

WebSocket-слой находится в `api/websocket`.

Он отвечает за канал уведомлений и хранение активных подключений. Аутентификация WebSocket использует отдельную FastAPI-зависимость из `api/security`, потому что WebSocket не работает с обычным HTTP `Depends` полностью так же, как REST endpoints.
