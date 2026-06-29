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

Production-скрипты хранятся в Git и запускают приложение через Poetry entrypoint `api-manager-books`.
Перед production-запуском нужны реальные TLS-файлы и `APP_ENV=prod`.

Создайте локальные env-шаблоны без реальных секретов:

```powershell
.\scripts\init-env.ps1
```

Для Linux/macOS:

```sh
sh ./scripts/init-env.sh
```

Скрипты создают `.env.prod.local` и `.env.dev.local`, если файлов еще нет. Эти файлы игнорируются Git.
Чтобы перезаписать шаблоны, используйте `-Force` в PowerShell или `--force` в shell.

Минимальный `.env.prod.local` для запуска приложения:

```ini
APP_ENV=prod
APP_HOST=0.0.0.0
APP_PORT=1408
TLS_CERT_FILE=C:\path\to\fullchain.pem
TLS_KEY_FILE=C:\path\to\privkey.pem
INITIAL_ADMIN_EMAIL=
INITIAL_ADMIN_PASSWORD=
```

На Linux/macOS значения с пробелами нужно экранировать или заключать в кавычки по правилам shell.

Production-запуск в CMD:

```cmd
start.bat
```

Production-запуск в PowerShell:

```powershell
.\start.ps1
```

Production-запуск в Linux/macOS:

```sh
sh ./start.sh
```

Сервер запускается с HTTPS на порту из `APP_PORT`, по умолчанию `1408`.

```text
https://localhost:1408
```

Для первого запуска с пустой таблицей пользователей нужно задать начального администратора в локальном env-файле или в окружении процесса:

```ini
INITIAL_ADMIN_EMAIL=admin@example.com
INITIAL_ADMIN_PASSWORD=change-this-long-password
```

Если переменные не заданы или пароль слишком короткий, приложение не стартует.

Dev-скрипты являются локальными файлами и не попадают в Git:

```text
start.dev.bat
start.dev.ps1
start.dev.sh
```

Они используют `.env.dev.local`, задают безопасный loopback-запуск `APP_ENV=dev`, `APP_HOST=127.0.0.1` и не требуют TLS-файлы. В dev-режиме приложение создает self-signed сертификат только для loopback bind `127.0.0.1` / `localhost`.

Ручной запуск без скриптов:

```powershell
poetry run api-manager-books
```

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
