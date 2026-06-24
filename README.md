# API Manager Books

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

## Запуск

```powershell
poetry run api-manager-books
```

## Тесты

```powershell
poetry run pytest tests -q
```

## Линтинг

```powershell
poetry run ruff check .
```
