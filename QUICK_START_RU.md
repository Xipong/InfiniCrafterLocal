# InfiniCrafterLocal v0.4.246 — setup/runbook

Опубликованная поставка 0.4.246 — мод **и** LocalGenerator вместе. [OpenRouter pin](docs/OPENROUTER_ROUTING_RU.md) текущего дерева пока unreleased. Этот runbook владеет setup/run; остальные документы не повторяют его.

## Установка

Нужны Python 3.11+ (Tk для GUI), Terraria/stable tModLoader с `ParticleLibrary`/`Luminance` (`modReferences`); C# build — [.NET 8 и внешние DLL](BUILD_QOL_RU.md#сборка).

Из распакованного корня Windows:

1. `01_INSTALL_MOD_TO_TMODLOADER.bat` заменяет `ModSources/InfiniCrafterLocal` пользователя: **старая папка удаляется**, сохрани свои изменения. tModLoader → Workshop → Develop Mods → Build + Reload; проверь версию.
2. `02_INSTALL_LOCAL_GENERATOR.bat` ставит runtime requirements. `04_OPEN_SETTINGS_GUI.bat` открывает GUI. Оба выбирают `py -3`, иначе `python`.

Нестандартный ModSources: `TMODLOADER_MODSOURCES` или первый аргумент `python tools/install_to_tmodloader_modsources.py "<ModSources>"` (также заменяет папку). Ручной путь в подготовленном Python-окружении, из корня:

```console
python -m pip install -r LocalGenerator/requirements.txt
python LocalGenerator/settings_gui.py
```

Это не установка мода/моделей. Локальные LLM/image servers и model files готовит оператор.

## Настройки

GUI сохраняет `LocalGenerator/config.env`. [config.example.env](LocalGenerator/config.example.env) — шаблон с примерными Windows-путями/старыми комментариями, не рабочий профиль. Существующий process environment имеет приоритет. Не перезаписывай личный конфиг обновлением; после изменений **Save → restart server**.

LLM и PNG независимы:

| Выбор | Поля маршрута |
|---|---|
| `INFINI_LLM_PROVIDER=local` | `INFINI_LMSTUDIO_URL`, `INFINI_LMSTUDIO_MODEL` |
| `…=openrouter` | `INFINI_OPENROUTER_API_KEY`, `INFINI_OPENROUTER_MODEL`; [upstream pin](docs/OPENROUTER_ROUTING_RU.md) отдельно |
| `…=openai_compat` | `INFINI_OPENAI_COMPAT_BASE_URL`, `INFINI_OPENAI_COMPAT_API_KEY`, `INFINI_OPENAI_COMPAT_MODEL` |
| `openai_codex` в LLM и/или Image selector | [Собственный ChatGPT login, models и ограничения](docs/CODEX_IMAGE_OAUTH_RU.md) |
| `INFINI_IMAGE_BACKEND=sdcpp` | `INFINI_SDCPP_SERVER_URL`; autostart: `INFINI_SDCPP_SERVER_EXE`, `INFINI_SDCPP_MODEL`, нужные `INFINI_SDCPP_VAE`/`INFINI_SDCPP_LLM`, `INFINI_SDCPP_SERVER_AUTOSTART=1` |
| `…=image_api` | `INFINI_IMAGE_API_BASE_URL`, `INFINI_IMAGE_API_KEY`, `INFINI_IMAGE_API_MODEL` |

Внешний sd.cpp: autostart=0. LoRA GUI принимает конкретный `INFINI_SDCPP_LORA_FILE`, каталог выводит из него. Другие image adapters — в GUI; неизвестный backend не превращается в готовый PNG. Ключи/сессии вне Git.

[Transport settings](docs/LLM_TRANSPORT_REQUEST_SHAPE_RU.md#настройки): `INFINI_LLM_RESPONSE_FORMAT`/`INFINI_LLM_API_MODE` управляют конвертом, не gameplay. Remote presets используют `json_object` + `chat_completions`, без гарантии для любого endpoint/model.

## Запуск и проверка

GUI **Start server** сначала сохраняет настройки; либо из корня:

```console
python LocalGenerator/server.py
```

Default bind `INFINI_HOST=127.0.0.1`, `INFINI_PORT=5055`. [Health](http://127.0.0.1:5055/health): сверить `version`, `serverRoot`, `configPath`, `llmProvider`, `imageBackend`, `imageBackendConfigError`. `ok=true` — ответ сервиса, **не** quota/model/generation proof. [Trace](http://127.0.0.1:5055/trace), `cache/events.ndjson` — stage errors; `INFINI_CONSOLE_EVENT_LEVEL=warn|error|info|debug|off` (default warn). Не публикуй личные raw prompts/config/traces.

Мод использует `http://127.0.0.1:5055/combine` (`GeneratorClient.Endpoint`), без публичного GUI/env selector. Смена адреса/порта требует согласования endpoint в исходниках мода; обычную установку оставь на 5055. GUI-owned сервер: **Stop server**, ручной: `Ctrl+C`; один процесс на порт.

## Первый craft

1. `InfiniCore`: 20 дерева recipe group Wood + 1 Fallen Star; dev-выдача — `/infinicore`.
2. Core в inventory → открыть inventory → два явных входа A/B station. Пустые/favorited items и сам Core не подходят.
3. Craft → ждать deliverable `GeneratedItemData`; progress не таймер выдачи. Не закрывай процесс незавершённой операции.

В MP только host/server генерирует/commit/refund; клиент отправляет intent, получает registry/assets, не готовый authoritative JSON.

## Multiplayer и диагностика

`INFINI_MP_ASSET_TRANSPORT=native` **по умолчанию**: PNG через Terraria packets, без внешнего HTTP для клиентов. При `http`: descriptor-verified `/get_asset?file=...`, достижимый `INFINI_ASSET_PUBLIC_BASE_URL`, bind `INFINI_HOST=0.0.0.0`, firewall только доверенным LAN/Radmin peers. Auto-guess предпочитает Radmin `26.x`; `26.x.x.x` — пример. `INFINI_TERRARIA_PORT` (обычно 7777) не generator port.

| Сбой | Действие |
|---|---|
| Нет health / другая копия | Python/requirements/bind/port; сверить root/config с GUI |
| Auth/quota/schema/timeout | Stage/status/body в trace; [transport boundaries](docs/LLM_TRANSPORT_REQUEST_SHAPE_RU.md#retries-и-границы-ошибок). Смена формата не лечит quota |
| Existing item без definition/PNG | `/getinfini`, `/infinicache stats`; HTTP URL/firewall или native sync |
| Missing/invalid texture | Runtime placeholder безопасен для отображения, не разрешает generator обойти обязательный PNG |
| Нужны числа/рисунки | [Команды и output paths](command.md) |

[Offline QA](LocalGenerator/QUICK_START_RU.md) не доказывает live craft, качество рисунка, Terraria/GPU/MP.
