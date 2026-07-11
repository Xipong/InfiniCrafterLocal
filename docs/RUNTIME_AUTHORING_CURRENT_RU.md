# v15 charge-release + sentry

- `charge_release` is executable through ranged/magic/low-level projectile calls with two bounded authored knobs.
- `deploy_sentry` is the only true sentry call; temporary helpers remain temporary.
- Both slices have explicit Python/C# owners and full final-`AttackSpec` projection tests.
- Protocol 14 syncs damage class, charge state and sentry scalar state.
- See `CHARGE_RELEASE_SENTRY_RUNTIME_RU.md`.

## 2026-07-10 — pre-livetest author/image contract v12

- Runtime API Python/C# синхронизирован на `v0.4.48`; ProjectileSyncVersion остаётся 12.
- Active helper call — `spawn_temporary_helper_projectile`; это bounded temporary projectile, не minion/sentry lifecycle. Удалённые function names отклоняются.
- `on_expire` означает любой projectile kill; `shotCount` — simultaneous multishot, не timed burst.
- Generated arrow/bullet ammo не обещает собственного generated AttackSpec; authored throwable/dart использует weapon/consumable_weapon + empty ammoFor.
- Visual Director авторит только `visualKit.bakedAssets`; неканонические asset-decision поля отклоняются; канонический output содержит только `visualKit.bakedAssets`.
- Projectile/child PNG описывает одно тело; runtime multiplicity не запекается в sprite.
- VFX Director получает compiled runtime fields, а не восстанавливает механику по prose.
- Десять ручных предлайфтестовых трейсов: `PRE_LIVETEST_MANUAL_TRACES_V12_RU.md`.
- Sparse-output behavior не изменён.

## 2026-07-10 — generic overhead barrage v11

- Каноническая delivery-механика называется `overhead_barrage`; старые family tokens больше не загружаются и не мигрируются.
- Executor больше не навязывает `star` effect, falling-star shape, magic/staff carrier или `tileCollide=false`. Projectile family/shape/effect/VFX наследуются из authored spec.
- Daedalus-like ranged payload сохраняет `arrow + effect=none`; Starfury-like `delivery=swing` сохраняет melee item hitbox и authored `star` projectile/effect; cast carrier остаётся magic.
- Исправлено сохранение explicit `delayTicks=0`; sparse/default policy не менялась.
- Fallback pose/use sound выбираются только по exact `delivery` enum, не по item names, tooltip или projectile theme.

# Runtime authoring — current state

## 2026-07-10 — maintainable runtime v10

- Добавлен exact secondary lifecycle `on_expire` через отдельный `runtime_authoring/secondary.py` и `GeneratedSecondaryTriggerPolicy.cs`; mixed triggers и скрытая комбинация `on_expire` с child-producing on-hit отвергаются.
- `overhead_barrage` — отдельный finite vertical slice: собственный Python policy, marker/delay executor и bounded descending children. Никакой общей trigger/state-machine.
- `state_meter` и `triggered_action` скрыты из active prompt, но старые/debug payloads остаются читаемыми и inert.
- Удалены мёртвые name/prose projectile helpers. Gameplay routing по prose не добавлен.
- Добавлен `docs/RUNTIME_VERTICAL_SLICES_RU.md` и contract tests, закрепляющие одного владельца на vocabulary/compiler/executor.
- Balance разделён через маленький policy-owner `core/balance_mode.py`: `safety` default, `normalize` opt-in, `report` diagnostic. Формулы не переписаны и не перенесены в mode-owner.
- Sparse-output behavior не изменён: explicit zero/default остаётся authored intent и сохраняет provenance.
- Projectile protocol: `ProjectileSyncVersion = 13`.
- Verification: 330 tests passed; prompt 22 422 / 24 000 chars, 24 active functions; static C# and hygiene checks PASS; real tML build skipped because `dotnet` is unavailable.

## 2026-07-10 — gameplay authoring/runtime completion v9

- `channel_beam` теперь конечная исполняемая capability, а не preserved intent: explicit `runtimeArchetype.family=channel_beam` или `cast_magic_weapon(family=channelled_beam)` компилируется в canonical `runtimeFamily=beam`. Слова `beam/laser/prism` в name, tooltip, visual prompt, projectileShape или material ничего не выбирают.
- C# исполняет один owner-held beam: точный duplicate guard по generated item id, `Collision.LaserScan` по стенам, line hitbox, синхронизация длины/направления, bounded width/range/charge и local-NPC immunity cadence.
- Channelled beam периодически платит фактический `HeldItem.mana` с cadence из authored `useTime`; zero-mana beam остаётся допустимой универсальной capability. `noItems`, CC, release и отсутствие mana корректно завершают holdout.
- `rangeTiles` и `homingStrength` больше не мёртвые поля: они проходят compiler/genome/AttackSpec/net sync и управляют конечными homing executors; `homingStrength=0` означает executor default, а `0..1` масштабируется в bounded steering.
- `useAnimationTicks`, `knockback`, `autoReuse`, beam knobs, immunity cadence и sound catalog ids получили корректный Applied-vs-Authored provenance.
- Beam balance считает реальную частоту повторных попаданий через `immunityCooldown`, а не item spawn rate; exact beam считается одним активным primary projectile. При опасном child-proc pressure safety сначала увеличивает immunity cadence, а не выдумывает другой дизайн.
- Удалены `weaponSubfamily` и `attackPatternTags`: runtime/presentation больше не несут вспомогательную taxonomy, которую будущий код мог бы превратить в alias-router.
- Починен end-to-end разрыв sound v8: exact sound ids больше не теряются при пересборке genome и доходят до финального `AttackSpec`.
- Починен реальный headless GUI import: `settings_gui` теперь загружает `tk_compat` через module import, а не удерживает stale package attribute после изоляции `tkinter`.
- Historical v9 verification: 317 passed; prompt 23 571 / 24 000 chars. Static C# and project-hygiene contracts: PASS. Реальный tModLoader build не выполнен только из-за отсутствующего `dotnet` в окружении.


## 2026-07-10 — exact Terraria sound catalog v8

- LLM получает один полный каталог из 92 точных акустических ролей: 60 use + 32 impact. Это не таблица оружия и не aliases по названиям предметов.
- `soundUseCatalogId` / `soundImpactCatalogId` принимаются только как exact ids; неизвестные значения попадают в `rejectedSoundCatalogIds`, затем используется маленький fallback только по уже скомпилированным `runtimeFamily/effect/onHit`.
- Старые `soundUseSearchQuery` / `soundImpactSearchQuery` удалены из Python, DTO и C#: никакой текстовый запрос не может стать скрытым классификатором. Future seam принимает только готовые `catalogId/path/source`.
- Идентификаторы каталога описывают акустическую роль (`magic_spectral`, `summon_skittering`), а не конкретный предмет/моба; конкретные `Zenith/Crystal Serpent/Hornet/Spider`-подобные имена удалены.
- Name, tooltip, material prose, projectile descriptions и search queries не выбирают built-in звук.
- Каталог Python и C# проверяется на полное совпадение; отдельный guard требует не менее 65 реально разных Terraria `SoundID`, чтобы большой список не схлопнулся в пять клипов.
- Vanilla `SoundStyle.Volume`, `Pitch` и встроенная `PitchVariance` не затираются: authored volume работает как множитель, pitch как offset, variance задаёт минимум.
- `soundPitchVariance` теперь исполняемый параметр `0..0.6`, проходит через JSON/DTO/child projectile/network sync и задаёт `SoundStyle.PitchVariance`. Старое поле `variation` остаётся JSON-совместимым отражением.
- `soundVolume` приведён к реальному диапазону `SoundStyle.Volume` — `0.05..1.0`; значения выше 1 больше не обещаются модели и не теряются молча в tModLoader.
- Prompt удерживает весь каталог в 24k-char budget за счёт удаления дублирующих инструкций, а не урезания vocabulary.

## v0.4.239 RuntimeArchetypeSpec + runtimeContract

- Добавлены `runtimeArchetype` и `runtimeContract` как data-authored runtime language вокруг текущего `runtimePlan.engineCalls`.
- `boomerang` теперь явно представлен как archetype/phase intent (`outbound_return`) и компилируется в существующий returning runtime; return pierce учитывается в scorer как phase potential, не бесконечный baseline DPS.
- Historical note: ранняя тематическая формулировка была заменена generic delivery `overhead_barrage`; текущий runtime принимает только каноническое значение.
- `channel_beam` и canonical `overhead_barrage` имеют отдельные finite executors; `secondary_attack` и остальные неподдержанные advanced mechanics сохраняются как preserved/unsupported intent с `unsupportedPromises`, а не исполняются магически.
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

Текущий authored-runtime path использует Terraria weapon family contract: `perform_melee_attack`, `fire_ranged_weapon`, `cast_magic_weapon`, `spawn_temporary_helper_projectile` компилируются в explicit AttackSpec. Старые prose/script поля остаются только совместимостью JSON/debug и не исполняются.

## v0.4.96 Terraria weapon family runtime expansion

- Runtime authoring расширен от слабых delivery aliases к семейным engineCalls: `perform_melee_attack`, `fire_ranged_weapon`, `cast_magic_weapon`, `spawn_temporary_helper_projectile`.
- Добавлены отдельные runtime-семьи для flail/yoyo/whip поверх существующих swing/thrust/shoot/cast/throw/summon.
- `perform_melee_attack(family=spear|shortsword|flail|yoyo|whip|boomerang|broadsword...)` компилируется в конкретную исполняемую механику, а не в “swing/shoot по названию”.
- Runtime API обновлён до `v0.4.24`, с поддержкой чтения старого `v0.4.23`.

## v0.4.96 delivery grammar expansion

- RuntimePlan использует конечные exact family/delivery значения. Семейные engine calls понижаются в маленькие executable-семьи без name/tooltip/material routers и без миграции удалённых spellings.
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
