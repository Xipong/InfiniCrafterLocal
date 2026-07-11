# Balance architecture — explicit modes, one policy owner

Текущий баланс не является вторым автором предмета. LLM пишет числа и механику; Python всегда держит shape/hard numeric bounds, а soft normalization включается только явно.

## Один владелец режима

`LocalGenerator/infini_local/core/balance_mode.py` хранит только exact policy:

```text
INFINI_BALANCE_MODE=report | safety | normalize
```

В этом файле нет DPS-формул, progression tables или category routing. Числовые envelopes остаются в `balance_policy.py`; отчёт остаётся в `balance_report.py`; callers явно решают, применять ли soft clamps.

## Режимы

### `safety` — default

- сохраняет authored weapon/equipment numbers против soft normalization;
- применяет технический Python corridor для projectile count/depth/range/lifetime/network pressure;
- вычисляет soft suggestions и записывает их как `applied=false`;
- C# hard clamps остаются последней защитой.

### `normalize` — opt-in legacy behavior

- применяет существующие weapon DPS/equipment soft envelopes;
- применяет технический safety corridor;
- все реальные изменения попадают в provenance/balance report.

### `report` — diagnostics

- не применяет Python soft normalization;
- не применяет Python runtime safety corridor;
- сохраняет advice/report для анализа;
- C# hard safety всё равно не отключается.

## Граница ответственности

Термины, которые используются в contract tests и debug taxonomy:

- `Python post-authoring balance` — существующие soft envelopes и advice после LLM authoring; они применяются только в `normalize`.
- `balanceClamp` — реально применённая soft normalization.
- `safetyClamp` — техническая защита runtime/FPS/network.
- `contractClamp` — shape/validation/unsupported repair.
- `Runtime compiler clamps` — bounded projectile/runtime safety после authoring.

Это **не category-routing**: режим и формулы не выбирают тип оружия по prompt/name/tooltip. Terraria progression guide — human reference, **не активный helper** и не prompt payload. Balance doc **не должен превращаться** в таблицу оружия, progression ontology или активный gameplay-helper.

```text
LLM author
  → structured repair/compile
  → exact balance mode policy
  → existing numeric envelopes or advice
  → runtime compiler safety (если mode=safety|normalize)
  → C# hard safety always
```

Режим не выбирается LLM и не добавляет ей полей. Sparse-output policy не меняется: явно authored zero/default не удаляется и сохраняет provenance.

## Что считается балансом, safety и contract repair

- `balance`: soft DPS/equipment advice или применённая normalization;
- `safety`: технические caps, которые защищают FPS/network/runtime;
- `contract`: shape repair, unsupported promise, validation failure.

`debug.balanceReport` всегда содержит `balanceMode`. Advice помечается `applied=false`, фактические clamps — `applied=true`.

## Почему не переписываем scorer в «идеальный балансер»

Текущие формулы полезны как диагностика, но не должны тихо становиться геймдизайнером. Поэтому v10 меняет policy применения, а не строит новую progression ontology, таблицу оружия или второй LLM judge.

## Инварианты

Removed prompt-only dynamic cap fields **больше не передаются** в LLM payload and remain forbidden; they are mentioned here only as non-active history: `softDamageCapPerHit`, `softAoeTilesCap`, `softActiveProjectileCap`, `sourceEnvelope`, `terrariaProgressionReference`.

- Никакого category routing по prompt/name/tooltip.
- Не копировать mode strings и формулы в новые модули.
- `balance_mode.py` не должен разрастаться в scorer.
- Equipment callers явно передают `apply_clamps`; скрытого global mutation нет.
- C# не становится soft-balance designer.

## v0.4.220 — targeted repair patch contract

Targeted runtime repair is not a second item author.  If the repair LLM returns a full item JSON, Python reduces it to the same narrow patch surface:

- `runtimePlan` may be replaced to fix executable `engineCalls`;
- `attack` may be patched for compiled runtime fields;
- explicit `repairPatch.gameplay` may adjust only narrow executable/stat fields;
- identity/prose/visual fields (`name`, `tooltip`, `concept`, `visual`, `tags`, parents, ids) are preserved;
- rejected full-rewrite fields are recorded in `debug.runtimePlanRepairPatchContract` and surfaced through `debug.balanceReport.clamps.contract`.

This keeps the boundary clean: LLM authoring creates the item, code-only repair fixes obvious shape problems, targeted retry fixes executable contract problems, Python soft balance clamps numbers, and C#/tML remains hard safety.


## v0.4.226 — architecture homogeneity cleanup

Цель этой правки — не добавить ещё один чистый блок сбоку, а убрать расхождение архитектурных словарей между подсистемами.

Что теперь считается каноном:

- `LocalGenerator/infini_local/core/balance_policy.py` — единственный Python-файл с coarse power bands и weapon envelope numbers.
- `balance_report.py` только отображает `powerBand`/`label` через `balance_policy.py`; он не хранит свою копию таблицы.
- `combine_pipeline.py` применяет weapon envelope через `weapon_envelope_for_bucket(...)`; он не держит свою копию `VANILLA_LIKE_WEAPON_ENVELOPES`.
- `InfiniNetPacketIds.cs` — единственный C#-файл с числовыми packet ids.
- `InfiniRuntimeLimits.cs` — единственный C#-файл с текущим runtime API и общими opcode limits.

Это сохраняет прежнюю идеологию:

```text
LLM author
→ code-only structural repair
→ targeted retry before C# only when needed
→ Python post-authoring soft balance
→ runtime compiler safety clamps
→ C# hard safety
```

То есть теперь блоки не просто аккуратные отдельно: они используют общий словарь границ и констант.

## v0.4.226 — equipment budget / provenance note

Armor/accessory balance now reports total soft-budget pressure through `accessoryBudgetReport` / `armorBudgetReport` and feeds balance clamps into `debug.balanceReport`. Runtime provenance is tracked separately so authored engineCalls can be compared with compiler defaults without exposing dynamic soft caps to the prompt.
