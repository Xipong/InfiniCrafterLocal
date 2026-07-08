# Runtime authoring notes — historical/current contract notes

## v0.4.239 RuntimeArchetypeSpec + runtimeContract

- Добавлены `runtimeArchetype` и `runtimeContract` как data-authored runtime language вокруг текущего `runtimePlan.engineCalls`.
- `boomerang` теперь явно представлен как archetype/phase intent (`outbound_return`) и компилируется в существующий returning runtime; return pierce учитывается в scorer как phase potential, не бесконечный baseline DPS.
- `apply_on_hit_effect(onHit=starfall)` теперь компилируется в конечный on-hit falling-star child primitive; полный `delayed_starfall` archetype/family всё ещё preserved/future, не name-router.
- `channel_beam`, `delayed_starfall`, `secondary_attack` и прочие неподдержанные advanced mechanics сохраняются как preserved/unsupported intent с `unsupportedPromises`, а не исполняются магически.
- Добавлен promise-truth validator: tooltip/fantasy/VFX/mechanicClaims сверяются с executable backing или помечаются `visual_only`/`unsupported`.
- C# получил data-only DTO `RuntimeArchetypeSpec`, `RuntimeContractSpec`, `MechanicClaimSpec`; старые JSON без этих полей остаются совместимыми.

См. `runtime_archetype_contract.md`.

## Existing notes

Эта страница содержит накопленные заметки по runtime authoring и может включать старые версии. Для текущей архитектуры сначала смотри:

- `../AGENTS.md`
- `../PROJECT_ARCHITECTURE_RU.md`
- `../LocalGenerator/PROJECT_ARCHITECTURE_RU.md`
- source of truth: `../LocalGenerator/infini_local/core/runtime_authoring/`, `../LocalGenerator/infini_local/core/result_models.py`, `../ModSources/InfiniCrafterLocal/Common/InfiniRuntimeLimits.cs`, `../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile*.cs`.

Правило: заметки ниже не доказывают, что capability реализован. Проверяй source и tests. No prose gameplay; explicit runtime contract only.

## v0.4.103 Z-Image positive-prompt sprite contract

- Z-Image Turbo/sd.cpp теперь получает positive-only sprite prompts: технические запреты и chroma-key контракт пишутся в основной prompt, negative_prompt очищается для Z-Image backend.
- Убрана лишняя фраза `Z-Image prompt`/повторяющаяся negative-boilerplate в финальном image prompt; retry теперь не раздувает comma-soup, а добавляет короткую техническую правку.
- Runtime API остаётся `v0.4.30`; это визуальный/prompt-layer cleanup, не новый gameplay contract.

- Runtime API обновлён до `v0.4.30`. `runtimeFamily` остаётся главным executable-полем; материал/форма вроде crystal_spear не выбирают damage class или executor.
- Добавлен очень лёгкий Python-side repair для маленьких моделей: direct `shoot_projectile` без `runtimeFamily` чинится только если `weaponFamily`, `delivery` или спец-`movement` дают ровно одну непротиворечивую runtime-family; `projectileFamily` считается формой снаряда и не выбирает executor. При конфликте крафт падает/идёт в LLM repair, а не уводится в кодовый fallback.
- Repair прозрачно логируется через `runtimeFamilyRepair` (`light:weaponFamily`, `light:delivery`, etc.); он не читает `projectileShape`, `projectileMotion`, `specialRule`, prompt/prose.
- Presentation/sound layers больше не восстанавливают runtime family из `delivery`/`movement`; визуал следует явному/repaired `runtimeFamily`.
- Сохранены previous-family механики: spear/thrust, returning, flail, yoyo, whip, shoot/cast/throw/summon, authored child presentation.

## v0.4.97

Текущий authored-runtime path использует Terraria weapon family contract: `perform_melee_attack`, `fire_ranged_weapon`, `cast_magic_weapon`, `summon_combat_entity` компилируются в explicit AttackSpec. Старые prose/script поля остаются только совместимостью JSON/debug и не исполняются.

## v0.4.96 Terraria weapon family runtime expansion

- Runtime authoring расширен от слабых delivery aliases к семейным engineCalls: `perform_melee_attack`, `fire_ranged_weapon`, `cast_magic_weapon`, `summon_combat_entity`.
- Добавлены отдельные runtime-семьи для flail/yoyo/whip поверх существующих swing/thrust/shoot/cast/throw/summon.
- `perform_melee_attack(family=spear|shortsword|flail|yoyo|whip|boomerang|broadsword...)` компилируется в конкретную исполняемую механику, а не в “swing/shoot по названию”.
- Runtime API обновлён до `v0.4.24`, с поддержкой чтения старого `v0.4.23`.

## v0.4.96 delivery grammar expansion

- Расширен runtimePlan delivery vocabulary: модель может писать Terraria-family слова (`spear/thrust/stab/rapier`, `bow/gun/launcher`, `staff/wand/book`, `boomerang/throw`, `summon/minion/sentry`), а адаптер канонизирует их в маленькие executable-семьи без возврата legacy prose-router.
- Добавлены alias maps для movement/effect/onHit: `laser -> phase`, `fire -> flame`, `electric -> lightning_arc`, `boomerang -> throw + boomerang movement` и т.п.
- Цель: не заставлять модель называть копьё `swing` или staff `shoot`, но и не обещать неподдержанный полноценный vanilla yoyo/whip/flail executor.

## v0.4.96 spear/thrust delivery cleanup

- Added explicit `delivery=thrust`/`spear` for spear, lance and polearm outputs; this is a held owner-checked thrust, not a sword swing and not a free-flying bolt.
- Generated spear-thrust projectiles now stay attached to the player, use line collision along the thrust, and draw at a readable visual size independent from the small hitbox.
- Parent knowledge scoring no longer treats owner-checked vanilla spear projections as long-lived free-flight projectiles.

# Runtime authoring v0.4.96

Текущая рамка:

1. C# отдаёт Python raw item/projectile/ammo данные.
2. Python передаёт компактные raw parent cards в ЛЛМ.
3. ЛЛМ авторит `runtimePlan.engineCalls`.
4. Код валидирует диапазоны/сетевой бюджет/краши и компилирует в runtime.
5. Спрайты генерируются через persistent stable-diffusion.cpp server. CLI удалён.
6. В мультиплеере крупные ассеты качаются по HTTP asset sync, а не через Terraria packet.


## v0.4.93 child projectile presentation

Боевые дочерние projectile не наследуют prose/prompt/full VFX-manifest родителя. При этом они сохраняют отдельную authored-презентацию: готовый `ChildSpritePath` используется как `ProjectileSpritePath` дочернего снаряда, `SecondaryProjectileShape` / `SecondaryMaterial` задают fallback-форму, цвет и плотность следа берутся из authored-полей родителя с жёсткими капами.

## Agent guardrail reminder

For current behavior, use source of truth files named above. If you change X, also check Y across Python compiler, C# DTO/runtime, tests and docs. Runtime authoring eventually emits explicit `GeneratedItemData` and `VfxManifest` fields; no prose gameplay. MP remains **server-authoritative** in the C# craft flow. Assets use final filenames and HTTP `/get_asset`; world-scoped cache/registry must not leak across worlds. Do not claim a second model-judge exists unless source implements it. `dict[str, Any]` / dicts / dictionaries remain an architecture risk in Python internals.
