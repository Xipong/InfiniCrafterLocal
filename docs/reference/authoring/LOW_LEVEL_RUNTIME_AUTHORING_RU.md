# Gameplay Author — authored shape и construction contract

[Generated boundary](../generated/LOWERY_RU.md) · [Source owners](../../development/CODE_MAP_RU.md#python) · [Repair](../../development/pipeline/TARGETED_REPAIR_PROTOCOL_RU.md) · [Neutral omissions](DECLARED_NEUTRAL_OMISSIONS_RU.md)

Это human projection, не owner schema/registry. Exact shape — [program_schema.py](../../../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py); model-facing prose — [author_item_contract.py](../../../LocalGenerator/infini_local/pipelines/author_item_contract.py). Inventory/units/wire facts генерируются в [capability inventory](../generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) и [primitive parity](../generated/PRIMITIVE_PARITY_RU.md); технический manifest не надо копировать в LLM-каталог.

Новые канонические формы pull, nearby damage, зависимых свойств и скорости,
а также точная граница совместимости со старыми предметами описаны в
[решениях по упрощению Author API](AUTHOR_API_SIMPLIFICATION_RU.md).

<a id="response"></a>
## Author response

Обязательные root-поля — `name`, `category`, `runtimeProgram`; `concept` и `realization` optional advisory. `runtimeContract` с compiler receipts не authored root field. `runtimeProgram` задаёт `apiVersion`, Author `schema`, один `primaryEntityId`, явные `entities[]` (`id/kind`), `bindings[]` (`id/input/action/stackCost/contactDamage`) и `calls[]` (`id/fn/target/params`). Exact required/optional keys — в schema, не в этом сокращённом перечне.

Current Author `infini.runtime-program.authoring.v6` задаёт независимые flat lanes `action`, `stackCost`, `contactDamage`. Saved wire v3 сохраняет nested `usePolicy`. Новый binding skeleton единообразен: `{id,input,action:{kind,targetId},stackCost,contactDamage}`. Исторические sparse bindings остаются valid: точные fixed literals можно явно передать или опустить — `hold.kind=spawn_entity`, `equipped.kind=equip_passive`, item-body-only `targetId` равен exact unique declared body ID, `hold/equipped` cost/contact равны integer `0`/boolean `false`, `place_item` — integer `1`/boolean `false`. Неверные present kind/target/cost/type отвергаются без coercion. Это объявленная lossless wire equivalence, не выбор action: active non-placement stack/contact и разные actions остаются независимыми решениями. `placementCallId`, `effectGroupId`, `stackConsumeChancePercent` сохраняют свои conditional constraints. Repair сравнивает только exact equivalent transactions через существующий owner; принятую source presence/absence frozen-first merge не переписывает. Для новых calls предпочтителен единый явный `id/fn/target/params` envelope: `target` — точный существующий совместимый entity ID, включая объявленный ID единственного `item_body`, а zero-arg `params` — закрытый `{}`. Только прежние точные пропуски item-body-only `target` и zero-arg `params` остаются допустимы в той же grammar без migration, router или выбора default. Присутствующие поля никогда не игнорируются; строка `item` допустима лишь как реально объявленный ID, не alias. Projectile/mixed targets и active non-placement stack/contact остаются явными model choices. Calls присоединяют одну capability к одной entity; typed references связывают entities. Movement, controller, damage, targeting, input, attachment, body contact, lifecycle и event topology остаются независимыми решениями Author. Weapon macro и routing по name/category/prose запрещены; schema/validator не выбирают содержательную замену.

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
сохранения собственного стека также требует `maxStack=1`. [Точные receipt/lifecycle правила](../items/OWN_STACK_CHANCE_RU.md).

Для разных item effects основного и альтернативного use Author явно связывает `params.effectGroupId` calls с `apply_item_effects.effectGroupId`; отсутствие selector сохраняет ungrouped effects. `refresh_generated_effect_group_while_held` выбирает отдельную generated-utility группу удерживания. Точные ограничения, общий player mobility cooldown, quick use и Repair — [именованные группы эффектов](../items/NAMED_ITEM_EFFECT_GROUPS_RU.md).

`configure_weapon_ammo` отдельно выбирает exact ammo category и initial speed basis для active `spawn_entity` shots. Terraria владеет выбором/расходом/экономией ammo и его вкладом в damage/knockback; authored entity сохраняет поведение projectile. `stackCost` остаётся стоимостью самого generated item. Полная граница и ограничения — [weapon ammo consumption](../items/WEAPON_AMMO_CONSUMPTION_RU.md).

`collect_seeds_from_grass` — независимый opt-in inventory passive без параметров/use binding: ровно `gameplay.collectSeedsFromGrass=true` от выбранного `.fn`. Native grass seed RNG/drop/owner остаются у Terraria; shared proxy flags не меняются. Ammo category и source parent flag сами эту capability не добавляют. [Точная inventory/native граница](../items/WEAPON_AMMO_CONSUMPTION_RU.md#явный-inventory-passive-сбора-семян).

<a id="construction"></a>
## Прямое построение, не procedural self-check

Author выдаёт один JSON: optional sketch `concept`, executable `runtimeProgram`, optional `realization.description/playerExperience/selfEvaluation`. Concept/report non-binding; `selfEvaluation` — свободный advisory текст, не структурированные verdict rows и **не наблюдавшееся исполнение**. Их отсутствие/оформление не отвергает executable craft и не вызывает Repair.

Construction facts живут у своих owners, а не в повторных глобальных checklist. Порядок ответа задают system и `requiredJsonShape`; отдельные повторные `gameplayAuthoringStages`, `principle`/`reportEvidenceRule`/`literalSynthesisRule` и `forbidden` не передаются. Полные catalog cards, shape examples и optional advisory guidance доступны во всех response modes, включая `json_object`/off: provider schema их не заменяет.

### Полезная композиция и самостоятельный выбор статусов

`priorityHeader` получает `AUTHOR_DESIGN_QUALITY_RULE` из prose owner: ценность основного
действия в обычной ситуации (в бою — в том числе против одиночной цели), достижимая
и полезная secondary/event-награда, взаимодополняющие действия и реально действующий
обмен риска/ресурса на пользу. Число capabilities само по себе не делает результат
интересным. Узкие применения, простые результаты, сильные оправданные преимущества
и намеренные sidegrades допустимы: нет требования всегда усиливать предмет,
добавлять twist, наследовать по эффекту каждого родителя или писать новый отчёт.
Это ориентиры Author в том же единственном ответе, не кодовые правила баланса,
admission gates или дополнительная critic-стадия.

`runtimeCapabilityContract.statusIdentityChoices` — один общий read-only словарь
загруженных buff identities (`source/complete/entries`, где entry содержит
`id/fullName`), а **не** перечень эффектов, доказанно нанесённых родителями.
Author вправе явно выбрать оттуда статус для нового предмета даже при неизвестной
механике родителей; выбор не удостоверяет наследование. Карточки обоих `buffId`
разрешают supplied identity либо exact parent ID, без старого copy-only ограничения.
Подсказки различают NPC damage-over-time, давление на defense и воздействие на AI,
не обещая обхода native immunity или применимости player-only debuff к NPC.
Recipient, event producer, trigger и duration всё равно выбираются явно.

Числовой `buffId`, bounds, schema и compiled wire не меняются. Старый запрос без
словаря не получает вымышленные ID; неполный словарь явно отмечен `complete=false`.
Repair видит тот же shared словарь без второго полного capability catalog, но
новая видимость не даёт права менять уже валидный `buffId`, event или соседний call.
Synthetic offline Author → parse → compile и hostile leaf-local Repair проверены
в обоих `json_schema`/`json_object`, включая poison без parent mechanic proof.
Это проверка исполнимости и model-facing контекста, не измерение качества live-model
генерации и не изменение сохранённых предметов.

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

`concept` и `realization` остаются advisory context. Если передан report, его поля `description` (до 4000), `playerExperience` (до 3000) и `selfEvaluation` (до 4000 Unicode code points) — optional текст. Local gameplay acceptance не требует структурированных action/behavior checks, verdict enums, повторных runtime IDs или обязательного replacement report. Несоответствие advisory shape может оставаться raw diagnostic, но не блокирует валидный `runtimeProgram` и не вызывает report-only Repair. Исполняемые choices/refs/dependencies, source work bounds и strict runtime schema сохраняют силу; код не сочиняет отсутствующий текст.

<a id="validation-events"></a>
## Validation, events и compilation

Validator сообщает exact paths и проверяет shape/refs/slots/dependencies/producers/cycles/budgets; compiler пишет только declared wire paths с exact global/capability receipts. Opcode кодирует уже выбранное имя capability. [Neutral omission](DECLARED_NEUTRAL_OMISSIONS_RU.md#contract) разрешено только объявленным ParamSpec после полной проверки; прочие missing/invalid values — RED, не fallback.

Event producer alternatives берутся только из `EVENT_KIND_REGISTRY` и `ENTITY_KIND_REGISTRY.base_events`. Author/Repair выбирает один **полный** вариант и явно добавляет необходимые calls/bindings; код не вставляет producer. `spawn_entity_on_event`/`pull_on_event` для periodic явно задают `when={everySeconds:s}` в пределах объявленных registry bounds. У непериодического варианта `everySeconds` отсутствует; скрытый период не добавляется.

`spawn_entity_on_event` и `target_and_fire` явно выбирают независимые `damageBasis`/`knockbackBasis` (`authored_child` либо `live_parent`) и `damageMultiplier`. Live parent означает actual projectile fields в момент event/fire; delayed action сохраняет их при enqueue, charge уже включён, повторного применения player/class modifiers нет. Для item-body events допустим только `authored_child`. Missing fresh choices — RED. [Полный child combat contract](../projectiles/CHILD_COMBAT_INHERITANCE_RU.md) описывает snapshots, старый wire, strict provenance и runtime refusal.

Для projectile `pull_on_event(mode=target_to_entity)` направляет NPC к центру испускающего projectile, включая `on_hit`. При runtime `delayTicks > 0` этот центр фиксируется при постановке события в очередь; другие hit-actions сохраняют центр поражённого NPC. В MP receipt использует центр проверенного server-side projectile, не координаты клиента.

Terminal meaning: `on_hit` требует collision; proximity detonation не hit. `on_expire` испускается при natural expiry и proximity detonation, не при любом early kill. `on_kill` покрывает terminal paths, включая collision/penetration/natural expiry/detonation; `on_tile_collision` — каждую collision. Bounce + только on_expire не обещает эффект на последнем ударе. [Runtime truth](../../../LocalGenerator/infini_local/pipelines/llm_authoring_prompt.py#L229) и consumer остаются источниками этих различий.

Числовые units/точные conversions и отсутствующие wire aliases — [standardization](../terraria/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md#units), не semantic repair. [Frozen-first Repair](../../development/pipeline/TARGETED_REPAIR_PROTOCOL_RU.md#frozen-first) не расширяет accepted design.

<a id="front-hand"></a>
## Независимое движение передней кисти

Новый Author выбирает отдельно ось (`set_projectile_aim`), привязку тела (`attach_projectile`), позу руки (`set_front_arm_pose`) и дополнительный вылет (`set_projectile_reach_curve`). Привязка к `front_hand` сама не навязывает треугольную позу, singleton, удержание кнопки, срок жизни или прохождение сквозь тайлы. Поза имеет явные start/peak/end stretch и peak progress: можно выбрать постоянное положение или асимметричное выдвижение. Поза не перемещает hitbox без отдельной привязки; вылет требует выбранной привязки. Единственный активный primary writer позы не запрещает несколько читателей положения руки.

Collision center и изображение следуют одному выбранному телу и оси. Hitbox остаётся штатным axis-aligned rectangle, не pixel blade/OBB; осевые/нормальные offsets задаются в мировых блоках, а image-local grip — в системе координат PNG. Native stretch выбирается по ближайшей длине, при равенстве — более короткий. Duration позы/вылета не продлевает lifetime или itemAnimation. Gameplay events используют выбранную ось и при нулевой translational velocity; delayed action сохраняет её при enqueue. Periodic dispatch сохраняет существующую фазу относительно movement update.

Visual Director передаёт size/forward axis/atomic grip выбранного финального PNG: `reuse_item_icon` использует root metadata, distinct `baked_sprite` — entity metadata. `no_asset`/`runtime_geometry` не требуют PNG. Missing selected leaves идут в точный frozen Visual Repair, не выводятся из art/hitbox/названия.

Сохранённые `move_front_hand=20` и `move_forward_then_retract=19` исполняются с прежними формулами, clocks, collision/lifetime semantics и без migration. В новом Author/Repair эти составные операции больше не предлагаются; отсутствие старого controller не дописывает вместо него новую композицию. Полная граница остальных motion primitives — [Projectile Author](../projectiles/PROJECTILE_AUTHOR_API_RU.md#composable-motion).

<a id="visual-vfx"></a>
## Visual/VFX boundary и headless replay

Roles losslessly выводятся из accepted kinds; VFX slots ограничены существующими entities/events. Renderer → texture dependency, dedicated impact PNG, material ingredients и единый delivery gate принадлежат [VFX materials](../presentation/VFX_MATERIAL_ELEMENTS_RU.md) / [PNG dependency owner](../../development/pipeline/IMAGE_ASSET_LIFECYCLE_RU.md#dependencies), а не Author.

Event consumers не обязаны иметь authored gameplay action ради VFX: `periodic` имеет свой producer, item-body `on_use` не зависит от spawn target, contact `on_hit` зависит от `contactDamage`, `place_item` не испускает `on_use`. Python и C# используют общий producer contract.

Offline Live20 DTO replay: `image_boundary.ndjson.finalContract` → `hydrate_no_image_fixture_assets` → настоящий `sanitize_recipe_for_delivery` → JSONL `{case,data}` → `tools/native/EngineRuntimeChecks.csproj -- --replay-contracts <path>`. QA PNG — техническая fixture, не артовый deliverable. Это проверяет `GeneratedItemData.FromJson` на указанном tModLoader, не world loop/render/MP.

Projection gates: `PYTHONPATH=LocalGenerator python tools/generate/generate_lowery.py --check`, `python tools/generate/generate_low_level_runtime_docs.py --check`; regressions — registry tests, three-stage/pipeline Repair tests из [test owners](../../development/TESTING_RU.md).

## Независимый свет размещённого предмета

`add_placed_light(placementCallId,strength,color)` — отдельный явный выбор Gameplay Author. Reference указывает ровно same-item `configure_tile_placement`, исполняемый `place_item`; не выбирается из названия станции, SoulOfLight, категории или sprite. Strength обязателен в 0.01..1.5 (RGB coefficient, не радиус), color — обязательный canonical token. Отсутствующий call не добавляет `placedLight` и не излучает свет.

Compiler losslessly копирует выбранные листья в exact binding `usePolicy.action.placement.placedLight`, с association и parameter receipts. `present_placed_item_sprite` и свет независимы: можно выбрать любой из них или оба; два нарисованных огонька не создают два emitters. Старые held/projectile lights не меняются. Свет native tile сохраняется отдельно.

Runtime расширяет существующий placement group/witness/definition transport, не создаёт вторую ledger. Exact same definition hash, binding, world scope и committed rectangle удостоверяют один center tile. `PostUpdateEverything` отправляет authored RGB в штатный `Lighting.AddLight`; PNG/Visual и optional pose decoder не требуются: light берёт уже доказанный material rectangle, а failure PNG pose остаётся literal pending diagnostic. Exact native metadata должна иметь callback-free bounded geometry (16x16/256 cells), включая alternates, либо стандартные 2x2 metadata/callbacks ванильных `Containers` и `Containers2` из [контракта размещения](../presentation/PRESENT_PLACED_ITEM_SPRITE_RU.md#native-containers). Обычные контейнеры используют native SP/MP contents/open/save/load, authenticated placement outcome и единственный generated return owner; body/light/VFX выбираются независимо. Неизвестные actor callbacks не допускаются даже при bare placement; MP peers требуют placement protocol6. Нового Author-поля lifecycle нет. Guard не ослабляется, выбранные calls не удаляются ради обхода отказа. Break и removal прекращают light, material возвращается по существующей ledger. World/mod unload очищают derived state. Malformed witness/foreign definition дают no-light quarantine с сохранением literal material record; MP mirrors принимают только server stream и exact registry hydration.

Проверено offline Python и native CPU queue/NBT/hook observers. Это не game loop, GPU propagation, live multiplayer или inference.

## Явные живые эффекты размещённого предмета

`enable_placed_vfx(placementCallId,minFrameY,maxFrameY)` — независимый opt-in того же `item_body`. Ссылка выбирает exact исполняемый `configure_tile_placement`; compiler пишет optional `placement.placedVfx` и exact association/leaf receipts. Оба integer bounds обязательны, inclusive `0..32767`, min ≤ max. Они сравниваются с **реальным top-left native TileFrameY**, не количеством кадров анимации и не временем. `0..32767` сознательно выбирает все nonnegative frames. Parent `nativeTileState`, если известен, — read-only наблюдение native API, а не auto-default: проверенный Campfire/style0 сообщает on `0..35`, off `36..71` из actual `Wiring.ToggleCampFire`. Runtime не содержит tile-ID/name/parent маршрутизатора.

В существующем VFX slot optional `placementBindingId` выбирает exact accepted `place_item` binding с `placedVfx` того же item-body. Только `periodic`, `anchor=self`, renderers `spriteElement`, `libraryParticle`, `lightCue`; остальные сочетания/чужая ссылка/null отвергаются. Director и его scoped Repair получают actual allowed bindings и bounds read-only; новой LLM-стадии нет. Omission сохраняет прежние item/projectile поведение, wire/hash и receipts. Такие слоты **не** испускаются из HoldItem/equipment; размещённый consumer читает только совпавший selector.

Source — authenticated retained ledger group/witness/exact definition/footprint, без второй material ledger, fake Player или projectile. Его frame: footprint center, forward `+X`, velocity `0`; `element.offsetForwardPx` сдвигает вправо, `offsetSidePx` вниз. Несколько independent flame assets и профилей исполняются прежними emission/update/render owners. Root PNG остаётся стабильным физическим предметом; optional static `present_placed_item_sprite` не отменяется и не переавторствует старое изображение. Visual/Repair описывают намеренные отдельные live effects, но не утверждают, что будущие VFX slots уже существуют.

`PostUpdateEverything` на всех клиентах один раз за world tick обновляет этот cosmetic source. Gate off/тип или tile отсутствует/return/replacement/world-exit завершают source-attached effects; world particles могут дожить только bounded duration. Reenable создаёт fresh activation; прежний binding никогда не оживает. Identity привязана к exact retained group object и projection generation, не только к координатам/definition ID. Definition hydration использует прежнюю bounded очередь; per-frame JSON/PNG GetData и ledger mutation не добавлены. Dedicated server молчит. Exact callback-free footprint/container guards, sole material return authority и transport не ослаблены.

Только для новой placed-selected cohort `maxParticlesTotal` — fresh allowance **одного due periodic burst**, а не cumulative lifetime permanent placement. Per-source/world-tick particle cap, draw cap и global live-record/particle ceilings прежние. Нулевой total запрещает particles. `lightCue` светит лишь на due world ticks: для непрерывного света модель явно выбирает `repeatEvery=1`; cadence не переписывается. Library motion — world-only, attached sprite retires вместе с activation.

Repro: `PYTHONPATH=LocalGenerator INFINI_SKIP_CONFIG_FILE=1 python tools/diagnostics/repro_placed_vfx_fixture.py`; checked-in `LocalGenerator/tests/fixtures/placed_vfx_final_wire.json` — честный deterministic synthetic-no-image CPU input. Зарегистрированные native checks читают именно final delivery, проводят реальный ledger commit, all-client update, FNA quad/ParticleLibrary instance CPU queues и LightingEngine queue. Проверяются независимые placements, off/reenable generations, late exact server hydration, stale removal и burst budgets за пределами исторического total. Это не GPU, game loop, live model/image output или MP socket match. Saved definitions/world/player/PNG не мигрируются.

## Проверенная согласованность prompt

Удалено устаревшее глобальное утверждение об отсутствии weapon-side ammo: существующая карточка `configure_weapon_ammo` остаётся единственным подробным объяснением этой capability; новая глобальная инструкция вместо старой не добавлена. Registry params, dependencies, schema, validation, compiler и C# не меняются.

Stationary entity может стрелять через explicit `spawn_entity_on_event` с `when={everySeconds:s}` без `target_and_fire`; последнее отдельно задаёт поиск NPC и cadence. Это проверяется admitted → compiled → strict-wire counterexample, а не выводится из имени turret/sentry. Default lifetime event allowance не пополняется; явно выбранный `set_descendant_concurrency` у root заменяет его replenishable descendant pool. Nested sources сохраняют ancestor limits, а static graph/depth/count и owner/entity caps остаются.

Regressions проверяют реальные serialized initial requests в `json_object`, `json_schema` и off, сохранение полного catalog, parent facts и нужных local explanations, а также scoped Repair без расширения edit permissions. Удаление дублирования и исправление ложных инструкций не измеряет live first-Author success, полезность предметов, art или игровой/MP runtime.
