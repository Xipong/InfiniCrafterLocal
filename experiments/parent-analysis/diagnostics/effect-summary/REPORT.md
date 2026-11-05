# Bounded effect-summary experiment: Last Prism

## Decision

Do not treat the remaining Last Prism uncertainty as proved false. A conservative, generalized call-effect summary is useful for ordinary helpers, but it does **not** safely remove the actual AI_075 blockers. The isolated implementation produces exactly the same 933,294-byte LastPrism packet and still fails default Author admission at **325,379 > 300,000 characters**. Raising a summary bound or labeling source factories as pure does not establish the missing proof.

No frozen candidate file or Git object was changed. The experiment is in this directory; `repo/` contains copied native sources only. 425 original C# file hashes were compared before/after and are unchanged. The experimental native build has 422 compiled sources, including one experimental summary file; this is not the frozen 421-source build.

## Exact native cause

All offsets below are standard IL offsets, not the earlier text decoder's +12-byte offsets.

1. Captured type633/style75 proves four initial AI_075 selectors at IL54, 1219, 2542 and 4659. Their selected successor edges eliminate earlier identities.
2. First still-reachable hazard is **IL5504: GetProjectileSource_FromThis(this)**. The method calls Entity.GetSource_FromThis at its IL2. That method constructs EntitySource_Parent(this, context) and returns it.
3. EntitySource_Parent's constructor **stores the original Entity reference in its backing field at IL8**. This is an actual returned alias container, not merely a property getter with unknown implementation.
4. The caller passes that source to scalar NewProjectile at AI_075 IL5571. Its 1,860-byte managed body calls **ProjectileLoader.OnSpawn(projectile, source) at IL1808**. A wrapper-aware interprocedural analysis must follow the contained parent reference through this callback boundary. Certifying only the factory's direct writes would miss this escape.
5. A separate conditional path calls **Kill(this) at AI_075 IL5598**, then rejoins the next type read at IL5604. Kill is 161,228 IL bytes and calls **ProjectileLoader.PreKill(this, ...) at IL110** and **ProjectileLoader.OnKill(this, ...) at IL161215**. The selected source does not prove that these callbacks preserve the actor identity. A larger budget cannot manufacture such a guarantee.
6. Therefore later sibling guards, including guarded candidate601, cannot simply be discarded. This does not prove they execute for ordinary LastPrism gameplay; it establishes that this source-only proof cannot exclude them. Actual child632 remains proved and delivered.

Evidence: `baseline-hazards.txt`, `native-factory-ctor-il.txt`, `callback-boundaries.txt`; full Kill source listing is `native-factory-kill-il.txt`. Native source module MVID is 033e87cd-cefe-4dc6-a1fb-e14aa938bbb2.

## What the prototype proves and refuses

`ClosedEffectSummary.cs` is a deliberately conservative structural proof over managed IL. It is generalized and has no item/projectile-ID whitelist. It proves a stronger, input-independent property than necessary: every possible reference argument and alias is prevented from escaping, and no Projectile.type/aiStyle field is written or address-exposed anywhere in the closed call graph. It does not attempt to guess exact aliases.

- Safe scalar reads and nonidentity field writes, local aliases, conditional alias joins, exact managed helper calls, and reference-free value construction can pass.
- Any identity-field write/address, including through a global/other-object alias, refuses the proof. The original source observation remains available.
- Reference field stores, reference/byref returns, array/indirect stores, pointer operations, unsupported opcodes and ref/out calls refuse. Returning a fresh nonalias reference also conservatively refuses; this prototype has no ownership/heap-return model.
- Constructor bodies and relevant type initializers are inspected. A constructor storing the actor into its result refuses. A constructor reading an actor scalar into a numeric field can pass.
- Actual callvirt dispatch is accepted only when nonvirtual, final or sealed. An exact `call` to a declared body differs from open virtual invocation; the tests cover this distinction.
- Exception regions and recursion refuse rather than assuming a normal-only path or treating an in-progress recursive summary as pure.
- Bounds: 4,096 bytes per method, depth8, 64 methods and 10,000 decoded instructions. Unknown/missing body, open generic, exhausted bound or inspection error yields no certificate, never a safe summary.
- Within a source scan, summaries are memoized by method and invocation opcode. Negative summaries retain the original hazard. No source observation or reliable literal is truncated.

This is a source-code experiment, not a whole-runtime guarantee against concurrent mutation, runtime detours or arbitrary code replacement. The existing captured-source scope remains necessary. Passing a finite test suite is not a formal proof of the implementation's completeness.

The experimental integration adds this proof only after a call actually may receive the actor and the existing narrow Entity accessor proof did not already suffice. It does not replace or weaken the existing direct-write and escape checks.

## Verification

- Standalone focused summary suite: **39 checks passed**. Includes direct and conditional aliases, global alias writes, type/aiStyle writes, reference returns, wrapper constructor escape, scalar-only constructor, open/final dispatch, cctor mutation, ref/out/local address, indirect/array escape, recursion, catch/finally and all four bounds. Entity.Center getter/setter pass; real source factory and Kill refuse.
- Experimental native compilation: **422 sources passed**, two existing CS1701 framework-reference warnings.
- Existing helper-spawn checks: **4/4 passed**.
- Existing identity receiver/mutation check: **1/1 passed**.
- Actual headless MagicAudit capture: no native defaults mismatches; independent LastPrism AI oracle again sees six child632 spawn requests, no error.
- Exact old/new packet byte equality, parsed equality, child632 retention, conditional601 retention and original-source hash preservation: **5/5 checks passed**.
- Default, unpatched Author request builder rerun with the experimental LastPrism and original NebulaArcanum: **expected budget failure reproduced**, 325,379 characters versus300,000. No HTTP request or model inference took place.

An initial combined test filter using `|` selected nothing because the harness accepts a literal substring; it was replaced by separate valid filters. The first Python attempt lacked pytest; the existing verify-venv then ran the real Author builder to its budget failure. Neither setup failure is counted as a behavior pass.

A full native suite, MSBuild/mod packaging, GPU/gameplay loop, multiplayer and model generation were **not run** for this experimental build. No Calamity binary was loaded.

## Size and latency

Packet before/after: **933,294 / 933,294 UTF-8 bytes, delta0**. Both SHA-256 values are `10013c6fe9eff33978e6feed1094a0e63df8039f12dcf248bac3e552940caed3`. No model-facing format was changed. Thus this route supplies no relief to the default Author budget.

One baseline process and one summary process each captured LastPrism three times, with sample registration performed before timing:

- Cold first Prepare: baseline9.1524s, summary9.2388s; observed delta+0.0863s (+0.94%). CPU11.53s/11.56s. Allocation2,618,305,968/2,619,325,912 bytes, +1,019,944 (+0.039%).
- Warm repetitions: baseline1.3417s/1.1519s, summary4.8564s/2.4991s. This environment was noisy; a one-process comparison cannot isolate a causal warm latency regression. Warm allocations were effectively unchanged at ~397.47MB.
- Standalone warm Entity.Center summary,100 repetitions: median0.0472ms, p950.1155ms, max0.2463ms.

These are measured observations, not a statistically established speedup or regression. The straightforward conclusion is **no measured size improvement and no demonstrated performance benefit** for LastPrism.

## Requirements before any production proposal

1. Preserve the existing unknown outcome at real escapes and callbacks. Do not whitelist GetProjectileSource_FromThis, Kill or any item identity.
2. A richer summary would need separate effects for identity mutation, direct escape, return-alias and contained-return-alias, plus heap/container reachability and invalidation when an alias reaches an unknown call. Return-alias is not the same as harmless return.
3. Open virtual/delegate/native/hook targets require a genuinely closed, certified target set, including the relevant configuration epoch. Source MVID alone cannot certify a mutable loaded hook registry. Otherwise retain unknown.
4. Positive proof receipts must include every transitive dependency's identity/body certificate, applicable dispatch assumptions, algorithm version and bounded-work outcome. The experimental integration does not yet publish these receipts and must not be adopted as production merely because tests pass.
5. Production implementation also needs request cancellation, bounded lifetime of caches, reviewed exception semantics or explicit refusal, and adversarial tests against alias/container flow. Recursion may remain a safe refusal; an optimistic provisional cache entry must never prove purity.
6. Since native callback boundaries remain, use a separately reviewed, lossless presentation/transport strategy for the current budget problem. Deleting guarded601 or raising the limit is a different product/contract choice, not an effect-summary result.

## Artifacts and reproduction

- `ClosedEffectSummary.cs`, `EffectSummaryTests.cs`, `summary-tests.json/.log`: isolated implementation and focused tests.
- `repo/ModSources/.../GeneratorClient.AttackIdentitySelection.cs`: copied integration only; original frozen path untouched.
- `native-build.log`, `helper-checks.log`, `identity-checks.log`: native build/check evidence.
- `capture-summary/LastPrism.packet.json`, `packet-comparison.json`: actual exact packet comparison.
- `author-default-with-deps.log`: rerun default budget refusal.
- `profile-baseline.json`, `profile-summary.json`, `latency-comparison.json`: exact raw timing/allocation samples.
- `frozen-native-hashes-before.json`: original native source hashes verified afterward.

Run standalone tests after `source ../ifc-toolchain-20261105/env.sh` with `dotnet EffectSummaryTests.dll summary-tests-rerun.json`. Rebuild using `dotnet "$DOTNET_ROOT/sdk/8.0.427/Roslyn/bincore/csc.dll" @tests.rsp`. Native build uses `../ifc-toolchain-20261105/compile-native.py` with the isolated `repo` and a fresh output path. The default Author reproduction uses the existing `ifc_recovery/verify-venv/bin/python` and the original offline capture harness; its expected exit is1 with the size error.
