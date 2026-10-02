# Visual/image/VFX/units: исторические решения и provenance

<a id="scope"></a>
## Как читать этот журнал

**История, не активный контракт, не backlog и не current-green stamp.** Counts/RED→GREEN/package observations ниже принадлежат указанным старым проходам; эта Markdown-консолидация не повторяла их live/GPU/game/MP проверки. Изменения .242–.246 и последующие accepted test/provider refactors могут сделать старые имена, строки, описание consumer или verdict неактуальными.

Активные guides: [Visual projects/metadata](VISUAL_PRESENTATION_METADATA.md), [presentation renderers](PRESENTATION_CONSISTENCY_RU.md), [VFX material elements](VFX_MATERIAL_ELEMENTS_RU.md), [image lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md), [model-facing units](MODEL_FACING_UNITS_RU.md). Actual source/validator/DTO важнее старого отчёта; verification commands и current test owners — [TEST_CONTRACT_OWNERS_RU.md](TEST_CONTRACT_OWNERS_RU.md).

<a id="provenance"></a>
## Полные исходные записи

Сохранённые исторические bytes доступны в Git commit `e715b34ab89ec41d2528417aff5ab8847ad15f62` и во внешнем `../artifacts/documentation-consolidation/baseline-docs.tar.gz` (от корня checkout). Документация не требует этот внешний архив для build/runtime и не включает его в portable source-generator bundle.

Для любой строки таблицы: `git show e715b34ab89ec41d2528417aff5ab8847ad15f62:<исторический путь>`. Это точный local provenance handle, не выдуманная hosted URL.

| Запись | Исторический путь в commit/archive |
|---|---|
| Image flags read-only audit | `IMAGE_FLAGS_AUDIT_RU.md` |
| Prompt audit старой claims-архитектуры | `PROMPT_AUDIT_REPORT_RU.md` |
| Полный параметрический units census | `docs/MODEL_FACING_UNITS_AUDIT_RU.md` |
| Первичные presentation fixes/решения | `docs/PRESENTATION_CONSISTENCY_RU.md` |
| Принятые simple presentation choices | `docs/PRESENTATION_SIMPLE_RU.md` |
| Renderer requirements / Live20 comparison | `docs/VFX_RENDERER_REQUIREMENTS_AND_LIVE20_RU.md` |
| Откат .243–.244 | `docs/VFX_ROLLBACK_RU.md` |
| Tick illustration со старыми Author keys | `LocalGenerator/docs/TERRARIA_TICK_GUIDE_RU.md` |

<a id="image-flags"></a>
## Image flags: read-only аудит 0.4.234 (2026-07-29)

Старая таблица backend/sd.cpp/asset-gating/postprocess/delivery/VFX/concurrency была inventory конкретного среза, не постоянной копией config defaults. Ссылки на line numbers, old tests и оценки «не покрыт» не используются как актуальная coverage matrix.

| Историческое finding/proposal | Разрешённый вывод сегодня |
|---|---|
| `INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES`, `INFINI_VISUAL_GENERATE_IMPACT_IMAGES`, `INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES` управляли GUI rows без image-generation consumer | В нынешнем production/config owner этих switches нет; exact authored assetMode/project и VISUAL_ASSET_MODE — [active owners](IMAGE_ASSET_LIFECYCLE_RU.md#configuration). Это не три оставшихся открытых дефекта. |
| Предложение `INFINI_IMAGE_GENERATION_CONCURRENCY` (1..4) для shared backend semaphore | Реальный нынешний key — **`INFINI_IMAGE_MAX_CONCURRENCY`**, gate=IMAGE_GENERATION_GATE. Старое предлагаемое имя не alias и не инструкция создать второй semaphore. |
| Предложения `INFINI_VFX_IMAGE_GENERATION`, `INFINI_EQUIPMENT_SPRITE_CANVAS` | Не приняты как новые controls этим документом. Их нельзя выдавать за runtime флаги или обязательный backlog; текущие scopes/canvas задают Director/schema/config. |
| Нужны authorship/retry/concurrency/toggle/removal tests | Старые рекомендации были планом; current owners — image attempt/adapter/ingredient/sprite/asset-transfer contracts и settings tests, не снятая old coverage table. |

Immutable source сохраняет полный 1.1–1.7 inventory, old removal locations, production-consumer table, proposals 4.1–4.3, test matrix 5.1–5.3 и сводку. Ни secret config, ни generation output этим refactor не создан.

<a id="prompt-audit"></a>
## Prompt audit: старые claims и позднее обещание

Отчёт использовал сохранённый Exact20 `live20-exact20-ea56-final-20260731-234617`: 20 Author, 1 scoped Gameplay Repair, 20 Visual, 20 VFX и 8 VFX Repair. Это **цитата старого evidence**, не новый прогон; исходная панель по записанному рядом с checkout пути сейчас не найдена. Проверяемый provenance — полный Git/archive отчёт; независимая повторная инспекция отсутствующего ledger здесь не заявляется.

| ID старого отчёта | Уникальное наблюдение / решение, не current-open verdict |
|---|---|
| MAJOR-1 | Name-substring canonical classifier: `GlowingMushroom→wings` из gloWING, `JungleSpores→ore` из spOREs; Boomstick/Minishark→ammo, HellstoneBar→stone/block. Рекомендация: source identity/runtime/placement/visual facts вместо taxonomy/hardcases. Model выбирает explicit runtimeProgram; code не выбирает noun/family. |
| MAJOR-2 | Ранний concept стал recursive fantasy, notableEffects были [] на всех 20 outputs с 2–16 calls. `lens_finch_staff` обещал loyal avian minions при straight projectile; Glowshroom Elixir prose обещал inventory/equipment light при backing add_hold_light. ID citation не доказывает текстовую semantic truth. |
| MAJOR-3 | Предложен late same-response realization вместо second LLM/verifier; description/playerExperience — human-visible report, не executable authority. Старые backedByClaims/trace форма и claims порядок **не** текущая схема. Текущий root/realization contract — [Author guide](LOW_LEVEL_RUNTIME_AUTHORING_RU.md) и canonical schema. |
| MAJOR-4 | Repair после binding mutation должен согласовать позднее обещание с **принятой**, не rejected out-of-scope частью patch. В Exact20 единственный Repair сменил inputs, оставил metadata/claims пустыми. Atomicity/partial-salvage риск сохраняется как provenance решения, не разрешение semantic rewrite или расширение frozen scope. Текущая policy — [Repair protocol](TARGETED_REPAIR_PROTOCOL_RU.md). |
| MAJOR-5 | Full early concept в Visual handoff мог утечь как final gameplay promise; рекомендованы physical intent, accepted runtime, realization и same-object project mapping. |
| MAJOR-6 | Universal entity prompt/silhouette/identity/impactPrompt писал неиспользуемые briefs для reuse/runtime_geometry/no_asset. Active conditional projects и selected impact request теперь описаны в [Visual guide](VISUAL_PRESENTATION_METADATA.md#owners), не старой таблице. |
| MAJOR-7 | Exported sort_keys=True менял model properties order; runtime provider dict order и generated JSON artifact нельзя считать одним consumer. Старое решение не позволяет вручную переформатировать generated artifacts. |
| MAJOR-8 | VFX description="" был dormant hook; нельзя считать, что старый VFX видел final realization. Текущий handoff сверяется по actual source/packet, не по имени hook. |

MINOR-1..8 того прохода: согласован program-before-claims order; удалена ранняя копия balanceCorridor (сам source-backed balance reference оставлен); различены model inference и запрещённый deterministic prose routing; prompt invariant renamed primaryEntityOwnership без смены transaction primaryEntitySelection; createTile/createWall удалены только из дублирующей crossModIdentity; убрана ссылка mergeLogic/sourceReading; accepted claims переданы read-only Repair; Visual final transparent background отделён от opaque request. Нынешний raw solid-key input описан в [image contract](VISUAL_PRESENTATION_METADATA.md#image-contract), а не трактуется по старой короткой инструкции.

Старый проход записал focused 78 / full 194 Python, 10 schemas, 51/51 capability prompt usability и frozen/policy/static/hygiene gates. Synthetic common prefix изменился с 77 605 до 81 361 chars; это исторический cache-prefix probe, не нынешний token/latency замер. C# gameplay, tooltips, live/API, game/build/package не менялись этим minor pass. Tree уже был dirty; он не объявлял весь snapshot independently audited. Финальная последовательность 7 старых recommendations — provenance, не список работ, которые все до сих пор открыты.

<a id="units-audit"></a>
## Units census: rename/conversion решения

Исходный аудит записал 52 capabilities / 229 params / 180 numeric, 229↔229 matching, классы keep=164 / identity-rename=14 / declared-convert=27 / engine-units=24. Это census того среза: полный registry text/old→new/wire-leaf/consumer trace доступен по immutable handle, а не поддерживается второй ручной таблицей. Исторический snapshot `icl-units-before.json` и `icl-unit-{item,movement,events,visual-vfx}-audit.md` названы входным evidence; они не были runtime authority и их наличие здесь не обещается.

Identity-renames (capability scope важен):

| Scope | Старый Author key → новый, значение wire не изменилось |
|---|---|
| configure_item_use | releaseTiming → heldSpriteVisibilityHint |
| configure_vanilla_ammo_item | shootSpeedPxPerTick → shootSpeedContributionPxPerUpdate |
| restore_resources_on_use | potionSickness → usesPotionRules |
| apply_generated_buff_on_use | movementSpeed → moveSpeedBonusFactor; jumpBoost → jumpSpeedBonusPxPerTick; manaRegen → manaRegenBonusPoints |
| configure_spawn | speedPxPerTick → speedPxPerUpdate |
| set_projectile_collision | localNpcHitCooldownTicks → localNpcHitCooldownEngineUnits |
| move_gravity_arc / move_bounce | gravityPerTick → gravityVelocityPerUpdate (два scope) |
| move_sine_homing | waveAmplitude → waveVelocityCoefficient |
| move_accelerate | acceleration → speedMultiplierPerUpdate |
| move_spiral | turnRadiansPerTick → turnRadiansPerUpdate |
| move_expanding_wave | scalePerTick → scaleGrowthPerUpdate |

Три изменённых regen names: accessory/armor lifeRegenHalfHpPerSecond → lifeRegenHpPerSecond и armor setBonusLifeRegenHalfHpPerSecond → setBonusLifeRegenHpPerSecond. Signed half-HP lattice отображается ×2 в прежний integer wire; existing 24 adapters не были новыми conversions. Buff movement percent conversion отклонена: контрпример `1.770282212988338*100/100 = 1.7702822129883378`, exact inverse полного domain не доказан. Текущие ограничения/zero/sentinels/terminal semantics — [units contract](MODEL_FACING_UNITS_RU.md), не старые stale VFX descriptions (например «duration только impactSprite» уже не current).

Старый итог записал 868 Python / 65 C# headless, DLL 0 errors/warnings, generated/contract/mutation/hygiene/static gates и no staged leaks; packaging отключён. Seed-wire hashes и captured Live20 bytes не переписывались ради rename, адаптация только test-local. Ни новый LLM/MP/game smoke, ни exhaustive arbitrary binary32 parity не проводились.

<a id="presentation"></a>
## Presentation .241–.242: исправление и согласованные choices

Первичный fix-report: base `def9cefdad7492182d47f8f11359edf9c1bdf725`; pinned tML `2026.6.3.6` / `v2026.06.3.6` / `29bf9785f5f4de8cd305be002c4cc48aa1177b20`. Его исходная таблица зафиксировала arms/facing/gravity, scale/zero/tint, equip transforms/visibility, VFX pixel/history/blend, particles/sound, premultiplied upload, 128px canvas/chroma и budget corrections. Baseline RED vertex alpha против additive A=0 и другие before/after details остаются в source report; current invariants — [presentation](PRESENTATION_CONSISTENCY_RU.md).

Старый итог: 1421 Python / 84 C# / Debug+Release 0 errors/warnings, 12 contract gates + 8 CI regressions, .tmod 13 entries и embedded DLL hash match; internal version .241. Upload/readback были intercepted seams, не GPU PNG decoder proof; новый Live20 не запускался. Это observations того package, не текущего deliverable.

В simple pass base `49d1ead6e6e67a20849bee5a0c31daa508e57441` владелец разрешил **«Сделай по своему усмотрению без переусложнений»**. Приняты, не названы lossless bugfix: optional atomic grip/mount/effectColor, реальные wave/arc/pulse/orbit/tip forms, hard item/equipment vs soft effect alpha, independent processing role, captured hit/crit position, event-aware budget/relay и exact existing collision geometry. Single-PNG armor сохраняется без atlas/skeleton/new backend. Legacy projectile/item relay v3 rejects v2; это требовало одинакового обновления participants, не migration.

Итог .242 записал 1510 Python / 101 headless C#, Release DLL 0 errors/warnings, 12 commands и 10 generated artifacts; CPU preview 7 renderer kinds × 2 blend modes × 12 frames, soft-alpha sheet из synthetic input. Physical generated grip/art quality не доказаны; arbitrary alpha после opaque flatten не восстанавливается. Package allowlist/VERIFICATION.json, exact commit/hashes/CI и запрет скрытого install/enabled.json/publication относятся к процессу release. Hosted CI, пропустивший tML DLL, не считается реальной local compilation.

Исходные «рекомендации мейнтейнера» — не все ещё open: grip/processing role/real primitive shapes/color/soft-alpha/event snapshots получили согласованное развитие, material fields — отдельное .245 направление. Полные atlases/accessory layer coverage/ParticleLibrary vertical slice/Item activation clock остаются отдельно определяемыми scopes, не silently implemented features.

<a id="renderer-live20"></a>
## Renderer requirements: captured Live20, не A/B

Срез `cf503d483baa87323bdab9c5d8871084391612c4`, панель `direct-construction-cf503d4-flash35lite-medium-live20` в `../artifacts/tool-runs/` от корня checkout. Старые actual json_object requests давали независимые enum списки без enforced structured-output; lightCue верно выбирал light, но неверно lane primary в 7 / support в 1. Cases: bee_boomstick, astral_minishark, infernal_boomerang, lens_finch_staff, jester_bow, obsidian_pickaxe, torch_mining_helmet, glowing_healing_potion. Противоречивый совет impact texture проявился в spider_sentry.

Fix сделал единую table surface/schema/diagnostics (lightCue light/cue; soundCue sound/cue; impactSprite impact), reused Director/Repair allOf и leaf diagnostics без autofill/gameplay/C# rewrite. Frozen-lane rewrite не отменяет полезный event fix; final tuple проверяется после merge. Это исправление сообщаемого интерфейса, не measured first-pass improvement. Записаны 6 первоначальных schema RED, 10 новых tests, full 882 Python и offline parity replay 18/18 final manifests (10 первоначально invalid всё ещё RED). Новый live/GPU/MP не выполнялся; meteor_spacegun Gameplay scope bug был отдельным.

| Старая панель | HEAD label | Final / без Gameplay Repair / без любых Repair | Gameplay / Visual / VFX Repair |
|---|---|---|---|
| primitive-proxy-flashlite35-live20-impact-fixed-20260925 | 27d5c40052786cd39088eacf94e16cbf2f5fdb6a, dirty | 20/20 / 16/20 / 14/20 | 4 / 1 / 2 |
| primitive-proxy-flashlite35-reusable-no-echo-live20-20260925 | тот же label, dirty | 20/20 / 14/20 / 10/20 | 6 / 4 / 1 |
| typed-ir-flashlite35-live20-2715c93-20260925 | 2715c93f45165d347a2499020ead5e21ec54db7f, clean | 14/20 / 10/20 / 4/20 | 6 / 1 / 5 |
| direct-construction-cf503d4-flash35lite-medium-live20 | cf503d483baa87323bdab9c5d8871084391612c4, clean | 18/20 / 10/20 / 3/20 | 9 / 0 / 10 |

Это recorded counters старого отчёта, **не пересчитанная здесь панель**. Во всех actual initial Author requests отчёт установил gemini-3.5-flash-lite, reasoning_effort=medium, temperature=.5; отсутствие expectedReasoningEffort в старом manifest не значило отсутствия wire effort. Старый token cap 12000, current-for-that-report 18000.

Causal limits: lightCue invalid/total по четырём панелям 1/4,1/10,5/6,8/10; hidden tuple condition существовал раньше. Mandatory item-stats поля/holdoutOffsets и local NPC минимум −1 уже существовали; omission не целиком новая обязательность. Замена required:true на общее «все, кроме optional:true» могла снизить заметность — гипотеза, не доказанная причина. Durable hybrid maxStack=1 — отдельное новое semantic constraint. Два final fails: astral_mirror HTTP timeout; meteor_spacegun reproduced harness scope/filter defect после Author errors, не два доказанных провала primitives.

Не controlled A/B: два старых trees dirty, recipe/parents/balance совпали лишь у 17/20 (infernal_boomerang, meteor_spacegun, corrupt_yoyo отличались); prompts/budgets/code и stochastic model менялись. Старые runtimeProgram entities/bindings/calls тоже исполнялись C# DTO/executors. Причинный вывод требует отдельно разрешённого matched screen с одинаковыми inputs/model/settings, не переименования old PASS в current acceptance.

<a id="rollback"></a>
## .243–.244 rollback и отдельное .245–.246 направление

Rollback вернул visual/VFX к .242 `4271b0bf996cf4152614fa389ad7f6a525f579b4`; опубликованный .242 и GitHub release не менялись. Убраны experiment spriteEmitter/texturedRibbon DTO/queue/mesh/material graph, sharpSpark/starFlare/optional colorProfile и profiles, composition guidance/schema/compiler/storage, experimental tests/docs/version bumps. Saves/config не менялись; experimental fields не мигрировались в legacy effects, fixtures только cancelled contract не объявлялись совместимыми.

Сохранились legacy renderers, Visual grip/mount/effectColor, collision geometry/immutable snapshots; independent fixes — dedup eligible item/world tick и gameplay-vs-VFX periodic, client PostUpdateEverything cleanup, type-aware frozen equality true/1/1.0. Experiment indexed-array merge был убран **тогда**; это не отменяет поздний exact delete/leaf policy material contract.

Переиспользуемое evidence: `../artifacts/vfx-rollback-to-0242/README_RU.md` от корня checkout — source delta/patch/SHA и rejected full deliveries; native FNA host, pixel oracle, continuity tooling/references/captures перечислены там. Архив не нужен active build. Old offline/headless/DLL/package rollback checks не означали GPU/game/MP/art acceptance, не запускали model/game и не устанавливали/публиковали мод.

.245 material spriteElement/texturedPath — **отдельный** [active contract](VFX_MATERIAL_ELEMENTS_RU.md), не восстановление четырёх масок .244. .246 добавила cache retirement/ownership cap, dead-item retirement, empty asset-domain leaf scope; эти active invariants вынесены в image/material guides. Transport version и runtime ABI не приравниваются.
