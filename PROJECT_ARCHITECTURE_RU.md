# InfiniCrafterLocal v0.4.248 — архитектура и границы authority

[Карта исходников](PROJECT_MAP_RU.md) · [Author-контракт](docs/LOW_LEVEL_RUNTIME_AUTHORING_RU.md) · [Repair](docs/TARGETED_REPAIR_PROTOCOL_RU.md) · [Generated boundary](lowery.md)

<a id="authority"></a>
## Кто принимает решения

Gameplay Author создаёт bounded runtimeProgram из конечных capabilities. Код валидирует, losslessly проецирует typed wire и исполняет exact opcodes; не выбирает дизайн из category/name/prose. Whole-weapon macros, semantic family/profile routers, arbitrary VM/generated C# и legacy weapon IR не являются architecture; старые schema/cache/replay не мигрируются.

| Authority | Canonical contract |
|---|---|
| Gameplay, primary, result identity | [Author shape/construction](docs/LOW_LEVEL_RUNTIME_AUTHORING_RU.md) |
| Grammar/shape/validation/compiler/wire | [Source owner map](PROJECT_MAP_RU.md#python); generated docs не shadow registry |
| Преобразования | [Fallback/Fix/declared Normalization/lossless Alias](docs/TECHNICAL_LOWERING_POLICY_RU.md#transformations) |
| Visual/VFX | [Stage handoffs](docs/THREE_STAGE_LLM_PIPELINE_RU.md#flow), accepted gameplay read-only |
| Storage/health/assets | [World recipe owner](docs/RECIPE_HEALTH_AND_CONTRACTS_RU.md), [image lifecycle](docs/IMAGE_ASSET_LIFECYCLE_RU.md) |
| Execution/net/world transactions | [C# consumers](PROJECT_MAP_RU.md#csharp), trust boundaries ниже |

[Registry](LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py) объявляет runtime API `infini.runtime-program.v5`, Author `infini.runtime-program.authoring.v4`, wire `infini.runtime-program.wire.v3`. Schema/validator/registry владеют finite composition limits (entities/bindings/calls, child depth, events/rate/lifetime, movement/controller slots), не копируемые counts в обзоре. Это не ECS/VM общего назначения.

<a id="pipeline"></a>
## Стадии и transport

[Pipeline](docs/THREE_STAGE_LLM_PIPELINE_RU.md#flow) владеет порядком, handoffs и accounting: fresh Author → Visual → VFX → image pass. Cache hit/dev fixture не три новых LLM вызова. [Frozen-first Repair](docs/TARGETED_REPAIR_PROTOCOL_RU.md#frozen-first) условен и bounded, не judge/critic или restart валидной стадии.

Cache-marked stage packets самодостаточны и не используют Responses history. Это **не** запрет continuation во всём transport: unmarked запросы из двух `system/user` messages могут продолжать `previous_response_id` внутри той же item lease. Cache marker исключает continuation и очищает chain; failover также её сбрасывает. Owners: [request builders](LocalGenerator/infini_local/pipelines/llm_authoring_pipeline.py), [transport](LocalGenerator/infini_local/pipelines/llm_transport.py); provider-specific ограничения и usage — [cache/latency](docs/LLM_PROMPT_CACHE_AND_LATENCY_RU.md), [request shape](docs/LLM_TRANSPORT_REQUEST_SHAPE_RU.md), [OpenRouter](docs/OPENROUTER_ROUTING_RU.md).

<a id="primary"></a>
## Primary, identity и lifecycle

[Primary/use contract](docs/LOW_LEVEL_RUNTIME_AUTHORING_RU.md#primary-use) владеет explicit primary selection, независимыми contact/action lanes и placement cost. Wire primaryOwner исполняем: noMelee/contact/heldProj/animation ownership, не telemetry; secondary spawn/урон не передают ownership.

Имя и категория authored. `bad_result_name` в [final normalize](LocalGenerator/infini_local/pipelines/final_normalize.py) отказывает craft с refund, а не генерирует замену. [normalize_category](LocalGenerator/infini_local/pipelines/result_identity_policy.py) сохраняет legacy metadata vocabulary normalization (в том числе `generic` для неизвестного значения); это не разрешение обойти strict Author enum и не gameplay routing. Parent hints/debug не впрыскиваются в authored tags; удалённые category sampling/coercion и шаблонный name generator не восстанавливаются.

<a id="profiles-world"></a>
## Профили, cache и world ownership

Multi-dev station lanes — операционная изоляция, не дополнительная Author capability. `/multidevcraft 2|3` разблокирует отдельные A/B escrow, request/task/progress/refund; lanes пинятся к `llm_1/2/3` без profile/model fallback. Обычный single-lane craft сохраняет transport round-robin/failover. Profile входит только в multi-dev world recipe cache identity, не меняя item wire/schema; upstream provider pin — отдельная настройка transport.

MP client передаёт lane и compact parent refs. Host/server проверяет unlock, изымает exact escrow и единолично коммитит generated result. [GeneratedStationEscrowStateSystem](ModSources/InfiniCrafterLocal/Common/Systems/GeneratedStationEscrowStateSystem.cs) хранит world-owned escrow и exactly-once outcome/craft journal по устойчивому client token; при capacity reject происходит до mutation, outcomes не вытесняются ради нового запроса.

Рецепты — strict world-scoped files с quarantine, stamps и производным health; [storage/health](docs/RECIPE_HEALTH_AND_CONTRACTS_RU.md#storage) не является migration/importer. Размещённая generated вещь хранится отдельно в [GeneratedPlacementLedgerSystem](ModSources/InfiniCrafterLocal/Common/Systems/GeneratedPlacementLedgerSystem.cs): слом превращает placement в world-persistent pending return той же вещи до попытки доставки. Полный inventory не даёт право потерять durable return. Recipe cache, station escrow и placed-item ledger — разные authorities.

<a id="runtime-trust"></a>
## Runtime, assets и предел доказательства

C# принимает strict DTO, exact inputs/opcodes/references; item/projectile hooks исполняют bounded entities/events, а не читают prose для выбора механики. Terraria mappings и намеренно custom/hidden surface — [standardization](docs/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md).

Owner-hit использует vanilla owner trust. [RuntimeHitPullBridge](ModSources/InfiniCrafterLocal/Common/Runtime/RuntimeHitPullBridge.cs) — receipt, **не collision proof**: сервер берёт actions/params из своей authored definition, wire не сообщает damage/buff/force. Lifecycle/identity fencing и budget/sync не доказывают независимую server collision validation. Подробные исторические execution/MP findings — [typed primitive audit](docs/HISTORY_RU.md#typed), не текущий all-modes acceptance stamp.

[Image lifecycle](docs/IMAGE_ASSET_LIFECYCLE_RU.md) — canonical request/attempt/publication owner; [VFX materials](docs/VFX_MATERIAL_ELEMENTS_RU.md) — renderer/texture/asset dependencies. Shared IDs не дублируют jobs, required PNG не placeholder, filesystem nonce не authored identity.

Registry witnesses, AST loss/range parity, frozen merge, mutation и stage-accounting tests доказывают проверенные seams. Их актуальные команды — [AGENTS](AGENTS.md#обязательный-vertical-slice) и [test owners](docs/TEST_CONTRACT_OWNERS_RU.md). Исторические counts не являются текущей гарантией. Headless DTO replay/no-image pipeline не проверяет игровой world loop, art quality или MP packet delivery; build/smoke — только фактически запущенные, иначе `notRun`.
