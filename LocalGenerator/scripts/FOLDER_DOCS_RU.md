# Пользовательские entrypoints

`bootstrap.py` — изолированная установка runtime requirements и запуск GUI/сервера.
Не импортирует приложение до запуска, не пишет config.env, не меняет системный Python.

- `gui` — подготовить `.venv` при необходимости и открыть браузерный Studio (`infini_local.desktop.web_studio`).
- `setup` — установить/обновить зависимости по `requirements.txt`.
- `server` — прямой сервер в консоли без GUI ownership guards.
- `doctor` — только показать пути и Python, без установки и сетевых запросов.

Windows-вход: `OPEN_INFINICRAFT.bat` в корне проекта. При переносе установки
удали только воспроизводимую `LocalGenerator/.venv` и запусти entrypoint снова;
сохрани личные `config.env`, профили, cache и recipes.
