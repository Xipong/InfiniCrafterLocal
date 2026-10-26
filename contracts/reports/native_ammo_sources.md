# Native ammo source observations

Producer: `tools/generate/generate_native_ammo_facts.py`; machine-readable evidence:
`native_ammo_sources.generated.json`. Capture: `GeneratorClient.AmmoFacts.cs`,
used by `GeneratorClient.ParentFacts.cs::AmmoRawFromItem`; Python projection:
`parent_context_pipeline.py::compact_ammo_profile`.

```sh
agent-python tools/generate/generate_native_ammo_facts.py \
  --assembly '<installed tModLoader.dll>'
# Same command with --check verifies both generated products.
```

## What is certified

The generator reads method IL without loading/executing the assembly. Runtime
matches method SHA256 plus module MVID before exposing generated native facts.
It recognizes complete item-type-guarded literal projectile assignments,
including exact input-projectile equality conditions; explicit native spawn
arguments; a bounded unit-counter loop with literal +/- bound adjustments; and
MountedCenter-relative Vector2 Y initialization inside a native spawn branch.
The count range is conservative and conditional, not a probability or cadence.
The origin reference is the constructor argument, not a complete final position.
Native aiming/spread is explicitly unmodeled rather than labeled ordinary direct
arrow delivery.

Default positive-ammo.shoot selection and category-offset arms come from the
actual PickAmmo IL. Category values come only from literal AmmoID static field
initializers, not weapon families or handwritten category semantics. Specific
launcher/ammo table selection is an unresolved earlier arm, not silently replaced
with the default or offset formula. Ordered stage call sites and ModItem /
GlobalItem dispatcher calls come from the same assembly; each dispatcher method
certificate is checked independently. Unsupported native binaries have no
certified call-order prose.

Loaded ModItem / attached GlobalItem metadata is inspectable, not intrinsically
unknown. Supported full override bodies are literal or input-equality-guarded
ref-projectile assignments, literal bool Shoot returns (only 0/1), and a single
straight-line fixed-projectile spawn followed by false. Method base override and
return signatures must agree. Calls, state-dependent expressions, unsupported
control flow, exception regions, invalid projectile literals and unsupported
bool representations remain opaque. No gameplay hook is executed for capture.
The selected **ammo's** PickAmmo override is distinct from the weapon's
ModifyShootStats / Shoot hooks. ModPlayer effects and incomplete GlobalItem
rosters remain explicit unknowns. Composition follows certified native phase and
owner-dispatch order, not the order in which owner metadata was collected:
all ModifyShootStats precede Shoot; GlobalItem.Shoot admission controls whether
ModItem.Shoot is reached. A fixed explicit spawn cannot be overwritten by an
earlier ref-projectile modifier. Multiple distinct explicit spawns do not become
one guessed output ID; their individual hook facts remain available.

## Packet meaning

- `projectileSemanticsReference`: source-stage facts, provenance and unresolved
  conditions, not a final-shot observation or mandatory child behavior.
- `candidateProjectileBindings`: per source/slot input identity bound to supported
  source rewrite predicates. A basic projectile may transform while a special
  projectile bypasses that exact guard. Opaque hooks remain unknown.
- `playerInventoryAmmoRaw` / `fallbackAmmoRaw`: ammo-item identity and separate
  damage, speed and knockback contributions. Identity replacement does **not**
  erase these stats. Inventory is observed; fallback examples are not possession
  or progression evidence. Author receives no stack quantities.
- Input projectile profiles are withheld when supported source rules replace
  them, a hook suppresses the default shot, or opaque hook inference would be
  required. A retained special input keeps its separate profile.
- `nativeReplacementProjectileRaw`: bounded distinct source-projected output
  identities and static projectile references, not inherited execution or final
  velocity. Invalid/out-of-range literals never become SetDefaults proof.

No strongest-ammo selection, recommended damage formula, automatic child
rebalancing, inventory-gated mechanics, recipe-stock key or progression mapping
is introduced. The Author chooses the child composition independently.

## Acceptance

Native registered checks: `ParentAmmoSourceSemanticsReachPrepare`,
`ParentAmmoModHookShapesAreInspectedNotExecuted`, and
`ParentAmmoMixedHooksKeepNativePhaseOrder`. The mixed-hook observer invokes the
production ammo-capture owner directly on a controlled ModItem/GlobalItem fixture;
it does not claim full content registration or execute those gameplay hooks.

The first covers native stock behavior; BloodRain and Shadowflame replacements;
Pulse Bow's later ItemCheck replacement; Hellwing's exact input-projectile-1
predicate and retained special arrows; and Daedalus retaining ammo identity with
its native aerial delivery. Actual PickAmmo and ItemCheck_Shoot requests are
observed only in isolated CPU tests. Pulse conversion retains ammo damage.
The second checks supported ModItem and GlobalItem shapes, ammo-owned PickAmmo,
opaque hooks with zero capture executions, invalid spawn literals, and emitted
bool 2/-1 negative controls.

`test_parent_ammo_source_semantics.py` checks actual source extraction and both
Author response-format projections. Its replay assertion helpers also accept
actual native Prepare JSON exports (`INFINI_PARENT_AMMO_PACKET` and its
`.hellwing.json` companion), preserving predicates/unknowns and proving that
irrelevant input-arrow projectile profiles stay absent while ammo-item stats
remain. Full runtime-library prompt capacity is a separate shared Author guard;
source facts must not be clipped to bypass it.
