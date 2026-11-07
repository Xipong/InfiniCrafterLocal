# Трёхстадийный LLM pipeline

[System authority](../architecture/ARCHITECTURE_RU.md#authority) · [Author](../../reference/authoring/LOW_LEVEL_RUNTIME_AUTHORING_RU.md) · [Repair](TARGETED_REPAIR_PROTOCOL_RU.md)

<a id="flow"></a>
## Happy path и handoffs

| Стадия fresh LLM craft | Baseline calls | Принятый output / следующий consumer |
|---|---:|---|
| Gameplay Author | 1 | Strict validation → technical compile → typed wire; entities/visual roles и raw parent facts → Visual |
| Visual Director | 1 | Entity-based visual kit; accepted gameplay + visual context → VFX |
| VFX Director | 1 | Finite slots над exact `entityId + event`; самостоятельные image ingredients → общий image pass |
| Repairs | 0 | Нет при валидных outputs |

После **трёх текстовых стадий**: asset runtime gates → image generation → visual delivery → parent summary → final normalize/runtime/VFX gates → stage accounting → world metadata/health → sanitize → final cached-payload check → atomic recipe commit. VFX asset ID, общий нескольким элементам, не требует отдельной image job на каждый элемент. Required PNG нельзя заменить placeholder. Visual/VFX не добавляют gameplay и не выбирают weapon family.

Stage-level Gameplay admission/compile/wire/conditional Repair находится в [gameplay_stage](../../../generator/infini_local/pipelines/author/stage.py); VFX transport — в [vfx_generation_pipeline](../../../generator/infini_local/pipelines/vfx/request.py). Их внутренние imports не являются compatibility API.

Parent context: `context/cards.py.raw_parent_card_for_llm` собирает Author/Visual packets из source facts и exact accepted generated runtime. `context/parents.py` извлекает current native numeric/projectile/ammo facts, generated parents сохраняют полный exact graph без single-projectile compatibility projection; identity primitives принадлежат `core.item_identity_tools`. Parent prose — advisory context, не authority или отдельная knowledge/category/power стадия. Provenance, zeros/false и Visual-only appearance сохраняются в соответствующем handoff.

Orchestration owner — [combine_pipeline.combine](../../../generator/infini_local/pipelines/combine_pipeline.py); assets — [image lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md) / [VFX materials](../../reference/presentation/VFX_MATERIAL_ELEMENTS_RU.md). Cache/dev path отдельно от fresh LLM craft.

## Сохранение принятых стадий

`combine` под существующим recipe-generation lock сохраняет accepted compiled Author, Visual kit и VFX manifest через `storage/craft_progress.py`, до image hydration. Это persistence принятого wire, не migration, Repair или новый authored fallback. Snapshot проверяется checksum всего envelope, exact identity (полные родители/world/lane/contracts), текущими wire/Visual/VFX validators и accounting. Принятый Author повторно не компилируется и не запрашивается. Смена connection/model settings не инвалидирует принятый дизайн; `USE_LLM`/dev mode и stamps контрактов входят в identity. Перестановка родителей восстанавливает исходный порядок.

`atomic_write_json` завершает запись до следующей стадии; I/O ошибки не преобразуются в новые платные запросы. Неподдерживаемый/повреждённый checkpoint сохраняется с явной ошибкой; несовпадение целых входов/контрактов начинает новый дизайн. Committed cache читается первым, cleanup checkpoint после commit best-effort. `.checkpoint` и атомарные `.tmp` не допускаются asset filename boundary. PNG receipts и reuse здесь отсутствуют; существующие image workers/retries/joins не меняются. Локальный lock сериализует потоки одного генератора, не несколько процессов.

Behavioral tests: `test_generation_resume.py` проверяет реальные stages, transport-only doubles, restart в независимых интерпретаторах, Repair/cancellation, cache precedence, private delivery boundary и I/O отказ без reauthor. Неуспешная запись первой стадии не может обещать восстановление результата после потери процесса.

<a id="repairs-accounting"></a>
## Conditional repairs и accounting

Executable Gameplay rejection открывает только Gameplay Repair; required Visual contract rejection — Visual Repair; VFX rejection — VFX Repair. Optional `concept`/`realization` и текстовый `selfEvaluation`, как и Visual `animationPlan`, advisory: их отсутствие/оформление не вызывает Repair и не блокирует валидный executable/art contract. Однозначный syntax-only дефект initial Author/Visual JSON исправляется локально с `fix:llm_json_syntax`, затем идёт обычная validation; неполный/неоднозначный источник отклоняется без дополнительного модельного вызова. Единственный scoped Repair остаётся для содержательной ошибки. Ошибка image generation/final delivery не разрешает новый бесконечный reauthor loop.

[Frozen-first protocol](TARGETED_REPAIR_PROTOCOL_RU.md#frozen-first) применяется во всех трёх доменах: exact invalid leaves/dependencies, read-only accepted context, audit проигнорированных лишних правок, полная повторная валидация. Repair предыдущий валидный stage не перезапускает; обязательного judge/critic нет.

`llmStageAccounting`: `gameplayAuthorCalls`, `gameplayRepairCalls`, `visualDirectorCalls`, `visualRepairCalls`, `vfxDirectorCalls`, `vfxRepairCalls`. Fresh happy path — `1/0/1/0/1/0`; каждый repair count не более одного. [Topology gate](../../../generator/infini_local/pipelines/combine_pipeline.py) проверяет это перед commit. Это logical stage calls, не обещание ровно трёх HTTP attempts: transport compatibility retries считают отдельно.

## Статические инструкции и provider cache

Каждый production builder (Author/Visual/VFX, их scoped Repair) создаёт complete JSON DEVELOPER с явно выбранными application-owned rules/catalog и complete JSON USER с оставшимися данными. `core/llm_prompt_cache.py:with_instruction_segments` не угадывает authority по повторяемости: только builder перечисляет instruction members. Parents/tooltips, accepted runtime, errors, invalid fragments, fieldPermissions/create-policy и item-specific output schema остаются USER. Состав объединённого dossier и frozen merge не меняются; trace сохраняет все сообщения.

Visual отдельно выделяет application-owned `spritePresentationReadOnly` (units/axis/formulas, registry descriptions и ownership rules) в DEVELOPER; выбранный runtime role roster `bakeFillByProcessingRole` и `acceptedPresentationMechanicsReadOnly` — USER. Scoped Repair выбирает нужные части guidance по exact editable paths: size-only сохраняет calibration, mechanics и parent visual references без повторного полного design dossier. Accepted visual source не обрезается. Entity-specific responseSchema и Repair permissions не повышаются до instruction authority.

Initial Visual/VFX и Repair с нужными invariant nodes включают явно выбранные application-owned canonical output grammar nodes в **тот же полный DEVELOPER** `schemaDefinitions={"$defs":…}` рядом с rules. VFX берёт `element/path/screenShake/particle/sound` непосредственно из schema владельцев `core/vfx/schema.py`/`core/vfx/materials.py`; Visual — `item` либо частичный `itemPatch` из `_visual_item_schema` и существующей provider projection. Остальная schema использует `#/$defs/…`; объединение definitions и case schema — та же JSON Schema grammar, не новый набор правил. Exact entity/event enums, item-body/texture/history clauses, configured limits, equipment branches и все Repair facts остаются case USER. Authority определяется владельцем grammar, не cacheability; runtime facts не повышаются до DEVELOPER.

Внутренний `_infini_prompt_cache={instructionMessageIndex:1}` объявляет конец полного DEVELOPER. Валидатор требует adjacent DEVELOPER/USER, disjoint nonempty objects, точные metadata keys и strict JSON: nested/escaped duplicates, NaN/Infinity/`1e999`, неверные roles/indices и overlaps отвергаются до send. Author/Gameplay Repair сохраняют прежний marker и wire/key bytes. Scoped Visual/VFX сохраняют протокол marker, но содержимое и identity отражают реально отправленную сокращённую grammar.

`response_format` содержит **полную inline provider schema текущего запроса**; у scoped Repair это permission-derived grammar, не весь initial design domain. Provider constraints не заменяются внешними refs. При json_object/off все поля остаются доступны через schemaDefinitions + case schema. Key включает весь declared static prefix и effective model/reasoning/format framing; для grammar framing case-specific full response schema исключена только из routing identity, не из запроса. Изменение definitions инвалидирует key, изменение runtime enums/parents/Repair tail — нет. Это не обещает, что provider сможет reuse prefix при смене structured schema.

`pipelines/transport/client.py` вычисляет content identity до dynamic USER. Native Codex сохраняет typed DEVELOPER/USER без demotion; Author JSON marker, key и `session-id` affinity byte-identical. Generic Responses сохраняет explicit developer, неизвестные roles отвергает вместо demotion. Только точный Nous Chat endpoint + OpenAI model получает измеренный `prompt_cache_key` и invariant final USER `JSON response.` (один раз); ни retention, ни Platform breakpoints, ни новые affinity headers ему не приписываются. Остальные optional controls остаются endpoint-allowlisted. Marker/key — не доказательство cache hit: это только raw provider cached-token counters на разных fresh tails.

Offline contract: `test_craft_instruction_segments.py` и `test_stable_schema_data.py` проходят все шесть builders через реальные senders с остановкой до auth/network: Nous/OpenAI/OpenRouter Chat, native Codex и OpenAI Responses × json_object/json_schema/off. Проверяются roles, полный provider schema, static/key invariance, parent/runtime-enum tail controls, canonical owner revision invalidation, valid/invalid `$defs` validator parity и malformed declaration refusal. Semantic tests читают derived dossier через `prompt_packet_helpers.py`, не подменяя production packets. Live/game/GPU acceptance отдельно.

Transport retries и self-contained requests — [отдельная boundary](../architecture/ARCHITECTURE_RU.md#pipeline), не новые authoring stages. [Provider-aware admission и quota feedback](../providers/LLM_PROVIDER_ADMISSION_RU.md): известный Nous OpenAI route не получает выдуманный char/4 token window; unknown routes сохраняют conservative policy, FIFO/deadline/429 общие. Offline tests: `test_low_level_three_stage_pipeline.py`, `test_pipeline_repair_contract.py` из [test owners](../TESTING_RU.md); green не означает live/game/MP прогон.

На обратной границе Responses reader берёт только `output_text` из typed assistant message, не текст reasoning/tool records; standalone `output_text` остаётся совместимым входом, когда typed message отсутствует. Общий JSON reader отдаёт приоритет единственному явно выделенному JSON/безымянному fenced block над JSON-примерами в окружающем тексте. Тело такого блока передаётся целиком: невалидный финальный ответ не заменяется первым подходящим примером, а несколько или незакрытый output block отвергаются. Без явного блока сохраняется прежний scanner. Это выбор transport framing, не исправление авторских полей: далее по-прежнему выполняются strict shape, exact permissions и frozen merge; парсер не выбирает ответ по успешности schema validation.

## Транспортные попытки и reasoning policy

`INFINI_LLM_NETWORK_ATTEMPTS=1` допускает не более одного generation dispatch на
логический вызов, включая schema/protocol negotiation, transient retry и pool failover.
Generic Chat/Responses используют общий dispatch guard; native Codex идёт напрямую
в `codex_auth.post_sse -> _generation_request`, где тот же N ограничивает sends
одного сериализованного запроса без внешнего retry/failover. Общий deadline
передаётся Codex как оставшееся время. Уже подтверждённый capability cache может
выбрать поддерживаемый формат сразу, без второго запроса.
При `N>1` сохранена существующая политика transient attempts выбранного профиля
и технического согласования/failover; число не переопределено как новый глобальный
максимум запросов всех профилей. Один deadline охватывает весь логический вызов.

Malformed/length JSON возвращается владельцу стадии без скрытого reroll исходного
задания и без изменения reasoning intent. `medium` остаётся рекомендуемым default;
явный effort/`off` не повышается ни у Author, ни у Repair. `off` опускает effort,
а не обещает выключить внутреннее reasoning провайдера; `none` переводится по
контракту выбранного API. Для Codex Visual/Visual Repair собственный
`INFINI_CODEX_VISUAL_REASONING` сохраняет приоритет над общим mode.

`apply_llm_common_options` сохраняет только внутренний configured mode, не floor.
Диагностика до отправки и итоговый transport debug содержат `configuredReasoningMode`,
`requestedReasoning` и `effectiveReasoning` фактического provider wire. В local
`effectiveReasoning` пуст; у Codex off нет effort, но сохраняется `summary=auto`.
Эти поля показывают запрос API, не измеренный внутренний effort модели. Внутренний
mode не уходит провайдеру. Сравнение качества low/medium не проводилось.
