# Image/VFX asset lifecycle — активный контракт 0.4.247

<a id="owners"></a>
## Канонический путь и владельцы

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

Source owners: [executor](../LocalGenerator/infini_local/pipelines/visual_sprite_generation.py), [backend adapters](../LocalGenerator/infini_local/pipelines/image_backend_pipeline.py), [plan](../LocalGenerator/infini_local/pipelines/visual_asset_plan.py), [delivery](../LocalGenerator/infini_local/pipelines/visual_delivery_gate.py), [storage admission](../LocalGenerator/infini_local/storage/world_storage.py), [AssetSync](../ModSources/InfiniCrafterLocal/Common/Services/GeneratedAssetSyncService.cs), [texture cache](../ModSources/InfiniCrafterLocal/Common/Services/RuntimeSpriteCache.cs).

<a id="attempts"></a>
## Одна попытка, private output и atomic publication

`maybe_generate_sprite` и `generate_visual_asset` сохраняют публичные интерфейсы и специфичные проекции, но используют один executor. Только он владеет budget, retry prompt, backend call, выбором варианта, postprocess, validation/refit, принятием, публикацией и receipts. Item-проекция сохраняет raw/status/technical metrics и visual-soul; остальные роли возвращают результат для своих canonical DTO.

Приватный immutable request разделяет logical asset ID, audit role, processing role, canvas/topology и конечную publication policy. Result содержит committed path, raw path, оба score, final prompt, validation/attempt receipts и failure phase. Это технические структуры Python, не новый LLM output, asset registry, VM или система callbacks.

У каждой invocation и попытки свой private `output_dir` вне `SPRITE_DIR` и world-recipe serving roots. Этот путь явно передаётся backend/postprocess/stages/refit; module-global directories не переключаются. Backend gate не расширяется на CPU/postprocess/publication.

Legacy logical IDs и retry suffixes, ComfyUI `{{SPRITE_ID}}`, authored prompts и seed policy не меняются ради изоляции файлов. У VFX сохраняется прежний nonce/digest, уже передававшийся backend. Custom ComfyUI workflow может сам выбирать remote SaveImage filenames: локальная изоляция не обещает изменить его remote storage.

Raw/stages остаются **private diagnostic files**, а не публичными ассетами. Обычное место — `image-diagnostics` рядом с `SPRITE_DIR`; если оно пересекается с serving roots, выбирается private temporary-root directory. Конкретный путь и `retained_private` записываются в debug receipt. Автоматическая очистка/квота диагностики в этой версии не добавлена: каталог может накапливаться; его не следует включать в переносимые исходники или раздачу PNG.

Новые non-VFX PNG получают ASCII filename по structured `[recipeId, auditRole, entityId, logicalAssetId]` и окончательным bytes, а не по конкатенации строк. Поэтому `impact:orb` и `entity:orb_impact` не могут перезаписать результат друг друга, даже когда старый logical asset ID совпал. VFX сохраняет прежний алгоритм `[recipeId, assetId] + NUL + bytes` и prefix.

Publisher пишет собственный уникальный `.part`, делает flush/fsync и atomic replace в конечном serving root. Hydration public path происходит только после commit. Mutable retry→canonical copy удалён. Имена существующих recipes/PNG не переименовываются и не мигрируются; новый materialization использует новый immutable filename.

VFX ID сохраняется буквально, включая регистр. `Glow/glow` и `spark/spark_refit` не должны сталкиваться при case-insensitive sync/refit. Конечный ASCII digest учитывает exact identity и окончательные PNG bytes; raw ID не становится filename, новое содержимое не перезаписывает ранее распределённое имя. Это техническое именование, не дополнительная integrity authority.

<a id="failure"></a>
## Failure policy без скрытого artwork

Local filesystem/write/commit failure — `failed`, пустые public paths и failure phase; не повторный backend call, новый prompt или replacement. `_execute_image_request` различает configuration, backend, selection, processing, validation, publication и projection. `IMAGE_BACKEND=off` возвращает `prompt_only`, не готовый PNG. Backend config error диагностируется до image attempts.

Непригодное provider image content допускает существующий bounded technical retry (`max(1, SPRITE_RETRIES+1)` attempts), но `CodexError`, `ImageOutputIOError`, publication failure и OSError в processing/projection терминальны. Public DTO гидратируется только после commit; projection-tail failure не делает DTO пригодным и не тратит новую модельную попытку.

Nonfatal validation может быть принята как `generated_warn_invalid`; допустимый technical refit не является новым дизайном. `vfx_strip` запрещает crop/recenter/rotation/silhouette-refit: keying/resize сохраняют full frame/UV. Legacy late-warning recovery разрешён только в своей nonterminal publication policy, не превращает disk/VFX failure в успех.

Explicit dev-only procedural policy отдельно требует `VISUAL_ALLOW_PROCEDURAL_FALLBACK` и отключённый `VISUAL_STRICT_AI_AUTHORSHIP`; она не действует для required VFX или `openai_codex` и не маскирует terminal local I/O. Required authored PNG при ошибке блокирует delivery; stock mask, белый quad и Dust его не заменяют. Пока валидный PNG ещё загружается клиентом, соответствующий texture consumer временно молчит.

<a id="dependencies"></a>
## Одна PNG dependency projection и ready-domain

`vfx_png_dependencies` выводит именно выбранного producer по существующим DTO и renderer consumption. Она используется validation, delivery и cache admission; C# проверяет тот же invariant через canonical renderer predicate.

- `item` выбирает inventory image.
- `entity` требует того же exact entity с `baked_sprite` либо `reuse_item_icon`.
- Legacy `projectile`/`field` дополнительно должны совпадать с actual entity `visualRole`.
- `impact` требует same-entity `impactSprite` producer.
- `asset` ссылается на точный объявленный ingredient ID; несколько consumers не создают несколько jobs.
- Primitive/Dust/cue renderer не получает PNG requirement только из проигнорированного texture hint.

Некорректная ссылка становится exact selector-leaf error для прежнего frozen-first Repair. Код не меняет Visual mode, не выбирает inventory icon и не создаёт compensating artwork. Уже валидные поля, gameplay и Visual остаются frozen. При неизвестном target сначала исправляется его identity; зависимая диагностика не должна размораживать корректный selector по отсутствующему контексту.

Прежде принятые, но неисполняемые legacy selectors теперь отклоняются явно. Это не silent migration. Старые корректные варианты и их отрисовка сохраняются.

Material `{source,assetId}` требует пустой assetId при `item|entity|impact` и точный declared ID при `asset`. Дубликаты IDs, dangling references и unused requests отвергаются; один ingredient request даёт одну job независимо от числа consumers. Null не означает отсутствие optional `assets`. Подробнее о layout/движении — [material contract](VFX_MATERIAL_ELEMENTS_RU.md#assets).

Fresh requests требуют непустого prompt. Полный локальный cache сохраняет captions; network projection обнуляет обе строки prompt/negativePrompt и оставляет asset identity, размер/layout, render references и готовые технические metadata. Runtime admission принимает этот объявленный stripped-вид, не применяет к нему правило нового image-запроса. Storage/delivery отдельно проверяют готовность ассетов, даже если проверка промежуточного compiled wire допускает pending records. Полный C# `GeneratedItemData.FromJson` принимает каждый объявленный VFX-ассет только с непустым PNG-path и точным `spriteStatus=generated|generated_warn_invalid` — и с captions, и в stripped network-виде. `pending`, `skipped`, `not_required`, `failed`, `prompt_only`, иной регистр или произвольный status не означают готовность. Это admission metadata; реальные PNG bytes по-прежнему проверяет существующий AssetSync.

<a id="bytes"></a>
## Serving bytes и единственный texture owner

Delivery/cache проверяют безопасное PNG-имя и реальные файлы из тех же roots, которые обслуживает `/get_asset`, а не только существование произвольного локального пути. Проверяется весь непустой runtime PNG-roster, включая сохранённые overlay/entity/impact entries: complete PNG, до 8 МиБ на файл, до 16 МиБ суммарно и не более 32 файлов. Необязательное отсутствие картинки отличается от присутствующего, но неготового пути.

`GeneratedAssetSyncService` сертифицирует canonical cache PNG/length/SHA на lifecycle boundary, proof живёт на существующем descriptor. `RuntimeSpriteCache.TryGet` предпочитает certified cache path local shadow **только** при непротиворечивой declared identity. Любой retained descriptor того же filename с другим length/hash отменяет priority независимо от registration order/proof; equal identities могут разделять proof. Без priority сохраняется прежний local-only путь. Descriptor-reference index обновляется на manifest replacement, validation/commit и disposal; Draw делает O(1) lookup и обычную length/mtime проверку без roster scan, PNG decode или SHA. Изменённые file stats/disposal отзывают priority; DTO paths/captions/network definition hash не переписываются.

Один normalized selected key используется lookup, catch/backoff и lifecycle invalidation, а не исходный alias. Load failure не открывает файл вновь до истечения backoff или explicit invalidation. Invalidation сразу прекращает выдачу stale texture; неизвестный key не создаёт запись.

`RuntimeSpriteCache` владеет GPU textures; AssetSync — подтверждёнными PNG bytes. Invalidation/LRU/Clear/Dispose отправляют заимствованные textures в одну очередь retirement **конкретного экземпляра кеша**. Callback в конце `Main.Update`, после текущего Draw, освобождает их безопасно: worker/download/unload не Dispose-ит ресурс, используемый SpriteBatch/DrawData. Повторный Dispose не воскрешает кеш и не освобождает twice.

При неизменном effective limit N resident ≤ N, resident + pending-retirement ≤ 2N. Исчерпание ownership budget временно запрещает новую load без stale result и missing/bad backoff; hot hits остаются, callback освобождает budget. Понижение лимита не освобождает уже заимствованное посреди Draw, поэтому ранее допущенный объём может сохраняться до безопасного retirement. PNG upload преобразует straight RGBA в premultiplied RGB только при cache insertion, не на каждом hit; alpha/PNG bytes/PCA-mask сохраняются. Ошибка readback/upload не публикует ресурс.

<a id="configuration"></a>
## Где менять настройку, а не контракт

Полный живой inventory — [pipeline_visual_config.py](../LocalGenerator/infini_local/pipelines/pipeline_visual_config.py), [vfx_manifest_config.py](../LocalGenerator/infini_local/core/vfx_manifest_config.py), [settings_schema.py](../LocalGenerator/infini_local/desktop/settings_schema.py), [config registry](../contracts/config_registry.json) и [config example](../LocalGenerator/config.example.env). Это не копия старой таблицы defaults/строк аудита.

- `INFINI_IMAGE_MAX_CONCURRENCY` задаёт backend gate, default 1, range 1..4; endpoint combine/multidev semaphores не заменяют его. Gate не охватывает CPU/postprocess/publication.
- `INFINI_VISUAL_ASSET_MODE` ограничивает materialization; обязательный authored asset, отключённый настройкой, не становится optional для delivery. Exact `assetMode`/Visual project выбирает Director, не старый GUI role toggle.
- Backend/model/seed/variants и sd.cpp profile arguments остаются в adapters/config; настройка не разрешает скрытый provider switch. Для Codex OAuth см. [его operations guide](CODEX_IMAGE_OAUTH_RU.md).
- Sprite keyer/master/downscale/stage/retry knobs меняют техническую обработку, не authored grip, palette, event или gameplay. Transparency contracts — [Visual metadata](VISUAL_PRESENTATION_METADATA.md#image-contract).

<a id="verification"></a>
## Проверка и границы

Регрессии покрывают последовательную role collision, overlapping requests при gate=1, точные backend IDs/seeds, реальную PNG-обработку и serving bytes, failure phases/cleanup, оба типа selectors, frozen Repair, storage refusal/quarantine и реальные C# DTO/texture consumers. Retained rendering проверяется отдельно на native FNA/GPU.

Offline provider responses и native fixture PNG являются явно ручными тестовыми данными. Эти проверки не означают live image-model quality, Terraria game-loop, двухклиентный MP или измеренное ускорение генерации. Ошибка диска больше не тратит дополнительные image requests, но обычная генерация всё ещё ограничена временем выбранного backend; FPS и latency улучшения без замеров не заявляются.

Текущие owners: `test_image_attempt_contracts.py`, `test_image_adapter_contracts.py`, `test_vfx_ingredient_generation_contracts.py`, `test_sprite_render_contracts.py`, `test_vfx_dependency_delivery_contracts.py`, `test_asset_transfer_cache_contracts.py`; C# — existing registered `EngineRuntimeChecks` partials. Команды и scope доказательства — [test owners](TEST_CONTRACT_OWNERS_RU.md). Исторические предложения image flags не выдаются за текущие defects/coverage: [decision record](VISUAL_AUDIT_HISTORY_RU.md#image-flags).
