# Bounded helper projectile-spawn candidate

## Decision

Local, unpublished candidate only. Extraction regression is RED→GREEN, but standard Author admission is **RED**, so this checkpoint is not ready to merge or ship. No production prompt limit was increased; no unknown or conditional source facts were silently removed. No Git objects, branches, commits, or PRs were created. The restoration owner tree is unchanged.

## Scope and baseline

Base: frozen local restoration candidate `ifc-replacement-profiles-fix-20261105`, derived from published PR330. Candidate: `ifc-helper-spawn-fix-20261105`. The four exact changed source files and hashes are in `helper-candidate-source-manifest.json`; `helper-candidate.patch` is a plain filesystem diff, not a Git object. Direct compiler input/hash manifest is `helper-final-native/compile-manifest.json` (421 C# sources).

The missing child extraction predates PR330. `GeneratorClient.ProjectileAttackFacts.cs` SHA-256 is `3739bc24337dd74f864d8d5e5b14e42d083d37db164ee94c5f3cd336eb0c16d0` in pristine baseline, PR330, and frozen restoration. On actual native tML/Terraria source, Last Prism helper AI_075 emits six projectile632 instances; the baseline packet has no child632 profile. ParentSourceGraph does reach AI_075, but the method-character bound leaves it unresolved. Existing root selection includes NewProjectile in dispatch roles, not motion helpers.

## Implementation

- Collect each reachable NewProjectile/NewProjectileDirect sink in already selected helper source independently.
- Use existing connected value/control-dependency serializer, source method/module/hash certificates and captured-identity proof. No projectile IDs or weapon names occur in production logic.
- Keep runtime guards, branch alternatives, loops, aliases and dynamic IDs symbolic. Do not execute, unroll, sample, or infer a spawn rate.
- Bounds: 32 source sites per helper; 24,000 expression work units shared; 12,000 per site. Cancellation is checked. A refused site gets an explicit unknown entry and an empty candidate list, not invented data. Other independently reachable sites can still succeed.
- Reuse existing canonical one-hop referenced-projectile profile expansion and its eight-profile cap. No new runtime design, inherited behavior, fallback mechanics or recursive profile explosion.
- Exact source-table union deduplicates dependencies, predicates and symbols only under identical source identity, coverage and identity proof. Conflicting rows or aliases remain separate; malformed/missing/duplicate row identities fail without partially mutating the destination.

## Important interpretation

The captured identity becomes unknown after an uncertified target-passing call or alias escape. Shared AI_075 therefore also exposes a conditional source candidate601 under live type==600, owner and ai guards. This is **not** evidence that Last Prism spawns601. The packet and Author/repair contexts retain the full predicates and source-call links. Seven other new spawn sites have dynamic unresolved types, not guessed IDs. Child632 has independent actual native six-spawn evidence.

## Validation

- Native baseline LastPrism test: expected RED (0/1, absent child profile).
- Focused final native tests: 4/4 PASS, covering actual native child, unknown guards/dynamic IDs/actor mutation/foreign actor/loops/EH, independent budget refusals and exact nonmutating merge conflicts.
- C# source contract check: PASS. Focused Python regressions: 91 PASS.
- Final all13 headless capture: 39 native ItemCheck_Shoot calls and six actual LastPrism AI_075 beams. Twelve of thirteen complete packets remain byte-identical to baseline; only LastPrism changes.
- Full native suite: 668 PASS, 0 FAIL; see `helper-final-native-full-correct-cwd.log`. Earlier wrong-working-directory run is invalid and excluded.
- Model context: 1,949 all13 card assertions, 288 child profile assertions, 26 exact stage delivery assertions and 50 child632/conditional601 linkage/guard assertions pass. These are deterministic evidence delivery tests, not model generation quality tests.
- Standard Author preparation fails before send: 325,379 characters against 300,000 default. Forty-two captured HTTP bodies are clearly marked diagnostic with only an in-memory limit override; there were no model calls or production limit changes.

## Size and performance

LastPrism raw packet: 488,950 baseline → 1,576,406 initial slice implementation → 933,294 final exact-merged candidate. Author card: 73,892 → 217,226 → 119,380 bytes. The extra referenced profiles contribute26,647 bytes; exact merge removed97,846 from the provisional card.

Ordinary three-stage Chat/json_object body total: 560,133 → 623,411 bytes (+63,278,11.30%). These are serialized bytes, not token/billing estimates. Default Author admission is the blocker, independent of provider transport. Alpha-only repair is unchanged. See `HELPER-CONTEXT-AUDIT.md` for every alternative request and stage size.

Prepare profiling completed with concurrent acceptance workload, so no CPU/wall speed claim. First LastPrism encounter allocated1,236,617,240→2,514,980,576 managed bytes (+103.38%). Warm mean393,620,348→397,469,368 (+0.98%). These are cumulative allocations, not resident RAM. This cold allocation increase is another readiness blocker. See `HELPER-PROFILE.md`. Fixed-roster first encounter is not independently cold per item; no gameplay loop/GPU/model is measured.

## Further options, not implemented

1. Keep this unpublished extraction checkpoint while redesigning the bounded parent-evidence contract.
2. Existing-style exact native-source sharing may help, but the measured best short literal-pool construction reaches304,803 chars, still4,803 above the guard. Whole-dossier pooling reaches290,212 but adds345 lookup values across evidence and capability/output instructions. This has only deterministic roundtrip validation, no model-decoding validation, and should not be adopted solely to pass a budget. See `LITERAL-POOL-TRADEOFF.md`.
3. More semantic precision could come from bounded callee effect summaries that prove no identity mutation/receiver escape, with conservative fallback on virtual dispatch, alias, constructor or exception uncertainty. This might exclude unrelated shared-helper branches legitimately, instead of deleting them as presumed irrelevant. It is a separate proof-strengthening change, not a cosmetic optimization.

## Separate Calamity boundary

Actual user Drive CalamityMod2.2.4/tML2026.6.3.4 archive was parsed statically. DarkSpark → DarkSparkPrism → seven DarkSparkBeam source loop is verified from actual DLL IL, distinct from vanilla LastPrism. Archive signature is zero and official provenance unconfirmed. No Assembly.Load, mod execution or registration occurred. Exact IFC runtime packet/model-stage verification for that build remains NotRun pending per-action approval for executing the unrecognized binary. Static report: `../calamity-drive/DARK-SPARK-STATIC-AUDIT.md`.
