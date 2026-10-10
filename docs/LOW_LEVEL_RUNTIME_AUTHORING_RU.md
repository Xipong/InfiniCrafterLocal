# Gameplay Author — authored shape и construction contract

[Generated boundary](../lowery.md) · [Source owners](../PROJECT_MAP_RU.md#python) · [Repair](TARGETED_REPAIR_PROTOCOL_RU.md) · [Neutral omissions](DECLARED_NEUTRAL_OMISSIONS_RU.md)

Это human projection, не owner schema/registry. Exact shape — [program_schema.py](../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py); model-facing prose — [author_item_contract.py](../LocalGenerator/infini_local/pipelines/author_item_contract.py). Inventory/units/wire facts генерируются в [capability inventory](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) и [primitive parity](PRIMITIVE_PARITY_RU.md); технический manifest не надо копировать в LLM-каталог.

<a id="response"></a>
## Author response

Текущий root содержит `name`, `category`, `concept`, `runtimeProgram`, `realization`. `runtimeContract` с compiler receipts не authored root field. `runtimeProgram` задаёт `apiVersion`, Author `schema`, один `primaryEntityId`, явные `entities[]` (`id/kind`), `bindings[]` (`id/input/usePolicy`) и `calls[]` (`id/fn/target/params`). Exact required/optional keys — в schema, не в этом сокращённом перечне.

`usePolicy` атомарно задаёт `action`, `stackCost`, `contactDamage`. Calls присоединяют одну capability к одной entity; typed references связывают entities. Movement, controller, damage, targeting, input, attachment, body contact, lifecycle и event topology остаются независимыми решениями Author. Weapon macro и routing по name/category/prose запрещены; schema/validator не выбирают содержательную замену.

<a id="primary-use"></a>
## Primary и независимые use lanes

Author выбирает **один точный существующий** `primaryEntityId` для lifecycle/held representation. Calls/bindings не содержат authored `role`; compiler материализует wire `binding.role=primary` только при `binding.usePolicy.action.targetId == primaryEntityId`, иначе `secondary`; kind выбранной entity даёт `primaryOwner=item_body|projectile`. Это mandatory projection, не compression и не эвристика.

Item graphic/body-contact representation принадлежит `item_body`. Projectile может стать primary только при явно authored projectile lifecycle/held ownership. Узкий invariant: если все active bindings spawn-ят одну entity, `contactDamage=false` и `configure_item_use.hideUseGraphic=true`, exact spawn target должен стать owner — невидимый body use не представляет. Факт spawn, damage, категория и название сами по себе primary не выбирают.

Один exclusive input имеет один root binding, но **не одну damage lane**. `contactDamage` независим от `action`; например, Starfury-like tuple (фрагмент binding, не полный response):

```json
{"input":"primary_use","usePolicy":{"action":{"kind":"spawn_entity","targetId":"falling_star"},"stackCost":0,"contactDamage":true}}
```

При primary body он сохраняет item hitbox и spawn-ит secondary projectile, который не отбирает `heldProj`/animation. `place_item`, `hold`, `equipped` требуют `contactDamage=false`: consumers эту contact lane не исполняют. Flail/yoyo/whip/holdout — примеры explicit projectile ownership, не распознаваемые families. Edge-case fixtures: `workbench_blade` (body + projectile), `door_on_chain` (projectile-owned flail); внешние [Starfury](https://terraria.wiki.gg/wiki/Starfury)/[Flails](https://terraria.wiki.gg/wiki/Flails) поясняют примеры, но authority — текущие consumers.

`stackCost=1` расходует **целую единицу** generated item на active use; projectile return не возвращает предмет и не является hidden charge counter. Reusable throw выбирает `0`. `place_item` требует `1`; предмет escrowed в world placement ledger и возвращается тем же generated item при сломе, не «навсегда расходуется». Reusable hybrid с placement и active `spawn_entity/use_item_body` при `stackCost=0` требует `maxStack=1`: одна durable вещь меняет inventory/placed form. One-shot non-placement use с cost `1` не подпадает под этот конкретный maxStack rule.

Для разных item effects основного и альтернативного use Author явно связывает `params.effectGroupId` calls с `apply_item_effects.effectGroupId`; отсутствие selector сохраняет ungrouped effects. `refresh_generated_effect_group_while_held` выбирает отдельную generated-utility группу удерживания. Точные ограничения, общий player mobility cooldown, quick use и Repair — [именованные группы эффектов](NAMED_ITEM_EFFECT_GROUPS_RU.md).

`configure_weapon_ammo` отдельно выбирает exact ammo category и initial speed basis для active `spawn_entity` shots. Terraria владеет выбором/расходом/экономией ammo и его вкладом в damage/knockback; authored entity сохраняет поведение projectile. `stackCost` остаётся стоимостью самого generated item. Полная граница и ограничения — [weapon ammo consumption](WEAPON_AMMO_CONSUMPTION_RU.md).

<a id="construction"></a>
## Прямое построение, не procedural self-check

Author выдаёт один immutable JSON в причинном порядке: начальный `concept` → executable `runtimeProgram` → `realization.description/playerExperience` → `realization.selfEvaluation`. Concept non-binding; расхождение диагностируется, не отвергает craft. Report и selfEvaluation — интерпретация Author, **не наблюдавшееся исполнение**.

Construction facts живут у своих owners, а не в повторных глобальных checklist:

| Место в packet | Правило построения |
|---|---|
| `requiredJsonShape.runtimeProgram.calls` | Совместимый existing target, exact params выбранной capability, все non-optional и условно обязательные поля |
| `catalog.fieldGuide` | Units/ranges и refs через targetKinds/allowSelf/graphEdge; отсутствие не создаёт неявной нейтрали |
| `catalog.entityKinds` | Required components/position driver; stationary contact без target-and-fire не firing turret; free projectile use создаёт independent instance, не singleton minion |
| `catalog.inputs/bindingActions` | Один root action; hold/equipped passive, активное действие требует active-use binding; independent contact lane, placement/escrow |
| `catalog.events` | On-use/hit/crit producers, terminal distinctions, explicit periodic timing |
| Capability cards | Channel/charge/release, cadence/animation, reusable hybrid bounds |
| Глобальные invariants | ID uniqueness, exact primary ownership, acyclic graph и spawn/depth budgets |

`planVsProgram.actionChecks` покрывает каждую planned action и executable input/event lane, включая aligned и added lanes; указывает exact runtime IDs, результат, intentionality и причину. `programVsReport.behaviorChecks` отдельно покрывает executable input/entity/event lanes против обоих report texts. Blanket aligned verdict не заменяет rows; непонятная семантика отмечается `uncertain`. `realization_execution_truth_for_llm()` остаётся источником Repair execution guidance; initial Author берёт оттуда диагностический selfEvaluation contract, а не новый judge-pass. Исторический builder замер — [отдельная запись](AUTHOR_DIRECT_CONSTRUCTION_RU.md#measurement), не обещание first-Author success rate.

<a id="validation-events"></a>
## Validation, events и compilation

Validator сообщает exact paths и проверяет shape/refs/slots/dependencies/producers/cycles/budgets; compiler пишет только declared wire paths с exact global/capability receipts. Opcode кодирует уже выбранное имя capability. [Neutral omission](DECLARED_NEUTRAL_OMISSIONS_RU.md#contract) разрешено только объявленным ParamSpec после полной проверки; прочие missing/invalid values — RED, не fallback.

Event producer alternatives берутся только из `EVENT_KIND_REGISTRY` и `ENTITY_KIND_REGISTRY.base_events`. Author/Repair выбирает один **полный** вариант и явно добавляет необходимые calls/bindings; код не вставляет producer. `spawn_entity_on_event`/`pull_on_event` при `event=periodic` требуют explicit `periodTicks` (6..3600), non-periodic его не требует; скрытый default 6 запрещён.

`spawn_entity_on_event` и `target_and_fire` явно выбирают независимые `damageBasis`/`knockbackBasis` (`authored_child` либо `live_parent`) и `damageMultiplier`. Live parent означает actual projectile fields в момент event/fire; delayed action сохраняет их при enqueue, charge уже включён, повторного применения player/class modifiers нет. Для item-body events допустим только `authored_child`. Missing fresh choices — RED. [Полный child combat contract](CHILD_COMBAT_INHERITANCE_RU.md) описывает snapshots, старый wire, strict provenance и runtime refusal.

Terminal meaning: `on_hit` требует collision; proximity detonation не hit. `on_expire` испускается при natural expiry и proximity detonation, не при любом early kill. `on_kill` покрывает terminal paths, включая collision/penetration/natural expiry/detonation; `on_tile_collision` — каждую collision. Bounce + только on_expire не обещает эффект на последнем ударе. [Runtime truth](../LocalGenerator/infini_local/pipelines/llm_authoring_prompt.py#L229) и consumer остаются источниками этих различий.

Числовые units/точные conversions и отсутствующие wire aliases — [standardization](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md#units), не semantic repair. [Frozen-first Repair](TARGETED_REPAIR_PROTOCOL_RU.md#frozen-first) не расширяет accepted design.

<a id="visual-vfx"></a>
## Visual/VFX boundary и headless replay

Roles losslessly выводятся из accepted kinds; VFX slots ограничены существующими entities/events. Renderer → texture dependency, dedicated impact PNG, material ingredients и единый delivery gate принадлежат [VFX materials](VFX_MATERIAL_ELEMENTS_RU.md) / [PNG dependency owner](IMAGE_ASSET_LIFECYCLE_RU.md#dependencies), а не Author.

Event consumers не обязаны иметь authored gameplay action ради VFX: `periodic` имеет свой producer, item-body `on_use` не зависит от spawn target, contact `on_hit` зависит от `contactDamage`, `place_item` не испускает `on_use`. Python и C# используют общий producer contract.

Offline Live20 DTO replay: `image_boundary.ndjson.finalContract` → `hydrate_no_image_fixture_assets` → настоящий `sanitize_recipe_for_delivery` → JSONL `{case,data}` → `tools/EngineRuntimeChecks.csproj -- --replay-contracts <path>`. QA PNG — техническая fixture, не артовый deliverable. Это проверяет `GeneratedItemData.FromJson` на указанном tModLoader, не world loop/render/MP.

Projection gates: `PYTHONPATH=LocalGenerator python tools/generate_lowery.py --check`, `python tools/generate_low_level_runtime_docs.py --check`; regressions — registry tests, three-stage/pipeline Repair tests из [test owners](TEST_CONTRACT_OWNERS_RU.md).
