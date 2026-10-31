# Item Test Workbench

## Standalone native loader

`loader-run` is the new CPU path for native tModLoader autoload from separate
DLLs. It needs no `.tmod` packaging, installation, game client or saved world:

```bash
python tools/item-test-workbench/workbench.py loader-run \
  --item /path/to/item.json --scenario /path/to/scenario.json --out /path/to/run
```

The first invocation builds the host and a separate production
`InfiniCrafterLocal.dll` from the real mod sources. Later invocations can use
`--no-build` while their build receipt remains valid. The usual reference DLL
environment described below is required. Native metadata is held in memory;
no archive is written. The process autoloads tML's built-in content and IFC,
builds native hook tables and uses actual Player/NPC/Projectile updates with
SystemLoader phases. It does not enumerate IFC gameplay handlers by name.
The wrapper records the effective production metadata/assets in `receipt.json`,
including an `INFINI_MOD_SOURCE_ROOT` override, and refuses evidence if those
inputs change during the run.

For a registered item use `--native-item WoodenBoomerang`, a native ID, or
`--native-item ModName/ItemName` instead of generated JSON. An additional mod
can be autoloaded from its separately built DLL using `--probe-dll PATH` and
`--probe-mod-root PATH` (directory containing its build.txt, localization and
assets). Its declared dependencies, including weak references, must be loaded;
unavailable ones are refused because this host does not emulate tML's separate
mod assembly contexts and weak-dependency type filtering.
For a native mod NPC set `dummy.nativeType` to its exact `ModName/NpcName`.

This path currently supports CPU scenes with aim/primary/alt/release, a bounded
tile layout, a controlled vanilla target or a mod NPC with its native defaults
and AI, plus the explicitly admitted assertions. Generated JSON must match the
scenario `worldId`; it is not rewritten. Reports disclose skipped world,
dust, gore, dropped-item and time phases and missing IFC mod dependencies.
ParticleLibrary/Luminance DLL references are present, but their complete mod
content and VFX lifecycle are not loaded by this path. This is not complete
game/client, arbitrary dependency graph, melee geometry or visual parity.
Unsupported scenario features fail explicitly; they do not fall back to the
older runner. The existing `run` and rendering tools retain their earlier scope.

`verify_native_loader.py` checks autoload and a missing-dependency control.
`verify_loader_scene.py` checks real combat and effects plus independent hooks
from `fixture-mod/WorkbenchObserverFixture.Standalone.csproj`. These are
standalone child processes, without launching `Terraria.Main` or a server.

A separate local utility for exercising an **already generated InfiniCrafterLocal
item JSON**, then inspecting its behavior with code and vision. Runs do not call an
LLM or image API. The C# project links the mod sources from this checkout and uses
actual installed Terraria/tModLoader assemblies—not a Python or JavaScript physics
port. It does not modify the mod's gameplay implementation.

This is a controlled test scene, **not a complete Terraria client/world emulator**.
A passing scenario certifies only its assertions and admitted execution paths.
See [support boundaries](SUPPORT_MATRIX.md) and [verification](VERIFICATION.md).

## Prerequisites

Run commands below from the repository root.

- Python 3.11+; Pillow for native PNG inspection/GIF export. CairoSVG is additionally
  needed for rasterizing the schematic SVG replay. The authored demo also uses the
  existing [LocalGenerator dependencies](../../LocalGenerator/requirements.txt).
- [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0).
- Matching [official tModLoader assemblies](https://github.com/tModLoader/tModLoader/releases)
  and their managed dependencies. Local development exercised tML `v2026.08.3.0`
  (Terraria 1.4.4.9); a different release requires revalidation.
- ParticleLibrary and Luminance reference DLLs, using the layout below. The existing
  [repository CI setup](../../.github/workflows/ci.yml) documents dependency download
  and tModLoader reference discovery after restoring the mod project. Use reputable
  upstream releases, not an arbitrary assembly pack. VFX asset setup additionally
  requires the exact ParticleLibrary DLL hash recorded in its manifest.

Set these to your own existing dependency directories:

```sh
export INFINI_TML_REFERENCE_DIR="/path/to/tml/references"
export INFINI_TML_DEPS_SRC="/path/to/mod-dependencies"
```

Expected files:

```text
$INFINI_TML_REFERENCE_DIR/tModLoader.dll
$INFINI_TML_REFERENCE_DIR/<other managed reference DLLs>
$INFINI_TML_DEPS_SRC/ParticleLibrary/ParticleLibrary.dll
$INFINI_TML_DEPS_SRC/Luminance/bin/Debug/net8.0/Luminance.dll
```

`DOTNET` can select a particular `dotnet` executable. `doctor` checks these basic
prerequisites; it is **not** a graphics initialization or native execution test.

```sh
python tools/item-test-workbench/workbench.py doctor
python tools/item-test-workbench/workbench.py build
```

## Fast agent workflow

For your own item, start with `probe`. It prepares the scene and suite and invokes
the existing native runner; no helper Python script or handwritten manifest is needed.

```sh
# One item, one click, full native Player.Update, compact reports.
python -m toolbox workbench probe --item /path/item.json
# Several items × explicit inputs. Shell globs expand into separate inputs.
python -m toolbox workbench probe --item /path/items/*.json --input primary alt \
  --out artifacts/my-probes
# Hold alternate for 90 ticks, release, observe until tick 179.
python -m toolbox workbench probe --item /path/item.json --input alt --hold 90 \
  --assert '{"kind":"entity_spawn_count","entityId":"my_projectile","value":1}'
# Repeated clicks every 30 ticks, with a real release after each press.
python -m toolbox workbench probe --item /path/item.json --repeat 30 \
  --assert dummy_damaged --set dummy.x=840 --set tiles.0.tileY=44
# Inspect the exact matrix/scenarios without an SDK, building, running or writing.
python -m toolbox workbench probe --item /path/item.json --input primary alt --plan
# Prepare a portable suite, including byte-identical item copies, entirely offline.
python -m toolbox workbench probe --item /path/item.json --prepare --out artifacts/prepared
python -m toolbox workbench suite artifacts/prepared/suite.json --out artifacts/prepared-runs
```

The default [probe scene](scenarios/probe.json) is a controlled floor and target,
180 ticks, seed 1, full player loop, one primary press at tick 0 and release at tick 1.
Its **only default assertion is `no_nonfinite`**. Exit 0 alone does not demonstrate
damage, successful input, correct mechanics or visuals. Add `--assert KIND` or
`--assert '{"kind":..., ...}'` for the behavior you intend to verify. Assertions and
native admission are still owned by C#, including unknown-kind/field refusals.

`--input primary alt idle equip` selects an explicit item × input matrix; an
unsupported binding remains an error. `--hold N` changes the press-to-release
interval; `--repeat N` sets the interval between presses. Repeat must exceed hold,
every release must fit inside `--ticks`, and the native 256-action/128-case limits
are checked before execution. No per-tick alternate-input script is required.
Use `--start`, `--ticks` and `--seed` to control timing and reproducibility.

`--set dotted.path=JSON` edits the scene, including array indices, without touching
the item. For example, supply ammunition explicitly with
`--set 'inventory=[{"slot":54,"itemId":97,"stack":100}]'`, or use
`--mode client_hybrid` for admitted client contact. `--mode client_vfx` requires
explicit `--set 'nativeRender={...}'` settings and the existing graphics/assets
setup. `--action '{"kind":"aim","tick":0,"x":850,"y":700}'` appends a native
action; same-tick additions follow generated press/release actions in supplied
order. Missing intermediate objects must be set as objects first. The item is
never rewritten to remove VFX or bypass native admission, and ammo, assertions,
mechanics and retries in another mode are never inferred from item names.

Explicit negative controls use the same exact suite expectation contract, e.g.
`--assert dummy_damaged --expect '{"status":"failed","failedAssertions":["dummy_damaged"]}'`.
The expectation applies to every selected case. A crash or an extra failed assertion
cannot satisfy it. Use separate commands or an explicit suite for differing expectations.

Without `--out`, execution/preparation chooses a fresh timestamped directory under
`artifacts/workbench`. It contains `suite.json`, `probe-plan.json`, `inputs/` and,
after execution, `probe-result.json`, `runs/summary.json` and each case's native trace
and agent report. The probe result includes original item paths and authored display
names, so a batch of files all named `item.json` remains distinguishable. Case
`observations` include native spawn/use/ammo event counts, separate projectile and
item-body hit/damage totals and resource endpoints. Zero recorded shots stay zero
even when the selected finite-state assertion passes; supply ammo and assert the
behavior you actually want to check.
The emitted manifest uses relative paths and survives moving the prepared directory.
Run all cases with one build; failures do not stop later cases. `--no-build` retains
the existing stale-build refusal. `--prepare` means **native notRun**, while `--plan`
is read-only and creates no directory. These conveniences use the existing isolated
native host; the separate tModLoader-process prototype has its own launcher.

All commands also work through `python -m toolbox workbench`. `catalog`, `report`
and `suite --plan` are offline/read-only unless an explicit report output
is requested. They need no game install, SDK or API credentials.

```sh
# Discover actual supplied scenarios and their complete assertion requests.
python -m toolbox workbench catalog
# Validate/list the portable native smoke matrix without building or writing.
python -m toolbox workbench suite tools/item-test-workbench/suites/smoke.json \
  --out artifacts/smoke --plan
# Build once, write synthetic fixtures through C#, run the controls.
python -m toolbox workbench suite tools/item-test-workbench/suites/smoke.json \
  --out artifacts/smoke
# Read compact results without dumping thousands of snapshots.
python -m toolbox workbench report artifacts/smoke/straight
```

Each `run` now writes `agent-report.json` and `agent-report.md` alongside the raw
inputs, `native.json`, `run.json` and process logs. Inspect `nativeStatus`, failed
assertion **requests**, `integrity`, coverage, first event ticks and failure context.
Final assertions do not identify a causal tick: only explicit native invariant
evidence sets `observedFailureTick`; otherwise context points to the last tick or
an assertion's requested tick. No event or cause is invented from the artwork.

`run.json` separately records `nativeExitCode`, `nativeStatus`, wrapper `exitCode`
and review export status. Exit 0 without a valid terminal trace is refused. Missing
frames or failed optional exports preserve the native outcome and logs but return
wrapper error 2. `--timeout 180` bounds native execution (allowed 1..3600 seconds).
`--review none` omits replay export for batch work; it **does not** disable native
rendering/capture requested by the scenario. `--review native` exports the exact PNG
viewer directly; `--gif-stride` applies to that viewer's GIF. Default review remains
`schematic`; `--png` selects schematic rasterization, not original game pixels.

For an authored graphics run, export a bounded, labelled vision contact sheet:

```sh
python -m toolbox workbench report artifacts/my-run \
  --out artifacts/my-run/agent-review --contact-sheet
```

`vision.png` contains at most 12 recorded native frames, prioritizing start/end,
first events, observed transitions and available neighboring ticks. `vision.json`
records original frame hashes/ticks. Only thumbnail scaling and labels are added;
no schematic substitution or intermediate animation is generated. Use the complete
`native-review` viewer/raw PNGs for omitted ticks. Visual approval remains a task
for the reviewing agent, never a conclusion of a hash check.

### Saved-run audit

Reports validate native trace structure, archived input/trace hashes, process status
and any recorded PNGs. The original checkout, original source paths and installed
game are not required to inspect a copied run directory. `verified` means internal
archive consistency, **not authentication, current source freshness or visual/game
approval**. Old/direct traces without all receipts remain `unverified`; changed or
inconsistent evidence is `invalid`. Missing current source/dependency installations
do not invalidate a portable archive. `--no-build` still checks the current build
before executing.

| Command | Exit 0 | Exit 1 | Exit 2 |
|---|---|---|---|
| `run` | Native assertions passed, requested evidence exported | Native assertions failed | Refusal, timeout, bad evidence or export error; inspect separate native status |
| `report` | Read/export succeeded; inspect `nativeStatus` and `integrity` | — | Invalid evidence or command/export error |
| `suite` | Every explicit expectation matched | At least one mismatch | Setup/manifest error |

### Your own scenario matrix

Use the checked-in [smoke suite](suites/smoke.json) as the manifest format. Paths
resolve relative to that **manifest**, independently of the caller's working
directory. A case has a unique safe `name`, exactly one `item` path, `vanillaItem`
name/ID string or `fixture` filename, a `scenario` path, and explicit `expect`.
Optional `itemBoundary`, `review`, and `timeout` select existing owner behavior.
All cases are planned before execution, built once and run in
separate processes; failed cases do not stop later controls. Summary checkpoints
retain `passed: false` until the entire matrix finishes.

```json
{
  "schemaVersion": 1,
  "cases": [
    {"name": "primary", "item": "item.json", "scenario": "primary.json", "expect": {"status": "passed"}},
    {"name": "miss-detector", "item": "item.json", "scenario": "miss.json", "expect": {"status": "failed", "failedAssertions": ["dummy_damaged"]}}
  ]
}
```

An expected failure must match the **exact multiset** of failed native assertion
names; an additional nonfinite failure or a process crash cannot satisfy a miss
control. Expected refusals use `{"status":"error","errorContains":"specific native reason"}`.
Their process status, valid trace, archive and error substring must all agree.
Suite success certifies the detector expectations, not health of negative items.
The five-case smoke is bounded infrastructure coverage, not all-item certification;
the specialized `verify_*.py` matrices remain available for their wider scenarios.

## First run: no generated artwork required

This exports explicitly synthetic fixtures using the native executable, then runs
one through actual item use, projectile update, collision and lifetime code:

```sh
python -m toolbox workbench fixtures --out artifacts/workbench-fixtures --no-build
python tools/item-test-workbench/workbench.py run \
  --item artifacts/workbench-fixtures/synthetic-straight.json \
  --scenario tools/item-test-workbench/scenarios/primary.json \
  --out artifacts/straight-run --no-build
python tools/item-test-workbench/workbench.py inspect artifacts/straight-run/native.json --summary
```

Use a **new output directory** for each run. `--no-build` requires matching recorded
build provenance; it is not permission to execute a stale binary after source edits.
To test your own item, replace `--item` and choose assertions appropriate to its
contract. Saved cache JSON uses `--item-boundary local_cache`, which invokes the
production cache reader and records its normalization receipt. It does not rewrite
the input file. A supported vanilla control can instead use
`--vanilla-item WoodenBoomerang` with `scenarios/full-vanilla.json`.

The C# CLI is also available directly:

```sh
dotnet tools/item-test-workbench/bin/Release/net8.0/ItemTestWorkbench.dll \
  --item /path/to/item.json --scenario /path/to/scenario.json \
  --output artifacts/direct-run/native.json
```

The Python wrapper adds source/dependency/input hashes and output-directory checks;
prefer it for reproducible evidence. Native exit codes: **0 passed, 1 assertion
failure, 2 error/refusal**. Missing dependencies or unsupported behavior are not PASS.

## Execution modes

Set `playerUpdate` in the scenario; see existing `scenarios/*.json` for action and
assertion syntax. Unknown commands and unsupported requested paths fail closed.

| Mode | Actual execution | Important boundary |
|---|---|---|
| `item_check` (default) | `Player.ItemCheck`, registered generated types, native projectile/NPC updates | Not the full player movement/buff/equipment loop |
| `full` | Original `Player.Update`, native physics, regeneration and supported ModPlayer/equipment clocks | Controlled world and target; no GPU rendering |
| `client` | Client player/use-style/item contact with a real loaded proxy texture | Restricted pure generated item-body contact |
| `client_hybrid` | Client player/projectile/scheduler, supported contact and child effects | Restricted no-authored-VFX combinations |
| `client_vfx` | Client combat plus original supported VFX update/draw paths | Requires real graphics/dependency resources; optional artwork/player/dummy modes below |

A full-player scene needs an explicit floor in `tiles`; otherwise the player really
falls. Ordinary fixture targets intentionally override NPC geometry/AI. The separate
`dummy.mode: "native_training_dummy"` uses genuine tile placement, tile entity and
NPC defaults instead. It requires the explicit player/artwork mode and dummy assets.

## Actual pixels versus schematic replay

`render`, `frame` and the run's `review/replay.html` visualize recorded positions and
collision boxes. They are **schematic telemetry replay, not game rendering**.

`native-review` consumes actual native-rendered PNGs and pairs each with its recorded
tick, input, events, resource state and draw provenance:

```sh
python tools/item-test-workbench/workbench.py native-review artifacts/my-run/native.json \
  --out artifacts/my-run/native-review --gif
python tools/item-test-workbench/workbench.py inspect artifacts/my-run/native.json --tick 30 --events
python tools/item-test-workbench/workbench.py timeline artifacts/my-run/native.json \
  --out artifacts/my-run/clocks.svg
```

Open the generated `native-review/native.html`. PNG hashes/dimensions and trace
completeness are validated. GIF export assembles recorded images; it does not invent
intermediate physics. `--gif-stride 2` samples only the GIF, leaving the HTML/trace
complete. Viewer charge indicators and observed-state bookmarks are telemetry, not
claims that the original game's HUD or audio was rendered.

### Native graphics and resources

The implemented offscreen graphics setup targets **Linux SDL/FNA/OpenGL**, including
software Mesa. Other platforms are not certified by this setup. Install a working
OpenGL/Mesa stack and expose the official tML native libraries and content:

```sh
export INFINI_TML_NATIVE_DIR="/path/to/tModLoader/Libraries/Native/Linux"
export INFINI_TML_CONTENT_DIR="/path/to/tModLoader/Content"
python tools/item-test-workbench/fetch_vfx_assets.py \
  --particle-dll "$INFINI_TML_DEPS_SRC/ParticleLibrary/ParticleLibrary.dll" \
  --out artifacts/dependencies/particle-assets
export INFINI_PARTICLE_ASSET_DIR="$PWD/artifacts/dependencies/particle-assets"
python tools/item-test-workbench/fetch_player_assets.py \
  --out artifacts/dependencies/player-assets --include-dummy
export INFINI_PLAYER_ASSET_DIR="$PWD/artifacts/dependencies/player-assets"
```

The VFX fetcher checks the installed DLL and downloads pinned upstream resources;
it does not replace the DLL. The player fetcher downloads 20 pinned **community
source PNGs**, or 22 with `--include-dummy`, not HD upscales. These are labelled
1.4.4.9 upstream but are not certified against official game XNB bytes. Both fetchers
verify hashes/sizes and refuse mismatches/symlinks instead of silently overwriting.
Game assets and external dependency binaries are **not bundled** with this utility.

For `client_vfx`, `nativeRender.drawArtwork: true` requires explicit
`artworkFiles`: genuine PNGs matching the item's selected publication identities.
Missing/wrong artwork is refused, not replaced by an invented sprite.
`drawPlayer: true` adds the actual starter player via original player draw layers,
loads genuine MagicPixel/PixelShader resources, and enables full projectile hooks.
Without that mode, the authored projectile draw-core path remains explicitly partial.
The inventory preview is a separate thumbnail, not a second world item.

`historyRibbon` uses the original `InfiniVfxRuntime.Draw` with the live generated
projectile's native center history and shared draw budget. Full artwork/player
mode executes it through original `GeneratedProjectile.PreDraw`. For a mechanical
or no-image item, explicitly select the procedural VFX-only path instead:

```sh
python -m toolbox workbench probe --item /path/item.json --mode client_vfx \
  --set dummy.x=840 \
  --set 'nativeRender={"drawProjectileVfx":true,"drawNativeDust":true,"cameraX":650,"cameraY":550}' \
  --assert dummy_damaged
```

This loads verified native MagicPixel/Dust/shader resources via the existing
`INFINI_PLAYER_ASSET_DIR` / `INFINI_TML_CONTENT_DIR` setup. It calls the original
under/over projectile VFX passes and detached wrapper without drawing or inventing
missing authored sprites. `drawProjectileVfx` and `drawArtwork` are separate explicit
choices; artwork mode already owns its full PreDraw. `impactRing` also requires
`drawNativeDust:true`. Active draw runs with `capture:false` too; capture selects PNG
export only. Recorded `activeProjectileVfx.historyRibbonDraws` contain actual native
history samples, submitted SpriteBatch segments and geometry. A stationary history
can correctly submit zero segments. These observations are not whole-artwork approval.

The separate current `historyTrail` renderer is admitted only for `trail.draw:
"stroke"`, `trail.source: "center"` with **`drawPlayer:true`** (and therefore
`drawArtwork:true`, exact publication PNGs and verified native player resources).
It executes the original full `GeneratedProjectile.PreDraw` and its live trail
samples. Partial authored draw-core and procedural-only scenes still refuse this
renderer; sprite/tip trail variants are not admitted by this bounded lane. No
new texture is synthesized for the stroke. `activeProjectileVfx.historyTrailDraws`
records original SpriteBatch submission counts per slot; admission alone, a
stationary zero-segment history or a PNG hash is not visual approval.

Particle resource readiness uses each selected `slot.particle.textureId` through
the production texture registry and drains the native main-thread queue per
distinct path. `nativeRender.readyLibraryTexturePaths` lists the paths actually
prewarmed; no particle slots means no invented particle texture. Missing selected
resources fail explicitly instead of substituting Star/WhitePixel. The existing
Star/effect resource prerequisites and receipts remain in force. VFX-only scenes
also require `Images/MagicPixel.png` through `playerAssetRoot` or
`INFINI_PLAYER_ASSET_DIR`: only that pinned PNG is decoded by the original native
PngReader, scoped and restored, without loading or drawing player artwork. Its
receipt is `nativeRender.magicPixelResource`; no synthetic white texture is used.
Only the existing
ParticleLibrary resource mod is registered: a selected Luminance particle texture
without its resource context is a refusal, not automatic dependency provisioning.

Reusable native controls, optionally including an unchanged historyRibbon item:

```sh
python tools/item-test-workbench/verify_history_ribbon.py --no-build \
  --out artifacts/history-controls --item /path/item.json
```

This matrix also exercises synthetic stroke/center `historyTrail`, both selected
Star/solidPixel particle resources, a native training dummy plus an invisible
moving hostile, capture-disabled parity, missing selected texture and partial/
procedural refusal controls. It now also needs the existing dummy assets
(`--include-dummy` setup above). Its `--item` option retains the earlier
**procedural historyRibbon** scene; it is not a generic full-artwork item launcher.
Use `workbench run` with an explicit full-artwork scenario for such an input.

Controlled `hostiles` remain **unrendered**. Only their `NPC.UpdateNPC` runs with
`dedServ:true`, omitting client FindFrame/artwork; a scoped restore also covers an
exception. Training-dummy client AI/frame and subsequent native client projectile,
damage, VFX and render phases are unchanged. `execution.controlledHostiles` and
the individual native phase events disclose this intervention. This is not
visible-enemy or complete NPC/client parity.

`drawNativeDust: true` runs original `Main.DrawDust` after the player pass. Because
that method can retire dust, **`capture: false` still executes the GPU draw lifecycle
in dust mode and skips only PNG export**. In earlier modes without native dust,
`capture: false` skips drawing. Read the report's explicit lifecycle/export flags.
Camera and one-render-per-tick cadence are part of this controlled scene.

## Public authored example

[The Lunar Harpoon example](examples/lunar-harpoon/README.md) contains assistant-authored
Author/Visual/VFX inputs and invokes the production compiler. Its supplied image was
created with image generation, then normalized through the existing asset pipeline.
This is not a claim that the complete mod LLM pipeline generated the example. Follow
its build instructions; replay requires no LLM API key.

## Agent review loop

1. Read the item and choose expected assertions **before** running it.
2. Keep the unchanged input, scenario, native trace, receipts and real frames together.
3. Check status, coverage, unsupported paths and failed assertions before vision review.
4. Inspect actual event/state ticks, not just the final frame or final mana balance.
5. Run a negative control, such as moving the target away while retaining a hit assertion.
6. Re-run both cases after a change. Do not relax assertions merely to obtain green output.

See [VERIFICATION.md](VERIFICATION.md) for portable checks and interpretation.

### Camera and controlled lighting diagnostics

`nativeRender.lightingMode` accepts `legacy_point` (default native white point at
 tile 50,45) or `viewport_fill` (explicit diagnostic white native lights on a
 four-tile grid). Both use **original** `Lighting.AddLight/LightTiles`. The processed
 region now follows the actual camera/zoom matrix, with a 16-tile margin clipped
 to the initialized world, rather than a fixed Y=32..56 band. This is controlled
 test illumination, not Terraria world-light parity; the fill mode is opt-in.

Every captured PNG's frame record includes `scene`: the camera, native-transformed
 player/projectile collision bounds, `hitboxIntersectsViewport`, and sampled
 `centerLightRgb`. This separates an off-camera or dark object from a missing
 spawn. Hitbox overlap and a draw call do **not** prove visible sprite pixels,
 complete VFX coverage, grip correctness or visual quality. Review original PNGs.
 The camera does not auto-follow or change gameplay; enlarge/reposition it in the
 explicit scenario when an intended lifecycle leaves the viewport.

### Authored material and impact textures

The original detached renderer also admits `spriteElement`, `texturedPath`, and
`impactSprite` when `drawArtwork=true`. Supply the exact referenced VFX and impact
PNG files alongside item/entity files in `artworkFiles`; unrelated files still
refuse. VFX files are checked against the canonical `[recipeId, assetId]` + NUL +
PNG identity (`infini_vfx_png_`); impact files use the canonical default impact
logical asset identity (`infini_asset_png_`). Missing, substituted or incorrectly
named bytes do not pass admission. Custom logical impact IDs remain unsupported.

`impactRing` additionally requires `drawPlayer=true` and `drawNativeDust=true`:
the original MagicPixel/Dust resources and complete native projectile hooks are
required, not reconstructed rings. Native snapshots now expose original material
path histories/geometries and detached impact records as well as particles. A
record proves state exists, not that it was drawn or visually approved; inspect
the corresponding original PNG frames and renderer coverage separately.

### Equipment reactions and secondary targets

CPU `playerUpdate: "full"` admits a single authored head/body/legs armor item or
accessory via `equip`, `vanity`, and `unequip`. The instance moves, rather than
being copied. Armor uses its actual generated armor proxy and native equip-slot
registration; `Player.Update` owns effects and reset. `player_stat_at` also accepts
`genericCrit` (including the native baseline).

Reaction scenarios can schedule `{"tick":5,"kind":"hurt_player","damage":10}`
or `{"tick":5,"kind":"strike_hostile","damage":10}`. They run **after** that
tick's native player update, so functional equipment registration, defense,
immunity, death credit and cooldowns are real. `strike_hostile` allocates a declared
one-HP, stationary Zombie fixture in slot 1 and calls `Player.StrikeNPCDirect`;
`GeneratedEquipmentKillGlobalNPC` is registered in the actual native loader.
Native death callbacks and player damage are recorded. The controlled hostile uses
an explicitly empty native loot table: this tests kill/reaction hooks, not vanilla
loot, enemy AI, graphical enemy death or multiplayer. A live previous hostile is
never silently overwritten. These stimuli are not admitted in rendered modes.

Optional `hostiles: [{"x":960,"y":700,"life":10000}]` provisions up to eight
additional stationary controlled Zombies in slots 2–9. They retain native geometry,
NPC updates, collision and damage hooks, but have disabled AI/gravity/contact damage
and zero defense/knockback. Their snapshots let a scenario distinguish secondary
projectile targeting from a hit on the first dummy. This is not NPC-AI certification.

```sh
python tools/item-test-workbench/verify_equipment_reactions.py --out artifacts/equipment
# For an independently source-built native executable, preserve its build receipt:
python tools/item-test-workbench/verify_equipment_reactions.py --out artifacts/equipment \
  --no-build --native-dll /path/to/ItemTestWorkbench.dll
```

### Native placement and mining world scenes

`world.trackTiles` selects explicit `{tileX,tileY}` cells for native telemetry.
Optional `world.walls` initializes bounded vanilla wall rectangles with `tileX`,
`tileY`, `width`, `height`, `wallId`; `tiles` still supplies Dirt terrain.
The scene loads Terraria's actual second tile/NPC metadata initializer, the
production placement ledger and its native `GlobalTile.CanDrop` callback, plus
native NBT bool serialization. It does not implement a parallel material ledger.

- `tile_target` sets the native tile target and mouse coordinates. Subsequent
  `primary`/`alt` runs real `Player.Update`/`ItemCheck`, `PlaceThing` or mining hooks.
- `break_tile` calls original `WorldGen.KillTile` as an **external break stimulus**.
  It is not evidence that a player mined the object. Primary pickaxe tests use
  ordinary input instead and observe the actual native tile removal.
- `tile_at`, `placement_groups_at`, `placement_pending_at` and
  `generated_world_items_at` assert native state at an explicit post-update `tick`.
  `tile_at` requires `tileX`, `tileY`, `hasTile` and, for a present tile, `tileId`.
  Count assertions require `value`. Assert stack debit separately with
  `generated_stack_at`; an observed world item count alone is not conservation.
- Snapshots include exact tile frames, pending/quarantined return counts and
  returned generated-item definition hashes. `GeneratedPlacementLedgerSystem`
  performs real post-world maintenance and `Item.NewItem` allocation.

```sh
python tools/item-test-workbench/verify_world.py --out artifacts/world-controls
```

The synthetic controls cover native campfire placement/last-unit debit, full
footprint removal, repeated break without duplicate return, a deliberately wrong
return count, native pickaxe mining versus no use, and an out-of-world refusal.
Placement lifecycle tests use `full` (dedicated visual branch); mining/contact uses
`client`. These controls do not certify placed-body artwork, wall breaking,
chests, arbitrary vanilla tiles, wiring, multiplayer, or the client renderer after
consuming the final held unit. World maps are disabled in this controlled scene;
map UI and full world ecology are not simulated.

### Resource, entity and long-lifecycle checks

`itemStack` provisions the actual generated item instance (default 1, bounded by
its native `maxStack`). Native `ItemCheck` owns consumption; the bench does not
subtract stacks. Arrow, bullet, flare and fallen star inventory go through native ammo selection.
Headless scenarios accept up to 14,400 ticks; rendered captures remain bounded to
600. This permits full multi-minute field expiry without increasing image budgets.

- `entity_spawn_count` counts distinct observed configured native lifetimes.
- `entity_hit_count_at_least` counts actual projectile hit callbacks;
  `entity_hit_count` requires an exact count, including zero. Both accept an
  optional `npcId` native slot filter (dummy: 0, controlled `hostiles`: 2 onward).
  For example, `{"kind":"entity_hit_count_at_least","entityId":"arrow","npcId":2,"value":1}`
  checks that the arrow actually hits the first downstream hostile. Child
  allocations, hits by a parent, or hits on a different target do not satisfy it.
  A spawn-only assertion cannot certify a hit-triggered projectile's usefulness.
- `entity_peak_active_at_most` checks native snapshots and configuration-time
  counts, including allocations between snapshots. All take `entityId` and `value`.
- `entity_inactive` and `entity_natural_expiry` take `entityId`; they inspect final
  native activity or observed lifetime-depleted Kill, respectively.
- `generated_stack_at` and `exhaustion_at` take post-update `tick` and exact `value`.
  Stack assertions sum the single generated identity across inventory/equipment.
- `target_effect_at` takes `tick`, `stat` and `value`. It samples the dummy's
  `lifeRegen`, `vx`, `vy` or active generated effect `count`, `lifeRegenPenalty`,
  `defenseDelta`, `contactMultiplier`, `velocityRetentionPerTick`. The latter are
  modifier totals, not proof of a particular hit or outgoing contact. Defense is
  applied by the registered `RuntimeHitNpcGeneration.ModifyIncomingHit` hook and
  does not change `npc.defense`. `target_hit_damage_at` checks actual item or
  projectile hit damage to the dummy at the specified tick; RNG and defense affect
  this value. The smoke controls check regen, expiry, velocity and a second hit,
  with an otherwise identical item lacking the effect as a negative control.
- Direct `Player.ApplyDamageToNPC` calls are observed separately from native
  item/projectile hit callbacks, so nearby-event damage is not mistaken for zero
  damage simply because it bypasses projectile contact callbacks.

```sh
python tools/item-test-workbench/verify_lifecycle.py --out artifacts/lifecycle
```

For separately source-built executables, the new lifecycle/world/equipment
verifiers accept `--no-build --native-dll PATH`. They record binary identity and
refuse a changed binary mid-matrix. This is direct native execution, **not** proof
of the standard wrapper's build provenance, archive or optional exports. Preserve
the external compiler/source/reference receipt with that evidence.

### Native placed-body drawing

`nativeRender.drawPlacedBodies: true` requires `drawArtwork: true` and an explicit
`world` scene. It calls the original `GeneratedPlacedBodyDrawSystem.PostDrawTiles`
over the real placement ledger and records successful original `DrawBody` calls.
`placed_body_draw_count_at_least` requires a positive `minimum`; no emitted body
cannot count as visual-path coverage. No native terrain texture or background is
invented. This verifies the authored placed-body renderer, not the complete world.

Returned material telemetry includes both the retained canonical source and returned
`ToNetworkJson` hashes. `generated_world_items_at` also rejects any returned item
whose canonical definition differs from the source; item ID/count alone is not
sufficient evidence that a placement round-trip preserved the definition.

Native movement inputs are explicit and persistent until changed:
`{"tick":20,"kind":"controls","left":false,"right":true,"jump":true}`.
All three booleans are required. Release them with all three `false`; ordinary
weapon `release` does not release movement. This requires full `Player.Update`,
which remains responsible for acceleration, jump, gravity, collisions and friction.
No workbench motion/physics model is used. Native input flags are in every player
snapshot. `verify_controls.py` checks run, jump, release and preflight refusals.

For equipped PNG checks, `verify_equipment_render.py` accepts `--item`, exact
`--artwork` PNG paths and `--player-assets`, plus the common output/build options.
It runs actual equipment layers and checks the idle player-region pixels against
unequip, retaining raw PNGs. A dispatched draw is **not** sufficient: fully occluded
overlays fail its visibility check. Facing/animation coverage remains explicit.
All equipment artwork runs require both exact item and `equipOverlayPath` PNGs,
even when the supplied scenario only uses the item in hand or places it.

Rendered movement can complete native achievements in the controlled scene. The
workbench preserves native achievement completion and its original notification/
sound dispatch, but captures achievement chat text before font layout, like the
existing generated-use-refusal text sink. It records `native_achievement_completed`
and `native_ui_message`; chat glyph rendering and audible audio are not certified.
This adapter does not alter world position, movement, achievement conditions or
item behavior. Unrelated chat paths are not silently swallowed.

## Item quality review (not just hook execution)

`quality_review.py` keeps native execution, numeric observations and visual judgment
separate. It never labels art acceptable because a draw occurred, a collider
passed, an overlay was visible, or the lowest alpha pixel touched a reference.

```bash
# Start with a proven private native scene: exact artworkFiles/player assets,
# correct ammo inventory, camera, terrain and item boundary. No asset rewriting.
python tools/item-test-workbench/quality_review.py cycle \
  --item /private/item.json --scenario /private/native-scene.json \
  --native-dll /absolute/ItemTestWorkbench.dll --hold-ticks 30 --out /private/review
# For passive equipment add --equipment (native equip, not invented use input).
# A single existing trace, including placement/drop scenes:
python tools/item-test-workbench/quality_review.py report /private/native.json \
  --out /private/report --terrain-reference
# Neutral sparse-support regression; requires existing native asset environment:
python tools/item-test-workbench/verify_quality.py \
  --native-dll /absolute/ItemTestWorkbench.dll --out /private/quality-controls
```

Scripted `primary` and `alt` represent held use intent until `release` or a
different use command. For held `alt` the harness reasserts alternate intent on
each update, since the native animation resets `altFunctionUse`; otherwise a
long hold can silently become primary use. This is an explicit scripted input
adapter, not a certification of physical right-click polling or repeat rules.

The compact cycle runs both facings, idle and native moving/jumping, with an
explicit held-input interval and release. It preserves ammo/environment settings
but replaces item-specific assertions with `no_nonfinite`: changed input cannot
inherit old shot counts. Inspect resource snapshots and observed held frames;
no-ammo refusal is not a missing animation. Use a long enough scene for recovery.
A separate scene may set `player.gravityDirection:-1` **and**
`player.gravitationPotion:true`: the real native buff permits inverted gravity.
Do not infer inverted-gravity coverage from ordinary facing tests; the summary
reports observed states. This is a native input scene, not a physics simulator.

Every artwork frame includes:
- Native front hand, rendered front hand (including `gfxOffY`), composite-arm
  authority, facing, gravity, velocity and input/use clocks. A frame-arm getter
  is not authoritative when the composite arm is disabled.
- Root held geometry **after** native player draw-data transformation, versus
  generated-projectile core geometry observed at actual `SpriteBatch.Draw`.
  Authored grip is projected through that exact draw. Distances and attachment
  offsets are observations: intentional authored reach is **review required**,
  never automatically canceled or declared invalid.
- Player/projectile colliders, placed footprint, and actual equipped layer draw
  anchors plus authored accessory mount. A visible badge can still be misplaced,
  badly scaled or aesthetically unsuitable.
- Placed-body alpha support per world-pixel column, clipped against transformed
  pixel polygons (`alpha>=128`, reported explicitly), contact-column count,
  minimum **and median** gap. Leaves or a single tilted end cannot turn a zero
  minimum into a generic support PASS. This measures silhouette, not structural
  material or semantic base. Textures are immutable during this isolated run.

Set `nativeRender.drawDroppedItems:true` alongside `drawArtwork` to execute
`GeneratedItem.PreDrawInWorld` on actual active generated `Main.item` instances
(e.g. native placement returns). Its collider, authored offsets and original
sprite draws are recorded separately. The diagnostic caller explicitly uses
white light and zero rotation; it is not complete `Main.DrawItem` treatment,
full-world item treatment, or detected terrain contact. Set explicit
`world.updateDroppedItems:true` to execute original `Item.UpdateItem` for active
world instances; snapshots record position/velocity and exact update scope. The
neutral regression moves the player away using native controls and verifies
settling on the configured tile floor. Pickup popup/font UI remains outside
this focused scene (keep the player away); no custom physics is substituted.
Collider/footprint bottoms are
reference lines, and authored offsets may deliberately produce nonzero gaps.

Reports retain byte-identical hash-verified original PNGs beside diagnostic
copies. Optional brown terrain rectangles are **schematic context only**, never
Terraria terrain pixels or full-world parity. No actual user definitions, art,
logs, videos or reports belong in the repository. Synthetic fixtures alone are
public. Direct DLL users must retain the independent source/reference build
receipt and use final exact source hashes; a successful render is not a packaged
live-game self-test.

### Native performance against the actual parents

`performance_review.py` runs one supplied use schedule against **lone, moving and
three grouped controlled Zombies**, once for the item and each exact distinct
`recipeMeta.parentIdentities` entry. Names in prose are never guessed as parents.
Missing generated parents and noncombat ingredients are `notRun`/`notMeasured`,
not zero-damage controls. Supply an actual generated parent with
`--parent-item 'generated:ID=/private/parent.json'`. Modded native parents are not
admitted. The recorded vanilla numeric ID must agree with native stable-name lookup.

```sh
python tools/item-test-workbench/fetch_performance_assets.py --out /private/parent-assets
python tools/item-test-workbench/performance_review.py \
  --item /private/item.json --item-boundary local_cache \
  --scenario tools/item-test-workbench/scenarios/performance-primary.json \
  --out /private/performance --plan
# Remove --plan to execute. For a separately source-built native binary also use:
# --native-dll /private/ItemTestWorkbench.dll
# For client contact geometry: --vanilla-assets /private/parent-assets
```

The example is **two explicit hold/release cycles**, not universal input for every
weapon. Tune range, aim, duration and holds to the authored item, then keep them
identical for all candidates. A non-auto-reuse sword held down may swing only once;
the report shows actual `Player.ApplyItemTime` ticks rather than calling the whole
held interval continuous fire. Ammo inventory is shared and actual matching-ammo
availability, native consumption callbacks and final stack debits are separate.
Full CPU scenes refuse native-contact weapons instead of reporting false zero
melee damage. For such weapons supply a `client_hybrid` scene (no VFX) or a
`client_vfx` scene with the item's exact admitted publication files.

A Live10 Terra ShadowFrost mechanical probe used the archived `test_fixture`
item, whose asset PNGs were already synthetic. The only change to its item JSON
was removing VFX slots, because `client_hybrid` does not execute authored VFX;
the runtime mechanics remained unchanged. In a close-range interior scene
(player 800,700; dummy 828,700; floor tileY 47), native contact and projectile
hits were both observed. This mode uses the repository's 32×32 generated proxy
texture for contact geometry, so it does not certify contact reach for final
artwork, VFX appearance, or a complete in-game fight.

In performance `client_vfx` runs, drawing and PNG capture are deliberately disabled
for **every** candidate; material assets still load where required. Vanilla items
use their pinned real item PNG for native use-style/hitbox geometry, never the
generated proxy. Native player/projectile/NPC, dust/lighting and detached-VFX
updates execute in the same mode. Draw-required effects such as `impactRing` may
refuse this non-drawing workload and remain explicitly unmeasured. Use the separate
visual workflow to inspect artwork; this report does not certify visuals.

`performance.json` and `.md` preserve each trial status and raw trace/log/hash
receipts. Measurements include separate item/projectile/direct-damage callbacks,
actual target HP lost, critical hits, sampled per-target native buff uptime, target
positions/armor, native use-clock intervals, paid mana and inventory debits. The
channels are **not blindly added**: direct damage may nest callbacks and health
loss also reflects DoT/regeneration. A dead target censors the remaining trial.
The same native RNG seed is reset **after scene/assets setup, before tick 0**;
weapons still consume RNG differently, so a single seed is not a distribution.
Initial native player/ammo and seed receipts are checked for equality. No prefixes,
armor/accessory loadout, real NPC AI or full-world certification is claimed. Moving
targets have an initial 0.5 px/tick velocity integrated by original `NPC.UpdateNPC`,
not a separate physics model. Zero-defense and configured-defense results are not
interchangeable. None of these measurements emits a balance/quality PASS.

Vanilla geometry loading uses the complete pinned source index of 5414 item PNGs,
embedded in the native executable. There is no per-item ID allowlist in the loader.
Fetch any needed native item IDs explicitly; the original twelve-item control set
remains the downloader's default:

```sh
python tools/item-test-workbench/fetch_performance_assets.py \
  --items 24 3507 --out artifacts/dependencies/vanilla-assets
python -m toolbox workbench probe --vanilla-item WoodenSword \
  --mode client_hybrid --set dummy.x=840 \
  --set 'vanillaAssetRoot="artifacts/dependencies/vanilla-assets"' \
  --assert dummy_damaged
```

The downloader and native loader verify exact Git blob SHA-1 and byte length against
the pinned commit's source tree, bounded PNG dimensions, and symlink/reparse refusal.
The native receipt adds SHA-256 and actual loaded dimensions. Missing or changed
PNGs refuse; they are not substituted. The index contains source availability facts,
not gameplay support guarantees. It is reproducible with
`index_vanilla_assets.py --out /path/vanilla-item-assets.json`. The PNGs are community
1.4.4.9 extractions, **not official-byte-certified**, and are not bundled.
Private definitions, authored art, logs and rendered evidence stay outside git.

For a sustained **repeated-press** view, choose an explicit schedule rather than
assuming auto-reuse. For example, add `--input-pattern repeated --repeat-every 30
--hold-ticks 5` (primary by default; `--repeat-input alt` selects alternate).
This replaces only use/release actions, preserving aim/movement and all scene
conditions, and applies the **same** schedule to every candidate. The report labels
these `repeated-*` scenes and shows actual native use-clock applications even when
a cooldown or channel lifetime prevents a requested press from firing. `both`
keeps the caller's supplied schedule too (six scenes instead of three); the bounded
default remains `supplied`. These are requested input opportunities, not invented
attack counts or a universal optimal firing schedule.

Additional **user-requested controls** can be added without changing recipe
metadata: `--control item:Terraria/Minishark:98 --control item:Terraria/Musket:96`.
They are labelled `requestedControl`, never `authoredParent`; both stable name and
native ID are verified. The report assesses requested-control comparability
separately so a real noncombat ingredient does not become a fake zero-damage
weapon. For bullet guns share the same bullet inventory; compare actual native
use-clock counts with ammo callbacks and stack debits. Native ammo conservation
and `autoReuse` remain active, not normalized away. Flare-gun utility/lighting and
status uptime are distinct from bullet-gun direct damage.

### Explicit vanilla controls and actual vanilla player layers

`performance_review.py --control item:Terraria/Minishark:98 --control item:Terraria/Musket:96`
adds **requested controls**, not fabricated recipe parents. They retain separate
comparison/admission rows. A noncombat parent refusal does not erase valid
requested-control measurements. Use both supplied held input and explicit
repeated presses: autoReuse and native ammo conservation change actual counts.
Never infer damage/resource rates from nominal damage or reuse flags alone.

For actual vanilla player/item artwork, set `drawArtwork:true`, `drawPlayer:true`,
`artworkFiles:[]` and the explicit `vanillaAssetRoot`. The ordinary native held-item
layer uses its genuine pinned texture; no generated proxy/layer replaces it.
Native items have no fabricated authored grip: their exact DrawData is recorded
and numerical grip error remains unavailable. Generated composite poses and
vanilla frame-arm poses may deliberately differ. `initialX/Y` and
`requestedSpawnX/Y` record actual/native requested projectile spawn centers,
not a guessed image muzzle marker.

```sh
python tools/item-test-workbench/verify_vanilla_pose.py \
  --native-dll /absolute/ItemTestWorkbench.dll \
  --vanilla-assets /private/performance-assets --out /private/vanilla-poses
```

This compact native control covers Minishark/Musket in both actual observed
facings, original player/item draw, original dust, PNG integrity and absence of
generated replacement/veto. Bullet simulation/hits still execute, but **vanilla
projectile sprites are explicitly not rendered** in this pose mode. Full-world
parity and an inferred vanilla hand/grip point are not claimed. Asset provenance
remains pinned community extraction, not official byte certification.


### Native vanilla projectile capture

Opt in with `nativeRender.drawVanillaProjectiles: true` alongside `drawArtwork`
and `drawPlayer`. Gameplay continues through original `Player.Update` / ItemCheck,
`Projectile.Update` and native hit hooks; the sprite pass calls original
`Main.DrawProj`. This admits only the pinned wooden arrow (1), ordinary bullet
(14), Holy Arrow (91), Hallow Star (92), Pulse Bolt (357) and Hellwing (485).
Other active types, hidden/special draw passes, missing PNGs and hash mismatches
refuse; no generated projectile or schematic sprite substitutes for them.
The default vanilla pose mode still omits projectile sprites explicitly.

```sh
python tools/item-test-workbench/fetch_performance_assets.py \
  --out artifacts/dependencies/vanilla-assets --include-projectiles
python tools/item-test-workbench/fetch_player_assets.py \
  --out artifacts/dependencies/player-assets --include-dummy
export INFINI_PLAYER_ASSET_DIR="$PWD/artifacts/dependencies/player-assets"
# Also configure the native tML/ParticleLibrary dependencies described above.
python tools/item-test-workbench/verify_vanilla_projectiles.py \
  --vanilla-assets artifacts/dependencies/vanilla-assets \
  --out artifacts/vanilla-projectiles --gif
```

The verifier builds once, runs Daedalus with wooden arrows, Pulse Bow and Hellwing
Bow with wooden/Holy arrows, and a bullet control. It retains native assertion,
ammo-source, hit and exact-frame evidence. Additional controls cover no ammo,
legacy omission, original camera culling, capture-disabled rendering without dust,
unsupported projectile type, invalid mode, and missing/tampered assets. An explicit
`--native-dll PATH --no-build` records an independent binary hash; retain its
source/reference build receipt. `--case NAME` runs a labelled subset, not the full
matrix. GIF/HTML review is exported under each passing bow's `review` directory;
no game PNGs, captured frames or private runs are bundled in source.

`scenarios/daedalus-stormbow.json` is the reusable native training-dummy scene.
Its relative `vanillaAssetRoot` matches the downloader command above. It asserts
native hits rather than an HP drop: the real dummy is immortal. The verifier's
other bows use a separate explicit side-view scene and solid wall. The wall has
native collision but no terrain artwork in this controlled renderer.

The explicit camera now applies **before player/projectile updates**, preserving
world-space aim. Original `Dust.NewDust` performs its real camera culling during
those updates; a distant scene no longer loses every trail before drawing starts.
The Pulse Bolt's pinned sprite is genuinely a transparent 1px resource: its visible
trail is original native dust, so enable `drawNativeDust` for its visual review.
Native Gore allocation is initialized for Holy Arrow impacts; Gore update/drawing,
full terrain/world rendering and audio remain outside this lane.

Reports distinguish `vanillaProjectileDrawAttemptCount` and per-projectile
`vanillaProjectileDrawAttempts` from observed `SpriteBatch.Draw` submissions in
`projectileDrawCount` / `projectileGeometry`. An off-camera `Main.DrawProj` attempt
cannot certify sprite drawing. A submitted draw still does not prove visible
pixels or aesthetic quality; inspect the original PNGs. Both scalar and vector
SpriteBatch overloads are observed once even when one forwards to the other.
`capture:false` with this opt-in still executes the native GPU lifecycle and omits
only PNG encoding, including when native dust drawing is disabled.

Native GIF export rounds cumulative native tick timestamps to centiseconds, so
60fps and stride-2 review do not accumulate a speed error. Palette conversion and
an explicit final 800ms pause remain; no intermediate game frame is invented.

Complete before/after native dust states live once in `nativeRender.snapshots`; PNG frame receipts refer to the same tick with `nativeDustStateTick` and counts. Compact JSON preserves every observation without duplicating particle arrays, keeping trail-heavy bow traces within the portable reader budget.
