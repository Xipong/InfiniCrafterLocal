# Исправления 0.4.251

Обновляй мод и LocalGenerator вместе. Корректные сохранённые recipes/PNG не мигрируются и не переавторствуются; личные configs, profiles и модели не входят в source ZIP.

## Изменения

- **Gameplay Repair:** исправление только JSON-типа сохраняется (`true` не равно `1`); зависимость выбранного conditional selector разрешена только по exact missing leaf из canonical registry. Уже корректные siblings/thresholds остаются frozen. Selector/дизайн модель выбирает сама, defaults/broad thaw не добавлены.
- **World cache:** явные stored recipeKey/worldId сравниваются с запросом до restamp. Противоречивая запись сохраняется целиком в quarantine и не выдаётся другим рецептом. Полный canonical runtime/VFX/assets admission действует и для default reader; caller validator может только добавить ограничения. Историческое отсутствие optional storage metadata не превращается в invented identity или importer.
- **Delayed NPC target:** captured incarnation token существующего owner сравнивается на due tick. MP SetDefaults того же object/slot с новой generation не переадресует старое действие; Transform с прежним token сохранён, stale direct pull не превращается в area pull.
- **Grounded:** реальная native опора проверяется в направлении gravDir, включая платформы, half blocks и slopes; zero-Y в воздухе недостаточно. Проверка не двигает игрока и не меняет native collision scratch flags.
- **MP QuickHeal/QuickMana:** generated utility получает отдельный bounded activation protocol с canonical server definition. Native pre-consumption Item sync охватывает first-use inventory и открытый Void Bag (сначала exact inventory-предмет открытой сумки, затем выбранный bank4 Item); heal/consume исполняются владельцем один раз, сервер не повторяет UseItem/mobility/spawn/VFX. Replay/session/identity/expiry guards защищают occurrence, но не являются независимым подтверждением native HP/расхода.
- **Игровой интерфейс:** «Кузня чудес», «Сердце кузни», «Горн 1/2/3», «Сковать» и кузнечные статусы вместо обычных LLM/backend labels. RU/EN локализация использует настоящий native prefix; таймеры, retry, host wait и возврат материалов сохранены. Старые authored имена/описания предметов не меняются.
- **Проверочный контур:** deadline test больше не требует входа HTTP handler после уже истёкшего полного 25ms бюджета. Whole-budget/noPOST/nofile и advisory continuation/bytes/deadline controls сохранены.

## Логирование

В GUI → «Сервер и крафт» добавлена видимая без Advanced галочка «Полное логирование (без обрезки)», по умолчанию ON. Пользовательский OFF сохраняется при save/reload и выборе presets. ON сохраняет полные sanitized запросы, ответы, payloads и failures без обрезки и автоматической ротации; OFF не создаёт дополнительных traces/stage/failure artifacts/events/access echo или backend stdout capture, оставляя краткие фатальные ошибки. Credentials редактируются до записи, чистый authored текст не меняется. После изменения — Сохранить → перезапустить сервер; установленная копия этим выпуском автоматически не меняется. Детали хранения, показа и очистки: [command.md](../command.md#полное-логирование-localgenerator).

## Граница приёмки

Native checks исполняют настоящие CPU tModLoader APIs/hooks и socket-free writer/server/remote decoder, не игру/world loop, GPU или живой MP-match. Python tests используют offline providers/fixtures. Normal Windows SDK build и package readback проверяются отдельно от headless harness. Финальные totals и exact release commit приводятся в GitHub release notes.
