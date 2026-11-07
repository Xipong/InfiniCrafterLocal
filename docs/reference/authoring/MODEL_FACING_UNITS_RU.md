# Model-facing units — Gameplay / Visual / VFX

<a id="authority"></a>
## Один источник диапазонов и преобразований

Gameplay параметры, descriptions, domains, units и exact wire mapping — [capability_registry.py](../../../generator/infini_local/core/runtime_authoring/capability_registry.py) (`CapabilitySpec` и конкретные объявления параметров). Общий контракт параметра и его точная проекция — [parameter_contract.py](../../../generator/infini_local/core/runtime_authoring/parameter_contract.py) (`ParamSpec`); model/audit представления registry — [registry_views.py](../../../generator/infini_local/core/runtime_authoring/registry_views.py). Структура — [program_schema.py](../../../generator/infini_local/core/runtime_authoring/program_schema.py), executable projection/receipts — [compiler.py](../../../generator/infini_local/core/runtime_authoring/compiler.py) и [technical_lowering.py](../../../generator/infini_local/core/runtime_authoring/technical_lowering.py). Полный roster — generated [capability inventory](../generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md), не ручная копия всех registry rows.

Путь изменения: registry → actual provider schema/prompt → validator/Repair → compiler receipt → strict wire → C# DTO/executor → regression. Исторический rename не становится Author alias; C# wire сохраняет объявленные старые leaves. Category/name/prose не выбирают единицу, sentinel, механическую композицию или default.

Свежий Gameplay Author использует `infini.runtime-program.authoring.v7`; runtime API остаётся `infini.runtime-program.v5`, persisted wire — `infini.runtime-program.wire.v3`. Author/Repair выбирают игровые расстояния в **блоках**, длительности в **секундах**, скорости в **блоках/с**. Смысл и диапазон каждого конкретного поля по-прежнему задаёт registry, а не suffix-эвристика.

| Семейство | Author | Canonical lowering в прежний wire |
|---|---|---|
| World distance | Объявленные registry distance fields, включая `radius`, `range`, `*Blocks` | ×16, если consumer хранит world pixels; already-block values не конвертируются повторно |
| World duration | Registry duration fields в секундах | ×60, ближайший целый world tick, половина тика вверх |
| Projectile velocity | Registry world speed/impulse fields | ×16/(60×N), N принадлежит этому target |
| Projectile gravity acceleration | `accelerate_y.accelY` | ×16/(3600×N²) |
| Continuous NPC acceleration | Registry continuous acceleration fields | ×16/(3600×N), по частоте вызывающего projectile |
| One-off impulse / player bonus / ammo contribution | Registry world speed/impulse fields | ×16/60; не использовать N projectile как множитель бонуса Player/Item |
| True angular rate | Registry angular-rate fields | /(60×N) |
| Technical counters, ratios, percent | Declared count/coefficient/percent | Их прежний контракт; это не duration/rate по одному названию |

N = explicit `projectile_collision.updatesPerTick` **того же target**; у ребёнка собственный N, а не N emitter-а. Missing, malformed и ambiguous clocks не заменяются единицей. Полный прежний engine domain доступен для каждого N=1..6 через registry-derived contextual Author bounds; engine bounds и native clamps не пересматриваются.

Секундная проекция — объявленная quantization, не обещание точного восстановления исходного decimal: половина тика округляется вверх. Ненулевой эффект не может исчезнуть при lowering/storage. Для integer world-pixel wire, например `offsetBlocks`, сохраняется точная пиксельная решётка; произвольная дробь блока не округляется скрыто.

Author/Repair принимают только текущие registry keys. Receipt проверяет точные current source paths, значения и ownership; source-free audit подтверждает лишь внутреннюю согласованность текущей проекции, не наличие исходного Author. Predecessor paths и старые единицы не являются aliases. Проверки: `test_author_world_unit_projection.py` и numeric/Repair/receipt controls.

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

Native `extraUpdates` даёт `N=extraUpdates+1` AI/movement updates/world tick. Wire velocities/gravity и engine local NPC cooldown сохраняют прежние engine units, но Author задаёт перечисленные физические world rates: lowerer учитывает N детерминированно. `scale_velocity.scalePerUpdate` и другие явно объявленные per-update coefficients остаются коэффициентами алгоритма; `immunity.localCooldown` и `initialIgnoreCountdownUpdates` — counts. Native `lifetimeTicks`, charge/warmup/return-after и scheduler `delayTicks` остаются world ticks; их Author counterparts теперь Seconds. VFX material simulation использует world ticks независимо от projectile N.

**16 world pixels = 1 блок**. Texture texels/canvas resolution и normalized UV — отдельные пространства; UV нельзя делить на16. Явные `*Px` hitbox/sprite/hand/beam geometry сохраняют пиксели. Standing unmounted collider обычного игрока — 20×42 world px (1,25×2,625 блока); базовый бег — 11,25 блока/с; начальная скорость обычного прыжка — примерно 18,79 блока/с вверх. Это сравнения для normal gravity без modifiers, не balance presets: initial jump velocity не задаёт высоту/дальность без hold duration, gravity и движения.

Только для прямолинейного движения с постоянной скоростью без столкновений дальность в блоках равна `speedBlocksPerSecond × lifetimeSeconds`. Movement/controller может полностью изменить эту оценку. Минимальный event period берётся из registry, не из формулы дальности.

Пример **частичных capability params**, не полный Author response: `spawn` задаёт `velocity={"speed":120}`, `count=1`, `spreadRadians=0`, `offsetBlocks=0.5`, `aim=cursor`, `position={"at":"owner_center"}`; `accelerate_y` — `accelY=900`; `projectile_lifetime` — `lifetimeSeconds=2.5`. Отдельный collision call явно задаёт N. При N=2 исполняемые wire speed=16 px/update, gravity increment=1 px/update², offset=8 px, lifetime=150 world ticks. Эти значения проверяет production compiler tracer; старые Author `constantSpeedPxPerUpdate/accelY/lifetimeTicks` не являются текущими keys.

<a id="gameplay"></a>
## Важные отличия единиц от обещаний

| Группа / поле | Буквальный смысл |
|---|---|
| Item use/animation | `useTimeSeconds` — базовый native use/reuse interval, `useAnimationSeconds` — независимая длина animation; отличия могут дать несколько uses, не обязательно один projectile/click. |
| Item facts | `manaCost` — базовая Item.mana до player modifiers; `valueCopper` — exact Item.value, не inferred resale; `craftYield` — запрос, фактическая stack выдача capped maxStack. Loaded rarity/ProjectileID/BuffID/DamageClass копируются из соответствующих source facts, не угадываются из имени. |
| Display/collision | Item scale, projectile `drawScale`, entity Visual scale — multipliers, не collision hitbox/radius. World pixels, tile radii и canvas pixels различны. |
| Knockback/light/aggro/mana regen | Item/Projectile.knockBack — engine strength; Lighting strength — RGB coefficient, не radius; aggro — raw Player.aggro (может быть отрицательным), не probability; manaRegen — raw Player.manaRegenBonus, не mana/s. |
| Ammo | `speedBonus` — signed базовый Item.shootSpeed вклад в vanilla PickAmmo, не финальная скорость projectile. `usesPotionRules` — Item.potion/use eligibility/sickness gating flag, не duration. |
| Equipment percentages | Уже объявленный /100 adapter; additive modifier, chance, percentage points и source-damage percent различны. Armor set требует полного matching set и head phase; equipment phase/damageClass — explicit selector, не router. Итог зависит от других Terraria modifiers/clamps. |
| Mining / ore sense | Mining speed multiplier делит Player.pickSpeed: больший divisor даёт меньший pickSpeed и более быстрое копание. `treasureSense` включает Player.findTreasure; это bool→0/1, не произвольный исторический oreSenseRadiusTiles. |
| Buff movement | `moveSpeedBonus` — additive percent [−50,200]; `movementSpeed = percent/100`, как у equipment. `20` добавляет `0.2` к Player.moveSpeed до остальных modifiers. `jumpSpeedBonus` — базовый вклад в Player.jumpSpeedBoost, не обещание итоговой высоты прыжка. |
| Projectile sentinels | `pierce=-1` — unlimited; `immunity:"once_per_npc"` — one-hit-per-NPC только local immunity; 0..600 raw cooldown counts, не world-tick duration. Owner immunity использует отдельный shared путь. |
| Movement/controller coefficients | `seek` lerp и `homing` angular cap — разные законы; `scale_velocity.scalePerUpdate` применяется на каждом AI update. `target_and_fire.sameTargetBias` меняет score, не вероятность; при soft range геометрическая граница не гарантируется. |
| Event effects | Spawn count — children; chain count — max дополнительных NPC. damageMultiplier берёт authored **base damage источника**, rounded/minimum 1 до defense, не damageDone и не additive percent. heal damageFraction — доля фактического damageDone; maxHeal — HP/event. |
| Pull / mobility | Pull strength — per-event/update velocity impulse с NPC knockBackResist, не displacement/second. radiusTiles ищет NPC только без directTarget и игнорируется owner_to_target. safeTileOnly — bounds/solid/lava checks, не universal hazard guarantee; recall_home его игнорирует. |
| Held visibility | `item_use.hideUseGraphic` управляет native item body; PNG metadata не выбирает release schedule или gameplay. |

Terminal owners: [GeneratedItemData.Apply](../../../mod/InfiniCrafterLocal/Common/Models/Runtime/GeneratedItemData.Apply.cs), [GeneratedItem](../../../mod/InfiniCrafterLocal/Content/Items/GeneratedItem.cs), [GeneratedProjectile executors](../../../mod/InfiniCrafterLocal/Content/Projectiles/Motion/GeneratedProjectile.Executors.cs), [RuntimeProgramExecutor](../../../mod/InfiniCrafterLocal/Common/Runtime/RuntimeProgramExecutor.cs), [delayed scheduler](../../../mod/InfiniCrafterLocal/Common/Runtime/RuntimeDelayedActionScheduler.cs), [player mobility](../../../mod/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.Mobility.cs). Exact opcode/wire route — canonical registry/receipts; старая таблица consumer line numbers не authoritative.

<a id="conversions"></a>
## Нули, нейтрали, nullable и доказуемые conversions

Regen `lifeRegen` у accessory/armor и `setBonusLifeRegenHpPerSecond`: authored [−50,100] с шагом .5, integer engine wire [−100,200], `wire=2×HP/s`, inverse `HP/s=wire/2`; сохраняются знак, 0 и endpoints. Generated buff regen имеет собственный registry domain [−50,60] с тем же half-HP lattice; не расширять его до signed equipment domain.

Existing /100 или bool→0/1 projection доказана только на своём declared image. Процентный /100 — объявленный scale adapter с обычной IEEE-754 точностью, **не биекция всех JSON/binary64 представлений**: соседние обычные doubles могут дать один результат деления; условие `x/100*100==x` не вводится как новый фильтр обычных значений. Такая точность не разрешает молча превращать ненулевой эффект в нейтраль. Она также не гарантирует exact binary32 round-trip произвольного JSON decimal или восстановление каждого старого DTO. Например bool ore sense не восстанавливает старые radius 2..60. Физические единицы меняются только объявленной canonical проекцией с их sign/zero/sentinels и engine domains; duration quantization описана отдельно выше. Ни prose, ни category не дают права вводить другую проекцию.

Buff movement использует тот же percent adapter и guard `nonneutral_must_remain_nonneutral`, что equipment. Float32 factors остаются выразимы: significand содержит не более 24 bits, умножение на `100 = 25×4` требует не более 29 significant bits и точно помещается в binary64; деление такого percent на 100 возвращает factor. Это доказательство о C# consumer values, не о произвольном historical JSON double. Archived wire не пересчитывается; retired `moveSpeedBonusFactor` receipts больше не принимаются, включая old-neutral omissions. Current signed-zero/underflow/source/Repair checks сохранены.

`false`, `0`, `0.0`, absent и `null` не взаимозаменяемы; frozen equality type-aware (true ≠ 1 ≠ 1.0). Только optional params с одинаковыми declared default/neutral допускают Author omission с отдельным receipt после всей composition validation. Missing dependency/invalid present value/empty required effect остаются RED. Repair omission — no-change; accepted absence не заполняется вне exact permissions. Правила — [declared neutrals](DECLARED_NEUTRAL_OMISSIONS_RU.md) и [targeted Repair](../../development/pipeline/TARGETED_REPAIR_PROTOCOL_RU.md).

Структурные `entity/binding/call` IDs, schema version, primary selection и diagnostic paths — не физические units. `bindings[].stackCost` (saved wire: `usePolicy.stackCost`) — точно 0 или 1 экземпляр generated item/accepted use; contactDamage — независимый bool. `*IndicesDelete` — zero-based array position, не tick. Author array maxima/Repair bounds — schema transport limits; compiler-owned runtime maxEntityCount/maxChildDepth/maxEventSpawnsPerActivation — bounded graph/ledger, не model-authored размеры.

<a id="visual"></a>
## Visual числа и schema transport

[Visual guide](../presentation/VISUAL_PRESENTATION_METADATA.md#size-axis) содержит required fresh v2 `renderSizePx` (integer 1..512, complete final-frame max-side world px), `forwardAngleDegrees` (finite −180..180, 0=+X, clockwise y-down final-PNG axis), independent canvas enums, inventory/world/entity multipliers, final-canvas normalized grip и mount offsets. Item-body/reuse inherit root size/canvas/axis; distinct baked owns свои choices. Canvas/fill не задают world footprint; `q=R/max(actual final frame)` применяется только при render, не в stats/hitbox/pose/network. Сохранённая wire absence остаётся historical без defaults/migration. Director и Repair получают exact G/itemUse/primary IDs, drivers, draw formulas и canonical fill/padding read-only; Visual не меняет mechanics/held visibility hints. Ordinary entity branches/Repair fields читаются у `_response_schema`/`_visual_repair_schema`, не из старой universal entity table.

Optional-null inverse допустим только для объявленных optional properties на **фактическом json_schema** transport. json_object/off/downgrade не получает этот alias; required coordinate null остаётся invalid. Zero-based deletion indices и текстовые длины — transport, не visual units.

<a id="vfx"></a>
## VFX: common controls не универсальная физика

Source: [VFX semantics](../../../generator/infini_local/core/vfx/contract.py), [Director/Repair schema](../../../generator/infini_local/core/vfx/schema.py), [presentation](../presentation/PRESENTATION_CONSISTENCY_RU.md#renderers) и [material contract](../presentation/VFX_MATERIAL_ELEMENTS_RU.md).

VFX Director получает accepted gameplay read-only. World pixels, texture texels, normalized UV и RGB не взаимозаменяемы. У body copies коэффициент `q=renderSizePx/max(actual final PNG frame)` принадлежит выбранному texture owner; не умножай повторно уже применённые entity/item scales.

| Поле / payload | Единицы и граница |
|---|---|
| `duration` | Individual lifetime в world ticks только у renderers, которым он принадлежит. Shape имеет explicit opacity endpoints, spriteElement — opacityProfile, libraryParticle — endOpacity; общего дополнительного fade нет. |
| `startTick` | Event delay либо projectile periodic age gate. Item periodic emitters требуют 0; historyTrail использует sample ages и не принимает это поле. |
| `repeatEvery` | Явная world-tick cadence: periodic ≥1, event=0 у shape/material/library/native emitters. Event sound scheduling-поля не принимает; live path их не использует. |
| `alpha` | Renderer-specific draw multiplier. Shape/contour имеют собственные opacity fields, Dust/light/sound не принимают common alpha. |
| Geometry / motion | Явные `*Px`, radians, native world-tick velocity/acceleration либо normalized profile position по nested schema, не общие scale/density/spread knobs. |
| Color | Локальные RGB objects с integer каналами 0…255; opacity отдельно. Sound/camera color не принимают. |

Каждый renderer получает только свои consumed fields. Запрещённое поле не становится optional default. `texturedPath` не имеет `duration/repeatEvery`; sound требует exact sample и `volume/pitch/pitchVariance`, без alpha-derived громкости. Точные sound/shape/history/material payloads описаны у собственных owners.

Wire caps `maxParticlesPerTick/maxParticlesTotal/maxDrawCalls`, `slotSeed`, optional `phaseOffset` и `recipeId` — технические runtime/identity поля, а не дополнительные творческие решения. Repair разрешает только exact invalid leaves; принятая пустота и нули frozen.

<a id="verification"></a>
## Проверка

### Текущие numeric boundaries

- `raw.item` и `raw.generatedParent` сохраняют engine/wire units. `sourceWireUnits` строится из `ParamSpec`/declared wire paths для реально присутствующих parent facts и не преобразует их. Initial Author получает scoped glossary, полный registry guide доступен standalone/Repair. [Request boundary](../../development/pipeline/AUTHOR_REQUEST_COMPACTION_RU.md).
- Ненулевой percent, исчезающий при `/100` или float32 storage, отвергается на точном authored leaf через `consumer_representability`. Число не округляется/заменяется; exact zero и обычные decimals остаются допустимы. Это не гарантия заметности после сложения с большими player stats.
- `sameAs` требует полного совпадения retained фактов, типов и presence; provenance `source` хранится отдельно. Speed/cooldown/penetration различия не скрываются.
- Charge release сохраняет explicit spawn speed, включая0; `channel_complete` требует целочисленного числа projectile updates, не приблизительного ratio threshold.
- Global Lowery proof связывает source primary/entity/binding identity и type/representation-aware projection. Wire-only consistency не является source proof.

Current owners: `test_registry_author_units.py`, `test_registry_wire_boundary.py`, `test_registry_receipt_identity.py`, `test_repair_frozen_contract.py`, `test_visual_presentation_metadata.py`, `test_vfx_packet_contracts.py`, `test_vfx_material_admission_contracts.py`; C# — existing `EngineRuntimeChecks`. [Test owners](../../development/TESTING_RU.md) задаёт команды и isolation. Инвентарный static trace, executable CPU test, native/GPU, live model и игровой/MP результат — разные доказательства.
