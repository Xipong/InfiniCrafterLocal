# Verification

## What a result means

The native executable reports `passed`, `failed` or `error` (exit codes 0, 1 and 2).
A pass requires the scenario's assertions and a complete valid trace. Dependency
readiness, a successful build, an image with plausible motion or an unsupported
path that never ran is not a behavioral pass.

The wrapper records item/scenario hashes, source/build fingerprints, assembly
hashes and command receipts. The build receipt hashes actual copied runtime DLLs
and load manifests separately from configured reference inputs; modified copied
dependencies invalidate `--no-build`. Native frames carry PNG hashes and associated ticks.
Keep these together: a screenshot alone cannot establish collision, damage,
resource payment or lifecycle correctness.

The wrapper additionally rejects a zero process exit without a valid terminal
native trace, status/exit disagreements, conflicting input hashes and incomplete
passing timelines. Native result and optional review export failures are recorded
separately. New receipts hash `native.json` itself; `report` audits the archived
bytes without depending on original absolute paths. Legacy/unreceipted traces are
inspectable but unverified, and hashes establish consistency rather than authenticity.

For agent iterations use the [fast workflow](README.md#fast-agent-workflow).
`suite suites/smoke.json` runs native synthetic/vanilla controls and checks an exact
negative assertion. An expected `failed` result
stays failed in each native trace and suite row. Matrix success means the detector
matched the declared expectations; it does not certify those failed items.

## Portable utility checks

These Python tests use local fixtures/mocks and do not require game assets:

```sh
python -m toolbox workbench test
```

The agent-workflow tests exercise archived evidence portability/tampering, the
true-PNG contact-sheet receipts, strict negative
expectations, malformed/missing terminal output, timeout receipts, optional export
failures, and matrix continuation. Synthetic boundary tests are labelled as such;
they do not stand in for running the native smoke matrix.

The shared manifest includes `item_workbench_python` in the Python CI group and
`item_workbench_build` in the build group. The latter compiles this linked-source
project; it does not run Linux graphics on the Windows build worker. Missing
prerequisites are reported as `notRun`, not a passing native build.

After the native prerequisites in [README.md](README.md) are configured, run the
public synthetic smoke test there. Then run its deliberately incorrect hit
expectation against a missed target:

```sh
python tools/item-test-workbench/workbench.py run \
  --item artifacts/workbench-fixtures/synthetic-straight.json \
  --scenario tools/item-test-workbench/scenarios/negative-miss.json \
  --out artifacts/straight-negative --no-build
```

The native result should be **failed**, not passed. An expected-failure test runner
may itself succeed only because it observed that failure; it must not relabel the
item's native result.

For graphics, run the [public authored example](examples/lunar-harpoon/README.md)
with its actual PNG and the explicitly fetched dependencies. Inspect both the
native assertions and the real frame viewer. Add a fresh repeat run, an early
release, a miss, and a wall-interception scenario as appropriate to the author's
contract. Preserve failed traces when diagnosing a regression.

Specialized `verify_*.py` scripts provide additional scenario matrices. Inspect
`--help` and their fixture requirements before running: some use repository test
corpora or explicit local inputs beyond the minimal public example. They are not
unconditional installation checks or proof of all-item parity.

## Evidence reviewed during development

Agent-workflow verification before removal of run comparison (2026-10-25): the
native smoke exercised passing controls and an exact `dummy_damaged` negative
failure. Two `client-vfx-captured` runs each passed and produced 80 native PNGs.
A 12-frame contact sheet was exported and visually inspected; this run is
VFX-only, not player/item/world artwork coverage. Copied archives audited as
verified. The then-current portable workbench tests, 94 toolbox tests and affected
owner checks (Python + native build) passed. The current smoke has five cases;
run comparison and its duplicate smoke case have been removed.

These native runs used the documented tML v2026.08.3.0 references and .NET SDK
8.0.408. This development container has mismatched process/procfs PID namespaces;
a local-only `open64` shim mapped current-process `/proc/<pid>/...` reads to
`/proc/self/...` so .NET/MonoMod could inspect their own process. No CLR, game DLL,
gameplay or workbench source was patched for that workaround, and it is not bundled
or required on ordinary hosts. Native assets, binaries and run outputs remain
external to repository source.

Local runs exercised native use/projectile collision and expiry; charge/release;
return; full player regeneration and buff clocks; bounded equipment and ammo;
client contact; original artwork/VFX/player/dummy/dust drawing; deterministic
repeats; and intentional invalid-input/missing-asset/incorrect-assertion controls.
The isolated Linux graphics setup produced real FNA/OpenGL software-rendered
frames. Native methods—not replay code—produced the gameplay trajectories.

These are **historical local development observations**, not a public CI guarantee,
a benchmark of every item, or an estimate of the percentage of bugs caught. This
checkout's linked production code and your installed assembly versions can change
results. Re-run the relevant checks and retain the new receipts. Repository CI's
existing mod/native tests do not automatically imply that this optional GPU
workbench and every scenario ran.

## Interpret states carefully

- Native regeneration can erase the final net mana loss. Check actual debit events
  and post-use ticks rather than inferring price from the last snapshot.
- Expiry requires that an effect appeared and then ended; an effect that never ran
  is a different outcome.
- Inactive projectile state does not prove owner arrival. Inspect the native kill
  event, position, lifetime and recorded arrival predicate.
- A target's collision rectangle is not its artwork rectangle. The native training
  dummy is immortal and tile-rendered; the simpler fixture target is explicitly
  modified for testing.
- With native dust enabled, capture-disabled runs still execute the same original
  render lifecycle and omit PNG export only. Compare update/draw side effects and
  RNG, not just PNG counts.
- Real pixels can establish visible pose/grip/direction only for loaded assets and
  executed passes. Read [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md) before extending that
  conclusion to other appearances, worlds, shaders or multiplayer.
