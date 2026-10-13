# Настройки генератора — 0.4.254

Основной вход — `OPEN_INFINICRAFT.bat`. Studio работает локально в браузере; его адрес с временным ключом сессии печатается в окне запуска. Этот адрес не публикуй. Порт Studio выбирается автоматически и **не** заменяет игровой HTTP endpoint `127.0.0.1:5055`. Кнопка «Сохранить настройки» и Ctrl+S записывают рабочий config; запуск — отдельное действие. Sidebar разделяет **«Запуск и состояние»**, **«Текстовые модели»**, **«Параллельный крафт»**, **«Изображения»**, **«Обработка спрайтов»**, **«Игра с друзьями»**, **«Профили и сервер»**, **«Диагностика»**. Он не меняет runtime-контракт.

## Сохранить, применить профиль, запустить

- **«Сохранить»** записывает текущие поля в `LocalGenerator/config.env`. Работающий сервер продолжает использовать конфигурацию своего запуска.
- **«Запустить сервер»** выполняет безопасную проверку владельца/занятости; только принятый запуск сохраняет конфиг и запускает сервер с текущими GUI-полями.
- После изменения настроек **сохрани и перезапусти** сервер. Проверка применённого конфига сравнивает лишь allowlist, не все secrets/pools.
- **«Применить»** загружает выбранный профиль в поля; затем сохрани. **«Сохранить как…»** записывает именованный профиль в `gui_user_presets.json`, не в рабочий config. API keys/токены в профиль не копируются.
- Ручное изменение встроенного профиля даёт `Custom`. Скрытые advanced-поля не удаляются. Именованный профиль сохраняет token limits и неизвестные настройки.

При ручном запуске process environment имеет приоритет над `config.env`. GUI строит копию environment и накладывает текущие `collect()`-поля поверх. [Точная семантика](OPERATIONS_RU.md#настройки).

## LLM: текстовая модель

| Маршрут | Что подготовить |
|---|---|
| `local` | LM Studio/API endpoint, загруженная модель; `INFINI_LMSTUDIO_URL`, `INFINI_LMSTUDIO_MODEL` |
| `openai_compat` | Совместимый base URL, свои key/model; `INFINI_OPENAI_COMPAT_*` |
| `openrouter` | Свои key/model; при необходимости [точный upstream pin](OPENROUTER_ROUTING_RU.md) |
| `openai_codex` | Собственная [OAuth-сессия и поддерживаемый маршрут](CODEX_IMAGE_OAUTH_RU.md), не обычный API key |

Preset с `json_object`/`chat_completions` не гарантирует совместимость любого провайдера. Shape rejection, auth и quota — разные ошибки. [Transport contract](../development/LLM_TRANSPORT_REQUEST_SHAPE_RU.md).

**Стиль промпта**: `Default` — обычное творческое направление; `Terraria Like` — читаемый игровой силуэт, компактная палитра и крупные пиксельные группы. Оба сохраняют контекст Terraria/tModLoader и прежний контракт Gameplay/Repair. Это guidance для будущих генераций, не доказанное live улучшение и не переавторство старых предметов.

## Изображения: отдельный маршрут PNG

- **sd.cpp**: autostart требует твоих exe, weights и нужных VAE/text-encoder файлов. Готовые пути/AMD-профили — примеры конкретной среды, не автоматический выбор для твоего GPU.
- **Внешний sd.cpp**: укажи URL запущенного сервера, выключи `INFINI_SDCPP_SERVER_AUTOSTART`; локальные exe/model пути тогда не обязательны.
- **Image API**: собственные base URL/key/model; поддержка формата и alpha зависит от endpoint.
- **Codex image**: отдельные условия [OAuth-route](CODEX_IMAGE_OAUTH_RU.md). Нет скрытого paid fallback.

Неизвестный backend или отсутствие рисунка не дают «готовый PNG». `item_body` всегда требует отдельный generated inventory sprite. [Lifecycle и delivery](../development/IMAGE_ASSET_LIFECYCLE_RU.md).

## Обработка спрайтов

Resize, chroma-key, alpha и палитра относятся к PNG, не к урону/управлению. Базовая явная resize-настройка — **BOX + premultiplied resize**; её можно сбросить отдельно без смены модели. Меняй по одному параметру и сравнивай новый результат.

- `BG color=transparent` запрашивает native alpha и отключает локальный chroma-keyer. Это не обещание, что endpoint реально вернёт alpha; `Alpha threshold` остаётся применим.
- Opaque chroma-профили используют локальную очистку фона. Tolerance/spill/residue не заменяют правильный image prompt.
- LoRA выбирается конкретным файлом; каталог выводится из него. Нужны совместимые weights/сборка.
- Сохранённые recipes/PNG не перерисовываются после смены профиля.

[Visual metadata](../reference/VISUAL_PRESENTATION_METADATA.md) описывает display size/grip/UV; [image lifecycle](../development/IMAGE_ASSET_LIFECYCLE_RU.md) — попытки и публикацию bytes.

## Мультиплеер и диагностика

Оставь **native** asset transport, если тебе не нужен специально настроенный HTTP. [Мультиплеер](MULTIPLAYER_RU.md). Логи по умолчанию подробные и растут без автоматической ротации; перед передачей проверь чувствительные данные. [Диагностика и очистка](DIAGNOSTICS_RU.md).

Источники defaults/профилей: [settings_schema.py](../../LocalGenerator/infini_local/desktop/settings_schema.py). В свежем шаблоне — `Custom`, local LLM и внешний sd.cpp (`autostart=0`), без личных model paths и автоматических hardware flags; доступность endpoints проверяешь ты. Этот документ не второй env registry; [пример конфига](../../LocalGenerator/config.example.env) не рабочий профиль.
