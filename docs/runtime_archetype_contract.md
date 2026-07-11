# RuntimeArchetypeSpec + runtimeContract refactor — v0.4.239

This document describes the typed runtime-authoring language added in v0.4.239.

## Boundary

InfiniCrafterLocal still keeps the same executable boundary:

1. LLM authors fantasy/resultKind/numbers/visual intent and `runtimePlan.engineCalls`.
2. The LLM may also author `runtimeArchetype` and `runtimeContract` as structured data contracts.
3. Python normalizes, validates, reports promise truth, and compiles only supported subsets into current `AttackSpec`/`GeneratedItemData` fields.
4. C# tModLoader executes only finite supported runtime primitives and hard clamps/normalizes incoming generated data.
5. Unsupported mechanics are preserved as intent/debug warnings, not silently executed and not routed from prompt keywords.

No C# codegen is introduced. C# does not parse item names, tooltip prose, visual prompts, parent names, or fantasy text into gameplay.

## RuntimeArchetypeSpec

`runtimeArchetype` answers: which finite behavior family is this item trying to use?

Example shape:

```json
{
  "runtimeArchetype": {
    "schema": "infini.runtime-archetype.v1",
    "source": "generated",
    "family": "boomerang",
    "phaseModel": "outbound_return",
    "channelled": false,
    "usesHeldProjectile": false,
    "overrideKnobs": {
      "returnDelayTicks": 24,
      "outboundPierce": 1,
      "returnPierce": -1,
      "localImmunityTicks": 12,
      "trailProfile": "amber_slime",
      "futureDebugKnob": {"preserved": true}
    },
    "supportStatus": "executable",
    "supportNotes": []
  }
}
```

Supported/exposed families in this patch:

- `custom_executor`: default/omitted path; current `runtimePlan.engineCalls` remain authoritative.
- `boomerang`: executable bridge to current returning/boomerang fields: `delivery=throw`, `movement=boomerang`, `runtimeFamily=returning`, `weaponFamily=boomerang`, plus phase metadata and scorer-safe return-pierce notes.
- `yoyo`, `flail`, `whip`: mapped only to existing finite runtime family fields. No giant vanilla item table.
- `held_swing`, `held_thrust`: explicit held/swing/thrust family metadata over current finite fields.
- `apply_on_hit_effect(onHit=overhead_barrage)`: executable on-hit overhead-projectile primitive (`onHitCode=18`), bounded by child caps and budget pressure. Star/arrow/shard theme comes only from explicit projectile/effect fields; removed names are rejected.
- `channel_beam`: executable bridge to canonical `runtimeFamily=beam`; held/channelled, wall-bounded line scan, explicit range/width/charge/immunity cadence, exact duplicate guard and periodic authored mana payment.
- `overhead_barrage`: executable finite target marker → delay → bounded authored projectile spawn above the target area. Retired family names are rejected.
- `secondary_attack`, `unsupported`: preserved intent/debug only unless another finite executor supports the exact behavior.

These are `RuntimeArchetypeSpec.family` values, not canonical `attack.runtimeFamily` executor values. For example, archetype `boomerang` compiles to `runtimeFamily=returning`; downstream runtime consumers only see the latter.

These are `RuntimeArchetypeSpec.family` values, not canonical `attack.runtimeFamily` executor values. For example, archetype `boomerang` compiles to `runtimeFamily=returning`; downstream runtime consumers only see the latter.

Known numeric knobs are clamped in Python/C#:

- `returnDelayTicks`: 0..180
- `outboundPierce`: -1..20
- `returnPierce`: -1..50
- `localImmunityTicks`: 0..60
- `arcDegrees`: 10..220
- `windupTicks`: 0..90
- `activeTicks`: 1..120
- `recoveryTicks`: 0..120
- `chargeTicks`: 0..300
- `beamWidthPx`: 2..96
- `maxActiveProjectiles`: 0..32

Unknown `overrideKnobs` are preserved in JSON/debug as inert future data.

## RuntimeContractSpec

`runtimeContract` answers: how should the item feel/control/sync, and which mechanic promises are supposed to be true?

Example:

```json
{
  "runtimeContract": {
    "schema": "infini.runtime-contract.v1",
    "primaryVerb": "returning boomerang throw",
    "controlStyle": "tap",
    "mustFeelLike": ["Enchanted Boomerang return", "high reward on return path"],
    "mustNotFeelLike": ["straight dagger projectile", "passive aura"],
    "stateFields": ["returnPhase"],
    "syncFields": ["owner", "phase"],
    "visualStateFields": ["trailProfile"],
    "mechanicClaims": [
      {
        "claim": "returns to the thrower and can hit again on return",
        "backing": "runtimeArchetype.family=boomerang",
        "status": "executable"
      }
    ],
    "unsupportedPromises": [],
    "executionStatus": "executable"
  }
}
```

`runtimeContract` is not direct gameplay. It informs validation/debug/future sync and detects tooltip/fantasy lies. It cannot override `runtimePlan.engineCalls` unless the Python compiler explicitly maps that contract/archetype to supported finite fields.

## Promise truth validator

Python now emits `debug.runtimePromiseTruth` and top-level `unsupportedPromises` when structured fields/prose/visual intent promise mechanics that are not backed by executable runtime.

Examples:

- “returns to thrower” + `runtimeArchetype.family=boomerang` => `executable`.
- “projectiles descend from above on hit” + `apply_on_hit_effect(onHit=overhead_barrage)` => `executable` bounded child projectiles; explicit `effect=star` keeps a star theme.
- “projectiles appear above the targeted area” without explicit `overhead_barrage` => `unsupported` unless clearly visual-only.
- “channel beam” + explicit `runtimeArchetype.family=channel_beam` or `cast_magic_weapon(family=channelled_beam)` => executable held beam. Beam wording without that exact structured selection remains visual-only/unsupported and never selects gameplay.
- “paired/dual sword” can be preserved as future `secondary_attack` intent. Broken dual-wield is not executed, but future finite support is allowed.
- “burst” with `onHit=burst` but no burst visual cap/impact feedback => partial warning.

The validator never creates gameplay from words. It only checks consistency and records warnings/unsupported intent.

## Visual link

Visual generation may read `runtimeArchetype`/`runtimeContract` to avoid contradictory sprites, but visual text never selects gameplay:

- A real boomerang family can suggest a returning silhouette when item identity also supports it.
- A shard/glaive with boomerang movement does not have to become a crescent just because movement returns.
- Unsupported paired sword can be drawn as one fused/split blade rather than broken dual-wield.
- Explicit executable channel beam may drive a held-emitter/beam visual; beam-like prose without the exact runtime family must remain visual-only.

## Save/load/net compatibility

C# `GeneratedItemData` now has data-only `RuntimeArchetypeSpec`, `RuntimeContractSpec`, and `MechanicClaimSpec` DTOs. `Normalize()` tolerates missing fields, clamps known knobs, and preserves unknown future knobs as JSON. Old generated recipes without these fields still load and execute through the existing runtime fields.

Generated JSON preserves the archetype fields. Executable beam state also has an explicit projectile protocol (`ProjectileSyncVersion = 13`) for range, homing strength, beam width, charge duration and current scanned length; direction/position use normal projectile sync.

## Secondary trigger lifecycle

`spawn_secondary_projectiles` accepts one exact trigger: `on_hit` or `on_expire`. The compiler rejects mixed trigger calls and rejects implicit dual child lifecycles. `on_expire` is implemented by a dedicated policy/compiler owner and a bounded C# kill-path; it is not a generic event/action framework.

## Deferred TODOs

- Full PacketRegistry consumer for `runtimeContract.syncFields`.
- Optional richer multi-beam/charge-release variants built from finite knobs, without item-name aliases.
- Full held projectile swing overlay.
- Feline bounce / sticky puddle / heat-jam executors as separate future finite slices. Overhead barrage is already executable under its exact canonical name.
- True paired/offhand dual-wield as a finite supported executor, not broken visual/prose routing.
