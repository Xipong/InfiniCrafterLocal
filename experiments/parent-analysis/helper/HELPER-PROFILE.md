# Helper-spawn Prepare profile

## Useful findings

- First LastPrism encounter in fixed13-item process: 1,236,617,240 → 2,514,980,576 managed allocated bytes (103.38% increase; +1,278,363,336).
- Repeated LastPrism captures, mean of2: 393,620,348 → 397,469,368 allocated bytes (0.98% increase).
- All39 within-build captures have stable per-item payload hashes: True. Twelve of13 item payloads are exactly identical across builds. LastPrism bytes488,950→933,294.
- Total managed allocation volume across39 calls: 26,937,299,888 → 28,223,417,224 bytes. These are cumulative managed allocations, **not peak or resident memory**.

The new sink-by-sink source closure analysis has substantial first-encounter allocation churn on this large shared helper. Exact final JSON union saves output bytes after analysis; it does not avoid repeated closure construction. Warm source-cache reuse makes the additional allocation much smaller. This is a performance risk in addition to the Author300k admission blocker; not a production-ready result.

## Measurement scope and limits

Two fresh processes ran sequentially, each with the same ordered13 vanilla items and3 Prepare calls per item. Native projectile ContentSamples were registered from actual SetDefaults. No gameplay loop, GPU, model request or Calamity binary execution occurred. Item0 encounters share any caches populated by preceding roster items; this is not an independently cold process per item. Iterations1/2 repeat the same item with the same random seed.

The restoration owner's integrated native and Python acceptance suites were running concurrently with changing load. Wall time **and process CPU** varied substantially even for unchanged paths. The observed total process-call CPU184.64→167.57 seconds is **not evidence of speedup**. Likewise the individual LastPrism CPU13.82→7.64 seconds cannot prove an improvement. A controlled repeated profiling window would be required for comparative latency. No latency claim is made.

Source extraction caching, GC and JIT remain process-local. Both builds use the same tML source module. The harness records GC.GetTotalAllocatedBytes(true), process TotalProcessorTime, wall time, payload bytes and SHA-256. No claim is made about billed tokens, game FPS or memory retained after collection.

## Reproduction and artifacts

- ProfileMagic.cs and native/ProfileMagic.dll: identical external harness.
- run_magic_profiles.py: sequential runner and exact comparison generator.
- profile-baseline.json/.log and profile-helper_final.json/.log:39 detailed observations per build.
- profile-comparison.json: build/module hashes, scope, all item comparisons and explicit overlap disclosure.
- profile-runner.log: runner output.

Run from the candidate after sourcing ../ifc-toolchain-20261105/env.sh. Use a new output root for repeated measurements to preserve this evidence. No source changes or Git operations are needed.

## Bounded optimization direction, not implemented

A shared immutable source-expression/dependency DAG per selected method could avoid rebuilding common closures for each sink. It must preserve per-site budgets, exact provenance, alternatives, unknowns, cancellation and independent site refusal. Merely sharing rendered text is insufficient if symbol/predicate side effects are dropped. Retaining a whole DAG also increases cache memory, so bounded cache scope and retained-size measurements are needed. Do not replace missing proofs with guessed child IDs or remove dynamic sites to make the benchmark smaller.
