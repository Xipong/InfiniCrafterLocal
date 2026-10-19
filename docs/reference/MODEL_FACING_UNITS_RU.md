# Model-facing units — Gameplay / Visual / VFX

<a id="authority"></a>
## Один источник диапазонов и преобразований

Gameplay параметры, descriptions, domains, units и exact wire mapping — [capability_registry.py](../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py) (`ParamSpec`/`CapabilitySpec`). Структура — [program_schema.py](../../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py), executable projection/receipts — [compiler.py](../../LocalGenerator/infini_local/core/runtime_authoring/compiler.py) и [technical_lowering.py](../../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py). Полный roster — generated [capability inventory](generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) / [primitive parity](generated/PRIMITIVE_PARITY_RU.md), не ручная копия всех registry rows.

Путь изменения: registry → actual provider schema/prompt → validator/Repair → compiler receipt → strict wire → C# DTO/executor → regression. Исторический rename не становится Author alias; C# wire сохраняет объявленные старые leaves. Category/name/prose не выбирают единицу, sentinel, механическую композицию или default.

Свежий Gameplay Author использует `infini.runtime-program.authoring.v6`; runtime API остаётся `infini.runtime-program.v5`, persisted wire — `infini.runtime-program.wire.v3`. Author/Repair выбирают игровые расстояния в **блоках**, длительности в **секундах**, скорости в **блоках/с**. Смысл и диапазон каждого конкретного поля по-прежнему задаёт registry, а не suffix-эвристика.

| Семейство | Author | Canonical lowering в прежний wire |
|---|---|---|
| World distance | `*Blocks`; существующие `rangeTiles`/`radiusTiles` уже означают блоки | ×16, если consumer хранит world pixels; already-block values не конвертируются повторно |
| World duration | `*Seconds` | ×60, ближайший целый world tick, половина тика вверх |
| Projectile velocity | `*BlocksPerSecond` | ×16/(60×N), N принадлежит этому target |
| Projectile gravity acceleration | `accelerationYBlocksPerSecondSquared` | ×16/(3600×N²) |
| Continuous NPC acceleration | `*BlocksPerSecondSquared` | ×16/(3600×N), по частоте вызывающего projectile |
| One-off impulse / player bonus / ammo contribution | `*BlocksPerSecond` | ×16/60; не использовать N projectile как множитель бонуса Player/Item |
| True angular rate | `*RadiansPerSecond` | /(60×N) |
| Technical counters, ratios, percent | Declared count/coefficient/percent | Их прежний контракт; это не duration/rate по одному названию |

N = explicit `set_projectile_collision.updatesPerTick` **того же target**; у ребёнка собственный N, а не N emitter-а. Missing, malformed и ambiguous clocks не заменяются единицей. Полный прежний engine domain доступен для каждого N=1..6 через registry-derived contextual Author bounds; engine bounds и native clamps не пересматриваются.

Секундная проекция — объявленная quantization, не обещание точного восстановления исходного decimal: половина тика округляется вверх. Ненулевой эффект не может исчезнуть при lowering/storage. Для integer world-pixel wire, например `offsetBlocks`, сохраняется точная пиксельная решётка; произвольная дробь блока не округляется скрыто.

Current Author/Repair принимают только v6 keys, не старые `*Ticks`/`*PxPerUpdate` как fresh aliases. Saved wire не переписывается. Source-free audit принимает только конечные predecessor paths, **явно объявленные для этой миграции** в `ParamSpec`; это не возврат всех ранее retired aliases и не importer. Source-backed audit требует exact current Author source. Архивные JSON/hashes остаются неизменными. Проверки: `test_author_world_unit_projection.py` плюс существующие numeric/Repair/receipt controls; historical diagnostic hash не становится current admission contract.

<a id="clocks"></a>
## World ticks, updates, pixels

Terraria nominal world clock — 60 ticks/s, tile — 16 px. Это не гарантия wall-clock при lag/pause и не единица каждого параметра, чьё старое wire имя содержит Tick.

| World ticks | Nominal seconds |
|---:|---:|
| 6 | 0.10 |
| 10 | 0.17 |
| 20 | 0.33 |
| 30 | 0.50 |
| 60 | 1.00 |
| 120 | 2.00 |
| 180 | 3.00 |

Native `extraUpdates` даёт `N=extraUpdates+1` AI/movement updates/world tick. Wire velocities/gravity и engine local NPC cooldown сохраняют прежние engine units, но Author задаёт перечисленные физические world rates: lowerer учитывает N детерминированно. `velocityRetention`/`speedMultiplierPerUpdate` и другие явно объявленные per-update coefficients остаются коэффициентами алгоритма; `immunity.localCooldown` и `initialIgnoreCountdownUpdates` — counts. Native `lifetimeTicks`, charge/warmup/return-after и scheduler `delayTicks` остаются world ticks; их Author counterparts теперь Seconds. VFX material simulation сохраняет свой world-tick контракт и этой миграцией не меняется.

**16 world pixels = 1 блок**. Texture texels/canvas resolution и normalized UV — отдельные пространства; UV нельзя делить на16. Явные `*Px` hitbox/sprite/hand/beam geometry сохраняют пиксели. Standing unmounted collider обычного игрока — 20×42 world px (1,25×2,625 блока); базовый бег — 11,25 блока/с; начальная скорость обычного прыжка — примерно 18,79 блока/с вверх. Это сравнения для normal gravity без modifiers, не balance presets: initial jump velocity не задаёт высоту/дальность без hold duration, gravity и движения.

Только для прямолинейного движения с постоянной скоростью без столкновений дальность в блоках равна `speedBlocksPerSecond × lifetimeSeconds`. Movement/controller может полностью изменить эту оценку. Минимальный event period берётся из registry, не из формулы дальности.

Пример **частичных capability params**, не полный Author response: `configure_spawn` задаёт `velocity={"constantSpeedBlocksPerSecond":120}`, `count=1`, `spreadRadians=0`, `offsetBlocks=0.5`, `aim=cursor`, `position={"at":"owner_center"}`; `move_gravity_arc` — `accelerationYBlocksPerSecondSquared=900`; `set_projectile_lifetime` — `lifetimeSeconds=2.5`. Отдельный collision call явно задаёт N. При N=2 исполняемые wire speed=16 px/update, gravity increment=1 px/update², offset=8 px, lifetime=150 world ticks. Эти значения проверяет production compiler tracer; старые Author `constantSpeedPxPerUpdate/accelY/lifetimeTicks` не являются текущими keys.

<a id="gameplay"></a>
## Важные отличия единиц от обещаний

| Группа / поле | Буквальный смысл |
|---|---|
| Item use/animation | `useTimeSeconds` — базовый native use/reuse interval, `useAnimationSeconds` — независимая длина animation; отличия могут дать несколько uses, не обязательно один projectile/click. |
| Item facts | `manaCost` — базовая Item.mana до player modifiers; `valueCopper` — exact Item.value, не inferred resale; `craftYield` — запрос, фактическая stack выдача capped maxStack. Loaded rarity/ProjectileID/BuffID/DamageClass копируются из соответствующих source facts, не угадываются из имени. |
| Display/collision | Item scale, projectile `drawScale`, entity Visual scale — multipliers, не collision hitbox/radius. World pixels, tile radii и canvas pixels различны. |
| Knockback/light/aggro/mana regen | Item/Projectile.knockBack — engine strength; Lighting strength — RGB coefficient, не radius; aggro — raw Player.aggro (может быть отрицательным), не probability; manaRegenBonusPoints — raw Player.manaRegenBonus, не mana/s. |
| Ammo | `shootSpeedContributionBlocksPerSecond` — signed базовый Item.shootSpeed вклад в vanilla PickAmmo, не финальная скорость projectile. `usesPotionRules` — Item.potion/use eligibility/sickness gating flag, не duration. |
| Equipment percentages | Уже объявленный /100 adapter; additive modifier, chance, percentage points и source-damage percent различны. Armor set требует полного matching set и head phase; equipment phase/damageClass — explicit selector, не router. Итог зависит от других Terraria modifiers/clamps. |
| Mining / ore sense | Mining speed multiplier делит Player.pickSpeed: больший divisor даёт меньший pickSpeed и более быстрое копание. `oreSenseEnabled` включает Player.findTreasure; это bool→0/1, не произвольный исторический oreSenseRadiusTiles. |
| Buff movement | `moveSpeedBonusPercent` — additive percent [−50,200]; `movementSpeed = percent/100`, как у equipment. `20` добавляет `0.2` к Player.moveSpeed до остальных modifiers. `jumpSpeedBonusBlocksPerSecond` — базовый вклад в Player.jumpSpeedBoost, не обещание итоговой высоты прыжка. |
| Projectile sentinels | `pierce=-1` — unlimited; `localNpcHitCooldownEngineUnits=-1` — one-hit-per-NPC только local immunity; 0..600 raw cooldown counts, не world-tick duration. Owner immunity использует отдельный shared путь. |
| Movement/controller coefficients | Boomerang returnSpeed — target after lerp; phaseStrength одновременно rotation/alpha, не collision phasing; waveVelocityCoefficient нормализуется при расчёте direction, не displacement. sameTargetBias насыщается на .9; target_and_fire range — soft score, не strict геометрическая граница. Charge powerMultiplier меняет и release velocity, не только damage/knockback. |
| Event effects | Spawn count — children; chain count — max дополнительных NPC. damageMultiplier берёт authored **base damage источника**, rounded/minimum 1 до defense, не damageDone и не additive percent. heal damageFraction — доля фактического damageDone; maxHeal — HP/event. |
| Pull / mobility | Pull strength — per-event/update velocity impulse с NPC knockBackResist, не displacement/second. radiusTiles ищет NPC только без directTarget и игнорируется owner_to_target. safeTileOnly — bounds/solid/lava checks, не universal hazard guarantee; recall_home его игнорирует. |
| Visibility hint | `heldSpriteVisibilityHint` не задаёт gameplay release schedule: immediate скрывает; on_release/after_charge явно сохраняют custom root во время use и не различаются расписанием. Empty/omitted при declared renderSizePx следует hideUseGraphic; без этой метадаты сохраняет исторический keep. |

Terminal owners: [GeneratedItemData.Apply](../../ModSources/InfiniCrafterLocal/Common/Models/Runtime/GeneratedItemData.Apply.cs), [GeneratedItem](../../ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs), [GeneratedProjectile executors](../../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Executors.cs), [RuntimeProgramExecutor](../../ModSources/InfiniCrafterLocal/Common/Runtime/RuntimeProgramExecutor.cs), [delayed scheduler](../../ModSources/InfiniCrafterLocal/Common/Runtime/RuntimeDelayedActionScheduler.cs), [player mobility](../../ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.Mobility.cs). Exact opcode/wire route — canonical registry/receipts; старая таблица consumer line numbers не authoritative.

<a id="conversions"></a>
## Нули, нейтрали, nullable и доказуемые conversions

Regen `lifeRegenHpPerSecond` у accessory/armor и `setBonusLifeRegenHpPerSecond`: authored [−50,100] с шагом .5, integer engine wire [−100,200], `wire=2×HP/s`, inverse `HP/s=wire/2`; сохраняются знак, 0 и endpoints. Generated buff regen имеет собственный registry domain [0,60] с тем же half-HP lattice; не расширять его до signed equipment domain.

Existing /100 или bool→0/1 projection доказана только на своём declared image. Процентный /100 — объявленный scale adapter с обычной IEEE-754 точностью, **не биекция всех JSON/binary64 представлений**: соседние обычные doubles могут дать один результат деления; условие `x/100*100==x` не вводится как новый фильтр обычных значений. Такая точность не разрешает молча превращать ненулевой эффект в нейтраль. Она также не гарантирует exact binary32 round-trip произвольного JSON decimal или восстановление каждого старого DTO. Например bool ore sense не восстанавливает старые radius 2..60. Физические единицы меняются только объявленной canonical проекцией с их sign/zero/sentinels и engine domains; duration quantization описана отдельно выше. Ни prose, ни category не дают права вводить другую проекцию.

Buff movement использует тот же percent adapter и guard `nonneutral_must_remain_nonneutral`, что equipment. Float32 factors остаются выразимы: significand содержит не более 24 bits, умножение на `100 = 25×4` требует не более 29 significant bits и точно помещается в binary64; деление такого percent на 100 возвращает factor. Это доказательство о C# consumer values, не о произвольном historical JSON double. Archived wire не пересчитывается; retired `moveSpeedBonusFactor` receipts больше не принимаются, включая old-neutral omissions. Current signed-zero/underflow/source/Repair checks сохранены.

`false`, `0`, `0.0`, absent и `null` не взаимозаменяемы; frozen equality type-aware (true ≠ 1 ≠ 1.0). Только optional params с одинаковыми declared default/neutral допускают Author omission с отдельным receipt после всей composition validation. Missing dependency/invalid present value/empty required effect остаются RED. Repair omission — no-change; accepted absence не заполняется вне exact permissions. Правила — [declared neutrals](DECLARED_NEUTRAL_OMISSIONS_RU.md) и [targeted Repair](../development/TARGETED_REPAIR_PROTOCOL_RU.md).

Структурные `entity/binding/call` IDs, schema version, primary selection и diagnostic paths — не физические units. `bindings[].stackCost` (saved wire: `usePolicy.stackCost`) — точно 0 или 1 экземпляр generated item/accepted use; contactDamage — независимый bool. `*IndicesDelete` — zero-based array position, не tick. Author array maxima/Repair bounds — schema transport limits; compiler-owned runtime maxEntityCount/maxChildDepth/maxEventSpawnsPerActivation — bounded graph/ledger, не model-authored размеры.

<a id="visual"></a>
## Visual числа и schema transport

[Visual guide](VISUAL_PRESENTATION_METADATA.md#size-axis) содержит required fresh v2 `renderSizePx` (integer 1..512, complete final-frame max-side world px), `forwardAngleDegrees` (finite −180..180, 0=+X, clockwise y-down final-PNG axis), independent canvas enums, inventory/world/entity multipliers, final-canvas normalized grip и mount offsets. Item-body/reuse inherit root size/canvas/axis; distinct baked owns свои choices. Canvas/fill не задают world footprint; `q=R/max(actual final frame)` применяется только при render, не в stats/hitbox/pose/network. Сохранённая wire absence остаётся historical без defaults/migration. Director и Repair получают exact G/itemUse/primary IDs, drivers, draw formulas и canonical fill/padding read-only; Visual не меняет mechanics/held visibility hints. Ordinary entity branches/Repair fields читаются у `_response_schema`/`_visual_repair_schema`, не из старой universal entity table.

Optional-null inverse допустим только для объявленных optional properties на **фактическом json_schema** transport. json_object/off/downgrade не получает этот alias; required coordinate null остаётся invalid. Zero-based deletion indices и текстовые длины — transport, не visual units.

<a id="vfx"></a>
## VFX: common controls не универсальная физика

Source: [vfx_manifest.py](../../LocalGenerator/infini_local/core/vfx_manifest.py) (`_VFX_NUMERIC_DESCRIPTIONS`, `_RENDERER_SEMANTICS`, Director/Repair schemas) и [presentation guide](PRESENTATION_CONSISTENCY_RU.md#legacy-vfx). Material payload ranges/units/zeros/profiles имеют отдельный [контракт](VFX_MATERIAL_ELEMENTS_RU.md), а не старые knobs.

VFX Director/Repair получают точный `acceptedGameplayReadOnly`: в частности base `useTime/useAnimation` и `itemScale` не восстанавливаются из realization. Для body sprite copies с declared `renderSizePx` коэффициент `q=R/max(actual final PNG frame)` берётся у выбранного texture owner. Projectile copies используют current P (уже D×E с последующим growth), slot scale и q; не повторно E/G. Dedicated impact, material world-pixel shapes и legacy absent-R ветки имеют отдельные правила в actual schema descriptions.

| Common field | Текущее использование |
|---|---|
| scale | Renderer-specific multiplier: procedural dimensions, sprite pose/texture size, lighting/dust имеют разные clamps; не единый sizePx. |
| density | Procedural tessellation/mote count и отдельный particle count/cadence coefficient, не particles/tick. |
| duration | Legacy detached sprite/primitive lifetime + linear fade; periodic procedural period при repeatEvery=0. Active history/straight beam не consume duration; event rings имеют дополнительный phase fade. spriteElement — individual lifetime с opacityProfile без implicit linear fade; texturedPath не имеет `duration`. |
| alpha | Sprite/primitive opacity; audio volume принадлежит только обязательному `sound.volume`, без alpha/phase fallback. Dust не использует slot alpha. Material alpha × opacityProfile один раз с отдельным RGB tint; explicit zero молчит. |
| spread | Legacy particle-speed coefficient, не radians/full cone; material spreadRadians задаёт угол отдельно. |
| startTick | Legacy projectile periodic particle/cue gate и procedural visibility delay; не item/detached lifetime, не active history/sprite/straight beam timing. Material: nonperiodic delay либо projectile age gate; item periodic=0; texturedPath sampling age gate. |
| repeatEvery | Legacy positive cadence/procedural period; 0 выбирает auto particle cadence (projectile density-derived, item=10 global updates) и duration procedural period. Item имеет global clock + seed phase, projectile — state world ticks. Material periodic ≥1, event=0; texturedPath не имеет `repeatEvery`, без повторной detached emission. |

Ordinary slots передают schema-required common fields и conditional renderer payload; assets optional. Local `color`, profile knots и library endpoints — RGB objects с integer каналами 0..255, alpha отдельно; sound/camera не имеют цвета. Repair использует slots/assets upsert, IDs и zero-based indices, без global metadata patch. Wire хранит только три реальные caps `maxParticlesPerTick/maxParticlesTotal/maxDrawCalls`, `slotSeed`/optional `phaseOffset` и `recipeId` для runtime/PNG identity. Это технические consumer fields, не дополнительные model choices. [Exact VFX contract](VFX_MATERIAL_ELEMENTS_RU.md#runtime).

<a id="verification"></a>
## Проверка отдельно от старого census

### Текущие numeric boundaries

- `raw.item` и `raw.generatedParent` сохраняют engine/wire units. `sourceWireUnits` строится из `ParamSpec`/declared wire paths для реально присутствующих parent facts и не преобразует их. Initial Author получает scoped glossary, полный registry guide доступен standalone/Repair. [Request boundary](../development/AUTHOR_REQUEST_COMPACTION_RU.md).
- Ненулевой percent, исчезающий при `/100` или float32 storage, отвергается на точном authored leaf через `consumer_representability`. Число не округляется/заменяется; exact zero и обычные decimals остаются допустимы. Это не гарантия заметности после сложения с большими player stats.
- `sameAs` требует полного совпадения retained фактов, типов и presence; provenance `source` хранится отдельно. Speed/cooldown/penetration различия не скрываются.
- Charge release сохраняет explicit spawn speed, включая0; `channel_complete` требует целочисленного числа projectile updates, не приблизительного ratio threshold.
- Global Lowery proof связывает source primary/entity/binding identity и type/representation-aware projection. Wire-only consistency не является source proof.

Current owners: `test_registry_author_units.py`, `test_registry_wire_boundary.py`, `test_registry_receipt_identity.py`, `test_repair_frozen_contract.py`, `test_visual_presentation_metadata.py`, `test_vfx_packet_contracts.py`, `test_vfx_material_admission_contracts.py`; C# — existing `EngineRuntimeChecks`. [Test owners](../development/TESTING_RU.md) задаёт команды и isolation. Инвентарный static trace, executable CPU test, native/GPU, live model и игровой/MP результат — разные доказательства.

Старые 229-row census, rename decisions и verification counts сохранены в [units history](../archive/VISUAL_AUDIT_HISTORY_RU.md#units-audit) и immutable source blobs. Это не утверждение, что все старые VFX consumer descriptions остаются верны после .242–.246, и не current-green stamp.
