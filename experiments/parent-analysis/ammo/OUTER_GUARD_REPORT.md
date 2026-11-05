# Native ammo enclosing-guard correction

Local source: `ifc-ammo-outer-guard-fix-20261105`. No Git objects, PR changes, game, graphics or world launch.

## Established defect

Certified tML 1.4.4.9, module `033e87cd-cefe-4dc6-a1fb-e14aa938bbb2`: Player.ItemCheck_Shoot tests current projectile 1 at IL521–523 before item 120 at525–533, then stores projectile 2 at535–536. The old extractor certified only the inner item block, dropping the outer predicate. Native RED reproduces Molten+Jester: actual 5, old source predicts 2. Flaming input 2 masked the defect in the old oracle.

## Correction and refusal boundaries

Generic contiguous equality-guard proof handles projectile/item nesting order, repeated equalities and byref/local targets. No fixed item/projectile tables or simulation. Unknown expressions, intervening mutations, contradictory guards and external entries do not become unconditional mappings.

Complete literal source sites whose applicability is unknown are separate `unresolvedLiteralWrites`. Proven ownership keeps the full projectile profile with explicit unresolved applicability; unproved ownership retains evidence without attaching a weapon-owned profile. Complex writes retain unknown offsets, including foreign-entry-rejected blocks. Any unresolved native write outranks aggregate positive labels, while independently certified rules/profiles survive. Actual item 4953 therefore correctly becomes aggregate unknown due existing opaque ItemCheck write 10873, retaining PickAmmo1→932 and profile 932.

## Native results

Actual PickAmmo and ItemCheck_Shoot/NewProjectile requests, seven weapons × four ammo inputs: 28/28 pass.

- Hellwing: Wooden→485; Flaming→2; Jester→5; Holy→91. Prepare retains conditional1→485 and full profile 485.
- Molten: Wooden→2; Flaming→2; Jester→5; Holy→91. Prepare retains conditional1→2 and full profile 2.
- Native consumer tests pass proved/unproved unresolved ownership, mixed known+unknown literal sites, known rule+opaque write, exact profile preservation and restored catalog state.

Final binary SHA256: `426df4ce3891258959d13d95e3115d02a18c893e63487675596189a0209711da`. Compile manifest source hashes match final C# files. Direct Roslyn build against actual tML references, not an SDK/MSBuild release claim.

## Regeneration scope

Fresh original versus corrected extraction differs only in Molten's predicate plus empty unresolved metadata. The old checked-in catalog was already stale: fresh original extraction also produces six additional spawn rows 273/368/674/675/757/1826. Honest regeneration includes them. Actual native defaults prove all six have useAmmo 0 and AmmoRawFromItem=null; these rows do not enter weapon ammo context. Source receipt: `outer-guard-semantic-diff.json`; exact native defaults: `ifc-toolchain-20261105/ammo-outer-native-evidence/non-ammo-catalog-rows.jsonl`.

## Artifacts and checks

- Review patch/hash manifest: `outer-guard.patch`, `outer-guard-changed-files.json`.
- Python RED: 14 failed / 5 passed, `outer-guard-python-red.log`.
- Final affected Python suite: 120 passed in 129.89s; deterministic native generator --check PASS; C# source policy gate PASS. Logs: `outer-guard-python-final.log`, `outer-guard-generator-check-final.log`, `outer-guard-csharp-contracts.log`.
- Native build/check logs: `ifc-toolchain-20261105/ammo-outer-final-{native-build,ammo-run,profile-run}.log`.
- Actual Prepare packets and accurately labeled synthetic-source-only unknown fixture: `ifc-toolchain-20261105/ammo-outer-final-native-evidence/`.

Full integrated Python/native/static acceptance and model-boundary/token-footprint checks remain parent-owned. No claim of live gameplay, GPU/network, spread/RNG completeness or final shot semantics.
