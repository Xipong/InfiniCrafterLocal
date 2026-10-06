# InfiniCrafterLocal v0.4.248 — setup/runbook

Поставка 0.4.248 — мод **и** LocalGenerator вместе, включая [OpenRouter pin](docs/OPENROUTER_ROUTING_RU.md). При обновлении сохрани личный `config.env`, cache, recipes/PNG и данные миров; модели и внешние `ParticleLibrary`/`Luminance` не поставляются. Runtime-исправления не перерисовывают старые PNG, а guidance применяется к будущей генерации. Этот runbook владеет setup/run; остальные документы не повторяют его.

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

GUI сохраняет `LocalGenerator/config.env`. [config.example.env](LocalGenerator/config.example.env) — шаблон с примерными Windows-путями/старыми комментариями, не рабочий профиль. При ручном запуске process environment имеет приоритет над config.env. GUI **Start** передаёт копию своего environment, поверх которой накладывает текущие поля `collect()`; для этих полей приоритет у GUI. Не перезаписывай личный конфиг обновлением; после изменений **Save → restart server**.

### Именованные профили и режим отображения

В GUI-only обновлении `0.4.248-gui.1` ручное изменение поля создаёт `Custom` в селекторе. «Сохранить как…» сохраняет текущие значения отдельным именованным профилем, **не меняя `config.env`**. Профили лежат в `LocalGenerator/gui_user_presets.json`; при обновлении сохрани его вместе с `LocalGenerator/config.env` и cache. Выбери `Мой: <название>` → «Применить» для загрузки, затем «Сохранить» для рабочего конфига. API keys/токены остаются текущими и в профиль не входят; лимиты tokens сохраняются. Основной режим скрывает неактивные backend-поля и технические настройки; переключатель «Расширенные настройки» раскрывает всё, не изменяя значения.

LLM и PNG независимы:

| Выбор | Поля маршрута |
|---|---|
| `INFINI_LLM_PROVIDER=local` | `INFINI_LMSTUDIO_URL`, `INFINI_LMSTUDIO_MODEL` |
| `…=openrouter` | `INFINI_OPENROUTER_API_KEY`, `INFINI_OPENROUTER_MODEL`; [upstream pin](docs/OPENROUTER_ROUTING_RU.md) отдельно |
| `…=openai_compat` | `INFINI_OPENAI_COMPAT_BASE_URL`, `INFINI_OPENAI_COMPAT_API_KEY`, `INFINI_OPENAI_COMPAT_MODEL` |
| `openai_codex` в LLM и/или Image selector | [Собственный ChatGPT login, models и ограничения](docs/CODEX_IMAGE_OAUTH_RU.md) |
| `INFINI_IMAGE_BACKEND=sdcpp` | `INFINI_SDCPP_SERVER_URL`; autostart: `INFINI_SDCPP_SERVER_EXE`, `INFINI_SDCPP_MODEL`, нужные `INFINI_SDCPP_VAE`/`INFINI_SDCPP_LLM`, `INFINI_SDCPP_SERVER_AUTOSTART=1` |
| `…=image_api` | `INFINI_IMAGE_API_BASE_URL`, `INFINI_IMAGE_API_KEY`, `INFINI_IMAGE_API_MODEL` |

Внешний sd.cpp: autostart=0; ему нужны доступный HTTP endpoint и уже работающий сервер, не локальные exe/model. `/visual_doctor.json` различает внешний и управляемый autostart, а при другом выбранном backend не требует sd.cpp. Без `probe=1` этот route не запускает image generation. LoRA GUI принимает конкретный `INFINI_SDCPP_LORA_FILE`, каталог выводит из него. Другие image adapters — в GUI; неизвестный backend не превращается в готовый PNG. Ключи/сессии вне Git.

[Transport settings](docs/LLM_TRANSPORT_REQUEST_SHAPE_RU.md#настройки): `INFINI_LLM_RESPONSE_FORMAT`/`INFINI_LLM_API_MODE` управляют конвертом, не gameplay. Remote presets используют `json_object` + `chat_completions`, без гарантии для любого endpoint/model.

## Запуск и проверка

GUI **Start server** сохраняет настройки при принятом запуске; занятый или непроверенный сервер не останавливает и настройки для такого restart не сохраняет.

`06_START_SERVER_DIRECT.bat` запускает тот же сервер в видимой консоли без GUI-проверки; сообщение об ошибке остаётся в окне. Не запускай второй экземпляр на занятом порту.

```console
python LocalGenerator/server.py
```

Default bind `INFINI_HOST=127.0.0.1`, `INFINI_PORT=5055`. [Health](http://127.0.0.1:5055/health): сверить `version`, `serverRoot`, `configPath`, `llmProvider`, `imageBackend`, `imageBackendConfigError`. `ok=true` — ответ сервиса, **не** quota/model/generation proof. [Trace](http://127.0.0.1:5055/trace), `cache/events.ndjson` — stage errors; `INFINI_CONSOLE_EVENT_LEVEL=warn|error|info|debug|off` (default warn). Не публикуй личные raw prompts/config/traces.

В текущем дереве `/health` дополнительно возвращает `generationActivity` (`active`, `waiting`, `accepting`) и частичный `effectiveConfig`: cache/world roots, image backend, основной LLM provider/model, exact OpenRouter upstream и sd.cpp autostart. Это явный allowlist без ключей, secret-derived hash или запроса разрешения `auto` model; он не подтверждает равенство всех pool/secret настроек. `/shutdown` атомарно отказывает с 409 при active/queued `/combine`; после согласованного shutdown новые генерации получают 503. `/shutdown?force=1` — явное принудительное прерывание, не resume/recovery protocol. Эти изменения включены в поставку 0.4.248; в старом опубликованном архиве 0.4.246 их нет.

В текущем GUI **Start / Stop** работают безопасно по умолчанию. **Force restart…** требует отдельного подтверждения и обходит только busy-проверку, не проверку root/PID и наличия корректного `effectiveConfig`. После HTTP 409 нет скрытого kill или повторного запуска; timeout/непонятный ответ не считаются свободным портом. Если старый сервер не отдаёт нужную projection, останови его прежним владельцем/через `Ctrl+C`, а не принудительным уничтожением неизвестного PID.

**Check applied config** асинхронно сравнивает только семь названных полей с текущими настройками запуска; расхождения показываются именами полей, без значений и ключей. **Save** сам по себе не применяет конфигурацию к работающему серверу. Изменение полей после проверки снимает устаревшее совпадение; `auto` не разрешается дополнительным запросом к модели.

Trace refresh выполняется вне Tk-потока; повторные обновления объединяются до последнего запроса. Отмена/закрытие запрещает показ позднего ответа, но не обещает принудительно прервать системный DNS или файловую блокировку. Offline trace, открытие папки и очистка используют cache root фактического GUI launch environment; относительный путь отсчитывается от `LocalGenerator`. Очистка затрагивает только три trace NDJSON, не recipes/PNG; чужой/непроверенный сервер, другой live cache или символические ссылки вместо trace/lock файлов — отказ без локальной подмены цели.

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
