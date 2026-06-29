# API Manager Books

FastAPI API для управления книгами, главами, файлами, избранным, историей чтения, пользователями и настройками базы данных.

## Требования

- Python 3.13
- Poetry

## Установка

```powershell
poetry install
```

## Настройки

Создайте локальный файл настроек из примера:

```cmd
copy config.example.ini config.ini
```

В PowerShell можно использовать:

```powershell
Copy-Item config.example.ini config.ini
```

`config.ini` хранит локальные настройки окружения и не должен попадать в Git.
Если старые PostgreSQL-учетные данные `admin/admin` уже использовались, смените пароль этой базы данных.

По умолчанию проект использует SQLite:

```ini
[database]
backend = sqlite

[sqlite]
path = var/app.db
```

Если `config.ini` отсутствует, приложение создаст файл с настройками по умолчанию при запуске.

## Запуск

Локальный dev-запуск:

```powershell
$env:APP_ENV = "dev"
$env:APP_HOST = "127.0.0.1"
poetry run api-manager-books
```

Сервер запускается с HTTPS на порту `1408`:

```text
https://localhost:1408
```

В dev-режиме приложение создает self-signed сертификат только для loopback bind `127.0.0.1` / `localhost`.
Для сетевого bind и production нужны явные TLS-файлы:

```powershell
$env:APP_ENV = "prod"
$env:APP_HOST = "0.0.0.0"
$env:TLS_CERT_FILE = "C:\path\to\fullchain.pem"
$env:TLS_KEY_FILE = "C:\path\to\privkey.pem"
poetry run api-manager-books
```

При старте также создаются таблицы базы данных. Для первого запуска с пустой таблицей пользователей нужно явно задать начального администратора:

```powershell
$env:INITIAL_ADMIN_EMAIL = "admin@example.com"
$env:INITIAL_ADMIN_PASSWORD = "change-this-long-password"
poetry run api-manager-books
```

Если переменные не заданы или пароль слишком короткий, приложение не стартует.

## Тесты

```powershell
poetry run pytest tests -q
```

## Политика загрузки файлов

Загрузки проверяются по расширению, MIME и бинарной сигнатуре там, где формат это позволяет. Лимиты задаются по типу загрузки и расширению:

| Тип загрузки | Расширения | Лимит |
| --- | --- | --- |
| `cover` | `jpg`, `jpeg`, `png`, `webp` | 10 MiB |
| `book_file` | `epub`, `pdf`, `fb2`, `txt`, `mobi`, `azw3` | 300 MiB |
| `chapter_file` | `txt`, `md` | 5 MiB |
| `chapter_file` | `jpg`, `jpeg`, `png`, `webp` | 15 MiB |
| `chapter_file` | `pdf` | 50 MiB |
| `chapter_file` | `mp3` | 150 MiB |

Для `chapter_file` из аудио поддерживается только `mp3`. Текстовые форматы (`txt`, `md`, `fb2`) не имеют полной проверки содержимого, поэтому для них проверяются расширение, MIME при наличии и размер.

## Линтинг

```powershell
poetry run ruff check .
```

## Архитектура

Краткое описание слоев и направления зависимостей находится в [docs/architecture.md](docs/architecture.md).
