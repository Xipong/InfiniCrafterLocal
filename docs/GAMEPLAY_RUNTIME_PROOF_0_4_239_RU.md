# Gameplay / Runtime Proof 0.4.239

Этот слой ловит разрыв «тесты зелёные, а runtimePlan → compiled fields → GeneratedItemData → C# не то».

## Автоматизировано

### 1) Compiler / provenance proof

```bash
cd LocalGenerator
PYTHONPATH=. python -m pytest -q tests/test_239_golden_runtime_proof_contract.py
PYTHONPATH=. python tools/generate_golden_runtime_proof.py --out ../agent_reports/runtime_proof --include-gameplay
```

Artifacts:

- `agent_reports/runtime_proof/compiler/<caseId>.json`
- `agent_reports/runtime_proof/gameplay_seam/<caseId>.json`
- `agent_reports/runtime_proof/summary.json`

### 2) Gameplay seam proof

Для каждого golden case harness делает:

1. `validate_and_repair`
2. `apply_item_knowledge`
3. `attach_gameplay_and_attack`

и проверяет final Python fields:

- `category`
- `gameplay.*`
- `attack.*`
- `accessory.*` / `armor.*`

Это уже ближе к реальному предмету, чем один compiler patch. Без LLM, HTTP, image backend, Terraria.

## Golden cases

| caseId | expected runtime/gameplay envelope |
|---|---|
| melee_swing_onhit | swing + frostburn onHit + melee damage/useTime |
| ranged_straight_shot | shoot + bow + straight |
| magic_cast_aura | cast + flame + lightning_arc + manaCost |
| summon_minion_safe | summon + minion |
| accessory_runtime | accessory fields, attack disabled |
| armor_runtime | armor body slot/stats, damage=0 |
| tool_mining_light | pick/axe/miningSpeedScale + runtime light |
| mobility_runtime | blink_to_cursor + cooldown/range/safeTile |
| visual_only_cue | combat works; no world-entity spawn |
| forbidden_world_entity | boss/world entity rejected; minion kept |

## Bugs caught by this proof layer

1. `armor_runtime` crash: `NameError: _num is not defined` in armor attach path.
2. `tool_mining_light` silent loss: authored `tool_capability` pick/axe were zeroed unless parents already looked like tools.
3. `emit_light` / `manaCost` seam: compiled light/mana did not always survive into final gameplay fields.

Fixes landed with the proof harness so the same cases stay green.

## What is still not proven

1. Full combine with live LLM planner.
2. Visual asset generation / sprite delivery.
3. Real in-game Terraria/tModLoader smoke.

## Human Terraria smoke checklist

| item / case | expected in game | observed | pass/fail | notes / screenshot |
|---|---|---|---|---|
| melee_swing_onhit | swing hitbox + frostburn-like on-hit |  |  |  |
| ranged_straight_shot | bow-like shoot projectile |  |  |  |
| magic_cast_aura | magic cast projectile/effect + mana cost |  |  |  |
| summon_minion_safe | minion-like summon, no boss |  |  |  |
| accessory_runtime | accessory equip stats only |  |  |  |
| armor_runtime | body armor equip stats only |  |  |  |
| tool_mining_light | mining power + light utility |  |  |  |
| mobility_runtime | blink/recall utility, safe tiles |  |  |  |
| visual_only_cue | combat works; VFX is presentation only |  |  |  |
| forbidden_world_entity | no boss/world entity spawn |  |  |  |

Fail conditions:

- no executable combat when combat expected;
- wrong family (swing instead of shoot/cast/summon);
- boss/world spawn;
- accessory/armor acting as weapon;
- tool/mobility fields missing at runtime;
- visual-only call invents gameplay.

## Next slices

B) Prompt/semantic repair — если golden/compiler/gameplay seam ok, но live LLM runtimePlan мусор.
C) Visual quality — если runtime ok, а спрайты/prompts слабые.
Terraria smoke — заполнить checklist выше на live mod.


## Full combine generation (authored golden plans)

```bash
cd LocalGenerator
PYTHONPATH=. python tools/generate_golden_runtime_items.py --out ../agent_reports/runtime_proof_items
```

This runs the real `combine()` path with LLM replay fixtures (no live network, image backend off) and writes full `GeneratedItemData` JSON per golden case.

Artifacts:

- `agent_reports/runtime_proof_items/<caseId>.full.json`
- `agent_reports/runtime_proof_items/summary.json`

Caught by this layer:

- LLM replay stage misroute: planner payloads containing both `repair` and `name` were classified as `name_repair`, dropping `runtimePlan` before compile.


## B slice started: promise/semantic honesty

- `runtime_promise_truth.py`: `onHit=starfall` is now treated as executable promise truth, not blanket unsupported.
- Claim patterns recognize natural starfall wording (`raining stars`, `stars from the sky`).
- Planner authorRules clarify: use `custom_executor` for normal engineCalls; mark unsupported only when there is no finite path.
- Prompt stays under budget: ~22921 chars.

This is semantic honesty repair, not a code router.
