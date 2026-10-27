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

Native geometry/ribbon extension (2026-10-27): Wooden Sword and a second native
item outside the previous control set loaded exact pinned PNGs and recorded real
hits. Missing, wrong-length, byte-tampered and symlinked item PNGs were refused by
the native loader. The complete source index contains 5414 item PNGs; source facts
are embedded in the checked executable and included in build freshness checks.
The unchanged archived contact weapon previously refused for `historyRibbon`
recorded one item-body and one projectile hit, 1064 original native ribbon segments
and 90 native PNGs in the explicit procedural VFX-only scene. The original native
SpriteBatch submissions were observed and a recorded frame visually inspected.
No authored image was substituted. Reusable history controls cover full native
PreDraw, stationary samples, capture-disabled GPU execution, repeat gameplay/pixels,
and missing draw-context/resources. Authored/player artwork remains unrendered in
procedural-only mode; full-game parity remains unclaimed.
The final native executable passed 70 existing native regression checks and all
27 history-ribbon checks, including the unchanged archived item. The affected
owner checks passed: C# build, 104 offline workbench tests and 8 executable CI
workflow tests; the 9 public CLI tests and all shared static gates also passed.

Real-item probe usability verification (2026-10-27): 20 archived IFC items and 8
vanilla identities were exercised in 55 native process runs. The default primary
probe admitted 12/20 IFC inputs, but five of those recorded zero shots without
ammo; seven recorded shots. Explicit ammunition, equip input, client contact and
world placement settings admitted a scenario for 19/20 definitions. Two archived
diagnostic JSONs required their existing clean delivery files; neither fresh nor
local-cache readers accepted the extra `runtimeContract` metadata. Source item
bytes remained unchanged. One contact weapon remained refused because its VFX
renderer was outside client admission. Seven vanilla identities recorded hits;
Wooden Sword remained refused by the native geometry PNG allowlist. A held native
Daedalus Stormbow control recorded 16 arrows and two hits after a single volley
missed the narrow target. These are scenario observations, not full-artwork/VFX
or whole-item certification. Probe results now retain authored names, source paths
and native activity aggregates, including successful finite-state probes with no shots.

Probe CLI verification (2026-10-27): 101 offline workbench tests, 9 public-entry
tests and 8 executable CI workflow regression tests passed, along with the
workbench build against the documented references. The isolated CI fixture copies
the probe parser's actual frontend dependencies before checking doctor/build status.
Actual native runs through `probe` exercised primary/alternate held input, charge
and release, explicit clicks at ticks 0/30/60/90, bullet consumption, vanilla and
saved-cache inputs. Exact negative assertions stayed failed; unexpected failures
returned a nonzero matrix result, and a rejected item did not stop the next healthy
case. Prepared suites also passed relocation and byte-preservation checks. Native
execution used the container-specific `/proc` workaround described below; no game
DLL or gameplay code was changed. These checks cover the probe wrapper and its
selected native scenarios, not a launched Terraria client or additional mod autoload.

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

### Synthetic material / scene controls

```sh
python tools/item-test-workbench/verify_materials.py --out artifacts/material-controls
```

This generates explicitly synthetic native fixture JSON and two colored control
PNGs locally, then executes the original material-path renderer. It checks path
history/retirement, native light bounds for a distant camera, and missing/tampered
publication and invalid lighting-mode refusals. A synthetic VFX-off control must
produce identical native gameplay snapshots; both original PNG sets are hash-checked
and the VFX-on frames must contain actual RGB differences. This verifies visible
material output in that controlled scene, not authored visual quality. No captured user
item or game PNG is bundled. `--native-dll PATH --no-build` accepts an independently built
native executable and records its hash; it does not claim a wrapper build receipt.

Native client consumable-depletion cases additionally require the pinned original
community `Images/Item_0.png`, provisioned by `fetch_player_assets.py` (20 core
PNGs, plus two optional dummy PNGs). This initializes native PlayerFrame after the
last item is consumed. The genuine repository GeneratedProjectile.png is loaded
for Main.LoadProjectile; authored item art is never replaced with that proxy.

### Lifecycle, world, equipment and input controls

Run each verifier into a fresh directory:

```sh
python tools/item-test-workbench/verify_lifecycle.py --out artifacts/lifecycle
python tools/item-test-workbench/verify_world.py --out artifacts/world
python tools/item-test-workbench/verify_placed_render.py --out artifacts/placed-render
python tools/item-test-workbench/verify_equipment_reactions.py --out artifacts/equipment-reactions
python tools/item-test-workbench/verify_equipment_render.py --item /path/to/equipment.json --artwork /path/to/item.png /path/to/overlay.png --player-assets /path/to/player-assets --out artifacts/equipment-render
python tools/item-test-workbench/verify_controls.py --out artifacts/controls
```

These execute original native gameplay/draw paths and explicit negative controls.
World removal via `break_tile` is native `WorldGen.KillTile`, not a claim that the
player mined the object; the separate mining scenario executes native player item
use. Returned generated items are compared with the complete source network
serialization, not merely name/ID/count. Placed rendering invokes the production
ledger renderer against a neutral background; it is not the complete terrain pass.
Equipment reactions use native hurt/death, and movement controls set only native
input flags before `Player.Update`. Draw calls alone do not establish visibility:
inspect output pixels and paired functional/vanity/unequipped scenes separately.

For an independently built executable, pass `--no-build --native-dll PATH` where
supported. Its exact binary hash is evidence, but not proof that the normal
MSBuild/wrapper path passed. Preserve failed controls and environment errors as
such; do not relabel unsupported or unexecuted paths as generic success.

### Quality/performance extension acceptance

Local extension checks (independent direct official Roslyn build; retain the
source/reference receipt, not a normal MSBuild-provenance claim):

- 87 offline workbench Python tests passed, including explicit facing/aim,
  input hold/release, non-authoritative frame-arm metrics, exact parent identity,
  shared scenario/loadout/RNG admission, repeated input, and asset manifest controls.
- All 59 existing native scenario/negative regression checks passed using
  `verify_native.py --no-build --native-dll PATH`.
- `verify_quality.py` passed original placement positives, intentional assertion
  negative and missing-PNG refusal, plus seven quality checks. Its neutral sparse
  base has zero minimum gap but an 18px median gap and only 6/42 contact columns.
  Original `Item.UpdateItem` moves the returned instance and settles its collider
  on the configured floor. The fixture never grants visual approval.
- Native vanilla contact, ammo and empty-ammo controls executed. Matched
  single-use and repeated-use parent comparisons execute the same client update
  phases with the seed reset after setup; actual use clocks, not damage formulas,
  measure cadence. A supplied single-use window is not sustained DPS.
- Private immutable original-art cases were inspected across actual observed
  facings, native movement/jump and explicit inverted-gravity buff scenes;
  root held / held projectile / equipment / placed / dropped observations remain
  separate. No private inputs or output artifacts are committed.

Useful commands:

```sh
python tools/item-test-workbench/workbench.py test
python tools/item-test-workbench/verify_native.py --no-build --native-dll /absolute/ItemTestWorkbench.dll --out /private/regressions
python tools/item-test-workbench/verify_quality.py --native-dll /absolute/ItemTestWorkbench.dll --out /private/quality
```

The old ordinary local MSBuild path remains blocked by NuGet migration mutex
initialization in this environment; GitHub exact-head build CI is recorded on
the draft PR. Optional JavaScript replay checks were not run here because `jsdom`
is unavailable (their code is unchanged). Live packaged-game self-test, complete
terrain/world renderer, multiplayer, audio output and pickup popup/font UI remain
notRun, not implied by native or CI success. Dropped frames are sampled before
that tick's world update; world snapshots are after it and must not be mistaken
for identical pose samples. Numeric observations and negative controls passing
never imply that an authored item looks good or is well balanced.


Requested vanilla controls add four passing native pose cases (Minishark/Musket,
both actual observed facings): original vanilla DrawData, no generated replacement
or veto, PNG integrity and immutable binary. The supplied actual item-control
matrix measured held and repeated-input trials separately; requested controls
never rewrite or masquerade as recipe parents. Native bullet simulation is
measured, while vanilla bullet sprite rendering remains explicitly notRun in
pose views. One seed/layout/window is not a universal balance recommendation.


### Vanilla bow/projectile extension

`verify_vanilla_projectiles.py` is the executable acceptance matrix for the opt-in
native sprite pass. It retains native cases, exact PNG hashes, ammo source IDs,
hit callbacks and expected failures; `--gif` also exports the recorded bow frames.
Its named no-ammo case must remain native `failed` with exactly the requested
projectile/hit failures, while the verifier accepts that detector outcome.
Capture-disabled/no-dust execution must still render and match the captured
control's native gameplay. Off-camera attempts must not count as submitted sprites.
Missing/corrupt PNGs and unsupported projectile types remain errors.

Offline synthetic checks additionally cover optional projectile-resource download,
verified reuse, corruption before any write, manifest/path refusals, and GIF
playback duration over 121 native ticks at several strides. They do not replace
the native matrix or human inspection of the captured PNGs. Current source and
installed tML changes require rerunning the affected cases; prior development
numbers above remain historical. The new lane initializes native Gore allocation,
not Gore update/rendering or full world parity.
