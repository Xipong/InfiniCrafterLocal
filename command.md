# Команды InfiniCrafterLocal в Terraria

Вводи команды в чат Terraria/tModLoader. Пути ниже относительны **`<Main.SavePath>/InfiniCrafterLocal/`** пользовательского tModLoader, не Steam-папке игры. Windows Documents/OneDrive/локализация зависят от профиля; не копируй чужой абсолютный путь.

| Команда | Результат |
|---|---|
| `/infinicore` | Один Core через quick-spawn в inventory; открыть inventory для station |
| `/multidevcraft [2\|3\|off]` | Сессионное число независимых craft lanes; без предметов/файлов |
| `/infinidummy [count]` | Target Dummy через quick-spawn; default 1, clamp 1–99, нечисло → 1 |
| `/getinfini` | Registry/asset catch-up; definitions `generated_items/<id>.json`, PNG/JSON `asset_cache/` |
| `/infiniitem [trace [held\|<1-58>]]` | Authored/last-applied snapshot только в чате; не изменяет предмет |
| `/infinicache [stats\|warm\|clear\|resetbad] [held\|inventory\|registry] [limit]` | RAM/GPU cache diagnostics; warm может получить assets на диск |
| `/infinidump` | Перезаписывает `items_runtime_dump.jsonl`, `projectiles_runtime_dump.jsonl` |
| `/infinidumppicture [all\|latest\|id-or-name-filter]` | Generated PNG/JSON/gallery в `picture_dumps/YYYYMMDD_HHMMSS/` |
| `/infinidumppicture source [held\|active\|baseline\|item <id/name>\|projectile <id/name>]` | Loaded Terraria/mod textures в `picture_dumps/source_YYYYMMDD_HHMMSS/` |

## Полное логирование LocalGenerator

В GUI → **Сервер и крафт** галочка **«Полное логирование (без обрезки)»** видна без расширенного режима и включена для нового config. Сохранённый `INFINI_TRACE_PROMPTS=0` не сбрасывается при открытии/сохранении GUI или выборе встроенного pipeline preset; пользовательский профиль сохраняет выбранное значение. Изменения применяются после **Сохранить → перезапустить сервер**.

- **ON:** полные sanitized prompts/ответы Gameplay/Visual/VFX (включая Repair), image prompts, payloads и шаги пишутся в `cache/prompt_trace.ndjson`, `cache/pipeline_trace.ndjson`, `cache/events.ndjson` без обрезки и автоматической ротации. Полные failure snapshots также архивируются в pipeline trace; `last_combine_failure.json` — только указатель последнего сбоя. `cache/stage_requests/*.json` сохраняет точные builder messages до provider conversion, с stage + recipeKey/recipeId + hash join, атомарно и без квот на длину/число записей. Не обещает захват transport headers или старого исторического HTTP wire; ошибка диска/неподдерживаемый message shape/linked storage дают refusal, а не частичный запрос.
- **OFF:** нет новых дополнительных prompt/pipeline traces, stage/failure debug artifacts, info/debug/warn events, HTTP access echo и захвата stdout/stderr запущенного GUI sd.cpp backend. Краткие фатальные ошибки и стартовый server baseline остаются; старый архив автоматически не удаляется. Внешний уже работающий backend GUI не перенастраивает.
- **Хранение ≠ показ:** GUI `/trace.json`/локальный fallback показывает последние записи; `INFINI_TRACE_EVENTS_TAIL` ограничивает число показанных строк, не архив. Содержимое показанного запроса/ответа остаётся полным. `INFINI_TRACE_MAX_PROMPT_CHARS=0` — настоящий unlimited sentinel для текстового web preview; положительное старое значение не обрезает сохранённые данные. При очень большом snapshot сохраняется I/O timeout, не подмена частичным успехом.
- **Безопасность/диск:** credentials редактируются перед сохранением/эхом; чистый authored текст (Unicode/CRLF/escape sequences) не переписывается. ON может занимать много диска: архив очищается только вручную. GUI Clear trace очищает три NDJSON; stage-request архив удаляй отдельно при остановленном сервере.
- **Область:** это переключатель дополнительной диагностики, не выключатель обязательного gameplay/progress, accepted recipe/history, механических receipts, transfer manifests или отдельно выбранного debug sprite-stage сохранения. Их отключение сломало бы pipeline/историю; модели, prompts/контракты и gameplay не меняются.

## `/multidevcraft`

`2` закрепляет окна за `llm_1`/`llm_2`, `3` — за `llm_1..llm_3`; `off` (также `0`/`1`) возвращает одно окно. Без аргумента цикл `1 → 2 → 3 → 1`. Каждое окно имеет собственные A/B, request/progress/refund. Занятое скрываемое окно нужно сначала завершить/освободить. Профили LLM 2/3 настраиваются во вкладке Multi-dev GUI; команда не обходит validation и server-authoritative commit, не выдаёт ингредиенты.

## `/getinfini`

Сбрасывает asset retry/backoff и повторяет недостающие PNG/JSON; в MP запрашивает полный registry сервера, вне MP обновляет локальные assets. **Не** создаёт рецепт, не вызывает LLM заново и не выдаёт предмет. Если catch-up не помог, проверь [выбранный MP transport](QUICK_START_RU.md#multiplayer-и-диагностика).

## `/infiniitem`

Без аргумента/с `help` — помощь. `trace`/`trace held` — предмет в руке; `trace 1` … `trace 58` — inventory slot, неправильный slot → held. Обычный предмет — `not generated`.

Applied — **последний `ApplyToItem` snapshot до последующих hooks/prefix**, не все текущие player/global modifiers; у clones/load snapshot может отсутствовать. Для полных чисел используй `/infinidump`.

## `/infinicache`

| Action / aliases | Эффект |
|---|---|
| Без args, `stats`, `status` | Texture count, memory estimate, hits/misses/loads/evictions, bad records, registry count, disk asset/download/missing counts |
| `clear` | Resident textures и missing/bad records из памяти; disk PNG/JSON/recipes/dumps остаются |
| `resetbad`, `reset` | Missing/bad backoff и asset retry state; только память |
| `warm`, `prefetch` | Прогрев sprites; недостающие PNG/JSON приходят в `asset_cache`, textures — RAM/GPU |

`warm [held|inventory|registry|all] [limit]`: default scope `inventory` (inventory, armor, misc equips), `held` — generated в руке, `registry`/`all` — registry; неизвестный scope также использует inventory. Default limit 64, clamp 1–512. Примеры: `/infinicache warm held`, `/infinicache warm inventory 64`, `/infinicache warm registry 256`. Dedicated server не имеет client GPU cache для warm.

## `/infinidump`

Каждый запуск перезаписывает оба runtime JSONL. Item rows содержат stats, use timing, damage class, rarity, tool/armor/accessory/ammo fields, `item.shoot`, projectile snapshot и texture metrics. Projectile rows — hitbox, AI style, penetration/lifetime/collision/immunity, minion/sentry flags, frames, selected `ProjectileID.Sets`, texture metrics. Эти реальные loaded rows можно передать генератору как [runtime dump inputs](LocalGenerator/README_RU.md#данные-и-настройки).

## `/infinidumppicture`: generated sprites

Default `latest` — до 12 последних items; `all` — весь registry. Filter ищется в id, name, parentA, parentB, recipeKey. Bundle содержит копии item/projectile/impact/child/field PNG, full/network JSON, `picture_dump_manifest.json`, `index.html`, `README.txt`.

## `/infinidumppicture source`: Terraria/mod textures

Aliases `source`: `src`, `ref`, `reference`, `original`, `vanilla`, `mod`, `modded`.

| Scope / aliases | Экспорт |
|---|---|
| Без scope, `held`, `current`, `selected` | Held item + связанный `item.shoot` projectile, если есть |
| `active`, `nearby`, `projectiles` | Уникальные active projectile textures + held item |
| `baseline`, `vanilla-baseline`, `starter` | Встроенный starter vanilla weapons set |
| `item`, `i` + query; либо query без `item` | Loaded item definitions по numeric id или точному display/internal/full name |
| `projectile`, `proj`, `p` + query | Projectile по numeric id или точному display/internal/full name |

Предмет не нужно иметь, исследовать или крафтить. Для vanilla используй display name текущей локализации; для modded подходит `SomeMod/InternalItemName`. Например, `/infinidumppicture source Гарпун`, явная форма `/infinidumppicture source item Гарпун`, либо `/infinidumppicture source projectile <id-or-exact-name>`.

Source bundle: `source_texture_manifest.json`, `index.html`, `README.txt`, `assets/item_<type>_<name>/item.png`, связанный `projectile_shoot.png`, `bundle_meta.json` (dimensions/types/use timing/shoot/shootSpeed/texture metrics). Item/projectile PNG — раздельные image references; итоговый путь выводится в чат.

Это static `TextureAssets.Item/Projectile`, **не screenshot**: rotation, lighting, трос/цепь, dust/trail и runtime draw не запекаются. На dedicated server picture dump недоступен без GPU textures. [Source владельцы команд](ModSources/InfiniCrafterLocal/Common/Commands/) задают фактический parsing и outputs.
