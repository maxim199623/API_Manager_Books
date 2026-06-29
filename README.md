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

По умолчанию проект использует SQLite:

```ini
[database]
backend = sqlite

[sqlite]
path = var/app.db
```

Если `config.ini` отсутствует, приложение создаст файл с настройками по умолчанию при запуске.

## Запуск

```powershell
poetry run api-manager-books
```

Сервер запускается с HTTPS на порту `1408`:

```text
https://localhost:1408
```

При запуске приложение создает self-signed сертификат, если его еще нет. Браузер или HTTP-клиент может показывать предупреждение о недоверенном сертификате.

При старте также создаются таблицы базы данных. Если таблица пользователей пустая, создается администратор по умолчанию:

```text
email: default@default.ru
password: default
```

Эти учетные данные нужно изменить перед реальной эксплуатацией.

## Тесты

```powershell
poetry run pytest tests -q
```

## Линтинг

```powershell
poetry run ruff check .
```

## Архитектура

Краткое описание слоев и направления зависимостей находится в [docs/architecture.md](docs/architecture.md).
