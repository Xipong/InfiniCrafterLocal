# Image/VFX asset lifecycle — 0.4.246

## Канонический путь

`Gameplay Author → Visual Director → VFX Director → image attempts → atomic PNG publication → delivery/cache → C#`.

Текстовых baseline-ролей по-прежнему три. Модель задаёт внешний вид, источники текстур, композицию и механику. Код выполняет техническую обработку и проверку; не выбирает оружейный архетип, stock-картинку, другую модель или новую механику.

| Объект | Единственный владелец |
|---|---|
| Принятые Visual/VFX requests | Канонические Visual DTO и `vfxManifest`; `visual_asset_plan.py` создаёт deep-copy план, не вторую truth source |
| Техническая image-попытка | `_execute_image_request` в `visual_sprite_generation.py` |
| Provider transport, seed/variants, backend admission | Существующие backend adapters и `IMAGE_GENERATION_GATE` |
| Raw/stages/master/final/refit промежуточные файлы | Явный invocation/attempt `output_dir` |
| Публичный завершённый PNG | Общий атомарный publisher |
| PNG-потребность VFX slot | Read-only `vfx_png_dependencies` в существующем VFX contract owner |
| Пригодность результатов к delivery/cache | Existing delivery gate и world-storage admission |
| Descriptor/hash/length при передаче | Existing AssetSync |
| Загруженные GPU textures | `RuntimeSpriteCache`, включая deferred retirement |

Diagnostic manifest и `debug.visualAssetPlan` остаются наблюдениями; изменение этих отчётов не меняет фактический roster или разрешения.

## Одна попытка вместо двух расходящихся циклов

`maybe_generate_sprite` и `generate_visual_asset` сохраняют публичные интерфейсы и специфичные проекции, но используют один executor. Только он владеет budget, retry prompt, backend call, выбором варианта, postprocess, validation/refit, принятием, публикацией и receipts. Item-проекция сохраняет raw/status/technical metrics и visual-soul; остальные роли возвращают результат для своих canonical DTO.

Приватный immutable request разделяет logical asset ID, audit role, processing role, canvas/topology и конечную publication policy. Result содержит committed path, raw path, оба score, final prompt, validation/attempt receipts и failure phase. Это технические структуры Python, не новый LLM output, asset registry, VM или система callbacks.

## Filesystem ownership отдельно от identity модели

У каждой invocation и попытки свой private `output_dir` вне `SPRITE_DIR` и world-recipe serving roots. Этот путь явно передаётся backend/postprocess/stages/refit; module-global directories не переключаются. Backend gate не расширяется на CPU/postprocess/publication.

Legacy logical IDs и retry suffixes, ComfyUI `{{SPRITE_ID}}`, authored prompts и seed policy не меняются ради изоляции файлов. У VFX сохраняется прежний nonce/digest, уже передававшийся backend. Custom ComfyUI workflow может сам выбирать remote SaveImage filenames: локальная изоляция не обещает изменить его remote storage.

Raw/stages остаются **private diagnostic files**, а не публичными ассетами. Обычное место — `image-diagnostics` рядом с `SPRITE_DIR`; если оно пересекается с serving roots, выбирается private temporary-root directory. Конкретный путь и `retained_private` записываются в debug receipt. Автоматическая очистка/квота диагностики в этой версии не добавлена: каталог может накапливаться; его не следует включать в переносимые исходники или раздачу PNG.

## Публикация только завершённых bytes

Новые non-VFX PNG получают ASCII filename по structured `[recipeId, auditRole, entityId, logicalAssetId]` и окончательным bytes, а не по конкатенации строк. Поэтому `impact:orb` и `entity:orb_impact` не могут перезаписать результат друг друга, даже когда старый logical asset ID совпал. VFX сохраняет прежний алгоритм `[recipeId, assetId] + NUL + bytes` и prefix.

Publisher пишет собственный уникальный `.part`, делает flush/fsync и atomic replace в конечном serving root. Hydration public path происходит только после commit. Mutable retry→canonical copy удалён. Имена существующих recipes/PNG не переименовываются и не мигрируются; новый materialization использует новый immutable filename.

Local filesystem/write/commit failure означает `failed`, пустые public paths и внутреннюю failure phase — не новую backend generation, не переписывание prompt и не procedural replacement. Непригодное содержимое provider image отличается от ошибки диска: оно может пройти существующий bounded technical retry. Nonfatal technical warning, допустимый refit, terminal Codex errors и explicit dev-only policy сохраняют свои отдельные условия. Для `vfx_strip` по-прежнему запрещены crop/recenter/rotation/refit, меняющие смысл UV.

## Одна PNG dependency projection

`vfx_png_dependencies` выводит именно выбранного producer по существующим DTO и renderer consumption. Она используется validation, delivery и cache admission; C# проверяет тот же invariant через canonical renderer predicate.

- `item` выбирает inventory image.
- `entity` требует того же exact entity с `baked_sprite` либо `reuse_item_icon`.
- Legacy `projectile`/`field` дополнительно должны совпадать с actual entity `visualRole`.
- `impact` требует same-entity `impactSprite` producer.
- `asset` ссылается на точный объявленный ingredient ID; несколько consumers не создают несколько jobs.
- Primitive/Dust/cue renderer не получает PNG requirement только из проигнорированного texture hint.

Некорректная ссылка становится exact selector-leaf error для прежнего frozen-first Repair. Код не меняет Visual mode, не выбирает inventory icon и не создаёт compensating artwork. Уже валидные поля, gameplay и Visual остаются frozen. При неизвестном target сначала исправляется его identity; зависимая диагностика не должна размораживать корректный selector по отсутствующему контексту.

Прежде принятые, но неисполняемые legacy selectors теперь отклоняются явно. Это не silent migration. Старые корректные варианты и их отрисовка сохраняются.

## Проверка и границы

Регрессии покрывают последовательную role collision, overlapping requests при gate=1, точные backend IDs/seeds, реальную PNG-обработку и serving bytes, failure phases/cleanup, оба типа selectors, frozen Repair, storage refusal/quarantine и реальные C# DTO/texture consumers. Retained rendering проверяется отдельно на native FNA/GPU.

Offline provider responses и native fixture PNG являются явно ручными тестовыми данными. Эти проверки не означают live image-model quality, Terraria game-loop, двухклиентный MP или измеренное ускорение генерации. Ошибка диска больше не тратит дополнительные image requests, но обычная генерация всё ещё ограничена временем выбранного backend; FPS и latency улучшения без замеров не заявляются.
