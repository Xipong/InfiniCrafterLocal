# Parent-local native buff operation fragments

## Packet seam

- `nativeBuffEffectReference` is captured once in `CaptureParentNativeFacts` for an observed, non-generated item's positive `buffType` + `buffTime` self-use request. Receiver is `player`; `requestedDurationTicks` stays separate from the update-effect evidence. Existing root/runtimeFacts/fingerprint copies are literal projections.
- Each fixed or random-alternative contact/projectile hit-status effect carries `buffEffectReference` with receiver `npc`. The existing status owner retains probability, random grouping, duration and application-source certificates unchanged.
- Only the observed buff is projected. There is no loaded-buff dictionary, preset/primitive routing table, gameplay-hook execution or semantic tooltip parsing.

## Source certificate and reproducibility

`tools/generate/generate_native_buff_effects.py` uses the existing read-only `dnfile`/`dncil` IL decoder. Native field signatures distinguish booleans from numeric fields. BuffID constants label branches **after** their ID has been derived from source comparisons; names do not select operations.

The runtime checks the entire DLL SHA256, module MVID, and every dependent method's IL SHA256 before looking up a row. Current generated support is exactly installed DLL `fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5`, MVID `033e87cd-cefe-4dc6-a1fb-e14aa938bbb2`. Certified methods: Player.UpdateBuffs; NPC.UpdateNPC_BuffSetFlags, UpdateNPC_BuffFlagsReset, UpdateNPC_BuffApplyDOTs and GetIncomingStrikeModifiers. Unknown binaries, modded buff/source semantics and absent source coverage return explicit unsupported observations, never guessed values.

```sh
/home/xipong/agent-work-main/scripts/agent-storage run --task buff-repro -- \
  /home/xipong/agent-work-main/scripts/agent-python tools/generate/generate_native_buff_effects.py \
  --assembly '/mnt/c/Program Files (x86)/Steam/steamapps/common/tModLoader/tModLoader.dll' --check
```

Generated products are `NativeBuffEffectCatalog.g.cs` and `native_buff_effect_sources.generated.json` alongside this report. No game/runtime assembly is loaded by the generator.

## Coverage and limits

Current source yields 77 player rows with direct typed boolean assignments and/or scalar additions/multiplications. These are **statement fragments**, not full effect implementations: e.g. Mining's source subtracts0.25 from Player.pickSpeed; Spelunker's source assigns Player.findTreasure=true. A flag is not advertised as its full downstream utility/AI behavior.

NPC source joins8 direct flag-gated periodic-regen penalty fragments and2 hit-local defense Flat contributions. Regression examples only: Poisoned's flag leads to clearing positive lifeRegen then subtracting12; Ichor leads to HitModifiers.Defense.Flat subtract15 only with ignoreArmorDebuffs=false. The latter is not a persistent NPC.defense mutation. The8 regen consumers are Poisoned, OnFire, CursedInferno, Frostburn, Venom, ShadowFlame, OnFire3 and Frostburn2; these names are generated results, not recognition selectors. BetsysCurse is the other defense consumer.

18 NPC rows are unsupported/flag-only, including Confused, Midas, SoulDrain, Oiled, Daybreak, projectile-count-dependent effects, progression-dependent Dryad effects and Shimmer. The analysis also retains177 player and1 NPC literal branch refusals. Complex calls, ref/StatModifier getter operations, nested branching, indirect/array stores, AI effects, contact-damage and velocity semantics remain outside this bounded subset. No claim is made about unrecognized dispatch shapes, all vanilla effects, mod effects, admission/immunity, actual duration refresh or final stats/damage.

Each scalar fragment retains `buffTypeEquals`, slot-local identity, source test/operation offsets and **nativeControlFlowMustReachTest**. Enclosing path conditions are explicitly unresolved, never silently dropped to claim an unconditional whole-buff effect. NPC consumer fragments additionally retain dontTakeDamage=false, the flag=true predicate, the buff-to-flag branch condition, reset-method provenance, and the defense consumer's ignoreArmorDebuffs gate.

## Numeric source units

- `native_member_units`: exact signed native-field contribution plus storage type. It is not automatically a percent/final stat. No per-stat primitive naming table is duplicated here.
- `dimensionless_factor`: multiply the current native member at that source site; not the final effective-stat multiplier.
- `native_lifeRegen_units`: signed native regen contribution, with positive-regen clearing retained. Independent source-shape evidence proves lifeRegenCount accumulation and120 accumulator units per one-HP decrement; the target uses realLife when nonnegative and is subject to resolved-target immortality. `nominalHpLossPerSecondAt60Updates` is an explicit unit comparison assuming60 accumulator updates/s (Poisoned6), not proved scheduling or final damage. Hooks, other contributions and grouped damage still apply.
- `defense_points`: hit-local HitModifiers.Defense.Flat contribution, not a persistent defense write or guaranteed damage delta.

## Verification handoff

Focused source-generator plus existing hit/attack source suites passed. Regeneration with `--check` against the exact installed DLL passed. The integrated actual-source native CPU run passed **488/488 checks**, including `ParentBuffEffectsAreSourceCertifiedAndParentLocal`, source refusals and executable buff/debuff consumers. This is not game-loop or live-MP acceptance.

The registered parent-source check verifies capture-only values, receiver separation, certificate refusals, literal Prepare projections and BladeofGrass's source Poisoned probability1/4 and420 ticks. No buff update/gameplay hook is invoked to discover facts. Optional exports: `INFINI_PARENT_STATUS_PACKET` writes actual Prepare(BladeofGrass, LightsBane); `INFINI_PARENT_BUFF_PACKET` writes Prepare(MiningPotion, SpelunkerPotion).

Actual native Prepare→provider HTTP serialization passes in both json_schema/json_object modes for four pairs (ammo rewrites, contact status and self-use buffs). The compact dossiers are198571–223921 Unicode characters under the unchanged225000 guard. Exact native source values shared by `sourceSameAs` indices are all recoverable from the same request; literal tooltips and generated-parent packets remain inline. No model/network inference was performed. Explicit no-image CPU fixture mode separately replays Python's delivery-stripped mechanical wire through the strict native reader and actual NPC/player consumers; it does not counterfeit completed PNG generation.
