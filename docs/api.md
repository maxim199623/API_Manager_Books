# API routes

Краткая карта основных маршрутов API и форматов входных данных. Точные схемы запросов и ответов смотрите в Swagger UI/ReDoc, потому что они строятся из текущих Pydantic-схем проекта.

```text
https://localhost:1408/docs
https://localhost:1408/redoc
```

## Общие правила

- Авторизованные REST-маршруты принимают access token в заголовке `Authorization: Bearer <access_token>`.
- Маршруты с загрузкой файлов принимают `multipart/form-data`.
- Обычные маршруты создания и обновления принимают `application/json`.
- Идентификаторы `book_id`, `user_id`, `file_id` передаются в path-параметрах в формате UUID.
- Номер главы `chapter_num` передается в path-параметрах как `int`.
- Поля со значением `null` допустимы только там, где поле помечено как опциональное.

Уровни доступа:

- `public` - Bearer access token не требуется;
- `user` - нужен `Authorization: Bearer <access_token>`;
- `admin` - нужен пользователь с ролью `admin`.

## Пользователи

| Метод | URL | Доступ | Назначение | Входные данные |
| --- | --- | --- | --- | --- |
| `POST` | `/users/auth` | `public` | Авторизация и выдача пары access/refresh токенов | JSON: `email` (`EmailStr`, обязательно), `password` (`str`, обязательно) |
| `POST` | `/users/refresh` | `public` | Обновление пары access/refresh токенов | JSON: `refresh_token` (`str`, обязательно) |
| `DELETE` | `/users/logout` | `user` | Завершение текущей сессии | Тело запроса не требуется |
| `GET` | `/users/me` | `user` | Получение текущего пользователя | Тело запроса не требуется |
| `POST` | `/users/add_user` | `admin` | Создание пользователя администратором | JSON: `email` (`EmailStr`, обязательно), `password` (`str`, обязательно), `role` (`"admin"` или `"user"`, по умолчанию `"user"`) |
| `GET` | `/users/get_users` | `admin` | Получение списка пользователей администратором | Тело запроса не требуется |
| `PATCH` | `/users/{user_id}` | `admin` | Частичное обновление пользователя администратором | Path: `user_id` (`UUID`). JSON: `email` (`EmailStr`, опционально), `password` (`str`, опционально), `role` (`"admin"` или `"user"`, опционально) |
| `DELETE` | `/users/{user_id}` | `admin` | Удаление пользователя администратором | Path: `user_id` (`UUID`); тело запроса не требуется |

Пример авторизации:

```json
{
  "email": "admin@example.com",
  "password": "change-this-long-password"
}
```

## Книги

| Метод | URL | Доступ | Назначение | Входные данные |
| --- | --- | --- | --- | --- |
| `POST` | `/books/add_book` | `admin` | Создание книги с опциональной обложкой и файлом | `multipart/form-data`: `title` (`str`, обязательно), `author` (`str`, опционально), `description` (`str`, опционально), `series` (`str`, опционально), `genres` (`str`, опционально), `format` (`str`, опционально), `cover` (`file`, опционально), `file` (`file`, опционально) |
| `GET` | `/books/` | `user` | Получение списка книг с фильтрацией, сортировкой и пагинацией | Query: `author` (`str`, опционально), `series` (`str`, опционально), `offset` (`int >= 0`, по умолчанию `0`), `limit` (`1..1000`, по умолчанию `100`), `sort_by` (`"created_at"`, `"progress"` или `"title"`, по умолчанию `"created_at"`), `sort_dir` (`"asc"` или `"desc"`, по умолчанию `"desc"`) |
| `PATCH` | `/books/{book_id}` | `admin` | Частичное обновление метаданных книги | Path: `book_id` (`UUID`). JSON: `title`, `author`, `description`, `series`, `genres`, `format` (`str`, все поля опциональны). Лишние поля запрещены |
| `DELETE` | `/books/{book_id}` | `admin` | Удаление книги | Path: `book_id` (`UUID`); тело запроса не требуется |

Пример `PATCH /books/{book_id}`:

```json
{
  "title": "Новое название",
  "author": "Автор",
  "genres": "fantasy, adventure"
}
```

## Файлы книг

| Метод | URL | Доступ | Назначение | Входные данные |
| --- | --- | --- | --- | --- |
| `GET` | `/books/{book_id}/cover` | `user` | Получение обложки книги | Path: `book_id` (`UUID`); тело запроса не требуется |
| `PUT` | `/books/{book_id}/cover` | `admin` | Обновление обложки книги | Path: `book_id` (`UUID`). `multipart/form-data`: `cover` (`file`, обязательно) |
| `GET` | `/books/{book_id}/file` | `user` | Скачивание файла книги | Path: `book_id` (`UUID`); тело запроса не требуется |
| `PUT` | `/books/{book_id}/file` | `admin` | Обновление файла книги | Path: `book_id` (`UUID`). `multipart/form-data`: `file` (`file`, обязательно) |

Ограничения загрузок:

| Тип поля | Расширения | MIME | Лимит |
| --- | --- | --- | --- |
| `cover` | `jpg`, `jpeg` | `image/jpeg` | 10 MiB |
| `cover` | `png` | `image/png` | 10 MiB |
| `cover` | `webp` | `image/webp` | 10 MiB |
| `file` книги | `epub` | `application/epub+zip` | 300 MiB |
| `file` книги | `pdf` | `application/pdf` | 300 MiB |
| `file` книги | `fb2`, `txt` | `text/plain`, `text/markdown` | 300 MiB |
| `file` книги | `mobi`, `azw3` | `application/octet-stream` | 300 MiB |

## Главы

Маршруты глав принимают JSON-данные главы. Файлы главы загружаются отдельными маршрутами из раздела “Файлы глав”.

| Метод | URL | Доступ | Назначение | Входные данные |
| --- | --- | --- | --- | --- |
| `POST` | `/books/{book_id}/chapters` | `admin` | Добавление списка глав к книге | Path: `book_id` (`UUID`). JSON-массив объектов: `chapter` (`int`, обязательно), `chapter_name` (`str` или `null`, опционально), `description` (`str`, обязательно) |
| `GET` | `/books/{book_id}/chapters` | `user` | Получение списка глав книги | Path: `book_id` (`UUID`); тело запроса не требуется |
| `GET` | `/books/{book_id}/chapters/count` | `user` | Получение количества глав книги | Path: `book_id` (`UUID`); тело запроса не требуется |
| `GET` | `/books/{book_id}/chapters/{chapter_num}` | `user` | Получение конкретной главы | Path: `book_id` (`UUID`), `chapter_num` (`int`); тело запроса не требуется |
| `PATCH` | `/books/{book_id}/chapters/{chapter_num}` | `admin` | Частичное обновление главы | Path: `book_id` (`UUID`), `chapter_num` (`int`). JSON: `chapter_name` (`str` или `null`, опционально), `description` (`str` или `null`, опционально) |

Пример `POST /books/{book_id}/chapters`:

```json
[
  {
    "chapter": 1,
    "chapter_name": "Начало",
    "description": "Текст главы"
  },
  {
    "chapter": 2,
    "chapter_name": null,
    "description": "Текст следующей главы"
  }
]
```

## Файлы глав

| Метод | URL | Доступ | Назначение | Входные данные |
| --- | --- | --- | --- | --- |
| `GET` | `/books/{book_id}/chapters/{chapter_num}/files` | `user` | Получение списка файлов главы | Path: `book_id` (`UUID`), `chapter_num` (`int`). Query: `name` (`str`, опционально), `extension` (`str`, опционально), `offset` (`int`, по умолчанию `0`), `limit` (`int`, по умолчанию `100`) |
| `POST` | `/books/{book_id}/chapters/{chapter_num}/files` | `admin` | Загрузка файла главы | Path: `book_id` (`UUID`), `chapter_num` (`int`). `multipart/form-data`: `file` (`file`, обязательно) |
| `GET` | `/books/{book_id}/chapters/{chapter_num}/files/{file_id}` | `user` | Скачивание файла главы | Path: `book_id` (`UUID`), `chapter_num` (`int`), `file_id` (`UUID`); тело запроса не требуется |
| `DELETE` | `/books/{book_id}/chapters/{chapter_num}/files/{file_id}` | `admin` | Удаление файла главы | Path: `book_id` (`UUID`), `chapter_num` (`int`), `file_id` (`UUID`); тело запроса не требуется |

Ограничения загрузок файлов главы:

| Расширения | MIME | Лимит |
| --- | --- | --- |
| `txt`, `md` | `text/plain`, `text/markdown` | 5 MiB |
| `jpg`, `jpeg` | `image/jpeg` | 15 MiB |
| `png` | `image/png` | 15 MiB |
| `webp` | `image/webp` | 15 MiB |
| `pdf` | `application/pdf` | 50 MiB |
| `mp3` | `audio/mpeg`, `audio/mp3` | 150 MiB |

## Избранное

| Метод | URL | Доступ | Назначение | Входные данные |
| --- | --- | --- | --- | --- |
| `POST` | `/books/{book_id}/favorite` | `user` | Добавление книги в избранное | Path: `book_id` (`UUID`); тело запроса не требуется |
| `DELETE` | `/books/{book_id}/favorite` | `user` | Удаление книги из избранного | Path: `book_id` (`UUID`); тело запроса не требуется |

## История чтения

| Метод | URL | Доступ | Назначение | Входные данные |
| --- | --- | --- | --- | --- |
| `GET` | `/books/chapters/read` | `user` | Получение списка прочитанных глав | Query: `book_id` (`UUID`, опционально), `offset` (`int >= 0`, по умолчанию `0`), `limit` (`1..1000`, по умолчанию `100`) |
| `GET` | `/books/{book_id}/chapters/read/count` | `user` | Получение количества прочитанных глав книги | Path: `book_id` (`UUID`); тело запроса не требуется |
| `DELETE` | `/books/{book_id}/history` | `user` | Очистка истории чтения книги | Path: `book_id` (`UUID`); тело запроса не требуется |

## Настройки

| Метод | URL | Доступ | Назначение | Входные данные |
| --- | --- | --- | --- | --- |
| `GET` | `/settings/` | `admin` | Получение текущих настроек приложения | Тело запроса не требуется |
| `PATCH` | `/settings/` | `admin` | Обновление настроек приложения | JSON: `backend` (`"sqlite"` или `"postgres"`, опционально), `echo` (`bool`, опционально), `sqlite_path` (`str`, опционально), `postgres_host` (`str`, опционально), `postgres_port` (`int`, опционально), `postgres_user` (`str`, опционально), `postgres_password` (`str`, опционально), `postgres_name` (`str`, опционально) |

Пример `PATCH /settings/` для SQLite:

```json
{
  "backend": "sqlite",
  "echo": false,
  "sqlite_path": "var/app.db"
}
```

Пример `PATCH /settings/` для PostgreSQL:

```json
{
  "backend": "postgres",
  "echo": false,
  "postgres_host": "localhost",
  "postgres_port": 5432,
  "postgres_user": "api_manager_books",
  "postgres_password": "change-me",
  "postgres_name": "api_manager_books"
}
```

## WebSocket

| Протокол | URL | Доступ | Назначение | Входные данные |
| --- | --- | --- | --- | --- |
| `WS` | `/ws/notifications` | `user`, token in query | Канал уведомлений для авторизованного пользователя | Query: `token=<access_token>`. После подключения сервер принимает текстовые сообщения, содержимое сообщений не обрабатывается |

Пример подключения:

```text
wss://localhost:1408/ws/notifications?token=<access_token>
```
