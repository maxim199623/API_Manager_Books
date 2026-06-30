# Локальная разработка

Документ описывает запуск проекта в dev-режиме. Production-запуск и production TLS описаны отдельно в README.

## Требования

- Python 3.13
- Git
- Poetry
- PostgreSQL, если локально проверяется backend `postgres`

По умолчанию проект использует SQLite.

## Установка

```bash
poetry install
```

Если репозиторий только что скачан, сначала перейдите в каталог проекта:

```bash
cd API_Manager_Books
poetry install
```

## Локальная база данных

Создайте локальный `config.ini` из примера:

```bash
cp config.example.ini config.ini
```

На Windows:

```powershell
Copy-Item config.example.ini config.ini
```

Минимальная SQLite-конфигурация:

```ini
[database]
backend = sqlite
echo = false

[sqlite]
path = var/app.db
```

`config.ini` содержит локальные настройки и не должен попадать в git.

## Dev-переменные окружения

Для локального запуска используются значения:

| Переменная | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `APP_ENV` | `dev` | Режим локальной разработки |
| `APP_HOST` | `127.0.0.1` | Loopback-хост для dev-запуска |
| `APP_PORT` | `1408` | Порт API-сервера |

Если таблица пользователей пустая, дополнительно задайте:

| Переменная | Пример |
| --- | --- |
| `INITIAL_ADMIN_EMAIL` | `admin@example.com` |
| `INITIAL_ADMIN_PASSWORD` | `change-this-long-password` |

Пароль первого администратора должен соответствовать политике паролей проекта.

## Запуск

PowerShell:

```powershell
.\start.dev.ps1
```

Windows CMD:

```cmd
start.dev.bat
```

Linux/macOS:

```bash
sh ./start.dev.sh
```

После запуска API доступен по адресу:

```text
https://localhost:1408
```

Документация FastAPI:

```text
https://localhost:1408/docs
https://localhost:1408/redoc
```

## Dev TLS-сертификаты

В dev-режиме приложение автоматически создает self-signed TLS-сертификат только при локальном bind:

- `APP_HOST=127.0.0.1`
- `APP_HOST=localhost`

Если `TLS_CERT_FILE` и `TLS_KEY_FILE` не заданы, используются пути по умолчанию в корне проекта:

| Файл | Назначение | Нужен клиенту |
| --- | --- | --- |
| `cert.pem` | Self-signed сертификат сервера | Да |
| `key.pem` | Приватный ключ сервера | Нет |

Клиенту нужен только `cert.pem`, чтобы доверять локальному HTTPS. `key.pem` нельзя передавать клиенту: это приватный ключ сервера.

Для браузера self-signed сертификат можно принять вручную или добавить `cert.pem` в локальное доверенное хранилище. Для HTTP-клиентов используйте `cert.pem` как CA/verify-файл, если клиент поддерживает такую настройку.

Если оба файла уже существуют, приложение переиспользует их. Если нужно выпустить новую локальную пару, удалите оба файла вручную и запустите dev-сервер заново.

Для bind на `0.0.0.0` или другом сетевом адресе автогенерация запрещена: нужно явно задать `TLS_CERT_FILE` и `TLS_KEY_FILE`.

Production TLS автоматически не создается. Для production нужен сертификат от внешнего CA или ACME-провайдера.

## Проверки

Все тесты:

```bash
poetry run pytest tests -q
```

TLS-логика запуска:

```bash
poetry run pytest tests/test_main_tls.py -q
```

Линтер:

```bash
poetry run ruff check .
```

## Что нельзя коммитить

Не добавляйте в git локальные runtime-файлы и секреты:

- `.env.dev.local`
- `.env.prod.local`
- `config.ini`
- `cert.pem`
- `key.pem`
- `var/security/`
- реальные пароли и строки подключения
