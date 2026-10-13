# Архитектура и границы authority

InfiniCrafterLocal состоит из Python authoring/asset pipeline и typed tModLoader executor. Модель выбирает дизайн; код проверяет объявленные контракты, технически проецирует их и исполняет. [Карта исходников](CODE_MAP_RU.md) · [Рабочие границы модулей](MODULES_RU.md) · [Задача → owner](OWNERS_RU.md).

<a id="pipeline"></a>
## Как craft проходит систему

```text
Station A/B inputs
  → host/server admission + escrow
  → GeneratorClient → HTTP /combine
  → world recipe cache либо fresh Author
  → deterministic validation → scoped Repair при отказе
  → compiler/lossless lowering → strict runtime wire
  → Visual → VFX → required image generation + delivery gate
  → world-scoped recipe + final PNG/descriptors
  → host pending transaction → durable outcome → spawned result
  → registry/hydration + asset sync → per-instance item/projectile executor
```

[Три стадии](THREE_STAGE_LLM_PIPELINE_RU.md#flow) задают handoffs/accounting: baseline fresh craft — Author → Visual → VFX → image pass. Cache hit/dev fixture не означает три новых LLM вызова. [Frozen-first Repair](TARGETED_REPAIR_PROTOCOL_RU.md#frozen-first) условен, bounded и относится только к invalid leaves/exact dependencies отвергнутой стадии; accepted context read-only. Это не judge/critic и не restart валидных стадий.

<a id="authority"></a>
## Кто принимает решения

| Authority | Canonical owner / контракт |
|---|---|
| Gameplay, primary и result identity | Gameplay Author; [Author shape](../reference/LOW_LEVEL_RUNTIME_AUTHORING_RU.md) |
| Finite mechanical/event/param facts | `capability_registry.py`; [source map](CODE_MAP_RU.md#python) |
| JSON shape / mutable Repair scope | `program_schema.py`, `repair_scope.py`, shared frozen merge |
| Validation / projection / strict wire | `validator.py`, `compiler.py`, `technical_lowering.py`, `wire_validator.py` |
| Visual/VFX | Своё authored представление поверх read-only accepted gameplay; [handoffs](THREE_STAGE_LLM_PIPELINE_RU.md#flow) |
| World recipe / health / asset publication | [Recipe owner](../reference/RECIPE_HEALTH_AND_CONTRACTS_RU.md), [image lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md) |
| Craft/placement/material claims | Host/server + отдельные durable state owners ниже |
| Runtime / multiplayer / drawing | [C# consumers](CODE_MAP_RU.md#csharp), [module boundaries](MODULES_RU.md#runtime-presentation) |
| Studio/config/process lifecycle | Existing native controller + browser adapter; [UI boundary](MODULES_RU.md#studio) |

Registry объявляет runtime `infini.runtime-program.v5`, fresh Author `infini.runtime-program.authoring.v5`, persisted wire `infini.runtime-program.wire.v3`. Entities/bindings/calls, movement/controller slots, event/rate/lifetime/depth limits задаются live registry/schema/validator, не copied counts в обзоре. Это конечная композиция, не arbitrary ECS/VM/generated C#.

Whole-weapon macros, semantic family/profile routers, legacy weapon IR и migration/cache importer запрещены. Name/category/tags/prose не выбирают механику. Четыре класса преобразований — [Fallback / Fix / declared Normalization / lossless Alias](TECHNICAL_LOWERING_POLICY_RU.md#transformations); generated [boundary](../reference/generated/LOWERY_RU.md) и receipts не являются вторым registry. Новая capability завершается только [полным vertical slice](ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md).

<a id="primary"></a>
## Primary и identity

[Primary/use contract](../reference/LOW_LEVEL_RUNTIME_AUTHORING_RU.md#primary-use) задаёт explicit primary, независимые contact/action lanes и placement cost. Wire primaryOwner реально управляет noMelee/contact/heldProj/animation, не только telemetry; secondary spawn/урон не передают ownership. Shared proxies исполняют per-instance definition, не type-wide weapon flags.

Имя и категория authored. `bad_result_name` в `pipelines/final_normalize.py` отказывает craft с refund, не генерирует замену. `result_identity_policy.normalize_category` сохраняет legacy metadata normalization (в том числе `generic` для неизвестного значения); это не обход strict Author enum и не gameplay routing. Parent hints/debug не дописываются в tags, category sampling/name generator не восстанавливаются. Finite localized feedback из typed executable facts разрешён; authored tooltip prose — нет.

Fresh Author shape и persisted wire/recipes имеют разные readers/provenance: retirement grammar не удаляет принятую вещь. Units/neutral/zero/absence и original numeric admission — [MODEL_FACING_UNITS](../reference/MODEL_FACING_UNITS_RU.md), [DTO boundary](MODULES_RU.md#contracts), не эвристика по DamageClass/категории.

## Transport не выбирает gameplay

Cache-marked stage packets самодостаточны и не используют Responses history. Это **не** глобальный запрет continuation: unmarked запросы из двух system/user messages могут продолжать `previous_response_id` внутри той же item lease. Cache marker исключает continuation/очищает chain; failover её сбрасывает. Owners — stage request builders и `pipelines/llm_transport.py`; [cache/latency](LLM_PROMPT_CACHE_AND_LATENCY_RU.md), [request shape](LLM_TRANSPORT_REQUEST_SHAPE_RU.md), [provider admission](LLM_PROVIDER_ADMISSION_RU.md).

Multi-dev lanes — операционная изоляция, не Author capability. `/multidevcraft 2|3` даёт отдельные A/B escrow/request/task/progress/refund и pin к `llm_1/2/3` без profile/model hopping. Обычный single-lane сохраняет transport round-robin/failover. Profile добавляется только в multi-dev world recipe cache identity, не wire/schema; upstream provider pin — отдельная настройка.

<a id="profiles-world"></a>
## Три разных владельца persistent state

| State | Owner | Что не передаётся другому слою |
|---|---|---|
| World recipe definition/cache | `storage/world_storage.py` / `world_recipe_runtime.py` | Health/trace — производные, не новый author/importer |
| Station A/B escrow и exactly-once craft outcome | `GeneratedStationEscrowStateSystem` + `InfiniCraftPlayer` | UI/HTTP response не коммитят материал и не становятся refund owner |
| Placed material group, pending return, prefix/quarantine | Все `GeneratedPlacementLedgerSystem` partials | Read-only body/light/cache не создают второй ledger |

MP client отправляет lane и compact parent refs; host/server проверяет unlock/реальные slots и единолично коммитит result. World escrow journal использует устойчивый client token; capacity reject происходит **до** mutation, outcomes не вытесняются ради нового запроса. В живой серверной сессии bearer token закреплён за одним экземпляром игрока: смена token/одновременный второй игрок отвергаются до recovery, reconnect разрешён после ухода прежнего экземпляра. Это session pinning, не аутентификация личности.

Материализация требует ещё pending transaction того же owner/lane и свободный world item slot. Durable расход коммитится с outcome до отправки результата; failure до commit удаляет новую allocation, если native spawn уже вернул её; transport failure после commit не возвращает потраченные inputs. Сторонний `ItemLoader.OnSpawn` exception **до возврата** `Item.NewItem` находится вне rollback guarantee: caller ещё не получил allocation identity. [Native craft lifecycle](NATIVE_CRAFT_LIFECYCLE_QOL.md) — подробный owner этого контракта.

Break размещённой вещи переводит group в world-persistent pending return **до** выдачи. Полный/cooling pool — retry, не потеря 100% material claim или новый refund. Corrupt definition/prefix сохраняется буквально в quarantine, не заменяется vanilla/unprefixed вещью; healthy saved definition может восстановить отсутствующую registry entry. Prefix witness, typed int-zero admission и независимый placed-light — [module contract](MODULES_RU.md#craft-placement).

<a id="runtime-trust"></a>
## Runtime trust, assets и доказательства

C# принимает strict DTO/inputs/opcodes/references и исполняет bounded bindings/entities/events. [Terraria standardization](../reference/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md) определяет finite engine mappings/custom surface. Unknown contract/version/opcode — fail closed; native source/version guards не заменяются guessed dispatch.

Owner-hit использует vanilla owner trust. `RuntimeHitPullBridge` — receipt, **не collision proof**: server берёт actions/params из своей authored definition, wire не передаёт damage/buff/force. Identity/lifecycle fencing/budget/sync не доказывают независимую server collision validation. Исторические execution/MP findings — [typed audit history](../archive/HISTORY_RU.md#typed), не current all-modes stamp.

[Image lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md) владеет request/attempt/atomic publication/delivery. Shared IDs не дублируют jobs; required PNG не заменяется placeholder, filesystem nonce не authored identity. Registry hydration и PNG chunks сохраняют собственных state owners; transient drawing до hydration не делает failed generation успешной.

Registry witnesses, schema/AST/range parity, frozen merge, mutation и stage accounting доказывают **проверенные seams**. Команды — [TESTING](TESTING_RU.md), [BUILD](BUILD_RU.md), [AGENTS](../../AGENTS.md#обязательный-vertical-slice). Headless DTO replay/no-image pipeline не проверяет game loop/art/GPU/MP delivery; native observer не равен socket match. Неисполненный уровень — `notRun`, независимо от старого PASS/count или registration. Исторические UI/fixture limits и отсутствующая cursor-check registration отмечены в [MODULES](MODULES_RU.md#verification).
