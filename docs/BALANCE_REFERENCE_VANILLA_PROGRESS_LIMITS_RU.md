# Balance architecture: one active soft authority + one debug report

v0.4.219 фиксирует анти-хаос правило: баланс не должен жить одновременно в prompt, JSON-helper'е, документации и C#. Активный soft balance остаётся в Python после LLM-authoring, а итоговая диагностика собирается в единый `debug.balanceReport`.

## Слои

```text
LLM author
  └─ пишет fantasy / resultKind / runtimePlan.engineCalls / numbers

Code-only structural repair
  └─ чинит кривую форму, если authored параметры уже понятны

Targeted retry before C#
  └─ включается только если предмет после code repair всё ещё не исполним

Python post-authoring balance
  └─ единственный мягкий балансный слой:
     - stat_profile_for(...)
     - VANILLA_LIKE_WEAPON_ENVELOPES
     - clamp_vanilla_like_weapon_damage(...)
     - authored_weapon_damage(...)

Runtime compiler clamps
  └─ режет только опасные runtime-числа:
     shotCount / pierce / lifetime / range / homing / AoE / child projectiles

C# hard safety
  └─ последний предохранитель перед Terraria runtime:
     JSON shape, max values, Texture/Projectile/FPS/network safety
```

## Что не является активным балансом

- `docs/TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md` — human/dev reference, не активный helper и не prompt payload.
- Prompt не получает parent-relative soft caps: они больше не передаются в LLM payload.
- C# не должен быть дизайнером баланса.

Из LLM payload не возвращать:

```text
softDamageCapPerHit
softAoeTilesCap
softActiveProjectileCap
sourceEnvelope
terrariaProgressionReference
```

## powerBand вместо hard gate

Internal buckets вроде `pre_hardmode_late`, `mech`, `plantera` — это грубые power-like labels, а не запреты прогрессии.

В `balanceReport` они отображаются как:

```json
{
  "powerBand": "power_03",
  "label": "late pre-Hardmode-like",
  "sourceBucket": "pre_hardmode_late"
}
```

Это нужно, чтобы не скатиться обратно в hard progression gates.

## Clamp taxonomy

`debug.balanceReport.clamps` разделяет причины:

```text
balanceClamp
  Python soft envelope: DPS pressure, weak anchor, recursive generated damage.

safetyClamp
  Runtime/C# safety: FPS/network/range/lifetime/projectile caps.

contractClamp
  Shape/repair/validation: structural code repair, targeted retry, unsupported runtime.
```

В JSON-ключах это хранится компактно:

```json
"clamps": {
  "balance": [...],
  "safety": [...],
  "contract": [...]
}
```

## Как читать balanceReport

Пример:

```json
{
  "schema": "infini.balance-report.v1",
  "powerBand": "power_03",
  "label": "late pre-Hardmode-like",
  "authored": {
    "damage": 120,
    "useTime": 20,
    "shotCount": 3,
    "costMultiplier": 2.1
  },
  "final": {
    "damage": 28,
    "useTime": 20,
    "attack": {
      "shotCount": 3,
      "pierce": 4,
      "homingStrength": 0.5
    }
  },
  "clamps": {
    "balance": ["authored_damage_soft_envelope"],
    "contract": ["runtime_repair_path"]
  }
}
```

Смысл: LLM authored сильную механику, Python не запретил её, но снизил hit damage из-за multishot/homing/pierce pressure.

## Почему caps выше ванильки

Generated-предмет должен иметь право быть ярче ванили:

- лучше получить сильный/странный предмет и потом нерфить;
- хуже получить серую безликую кашу;
- низкоуронный utility item не апается насильно (`raise_floor=False` для authored damage).

## High-risk mechanics

Homing, pierce, defense debuff, through-block hits, lifesteal, multishot, long range и big AoE не запрещены.

Они оплачиваются через:

```text
useTime × shotCount × pressure_cost × DPS envelope
```

и через runtime safety clamps:

```text
shotCount / pierce / lifetime / range / homing / AoE / child projectiles
```

## Guard phrases / старые инварианты

- Это не category-routing: код не решает семейство предмета по словам prompt/name.
- Terraria guide не должен превращаться в active helper, prompt reference или второй валидатор.
- Balance doc не должен превращаться в таблицу рецептов; он описывает responsibility boundaries.

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
