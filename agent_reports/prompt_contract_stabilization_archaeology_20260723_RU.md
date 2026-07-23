# Каузальная археология: стабилизация prompt/function 21–23 июля 2026

**Тип документа:** historical causal archaeology + implemented remediation + post-implementation audit; independent verification boundary is documented in section 17.
**Дата сборки отчёта:** 2026-07-23.
**Репозиторий:** `InfiniCrafterLocal_v0_4_234_secondary_refit_noise_cleanup`.
**Baseline HEAD исследуемого окна:** `61bab5e` (2026-07-19 01:58:07 +0300) — *Add debug minimum yield for attack consumables*.
**Коммитов в исследуемом окне после 19 июля:** **0** (проверено `git log --after='2026-07-19'`, `git rev-list --count 61bab5e..HEAD` → 0 до closing commit).
**Состояние 21–23 июля:** **грязное working tree** (`gitClean: false` во всех live-summary; на момент исходной археологии ~131 dirty path).
**Метод sections 1–10 в исходной рабочей среде:** read-only evidence — git/reflog, `git diff HEAD`, `agent_reports/tmod_use_driver_multi_lane_research_20260721.md`, `artifacts/tool-runs/**/{summary.json,results.ndjson,logical_llm.ndjson,cache/prompt_trace.ndjson,ab_report.md}`, audits, делегат-логи `deleg_37a7fe02/task-0.log` и `task-1.log`. Переданный clean archive не содержит этих external run/delegation artifacts и commit object `fa01d50`, поэтому численные утверждения sections 1–10 и 12 имеют статус historical report, а не independently reproduced из архива. Реализация и diagnostic Live описаны отдельно в sections 11–16; независимый audit snapshot `c82d168` — в section 17.

**Корректная рамка стоимости:** сообщённые пользователем **≈100M токенов** — это расход на Hermes/этого агента и связанные developer/audit циклы при повторной стабилизации архитектуры. Из них основная часть — порядка **≈90M** — ушла не на добавление самих функций, а на устранение каскадных отказов после изменений средней значимости. Локальная Gemini Live-телеметрия не является оценкой этой суммы и не используется для её уменьшения или опровержения.

**Независимая оговорка 23.07:** ≈100M/≈90M — owner-reported project estimate без локального единого ledger; audit не переименовывает его в измеренную величину. Code-level выводы, воспроизведённые из clean archive, отделены в section 17 от external Live/accounting claims.

---

## 0. Оглавление

1. [Git-факт и pre-21 baseline](#1-git-факт-и-pre-21-baseline)
2. [Исходная проблема: semi-canonical `ENGINE_FN_CATALOG_V2`](#2-исходная-проблема-semi-canonical-engine_fn_catalog_v2)
3. [Что именно изменилось 21 июля (use-driver / root executor / functions / prompt)](#3-что-именно-изменилось-21-июля)
4. [Хронологическая таблица прогонов](#4-хронологическая-таблица-прогонов)
5. [Классы отказов и поздние generic-фиксы](#5-классы-отказов-и-поздние-generic-фиксы)
6. [Метрика contract fingerprint](#6-метрика-contract-fingerprint)
7. [Стоимость архитектурной нестабильности](#7-стоимость-архитектурной-нестабильности)
8. [Почему среднее изменение вызвало глобальную стабилизацию](#8-почему-среднее-изменение-вызвало-глобальную-стабилизацию)
9. [Пути доказательств и пределы верификации](#9-пути-доказательств-и-пределы-верификации)
10. [Сжатый каузальный итог](#10-сжатый-каузальный-итог)
11. [Реализованная архитектура после археологии](#11-реализованная-архитектура-после-археологии)
12. [Diagnostic Live20 23.07.2026](#12-diagnostic-live20-23072026)
13. [Final artifact audit](#13-final-artifact-audit)
14. [Local gates: исходная среда и независимое воспроизведение](#14-local-gates-исходная-среда-и-независимое-воспроизведение)
15. [Как теперь делать partial extension без нового semantic spaghetti](#15-как-теперь-делать-partial-extension-без-нового-semantic-spaghetti)
16. [Итог](#16-итог)
17. [Независимый audit snapshot `c82d168`](#17-независимый-audit-snapshot-c82d168)

---

## 1. Git-факт и pre-21 baseline

### 1.1. Нет коммитов после 19 июля; 21 июля = dirty WT

| Утверждение | Доказательство |
|---|---|
| Последний commit | `61bab5e` 2026-07-19 01:58 +0300 |
| Коммиты 20–23.07 | **отсутствуют** |
| Reflog HEAD | только commit-цепочка до `61bab5e`; нет checkout/commit 21–23.07 |
| Live identity | все `summary.json` 21–23.07: `gitHead=61bab5e79d27…`, `gitClean=false` |
| API bump в WT | `.agent/manifest.json`: `v0.4.52` → **`v0.4.53`** (uncommitted) |

Следствие: «релиз 21 июля» — это **не snapshot commit**, а **непрерывная мутация dirty tree** + кампании в `artifacts/tool-runs`. Любая корреляция «commit SHA → prompt» для 21–23.07 **невозможна**; коррелировать можно только run-артефакты ↔ содержимое WT на момент run (частично через `runnerSha256` / `stageAccountingSha256` / fingerprint промпта).

### 1.2. Pre-21 baseline (committed почва)

| Шаг | Commit | Суть (уже в истории до dirty-окна) |
|---|---|---|
| 18.07 12:54 | `7e79efa` | `refactor: finalize authored gameplay pipeline` — author pipeline, runtime_authoring, repair/leaf foundation |
| 18.07 12:12 | `fa01d50` (immutable candidate / proxy exact20) | clean-tree Live20 baseline: **20/20 OK**, firstAuthor=15, repairFree=15, scopedRepair=5 |
| 18.07 visual | `f0faec4`…`e9c1f98` | Visual Director ownership/cardinality; VFX cardinality exact20 всё ещё **OK 20/20** |
| 19.07 | `08336f6`, `61bab5e` | MP craft escrow / remote visuals; debug min yield attack consumables |

**Зафиксированный clean baseline (для сравнения стоимости/стабильности):**

- Run: `gemini31-flash-lite-final-exact20-fa01d50-proxyon-20260718-121954`
- `gitClean=true`, head `fa01d50`
- reasoningEffort=`minimal`, maxTokens=16384
- tokens (logical `response.usage`): prompt **316 596**, completion **66 696**, total **383 292** / 85 usage rows
- mean `initial_author.prompt_tokens` ≈ **7420**
- Catalog functions в prompt: **24**
- API: `v0.4.52` (на fa01d50-эре в части fixed4 уже v0.4.52; ранние canary — v0.4.51)

К 21.07 эта baseline **не была «сломана коммитом»** — её перекрыл dirty WT с новой семантикой root executor / multi-lane / repair / placeable.

---

## 2. Исходная проблема: semi-canonical `ENGINE_FN_CATALOG_V2`

### 2.1. Что catalog *реально* канонизирует

`ENGINE_FN_CATALOG_V2` в `LocalGenerator/infini_local/core/runtime_authoring/schema.py` — **полуканон (semi-canonical)**:

| Слой | Владелец | Что даёт catalog | Что **не** даёт catalog |
|---|---|---|---|
| Имена функций + краткие cards (`does`/`params` text) | `schema.ENGINE_FN_CATALOG_V2` → prompt builder | inventory visible functions, param **names** в cards | строгие типы, closed enums runtime |
| Prompt cards / priorityHeader | `pipelines/llm_authoring_prompt.py` | partially **derived** from catalog + hand-written rules | полный legal set применения |
| Accepted extras / shared root params | `schema.ROOT_EXECUTOR_SHARED_PARAM_NAMES`, `accepted_engine_param_names` | extras set на root | кто имеет право патчить их в repair |
| Types / enums | `engine_call_contracts.py` (`_ENUM_PARAMS`, `_catalog_enum_values`, pydantic models) | partial pipe-enum inference from card text | полный closed set; silent unknowns forbidden отдельно |
| Applicability (когда fn законна) | `reports.py` + `runtime_family_policy.py` + C# `HasValidExecutorContract` | `requiresRootExecutor` flag на entry | family×delivery matrix, resultKind gates |
| Atomic repair groups | `ENGINE_FN_REPAIR_DEPENDENCY_GROUPS`, `repair_param_*` | группы «править вместе» | authorization scope на конкретный failure |
| Repair authorization / application | `author_item_repair_scope.py`, `author_item_repair_delta.py`, `author_item_repair.py` | cards `requiredTogether` / paths | delta validation, out_of_scope rejects |
| Compiler lowerers | `compiler.py` (`compile_runtime_plan_to_genome_patch`, pierce/aoe/onHit lowers) | — | mapping authored → genome/wire |
| Provenance map | `reports.runtime_plan_provenance_report`, pipeline boundary | — | drop/mismatch → hard fail |
| Final projection / DTO | `final_projection.py` (`compile_runtime_plan_to_final_result`) | — | compiler-owned fields на финале |
| C# execute / normalize | `GeneratedItemData.*`, `GeneratedRuntimeFamilyPolicy.HasValidExecutorContract` | — | runtime reject / apply |

**Вывод:** catalog — inventory + narrative cards + часть flags (`requiresRootExecutor`). Он **не** single source of truth для исполнения. Prompt/cards **частично derived**, но types/enums, accepted extras, applicability, atomic repair groups, repair auth/apply, compiler lowerers, provenance, final projection и C# — **отдельные владельцы**. Именно эта развилка создаёт класс «prompt сказал X / schema card сказал Y / repair не дал branch / compiler dropped provenance / C# reject».

### 2.2. Таблица владельцев + конкретные Live-отказы

| Владелец (файл) | Ответственность | Live failure example (case → error class) |
|---|---|---|
| `schema.py` `ENGINE_FN_CATALOG_V2` | fn inventory, card text, `requiresRootExecutor`, repair dependency groups | Добавление `placeable_behavior` (24→25) без синхронного API/C# → `silt_extractinator` placeability/ammo drift (audit 22.07) |
| `llm_authoring_prompt.py` | priorityHeader, oneRootExecutor rules, body+projectile encoding, cards projection | Переименование primary→root без полного alignment repair/reports → волна tool/helmet canary FAIL 21.07 |
| `author_item_contract.py` | response/repair JSON schema, `engineCallParamDeletes`, `engineCallIdPatches` | `woodwork_blade`: `out_of_scope_engine_call_param:set_item_stats_01:knockback` (fixed-acceptance 22.07) |
| `engine_call_contracts.py` | strict param models, closed enums | `jungle_whip` invented `damageClass=nature` (audit; closed later by canonical damageClass) |
| `reports.py` | structural validation, one-root, placeable gates, provenance | `vital_regen_band`: `compiler_provenance_dropped`; `bee_boomstick`: `compiler_provenance_mismatched` |
| `runtime_family_policy.py` + C# `HasValidExecutorContract` | family×delivery legal matrix | `gel_grenade` A/B medium: incompatible `runtimeFamily=shoot + delivery=throw` |
| `compiler.py` | lowerers authored→genome | composite projectile pressure / incomplete attack.genome after repair (`corrupt_yoyo` final-acceptance) |
| `final_projection.py` | final DTO / compiler-owned fields | `obsidian_pickaxe`: missing `axePower`/`hammerPower` in final projection (live20 low-vfx4k 21.07) |
| `author_item_repair_*.py` | scope, delta auth, apply | `infernal_boomerang`/`gel_grenade`/`meteor_spacegun`: `targeted_repair_has_no_authorized_delta_branches`; `ropebound_spear`: invalid delta `exactly_one_schema` |
| `runtime_tooltip.py` / projection tooltip path | tooltip ≠ free `coreMechanic` | research 21.07: compiled-wire tooltip must not copy prose |
| C# `GeneratedItemData.Apply/Normalize`, equip overlay layers | execute + visual hydrate | equip_overlay / sentry root vs child roles (audit visual findings) |

### 2.3. Почему semi-canonical создаёт дорогую стабилизацию

1. **Один semantic intent** (например «one use-driver, multi damage lanes») требует согласованного diff минимум в: prompt rules, catalog flags, reports one-root, family policy, C# executor contract, repair scope, tests — **без atomic cross-owner commit** (и без commit вообще в dirty-окне).
2. **Repair** авторизует leaf-paths от failure report, но legal set params/enums/applicability живёт в других модулях → частый terminal class `no_authorized_delta_branches` / `out_of_scope_*` / invalid delta schema.
3. **Provenance/final projection** — post-author gates: author+repair могут «пройти schema», но упасть на boundary → полный logical cost уже оплачен.
4. Каждое «узкое» исправление card/text/flag **меняет stable contract fingerprint** → следующий Live20 по сути заново платит large-batch цену.

---

## 3. Что именно изменилось 21 июля

Источники: research report 21.07, `git diff HEAD` ключевых файлов, prompt_trace identity, run timestamps.

### 3.1. Исследование use-driver (документ)

`agent_reports/tmod_use_driver_multi_lane_research_20260721.md` (mtime 2026-07-21 23:32):

- **Верно:** один **root executor / use-driver на use mode**.
- **Неверно:** запрет более одного **источника урона**.
- Контракт: `one root executor per use mode + optional item/body damage lane + bounded projectile/child/impact/field lanes`.
- Канон: `shoot+swing` = body hitbox + projectile; held/flail/yoyo/whip/beam — projectile-owned lifecycle; alt-use = отдельный mode.
- Зафиксированные связанные исправления (в WT, не в commit): rename `onePrimaryFunction`→`oneRootExecutor` **без compatibility alias**; Python/C# family-delivery matrix; tooltip not from prose; reusable gear economy; equip_overlay path; VFX diversity by executable signatures.

### 3.2. Точные surface-изменения (HEAD `61bab5e` → dirty WT)

| Surface | Diff (stat / символы) | Намерение |
|---|---|---|
| `llm_authoring_prompt.py` | ~258 lines churn | `PRIMARY_*` → `ROOT_EXECUTOR_*`; `oneRootExecutor`, `bodyPlusProjectileEncoding`; combat root required params; placeable rule; parent role obligation |
| `author_item_contract.py` | ~184 lines | scoped repair schema; `engineCallParamDeletes` / `engineCallIdPatches`; provider repair projection by allowed keys |
| `schema.py` | ~174 lines | `placeable_behavior` (**24→25** fn); `requiresRootExecutor` on contact/trail; `ROOT_EXECUTOR_*`; `ENGINE_FN_REPAIR_DEPENDENCY_GROUPS` + `repair_param_*` |
| `reports.py` | ~957 lines churn | one-root messaging; placeable/furniture gates; family delivery accepts; provenance/quality |
| `compiler.py` | ~206 lines churn | lowerers split / cleanup toward `final_projection` |
| `llm_authoring_pipeline.py` | **−1381 / +33** | repair/orchestration вынесены в `author_item_repair*.py` |
| `runtime_family_policy.py` | ~100 lines | family×delivery |
| **New** `author_item_repair.py` / `_delta.py` / `_scope.py` | 472+614+922 lines | targeted repair auth/apply |
| **New** `final_projection.py`, `equipment.py`, `runtime_tooltip.py`, `parent_role_facts.py` | owners final wire / equipment / tooltip / parent roles |
| Tests | `test_248_use_driver_equipment_visual_contract.py`, ownership contracts, updates `test_247_*` | pin new semantics |
| API | manifest `v0.4.52`→`v0.4.53` | placeable_behavior wire sync claim (audit) |

### 3.3. Ранние canary 21.07 (ещё до full Live20)

| Run | Cases | Result | Смысл |
|---|---|---|---|
| `use-driver-canary-20260721-203606` | 2 | FAIL both (`obsidian_pickaxe`, `torch_mining_helmet`) | tool/armor role + root rules сразу красные |
| `use-driver-proxy-canary-20260721-204032` | 2 | FAIL same | proxy path не спасает |
| `use-driver-current-health-20260721-210801` | 1 | FAIL pickaxe | health gate красный |
| `live20-no-image-health-20260721-215626` | 1 | structural path с repair | progress к full 20 |

---

## 4. Хронологическая таблица прогонов

Условные обозначения: FA = firstAuthorSuccesses; RF = repairFreeSuccesses; SR = scopedRepairCalls; L = logicalRequests.
Tokens — сумма `logical_llm.ndjson` → `response.usage` где посчитано точечно.

| Когда | Run | N | OK/Fail | FA/RF/SR/L | Tokens total | Примечание |
|---|---|---:|---|---|---:|---|
| 18.07 | `…exact20-fa01d50…121954` | 20 | **OK 20** | 15/15/5/85 | **383 292** | clean baseline minimal |
| 18.07 | `…vfx-cardinality-e9c1f98…` | 20 | **OK 20** | 15/15/5/65 | (task-1) | pre-dirty visual OK |
| 21.07 20:36 | `use-driver-canary-…` | 2 | 0/2 | 0/0/0/2 | small | dirty start |
| 21.07 20:40 | `use-driver-proxy-canary-…` | 2 | 0/2 | 0/0/0/2 | small | |
| 21.07 21:08 | `use-driver-current-health-…` | 1 | 0/1 | 0/0/0/1 | small | |
| 21.07 21:56 | `live20-no-image-health-…` | 1 | path w/ SR | 0/0/1/4 | | |
| 21.07 21:58 | **`live20-no-image-20260721-215815`** | 20 | 15/5 | 9/9/9/62 | **332 202** | maxTokens 12k; reasoning null; mean author p≈**7693** |
| 21.07 22:44 | `gemini31-…-low-medium-ab-…` | 5×2 | A/B | see report | per-arm ~10–18k | low лучше medium по quality |
| 21.07 23:07 | **`live20-no-image-low-vfx4k-…`** | 20 | 16/4 | 14/14/3/55 | **337 487** | effort=low; VFX 4k |
| 22.07 03:29 | `live3-parallel-canary-…` | 3 | 2/1 | 0/0/2/9 | | runner→`2eabd92a`, stageAcc→`3e5edd` |
| 22.07 03:47 | `live20-parallel3-fixed-…034734` | 20 | 13/7 | 9/9/10/56 | | parallel3; runner `02c0b3c4` |
| 22.07 04:20 | `live7-regression-parallel3-…` | 7 | 6/1 | 1/1/6/26 | | yoyo residual |
| 22.07 04:48 | `live20-parallel3-final-…` | 20 | 14/6 | 7/7/13/61 | **345 893** | SR↑ |
| 22.07 05:15 | `live6-failure-closure-…` | 6 | 4/2 | 3/3/3/17 | | targeted closure |
| 22.07 05:44 | `live20-fixed-acceptance-…` | 20 | 17/3 | 11/11/9/63 | **364 600** | |
| 22.07 06:29 | `live20-final-acceptance-…` | 20 | 17/3 | 6/6/14/72 | **388 291** | audit source; 1× HTTP 429 |
| 22.07 07:xx | live1/live2 closures (yoyo, bee, helmet, astral…) | 1–2 | mixed | high SR density | | micro-batch same contract cost |
| 22.07 07:55→23:xx | **много** `live20-fixed-reset-*` | 20 or partial | rarely clean | high churn | often ~0.35–0.38M / full | fingerprint thrash |
| 22.07 10:05 | `live20-fixed-reset-…100523` | 20 | 16/4 | 7/7/13/68 | | **fc 24→25 / API v0.4.53** first in window |
| 22.07 14:59 | `live20-fixed-reset-…145929` | 20 | 19/1 | 13/13/7/65 | **383 328** | best-ish 19/20 |
| 22.07 16:47 | `live20-fixed-reset-…164742` | 20 | 11/9 | 6/6/5/48 | | regression wave |
| 22.07 late | fixed20-supervisor / quota probes / swift-boots smokes | mixed | incomplete NO_SUM common | | | transport/quota noise |
| 23.07 01:xx | glowing-potion-* smokes | 1 | | | | root-owner / buffType pins |
| 23.07 03:13 | `live20-fixed-reset-…031309` | 20 | 16/4 | 10/10/10/76 | **371 030** | runner `a6a694ff` |
| 23.07 04:22 | `pre-prompt-contract-refactor-…` | — | NO_SUM | | | marker before next refactor |

**Наблюдение по таблице:** после clean 20/20 (18.07) **ни один** полный Live20 21–23.07 в проверенных summary не вернулся к `ok=true` 20/20. Лучшие точки — 19/20 и 17/20 при **сопоставимом или большем** logical/token spend, чем baseline.

### 4.1. Failed cases — снимок ключевых full-20

**live20-no-image-20260721-215815 (5 fail):**
`ropebound_spear` invalid repair delta · `infernal_boomerang` no authorized branches · `gel_grenade` no authorized branches · `vital_regen_band` provenance_dropped · `glowing_healing_potion` strict authoring boundary.

**live20-no-image-low-vfx4k-20260721-230730 (4 fail):**
`woodwork_blade` / `meteor_spacegun` / `lens_finch_staff` no authorized branches · `obsidian_pickaxe` final projection missing axe/hammer.

**live20-fixed-acceptance-20260722-054420 (3 fail):**
`woodwork_blade` out_of_scope knockback · `astral_mirror` strict authoring · `glowing_healing_potion` provenance_dropped.

**live20-final-acceptance-20260722-062906 (3 fail):**
`bee_boomstick` provenance_mismatched · `corrupt_yoyo` incomplete attack.genome after repair · `glowing_healing_potion` HTTP 429.

---

## 5. Классы отказов и поздние generic-фиксы

| Класс отказа (симптом) | Типичные cases | Поздний generic-фикс (WT owners) |
|---|---|---|
| `targeted_repair_has_no_authorized_delta_branches` | boomerang, gel, meteor, woodwork, lens | `ENGINE_FN_REPAIR_DEPENDENCY_GROUPS`, `repair_param_*`, cards `requiredTogether`/`allowedTogetherValues` in contract+scope |
| invalid repair delta / `exactly_one_schema` | ropebound_spear | repair response schema projection; delta one-of hardening |
| `out_of_scope_engine_call_param` / identity | woodwork knockback; category/resultKind | `engineCallParamDeletes`; authorized path sets in `_delta` |
| `compiler_provenance_dropped` / `_mismatched` | vital_regen_band, glowing potion, bee | provenance report + final boundary in pipeline; repair must not strip owners |
| final projection missing compiler-owned fields | obsidian_pickaxe axe/hammer | `final_projection.py` ownership; tool zero-field semantics |
| placeable / furniture / ammo identity | silt_extractinator | **`placeable_behavior`** + API v0.4.53 + parent role facts + C# createTile/Wall |
| role loss armor→weapon / tool combat root | torch_mining_helmet, pickaxe | parent_role_facts; sole-armor preservation; body tool without combat root rule |
| reusable gear spent as consumable | woodwork, ropebound | economy invariant reusable maxStack=1 craftYield=1 |
| sticky/cling prose without primitive | gel_grenade | executable-only obligation (audit CLOSED at author) |
| family×delivery illegal | gel medium A/B | runtime_family_policy + prompt tables |
| damageClass invented | jungle_whip | canonical/modded damageClass + whip→summon_melee_speed |
| VFX truncation | pre-4k era | VFX max tokens 4000; A/B: 0× `finish_reason=length` |
| HTTP 429 / transport | glowing potion final-acceptance | quota probes; not a contract fix |
| parallel accounting / stage mix | parallel3 runs | `stageAccountingSha256` c5c8db→3e5edd; runner sha waves |

**Паттерн:** фиксы 22–23.07 в большинстве — **generic contract/repair/projection**, а не case hardcode. Но каждый generic-фикс снова двигал **author contract fingerprint**, из-за чего приходилось переигрывать large Live20.

---

## 6. Метрика contract fingerprint

### 6.1. Метод (воспроизводимый)

1. Взять все `artifacts/tool-runs/*2026072[1-3]*/cache/prompt_trace.ndjson`, где есть строка `Planner request` (**Author-containing**).
2. Распарсить `.prompt` как JSON; удалить **`itemA`/`itemB`** (case-specific parents).
3. `sha256` канонического JSON остатка → **stable contract fingerprint** (prefix 16 hex в таблицах).
4. `functionCount` = `len(availableFunctions)` (24 или 25).
5. Упорядочить runs по timestamp в имени; **consecutive contract segment** = смена fingerprint относительно предыдущего run в этом порядке (с учётом повторных появлений).

### 6.2. Verified numbers (окно имён `*20260721*`…`*20260723*`)

| Метрика | Значение | Комментарий |
|---|---:|---|
| Author-containing runs | **81** | совпадает с требуемым «81 Author-containing runs after start» |
| Unique stable contract fingerprints | **20** | sha256(prompt − parents); близко к целевому «19» — расхождение на 1 из-за включения/исключения mis-timestamped `quota-probe-secondary-*` и revisit fingerprint |
| Consecutive contract segments | **21** | **verified** |
| FP-changes без смены function count | **19** (при корректной интерпретации: 20 changes − 1 реальный fc transition; reverse 25→24 от mis-ordered quota — артефакт сортировки short-ts probe, не продуктовый rollback) | |
| Function count transitions | **только 24→25** | first in-window at `live20-fixed-reset-20260722-100523`; new fn = **`placeable_behavior`**; API `v0.4.53` |
| Catalog HEAD vs WT | HEAD **24** keys → WT **25** keys | `comm` diff: только `placeable_behavior` |

**Интерпретация:** почти вся «стабилизация» 21–23.07 — это **движение контракта при постоянном числе функций (24)**, затем одна инвентарная экспансия (25), и снова текстово-rule churn при 25. Смена fingerprint **без** смены function count = дорогие переписи rules/cards/repair/projection, которые всё равно инвалидируют «тот же» Live20.

### 6.3. Сегменты (сжато)

1. early probes / use-driver canary (fc=24, api v0.4.52)
2. live20 21.07 health → full → low-vfx4k (несколько FP)
3. parallel3 / yoyo / closure micro-runs (частые FP)
4. fixed-acceptance / final-acceptance
5. fixed-reset wave **fc→25 / v0.4.53**
6. late reset + glowing-potion smokes (fc=25)

---

## 7. Стоимость архитектурной нестабильности

### 7.1. Основная величина: ≈100M токенов Hermes-разработки

Пользователь сообщил, что изменения 21 июля в итоге потребовали порядка **≈100M токенов работы этого агента/Hermes и связанных developer/audit циклов**. Существенно, что большая часть расхода — ориентировочно **≈90M** — пришлась уже не на исходное улучшение prompt и добавление функций, а на последующую стабилизацию и попытки снова получить безошибочное исполнение LLM.

Это не внешний «непроверенный биллинг», который нужно сопоставить с Live runner. Это исходная стоимость проекта, сообщённая владельцем, и главный архитектурный симптом отчёта:

> Изменение средней значимости не осталось локальным. Оно вызвало каскад по prompt, provider schema, repair authorization, compiler, provenance, final projection, Visual/VFX handoff и C# runtime, после чего агент многократно искал и закрывал очередной разрыв на следующем owner.

Поэтому вопрос отчёта — не «действительно ли Live израсходовал 100M», а **почему архитектура заставила потратить около 100M agent tokens на повторную глобальную стабилизацию после сравнительно ограниченного feature diff**.

Точный provider/session split этой суммы локально не реконструирован: в него входили длинные Hermes-сессии, вызовы инструментов, аудиты, контекстные повторения, Spark/Grok/другие developer-модели и итерационные исправления. Это ограничивает бухгалтерскую детализацию, но не меняет причинную постановку.

### 7.2. Локальная Gemini Live-телеметрия — вторичный диагностический канал

Источник: `logical_llm.ndjson` → `response.usage.{prompt,completion,total}_tokens` (Gemini via Google OpenAI-compat).

Эти числа описывают только item-generation requests. Они **не измеряют** Hermes-разработку и не должны сравниваться с ≈100M как с альтернативной оценкой. Их роль уже: показать количество повторных кампаний, repair density и то, что каждое изменение contract fingerprint снова оплачивало крупный regression signal.

| Охват | files (logical) | usage rows | prompt | completion | **total** |
|---|---:|---:|---:|---:|---:|
| Имена `*2026072[1-3]*` (пересчёт 23.07) | 82 | 1516 | 6 560 317 | 1 029 955 | **≈8.93M** |
| task-1 (mtime-окно Jul21–23, чуть шире) | 92 | 1542 | 6 673 962 | 1 047 961 | **≈9.08M** |
| task-1 all-time logical | 260 | 3719 | 18 566 477 | 3 099 992 | **≈23.5M** |
| task-1 jul18 era | 58 | 1102 | — | — | **≈5.16M** |
| task-1 feature window →22.07 08:00 | 35 | 475 | — | — | **≈2.74M** |
| task-1 stabilization 22.07 08:00+ | 57 | 1067 | — | — | **≈6.34M** |

Точечные full-20:

| Run | total tokens | vs fa01d50 baseline 383k |
|---|---:|---|
| fa01d50 exact20 OK | 383 292 | 1.00× |
| live20 21.07 215815 FAIL5 | 332 202 | 0.87× (меньше non-author/visual success path) |
| live20 low-vfx4k FAIL4 | 337 487 | 0.88× |
| parallel3-final FAIL6 | 345 893 | 0.90× |
| fixed-acceptance FAIL3 | 364 600 | 0.95× |
| final-acceptance FAIL3 | 388 291 | 1.01× |
| reset 145929 FAIL1 | 383 328 | 1.00× |
| reset 031309 FAIL4 | 371 030 | 0.97× |

**Mean initial_author prompt:** jul18 ≈ **7420** → live21 ≈ **7693** (+~3.7%). Этот рост слишком мал, чтобы объяснить ≈100M developer cost. Причина — не размер одного запроса, а количество agent iterations, audits, repairs, reruns и повторных проходов через связанные owners.

A/B `gemini31-flash-lite-current-pipeline-low-medium-ab-20260721-224404` показал, что medium не дал quality gain, а low имел лучший first-author результат. Это полезная настройка Live-контура, но не решение архитектурного blast radius.

---

## 8. Почему среднее изменение вызвало глобальную стабилизацию

### 8.1. Каузальная цепочка стоимости

```
средний feature diff: oneRoot multi-lane + новые функции + repair extract
  → одно изменение вручную отражается в нескольких shadow contracts
    → prompt/provider принимают одно, repair разрешает другое,
      compiler/provenance/final projection/C# ожидают третье
        → первый canary/audit/test показывает только ближайший разрыв owner N
          → агент исследует, исправляет owner N и меняет contract fingerprint
            → повторные tests/audits/Live/context показывают разрыв owner N+1
              → новая длинная итерация агента и новый глобальный regression net
                → … 21 contract segment / 81 Author-containing run
                  → около 90M из 100M agent tokens уходит на стабилизацию
```

Live20/parallel/reset waves были измеримым проявлением цикла, но не всей его стоимостью. Основной расход создавали длинные Hermes-итерации: повторное чтение связанных слоёв, восстановление контекста, локальные и независимые аудиты, изменение нескольких владельцев, повторные gates и разбор нового класса ошибки. Поэтому ≈100M — стоимость **глобального blast radius для агента**, а не сумма строк `response.usage`.

### 8.2. Почему intermediate batch (live1/live3/live6/live7, smokes) ≈ large Live20

1. **Фиксированный тяжёлый author prefix:** ~7.4–7.7k prompt tokens contract+cards на **каждый** `initial_author`, независимо от N=1 или N=20.
2. **Repair не дешёвый:** scoped repair всё ещё тащит failure report + function cards + authorized paths; при `no_authorized_branches` деньги author уже сожжены.
3. **Post-author gates** (provenance, final projection, C#) срабатывают **после** LLM spend.
4. **Fingerprint thrash (21 сегмент / ~20 уникальных FP на 81 run):** кэш промпта/«тот же контракт» почти не живёт между итерациями; каждый mid-fix — new contract plate.
5. **parallel3** увеличивает concurrent logical pressure и SR count (stageAccounting смена c5c8db→3e5edd), не уменьшая per-item author cost.
6. **Incomplete resets** (много `live20-fixed-reset-*` без summary / partial results) добавляют «оплату входа» без complete learning signal — cost без закрытия гипотезы.
7. **19 FP-смен без смены function count** = высокая семантическая/текстовая нестабильность при том же inventory: модель и repair policy переобучаются на wording, не на новом primitive — снова large regression net.

Следствие: **оптимум «сначала cheap canary» разрушен**, потому что canary и Live20 делят один и тот же fat contract prefix, а критерий приёмки всё равно global Live20. Micro-batch экономит только tail visual/VFX и часть case diversity, но не основную author-cost массу и не снимает need full-20 после каждой FP-смены.

### 8.3. Связь с semi-canonical catalog

Если бы catalog был **полным** каноном (types, enums, applicability, repair groups, lowerers, provenance keys, projection fields, C# parity) с одним version bump, то:

- меньше orphan failures «prompt ok / repair empty / projection miss»;
- меньше FP-смен на чисто текстовые переписи;
- mid-batch реально валидировал бы **тот же** contract surface, что large-batch.

Фактически catalog оставался inventory+cards, а стабилизация шла **по периметру владельцев** — отсюда cost structure «много large-equivalent runs».

### 8.4. Правильный критерий исправления

Архитектура считается исправленной не потому, что один Live20 стал дешевле на несколько процентов. Нужна **change locality**:

1. изменение одной функции/параметра начинается в одном typed owner;
2. prompt/provider/repair/provenance surfaces выводятся из него либо имеют явный compile-time parity gate;
3. deterministic affected replay проверяет затронутые functions до нового LLM spend; call-shape/form coverage используется corpus builder-ом, но отдельного form selector в текущем API нет;
4. unrelated gameplay/Visual/VFX/C# owners не требуют ручной синхронизации;
5. full Live используется как финальная приёмка, а не как следующий debugger архитектуры.

Именно неспособность выполнить эти пять условий до рефакторинга объясняет основную часть ≈100M расхода.

---

## 9. Пути доказательств и пределы верификации

### 9.1. Evidence paths (absolute)

| Path | Роль |
|---|---|
| `/home/xipong/agent-work-main/projects/InfiniCrafterLocal/InfiniCrafterLocal_v0_4_234_secondary_refit_noise_cleanup/` | project WT + git |
| `…/agent_reports/tmod_use_driver_multi_lane_research_20260721.md` | use-driver research 21.07 |
| `…/agent_reports/prompt_contract_stabilization_archaeology_20260723_RU.md` | **этот отчёт** |
| `/home/xipong/agent-work-main/projects/InfiniCrafterLocal/artifacts/tool-runs/` | summaries, results, logical_llm, prompt_trace |
| `…/gemini31-flash-lite-final-exact20-fa01d50-proxyon-20260718-121954/` | clean baseline |
| `…/live20-no-image-20260721-215815/`, `…-low-vfx4k-20260721-230730/` | first dirty Live20 |
| `…/gemini31-flash-lite-current-pipeline-low-medium-ab-20260721-224404/ab_report.md` | A/B low/medium |
| `…/live20-final-acceptance-20260722-062906/`, `…/live20-fixed-acceptance-20260722-054420/` | acceptance wave |
| `…/live20-fixed-reset-20260722-100523/` | fc 24→25 marker |
| `/home/xipong/agent-work-main/projects/InfiniCrafterLocal/artifacts/audits/preliminary-live20-20260722-current-candidate.md` | gameplay/visual disposition |
| `/home/xipong/.hermes/cache/delegation/live/deleg_37a7fe02/task-0.log` | git archaeology subagent |
| `/home/xipong/.hermes/cache/delegation/live/deleg_37a7fe02/task-1.log` | run/token archaeology subagent |
| WT sources: `LocalGenerator/infini_local/core/runtime_authoring/{schema,reports,compiler,final_projection,engine_call_contracts}.py`, `pipelines/{llm_authoring_prompt,author_item_contract,author_item_repair*}.py`, `ModSources/…/GeneratedRuntimeFamilyPolicy.cs` | ownership |

### 9.2. Verified limits (что нельзя честно утверждать)

1. **Точный byte-for-byte source snapshot на каждый ранний run** — до closing commit его не было; сохранялись gitHead=61bab5e + dirty flag + runner/stageAccounting hashes.
2. **Точный provider/session split ≈100M agent tokens** — локальный единый ledger всех Hermes-сессий, контекстов, Spark/Grok и tool calls не реконструирован. Это не превращает сообщённую пользователем общую стоимость в «неподтверждённую Live-оценку»; неизвестна детализация, а не смысл величины.
3. **Unique FP = 19 vs 20** — зависит от включения short-ts quota probes; segments=21 и runs=81 стабильны.
4. **Gemini item-generation usage** — task-1 дал all-time ~23.5M, точечный пересчёт 21–23 ≈8.93–9.08M. Это наблюдаемая подсистема и она не измеряет общий расход агента на разработку/стабилизацию.
5. **Каузальность «этот diff строка → этот fail case»** для каждой из 21 FP-сегментов — не полная; таблица классов fail↔fix надёжнее, чем неподтверждённый line-bisect.
6. Sections 1–10 фиксируют исходную археологию; sections 11–16 отдельно описывают последующую реализацию, diagnostic Live и post-Live audit.
7. В переданном clean archive отсутствуют перечисленные `artifacts/tool-runs`, делегат-логи, `/tmp` ledger и commit object `fa01d50`; независимый audit этого archive может проверить код/commits/gates, но не пересчитать historical Live/token claims.

---

## 10. Сжатый каузальный итог

1. После 19.07 **не было коммитов**; 21–23.07 работа шла в **dirty WT** поверх baseline `fa01d50`/`61bab5e`.
2. 21.07 ввели **one root executor / multi damage lane**, новые функции и вынесли repair — правильный product direction, реализованный поверх semi-canonical catalog и нескольких ручных shadow contracts.
3. Изменение средней значимости разошлось между prompt/provider, repair, compiler, provenance, final projection, Visual/VFX и C#, поэтому последующие failures появлялись последовательно, а не одним ранним gate.
4. Агент многократно исследовал и исправлял следующий owner: **21 contract segment**, около 20 fingerprints, **81 Author-containing run**, дополнительные audits/context/tool cycles.
5. Сообщённая стоимость этого цикла — **≈100M Hermes/agent tokens**, причём основная часть, порядка **≈90M**, пришлась на стабилизацию после feature work.
6. Локальные ≈9M Gemini item-generation tokens — только вторичная телеметрия regression campaigns; они не являются нижней оценкой и не опровергают общий agent spend.
7. Главный cost multiplier: **medium diff × scattered ownership × late detection × repeated global regression/context**, а не количество функций и не несколько процентов размера prompt.
8. Правильная цель рефакторинга — **change locality**: одна typed точка изменения, derived/parity surfaces, affected historical replay и full Live только как финальная приёмка.

---

## 11. Реализованная архитектура после археологии

Археология выше объясняет причину затрат; этот раздел фиксирует уже выполненный ответ на неё.

### 11.1. Стабильный pipeline, не новые LLM-роли

Сохранён жёсткий конвейер:

```
Author → Visual Director → VFX Director
```

Для каждой стадии допускается не более одного bounded repair. Не добавлены judge/verifier/model-router роли, повторная генерация «до красоты», name/tooltip/tag classifiers, item-specific hardcases или произвольный C# от LLM.

### 11.2. Function contract стал typed registry

`function_contract_registry.py` + `function_contract_types.py` теперь владеют immutable function/param primitives:

- param name, value kind, enum/pattern/object/list boundary;
- provider JSON Schema projection;
- prompt card projection;
- compiled-field/provenance obligation;
- root-executor flag;
- repair dependency groups;
- typed lowerer identity для affected replay.

Applicability пока **не** полностью принадлежит registry: `allowed_result_kinds` является reserved metadata и пуст во всех production entries; фактическая family/result-kind policy остаётся в `reports.py` и runtime-family policy. Это остаточный multi-owner seam, а не завершённая canonicalization.

Исходный frozen surface `engine_function_contract_surface_v1.json` фиксировал catalog/provider/accepted params/repair groups, но не всю per-param wire/prompt/lowerer metadata. Независимый audit расширил fixture полным `typedContracts`, чтобы изменения `wireObligation`, `compiledFields`, prompt visibility/group, nested wire paths и lowerer mapping давали явный frozen diff. Ранее audit также убрал non-executable `set_alt_use_mode.mode=none` из Author-visible enum; defensive compiler normalization старых данных оставлена отдельно и не расширяет новый contract.

### 11.3. Compiler/final-wire ownership

- `compiler.py` компилирует authored primitives;
- `final_projection.py` — единственный production projection owner;
- provenance requirements проецируются из canonical `WireObligation`, а не из ещё одного ручного param set;
- `CONTROL_DERIVED`, `DEFERRED_VFX`, `NON_WIRE` отличены от настоящих final-wire полей;
- report и apply paths разделены: проверка не должна скрыто мутировать gameplay DTO;
- C# остаётся finite executor и строгим конечным boundary, а не semantic repair layer.

Это устранило классы ложных `compiler_provenance_dropped`, missing tool/equipment fields и «prompt принял — wire потерял».

### 11.4. Bounded repair как строгая транзакция

`author_item_repair.py`, `_scope.py`, `_delta.py` отделены от main Author orchestration. Repair получает только доказанные callId/field paths и typed constraints. ID rename + param patch применяются атомарно: сначала проверяются все ID patches, param mutations относятся к старому owner, rename выполняется последним. Неавторизованные/missing/duplicate paths fail-closed.

### 11.5. Historical replay вместо нового Live после каждого leaf diff

`qa/runtime_contract_replay.py`, `tools/build_runtime_contract_replay_corpus.py` и frozen corpus позволяют:

- replay старых runtime plans через production compiler/final projection без LLM;
- выбирать affected cases по changed functions;
- сохранять authored function provenance отдельно от executable normalized plan в новых corpus;
- сравнивать canonical final-section fingerprints;
- fail-closed на unknown/uncovered function, rejected calls, validation.ok=false и dropped provenance;
- не хранить machine-specific absolute paths.

В snapshot `c82d168` selector имел false-green gap: typed functions, понижаемые в `shoot_projectile`, могли выбрать 0 cases в legacy corpus. Независимый audit добавил lowerer metadata и две честные стратегии: exact authored-function selection для provenance-aware corpus и консервативный canonical-lowerer fallback для legacy corpus. Отдельного selector по form нет; call-shape/result-kind используются при построении representative corpus.

Это основной механизм для будущей частичной модификации: сначала contract diff + affected replay + local gates; Live не является первым отладчиком.

### 11.6. Visual/VFX contracts

- Visual roles вынесены в canonical role registry;
- Gemini structured schema полностью inline: без `$defs/$ref`;
- `palette` и nested fields проходят strict JSON Schema;
- returning/thrust/yoyo item-bodied projectiles reuse item sprite;
- equip overlays для armor/accessory являются отдельными required assets;
- sentry root/child roles различены;
- VFX slots проверяются по finite vocabulary и typed runtime event reachability.

Последнее утверждение было неполным для closing snapshot `c82d168`: Author `visual_effect_cue` ещё принимал free-string `rendererKind`, `channel` и `particleSystemId`, а direct compiler мог молча получить partial/default cue. Независимый audit закрыл Author/provider enums, defensive compiler bypass и VFX Director одним canonical vocabulary; соседние finite `effect`, `onHit` и `armorSlot` также закрыты.

Предыдущий post-Live audit добавил две generic обязанности:

1. persistent `runtimeFamily=summon` обязан явно иметь projectile body: `baked_sprite + projectileSpritePrompt` либо authored `reuse_item_sprite`;
2. VFX Director получает `allowedEvents`; projectile-only `hit/travel/kill/expire` запрещены для furniture, disabled attack и body-only `swing`.

### 11.7. Transport/accounting

- Gemini endpoint закреплён в `chat_completions`, поэтому параллельные `/responses` 404 probes не возникают;
- retry causes накапливаются, а не перезаписываются;
- summary различает logical calls, HTTP calls, overhead и transport retry events;
- final runner имеет hard gate `--require-zero-transport-retries`.

External harness paths `/home/xipong/agent-work-main/projects/InfiniCrafterLocal/toolbox/` и `/home/xipong/.hermes/scripts/run-infini-fixed20-reset.sh` не принадлежат этому Git worktree и не являются отдельными Git repositories. Они проверены и их hashes зафиксированы в Live ledger, но project commit ниже физически не может их включить.

---

## 12. Diagnostic Live20 23.07.2026

### 12.1. Важная процессная оговорка

Прогон был запущен агентом ошибочно: условие пользователя «если запускать, то только после всех изменений и batch=3» было неверно истолковано как разрешение. После прямого замечания пользователь отдельно сказал прогон не отменять. Он был доведён до артефакта. Новых ICL Live без отдельной текущей команды **«запускай»** больше не будет.

### 12.2. Frozen snapshot до inference

Pre-Live ledger: `/tmp/icl-final-live-candidate.json`. Этот ledger и external runner artifacts отсутствуют в переданном archive; следующие значения сохранены как historical record исходной среды, а не независимо пересчитаны audit-ом.

- git HEAD: `61bab5e79d272577799120248608b94a074e5fa4`;
- tracked diff SHA-256: `47f23a1f96157cdc223a6f7ca21ffbb9da215b724c7ddd71d3729141c5a5089c`;
- untracked contents SHA-256: `7f7738234514c149ab607e695af0b1c4da01eb77e7a67769d95e9b0b1d090e93`;
- 36 untracked files;
- launcher SHA-256: `8b54a73e9eeaa5cec9e4dff51a8451494e12a9ebdff12a779c34543ee426a599`;
- toolbox runner SHA-256: `9fe634972d10784ae72bd5b42f8f0bf0265468278d4c35017830acf0feb8016f`;
- stage-accounting SHA-256: `3723b69651364529d6264c10fdc121fddfd19af45c452c54c70413a3de6b25d`.

Post-Live fingerprint совпал со snapshot byte-for-byte.

### 12.3. Результат

Результат ниже сообщён исходным Live ledger; independent archive audit его не воспроизводит.

Artifact: `/home/xipong/agent-work-main/projects/InfiniCrafterLocal/artifacts/tool-runs/live20-fixed-reset-20260723-124510/`.

| Gate | Result |
|---|---:|
| Cases | **20/20 PASS** |
| First-author | **13/20** (порог ≥10) |
| Initial Author | 20 |
| Scoped Author repair | 7 |
| Downstream calls | 42 = 40 mandatory Visual/VFX + 2 bounded repair |
| Logical requests | **69** |
| HTTP requests | **69** |
| HTTP overhead | **0** |
| Transport/fallback events | **0** |
| Reported tokens | **332,108** |
| Runner exit | **0**, `ok=true` |

Относительно v6 accounting (74 logical / 79 HTTP) это −5 logical (−6.76%) и −10 HTTP (−12.66%). Относительно clean fa01d50 baseline 383,292 tokens — −51,184 (−13.35%). Это подтверждает чистоту transport/accounting конкретного Live, но **не измеряет возврат ≈100M agent spend и не доказывает change locality**. Для основной проблемы важнее, потребуется ли после следующего medium-size contract diff снова глобально стабилизировать все стадии.

Два downstream repair были точными и полезными:

- Spider Visual: missing sentry projectile + child baked roles;
- Vital Band VFX: неизвестный enum `emissionMode=rise` → canonical value.

---

## 13. Final artifact audit

### 13.1. Что было подтверждено исходным artifact audit

Перечень ниже относится к external Live artifacts исходной среды, которых нет в clean archive; независимый audit проверял соответствующие generic code contracts, а не заново открывал эти 20 item manifests.

- Woodwork body-primary: `runtimeFamily=swing`, `delivery=swing`, item melee hitbox включён;
- Obsidian Pickaxe — native body tool, `pickPower=110`, без fake projectile family;
- spear/boomerang/yoyo reuse item sprite; flail/whip имеют distinct body;
- sentry имеет baked root + child;
- Boots/Band/Helmet имеют required baked equip overlays;
- armor/accessory/tool/furniture/potion wiring и durable/consumable stack semantics согласованы;
- Grenade/Potion/furniture расходуемы; weapons/tools/equipment non-consumable;
- Jester Bow использует arrow ammo и не расходует Fallen Star на каждый выстрел;
- все 20 VFX manifests прошли finite shape/runtime boundary старого snapshot;
- transport accounting непротиворечив.

### 13.2. Найденные false-PASS классы и generic fixes после Live

Live был полезен как диагностический corpus и выявил четыре общих seam:

1. **Astral Mirror:** `apply_player_effect_on_use` содержал только `healLife=0`, `healMana=0`, `note=Recall...`; note=`NON_WIRE`, recall отсутствовал. Добавлен общий запрет use-effect без хотя бы одного executable heal/buff/generatedBuff.
2. **Woodwork:** `set_alt_use_mode(mode=none,cooldownTicks=10)` был мёртвым call. `none` удалён из Author provider enum; direct runtime report также fail-closed.
3. **Lens Finch Staff:** `runtimeFamily=summon` имел описанный «optical finch», но Visual не authored `bakedAssets`, поэтому projection выбрала `particle_vfx`. Добавлена typed summon-body obligation.
4. **Dead VFX events:** Woodwork, Obsidian Pickaxe и Silt Extractinator получили `event=hit`, хотя у body swing/tool/furniture нет `GeneratedProjectile` consumer. Добавлен вывод допустимых событий из typed runtime facts текущего item в VFX prompt и validator. Replay обнаружил ровно эти три cases.

Все четыре исправления — по finite typed contract, без item names/prose classifiers и без нового LLM-role.

### 13.3. Subjective, но не structural blocker

`gel_grenade` Author сделал executable launcher/shoot вместо доступного throw family. Это слабее ожидаемой fantasy, но wire честен. Code-owned правило «любой consumable ranged = throw» было бы ложным для darts/scrolls/ammo-like предметов; item hardcase не добавлялся. Это остаётся зоной Author quality/human review, а не основанием для semantic router.

### 13.4. Честная verification boundary

Результат 20/20 относится к pre-audit frozen snapshot. Четыре generic post-audit delta подтверждены exact offline replay и tests, но **не новым Gemini Live**. Поэтому нельзя утверждать, что текущий post-audit tree имеет Live-confirmed 20/20. Новый Live требует отдельного явного разрешения пользователя.

### 13.5. Дополнительные false-PASS seam, найденные независимым audit

Audit clean snapshot `c82d168` воспроизвёл ещё два общих дефекта:

1. invented finite VFX tokens проходили Author provider boundary, а compiler мог сохранить частичный cue;
2. changed typed lowerer function (`fire_ranged_weapon` и аналоги) выбирала 0 historical cases, потому что frozen corpus содержал только normalized `shoot_projectile`.

Оба исправлены generic/fail-closed в ветке `audit/verify-contract-stabilization`. Full committed corpus после правок: 82 cases, 0 fingerprint failures; legacy selection для `fire_ranged_weapon`: 68 conservative executor cases вместо пустого PASS. Новый Live не запускался.

---

## 14. Local gates: исходная среда и независимое воспроизведение

### 14.1. Заявленные результаты исходной среды

- Python: **255 passed**;
- focused Visual/gameplay: 66 passed;
- VFX/runtime registry: 31 passed;
- toolbox stage accounting: 5 passed;
- toolbox py_compile: PASS;
- compileall: PASS;
- schema export: 5/5 current;
- config registry: PASS;
- contract parity: PASS;
- mutation gate: PASS;
- semantic runtime baseline: 10 cases, 0 differences;
- C# contract scanner: PASS;
- project hygiene: PASS;
- Ruff: PASS;
- Pyright: 0 errors / 0 warnings;
- Planner prompt: **26,987 / 27,000**, 25 functions, hard-limit GREEN;
- tML Debug build: 0 warnings / 0 errors;
- tML Release build: 0 warnings / 0 errors;
- `agentctl`: `ok=true`, `releaseReady=true`.

Эти результаты относятся к исходной рабочей среде, описанной автором отчёта. Переданный archive не содержит external harness/ledger и не позволяет независимо повторить весь набор. Ошибочные side invocations с неверным cwd/nonexistent Pyright config не считаются gates в исходном отчёте.

### 14.2. Независимое воспроизведение из clean archive после audit fixes

Подтверждено в portable sandbox:

- `validate_sandbox.py`: `ok=true`, syntax/JSON 282 Python + 13 JSON, config registry/C# scanner/hygiene PASS;
- compileall: PASS;
- schema export: 5/5 current;
- contract parity, delivery contract, mutation gate, runtime-impact: PASS;
- semantic runtime baseline: 10 cases, 0 differences;
- Planner prompt: **26,988 / 27,000**, 25 functions, no problems/warnings;
- registry validation: 0 errors;
- finite VFX negative checks: 9 fields rejected/inert;
- historical replay: 82 cases, 0 failures.

Не воспроизведены: full pytest/255 (в sandbox нет Hypothesis), Ruff, Pyright, tML Debug/Release и новый Live. Поэтому в этой среде `releaseReady=false`; это честная dependency/verification boundary, а не обнаруженный runtime regression.

---

## 15. Как теперь делать partial extension без нового semantic spaghetti

1. **Сначала typed contract diff.** Новая функция/param начинается в immutable registry, не с prompt prose.
2. **Одновременно определить lifecycle:** provider type, compiler fields, provenance obligation, final DTO/C# executor и repair group; applicability до отдельной migration синхронизируется с её текущими owners в `reports.py`/runtime-family policy.
3. **Prompt только проецируется** из registry/role/event policy; не писать второй список enum/params вручную.
4. **Frozen surface test** должен показать минимальный ожидаемый diff.
5. **Affected historical replay** выбирается по changed functions и проходит без LLM; новый corpus обязан сохранять authored function provenance. Call-shape/form coverage проверяется builder-ом, а не несуществующим form selector.
6. **Mutation/parity/delivery/C# gates** доказывают весь wire до оплаты модели.
7. **Targeted canary/Live** возможен только после gates и только по явной текущей команде пользователя; batch/config являются ограничениями запуска, а не разрешением.
8. **Full Live20 — acceptance, не debugger.** Если он находит general seam, исправляется canonical owner; item-name exception запрещён.
9. **Human quality review остаётся отдельным:** executable, но скучный/неидеальный выбор (пример Gel Grenade) нельзя безопасно «чинить» скрытым classifier’ом.

---

## 16. Итог

Архитектурная миграция существенно реализована: prompt/runtime contract больше не является одной неразделимой текстовой плитой. Function/provider/prompt/wire metadata, repair, final projection, Visual roles, VFX policy и historical replay имеют более явных владельцев и deterministic gates. Однако closing snapshot `c82d168` ещё содержал воспроизводимые VFX и replay false-PASS seam, поэтому прежняя формулировка «текущий tree стабилизирован» была слишком сильной.

Независимый audit закрыл эти два seam, расширил frozen typed surface и исправил source-of-truth maps. Applicability пока остаётся отдельной policy surface, legacy replay corpus не имеет authored provenance, а post-audit tree не имеет нового Live confirmation. Поэтому корректный статус текущей ветки — **offline deterministic contract candidate**, не безусловно Live-confirmed/release-ready snapshot в любой среде.

Отчёт не должен подменять цель более дешёвым Live. Окончательное практическое доказательство — следующий реальный medium-size feature/contract diff должен остаться локальным: один typed owner, минимальный frozen diff, affected replay и отсутствие глобальной рестабилизации. Owner-reported ≈100M cost framing остаётся архитектурной мотивацией, но не измеренной этим archive величиной.

---

## 17. Независимый audit snapshot `c82d168`

Полный отдельный документ: `agent_reports/prompt_contract_stabilization_independent_audit_20260723_RU.md`.

Сжатый результат:

- основное архитектурное направление подтверждено кодом и не является выдумкой;
- external Live/token facts не могут быть independently reconstructed из переданного архива;
- на исходном `c82d168` воспроизведены два false-PASS: open finite VFX tokens и empty affected replay для typed lowerers;
- fixes сделаны generic/fail-closed в `audit/verify-contract-stabilization`;
- deterministic gates и 82-case replay зелёные;
- full pytest/Pyright/Ruff/tML/Live в audit environment не подтверждены;
- applicability и legacy authored-provenance corpus остаются честно отмеченными residual boundaries.

---

*Конец скорректированного отчёта. Sections 1–10 — historical causal archaeology; sections 11–16 — implemented architecture/Live narrative with corrected verification status; section 17 — independent code audit of the distributed snapshot.*
