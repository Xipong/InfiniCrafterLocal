# Gameplay Author — authored shape и construction contract

[Generated boundary](generated/LOWERY_RU.md) · [Source owners](../development/CODE_MAP_RU.md#python) · [Repair](../development/TARGETED_REPAIR_PROTOCOL_RU.md) · [Neutral omissions](DECLARED_NEUTRAL_OMISSIONS_RU.md)

Это human projection, не owner schema/registry. Exact shape — [program_schema.py](../../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py); model-facing prose — [author_item_contract.py](../../LocalGenerator/infini_local/pipelines/author_item_contract.py). Inventory/units/wire facts генерируются в [capability inventory](generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) и [primitive parity](generated/PRIMITIVE_PARITY_RU.md); технический manifest не надо копировать в LLM-каталог.

<a id="response"></a>
## Author response

Текущий root содержит `name`, `category`, `concept`, `runtimeProgram`, `realization`. `runtimeContract` с compiler receipts не authored root field. `runtimeProgram` задаёт `apiVersion`, Author `schema`, один `primaryEntityId`, явные `entities[]` (`id/kind`), `bindings[]` (`id/input/action/stackCost/contactDamage`) и `calls[]` (`id/fn/target/params`). Exact required/optional keys — в schema, не в этом сокращённом перечне.

Current Author `infini.runtime-program.authoring.v5` задаёт независимые flat lanes `action`, `stackCost`, `contactDamage`. Saved wire v3 сохраняет nested `usePolicy`. Новый binding skeleton единообразен: `{id,input,action:{kind,targetId},stackCost,contactDamage}`. Исторические sparse bindings остаются valid: точные fixed literals можно явно передать или опустить — `hold.kind=spawn_entity`, `equipped.kind=equip_passive`, item-body-only `targetId` равен exact unique declared body ID, `hold/equipped` cost/contact равны integer `0`/boolean `false`, `place_item` — integer `1`/boolean `false`. Неверные present kind/target/cost/type отвергаются без coercion. Это объявленная lossless wire equivalence, не выбор action: active non-placement stack/contact и разные actions остаются независимыми решениями. `placementCallId`, `effectGroupId`, `stackConsumeChancePercent` сохраняют свои conditional constraints. Repair сравнивает только exact equivalent transactions через существующий owner; принятую source presence/absence frozen-first merge не переписывает. Для новых calls предпочтителен единый явный `id/fn/target/params` envelope: `target` — точный существующий совместимый entity ID, включая объявленный ID единственного `item_body`, а zero-arg `params` — закрытый `{}`. Только прежние точные пропуски item-body-only `target` и zero-arg `params` остаются допустимы в той же grammar без migration, router или выбора default. Присутствующие поля никогда не игнорируются; строка `item` допустима лишь как реально объявленный ID, не alias. Projectile/mixed targets и active non-placement stack/contact остаются явными model choices. Calls присоединяют одну capability к одной entity; typed references связывают entities. Movement, controller, damage, targeting, input, attachment, body contact, lifecycle и event topology остаются независимыми решениями Author. Weapon macro и routing по name/category/prose запрещены; schema/validator не выбирают содержательную замену.

<a id="primary-use"></a>
## Primary и независимые use lanes

Author выбирает **один точный существующий** `primaryEntityId` для lifecycle/held representation. Calls/bindings не содержат authored `role`; compiler материализует wire `binding.role=primary` только при `binding.usePolicy.action.targetId == primaryEntityId`, иначе `secondary`; kind выбранной entity даёт `primaryOwner=item_body|projectile`. Это mandatory projection, не compression и не эвристика.

Item graphic/body-contact representation принадлежит `item_body`. Projectile может стать primary только при явно authored projectile lifecycle/held ownership. Узкий invariant: если все active bindings spawn-ят одну entity, `contactDamage=false` и `configure_item_use.hideUseGraphic=true`, exact spawn target должен стать owner — невидимый body use не представляет. Факт spawn, damage, категория и название сами по себе primary не выбирают.

Один exclusive input имеет один root binding, но **не одну damage lane**. `contactDamage` независим от `action`; например, Starfury-like tuple (фрагмент binding, не полный response):

```json
{"input":"primary_use","action":{"kind":"spawn_entity","targetId":"falling_star"},"stackCost":0,"contactDamage":true}
```

При primary body он сохраняет item hitbox и spawn-ит secondary projectile, который не отбирает `heldProj`/animation. Для `place_item`, `hold`, `equipped` Author передаёт boolean `contactDamage=false` или сохраняет исторический пропуск; Lowery записывает в wire то же фиксированное `false`, поскольку consumers эту contact lane не исполняют. Flail/yoyo/whip/holdout — примеры explicit projectile ownership, не распознаваемые families. Edge-case fixtures: `workbench_blade` (body + projectile), `door_on_chain` (projectile-owned flail); внешние [Starfury](https://terraria.wiki.gg/wiki/Starfury)/[Flails](https://terraria.wiki.gg/wiki/Flails) поясняют примеры, но authority — текущие consumers.

`stackCost=1` расходует **целую единицу** generated item на active use; projectile return не возвращает предмет и не является hidden charge counter. Reusable throw выбирает `0`. Для `place_item` Author передаёт integer `stackCost=1` или сохраняет исторический пропуск, а Lowery записывает то же фиксированное `1`; предмет escrowed в world placement ledger и возвращается тем же generated item при сломе, не «навсегда расходуется». Reusable hybrid с placement и active `spawn_entity/use_item_body` при `stackCost=0` требует `maxStack=1`: одна durable вещь меняет inventory/placed form. One-shot non-placement use с cost `1` не подпадает под этот конкретный maxStack rule.

Явная optional `stackConsumeChancePercent` (0..100) разрешена только active non-placement
binding с `stackCost=1`: вероятность применяется после completed use. Отсутствие
сохраняет deterministic расход; placement/аммо не затрагиваются. Hybrid с шансом
сохранения собственного стека также требует `maxStack=1`. [Точные receipt/lifecycle правила](OWN_STACK_CHANCE_RU.md).

Для разных item effects основного и альтернативного use Author явно связывает `params.effectGroupId` calls с `apply_item_effects.effectGroupId`; отсутствие selector сохраняет ungrouped effects. `refresh_generated_effect_group_while_held` выбирает отдельную generated-utility группу удерживания. Точные ограничения, общий player mobility cooldown, quick use и Repair — [именованные группы эффектов](NAMED_ITEM_EFFECT_GROUPS_RU.md).

`configure_weapon_ammo` отдельно выбирает exact ammo category и initial speed basis для active `spawn_entity` shots. Terraria владеет выбором/расходом/экономией ammo и его вкладом в damage/knockback; authored entity сохраняет поведение projectile. `stackCost` остаётся стоимостью самого generated item. Полная граница и ограничения — [weapon ammo consumption](WEAPON_AMMO_CONSUMPTION_RU.md).

<a id="construction"></a>
## Прямое построение, не procedural self-check

Author выдаёт один immutable JSON в причинном порядке: начальный `concept` → executable `runtimeProgram` → `realization.description/playerExperience` → `realization.selfEvaluation`. Concept non-binding; расхождение диагностируется, не отвергает craft. Report и selfEvaluation — интерпретация Author, **не наблюдавшееся исполнение**.

Construction facts живут у своих owners, а не в повторных глобальных checklist. Порядок ответа задают system и `requiredJsonShape`; отдельные повторные `gameplayAuthoringStages`, `principle`/`reportEvidenceRule`/`literalSynthesisRule` и `forbidden` не передаются. Полные catalog cards, shape examples и диагностический selfEvaluation сохраняются во всех response modes, включая `json_object`/off: provider schema их не заменяет.

Call/binding spelling и точные fixed-literal omissions объясняются один раз в `fieldGuide.rowShapes` (`RUNTIME_ROW_SHAPE_RULE`); в Repair та же инструкция передаётся в `rules`. `bindingTarget` сохраняет targeting/contact semantics, `stackCost` — расход/escrow и optional chance, без повторного описания формы. Source-motion guidance живёт в `fieldGuide.projectileMotion`, отдельный header сохраняет предпочтение source tempo. У `present_placed_item_sprite` summary/params/requires владеют PNG, transforms и exact tile reference; overlay добавляет только certified footprint/refusal. Актуальный полный набор cards и executable grammar берётся из canonical registry; число capabilities — в generated inventory.

| Место в packet | Правило построения |
|---|---|
| `requiredJsonShape.runtimeProgram.calls` | Единый явный пример `id/fn/target/params` из canonical schema; прежние точные item-only/noarg omissions допустимы, значения параметров принадлежат карточке выбранной capability |
| `requiredJsonShape.runtimeProgram.bindings` | Шесть отдельных примеров из binding schema: active spawn/body/effects, placement, hold, equipped; это формы, не одна композиция или design defaults |
| `catalog.fieldGuide` | Units/ranges и refs через targetKinds/allowSelf/graphEdge; отсутствие не создаёт неявной нейтрали |
| `catalog.entityKinds` | Required components/position driver; stationary kind не требует controller и сам не стреляет: explicit periodic spawn может стрелять без NPC acquisition; free projectile use создаёт independent instance, не singleton minion |
| `catalog.inputs/bindingActions` | Один root action; hold/equipped passive, активное действие требует active-use binding; independent contact lane, placement/escrow |
| `catalog.events` | On-use/hit/crit producers, terminal distinctions, explicit periodic timing |
| Capability cards | Channel/charge/release, cadence/animation, reusable hybrid bounds |
| Глобальные invariants | ID uniqueness, exact primary ownership, acyclic graph и spawn/depth budgets |

Author и Repair используют одну проекцию формы call. В Repair показываются только формы, встречающиеся в scoped `callsUpsert` union; пустой union даёт пустой список примеров. Конкретные чужие capabilities не предлагаются как образцы. `readOnlySourceFragments.brokenFragments` остаётся источником полного существующего узла: копируются его обязательные поля, разрешено менять только точные permissions, принятые optional значения и отсутствие сохраняются. Формы binding получают ключи и selector literals от `program_schema.py`; единичные учебные значения принадлежат prose owner и никогда не подставляются в Author или Repair. Offline tests проверяют эти формы и реальные packets в `json_object`/`json_schema`; улучшение first-Author success rate ими не измеряется.

Форма `realization.selfEvaluation.planVsProgram` запрашивается у Author и Repair для полезной самопроверки, но её отсутствие или ошибки оформления остаются только raw shape diagnostics: сами по себе они не отменяют craft и не вызывают Gameplay Repair. Код не дописывает и не исправляет отчёт. Это изменение границы приёмки диагностического поля, не runtime-преобразование или fallback. `description`, `playerExperience`, `programVsReport` и их контейнеры сохраняют строгую проверку; gameplay choices/refs/dependencies и schema-derived resource bounds также остаются обязательными. Разрешённый `realizationReplacement` в Repair подчиняется той же границе; permissions и frozen-first merge не расширяются.

`planVsProgram.actionChecks` покрывает каждую planned action и executable input/event lane, включая aligned и added lanes; указывает exact runtime IDs, результат, intentionality и причину. `programVsReport.behaviorChecks` отдельно покрывает executable input/entity/event lanes против обоих report texts. Blanket aligned verdict не заменяет rows; непонятная семантика отмечается `uncertain`. `realization_execution_truth_for_llm()` остаётся источником Repair execution guidance; initial Author берёт оттуда диагностический selfEvaluation contract, а не новый judge-pass. Исторический builder замер — [отдельная запись](../archive/AUTHOR_DIRECT_CONSTRUCTION_RU.md#measurement), не обещание first-Author success rate.

<a id="validation-events"></a>
## Validation, events и compilation

Validator сообщает exact paths и проверяет shape/refs/slots/dependencies/producers/cycles/budgets; compiler пишет только declared wire paths с exact global/capability receipts. Opcode кодирует уже выбранное имя capability. [Neutral omission](DECLARED_NEUTRAL_OMISSIONS_RU.md#contract) разрешено только объявленным ParamSpec после полной проверки; прочие missing/invalid values — RED, не fallback.

Event producer alternatives берутся только из `EVENT_KIND_REGISTRY` и `ENTITY_KIND_REGISTRY.base_events`. Author/Repair выбирает один **полный** вариант и явно добавляет необходимые calls/bindings; код не вставляет producer. `spawn_entity_on_event`/`pull_on_event` при `event=periodic` требуют explicit `periodTicks` (6..3600), non-periodic его не требует; скрытый default 6 запрещён.

`spawn_entity_on_event` и `target_and_fire` явно выбирают независимые `damageBasis`/`knockbackBasis` (`authored_child` либо `live_parent`) и `damageMultiplier`. Live parent означает actual projectile fields в момент event/fire; delayed action сохраняет их при enqueue, charge уже включён, повторного применения player/class modifiers нет. Для item-body events допустим только `authored_child`. Missing fresh choices — RED. [Полный child combat contract](CHILD_COMBAT_INHERITANCE_RU.md) описывает snapshots, старый wire, strict provenance и runtime refusal.

Для projectile `pull_on_event(mode=target_to_entity)` направляет NPC к центру испускающего projectile, включая `on_hit`. При `delayTicks > 0` этот центр фиксируется при постановке события в очередь; другие hit-actions сохраняют центр поражённого NPC. В MP receipt использует центр проверенного server-side projectile, не координаты клиента.

Terminal meaning: `on_hit` требует collision; proximity detonation не hit. `on_expire` испускается при natural expiry и proximity detonation, не при любом early kill. `on_kill` покрывает terminal paths, включая collision/penetration/natural expiry/detonation; `on_tile_collision` — каждую collision. Bounce + только on_expire не обещает эффект на последнем ударе. [Runtime truth](../../LocalGenerator/infini_local/pipelines/llm_authoring_prompt.py#L229) и consumer остаются источниками этих различий.

Числовые units/точные conversions и отсутствующие wire aliases — [standardization](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md#units), не semantic repair. [Frozen-first Repair](../development/TARGETED_REPAIR_PROTOCOL_RU.md#frozen-first) не расширяет accepted design.

<a id="front-hand"></a>
## Независимое движение передней кисти

`move_front_hand` (opcode20) — явная низкоуровневая операция, не оружейный preset. Author выбирает её и все пять параметров; damage class, event graph, lifetime, item-use, contact lane и внешний вид остаются отдельными решениями. Точные dependencies/диапазоны принадлежат [registry catalog](generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md), а не этой навигационной заметке. Код не добавляет singleton, launch, motion или grip за модель.

Native pose использует руку H и collision center C = H + aimedAxis * authored hitboxOffsetPx. Hitbox остаётся штатным axis-aligned rectangle, не pixel blade/OBB; coherent art/offset требует согласованного authored дизайна. Поза проходит extension/retraction по завершённым active world ticks `floor(activeAIUpdates/(extraUpdates+1))`, выбирая ближайшую native stretch length, ties shorter. Duration не продлевает lifetime или itemAnimation. Initial axis и synced cursor mode выбираются явно.

Для sprite presentation Visual Director передаёт size/forward axis/atomic grip выбранного финального PNG: `reuse_item_icon` использует только root metadata; distinct `baked_sprite` — только entity metadata. `no_asset`/`runtime_geometry` не требуют этих PNG dependencies. Missing selected leaves идут в точный frozen Visual Repair, не выводятся из art/hitbox/названия. Старый `move_forward_then_retract` (code19) остаётся owner-center18px + triangular displacement, не управляет кистью и не превращается в новый driver; сохранённые рецепты не мигрируются.

<a id="visual-vfx"></a>
## Visual/VFX boundary и headless replay

Roles losslessly выводятся из accepted kinds; VFX slots ограничены существующими entities/events. Renderer → texture dependency, dedicated impact PNG, material ingredients и единый delivery gate принадлежат [VFX materials](VFX_MATERIAL_ELEMENTS_RU.md) / [PNG dependency owner](../development/IMAGE_ASSET_LIFECYCLE_RU.md#dependencies), а не Author.

Event consumers не обязаны иметь authored gameplay action ради VFX: `periodic` имеет свой producer, item-body `on_use` не зависит от spawn target, contact `on_hit` зависит от `contactDamage`, `place_item` не испускает `on_use`. Python и C# используют общий producer contract.

Offline Live20 DTO replay: `image_boundary.ndjson.finalContract` → `hydrate_no_image_fixture_assets` → настоящий `sanitize_recipe_for_delivery` → JSONL `{case,data}` → `tools/EngineRuntimeChecks.csproj -- --replay-contracts <path>`. QA PNG — техническая fixture, не артовый deliverable. Это проверяет `GeneratedItemData.FromJson` на указанном tModLoader, не world loop/render/MP.

Projection gates: `PYTHONPATH=LocalGenerator python tools/generate_lowery.py --check`, `python tools/generate_low_level_runtime_docs.py --check`; regressions — registry tests, three-stage/pipeline Repair tests из [test owners](../development/TESTING_RU.md).

## Независимый свет размещённого предмета

`add_placed_light(placementCallId,strength,color)` — отдельный явный выбор Gameplay Author. Reference указывает ровно same-item `configure_tile_placement`, исполняемый `place_item`; не выбирается из названия станции, SoulOfLight, категории или sprite. Strength обязателен в 0.01..1.5 (RGB coefficient, не радиус), color — обязательный canonical token. Отсутствующий call не добавляет `placedLight` и не излучает свет.

Compiler losslessly копирует выбранные листья в exact binding `usePolicy.action.placement.placedLight`, с association и parameter receipts. `present_placed_item_sprite` и свет независимы: можно выбрать любой из них или оба; два нарисованных огонька не создают два emitters. Старые held/projectile lights не меняются. Свет native tile сохраняется отдельно.

Runtime расширяет существующий placement group/witness/definition transport, не создаёт вторую ledger. Exact same definition hash, binding, world scope и committed rectangle удостоверяют один center tile. `PostUpdateEverything` отправляет authored RGB в штатный `Lighting.AddLight`; PNG/Visual и optional pose decoder не требуются: light берёт уже доказанный material rectangle, а failure PNG pose остаётся literal pending diagnostic. Native geometry ограничена certified 16x16/256 cells; независимые post-place actors не поддерживаются. Break и removal прекращают light, material возвращается по существующей ledger. World/mod unload очищают derived state. Malformed witness/foreign definition дают no-light quarantine с сохранением literal material record; MP mirrors принимают только server stream и exact registry hydration.

Проверено offline Python и native CPU queue/NBT/hook observers. Это не game loop, GPU propagation, live multiplayer или inference.

## Проверенная согласованность prompt

Удалено устаревшее глобальное утверждение об отсутствии weapon-side ammo: существующая карточка `configure_weapon_ammo` остаётся единственным подробным объяснением этой capability; новая глобальная инструкция вместо старой не добавлена. Registry params, dependencies, schema, validation, compiler и C# не меняются.

Stationary entity может стрелять через explicit `spawn_entity_on_event` с `when={everyTicks:n}` без `target_and_fire`; последнее отдельно задаёт поиск NPC и cadence. Это проверяется admitted → compiled → strict-wire counterexample, а не выводится из имени turret/sentry. Default lifetime event allowance не пополняется; явно выбранный `set_descendant_concurrency` у root заменяет его replenishable descendant pool. Nested sources сохраняют ancestor limits, а static graph/depth/count и owner/entity caps остаются.

Regressions проверяют реальные serialized initial requests в `json_object`, `json_schema` и off, сохранение полного catalog, parent facts и нужных local explanations, а также scoped Repair без расширения edit permissions. Удаление дублирования и исправление ложных инструкций не измеряет live first-Author success, полезность предметов, art или игровой/MP runtime.
