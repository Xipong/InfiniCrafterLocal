# Item Test Workbench

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
subtract stacks. Arrow, bullet and flare inventory go through native ammo selection.
Headless scenarios accept up to 14,400 ticks; rendered captures remain bounded to
600. This permits full multi-minute field expiry without increasing image budgets.

- `entity_spawn_count` counts distinct observed configured native lifetimes.
- `entity_hit_count_at_least` counts actual projectile hit callbacks.
- `entity_peak_active_at_most` checks native snapshots and configuration-time
  counts, including allocations between snapshots. All take `entityId` and `value`.
- `entity_inactive` and `entity_natural_expiry` take `entityId`; they inspect final
  native activity or observed lifetime-depleted Kill, respectively.
- `generated_stack_at` and `exhaustion_at` take post-update `tick` and exact `value`.
  Stack assertions sum the single generated identity across inventory/equipment.
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
