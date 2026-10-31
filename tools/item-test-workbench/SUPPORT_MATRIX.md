# Supported boundaries

This matrix describes **bounded implementation paths**, not a promise that every
combination of capabilities works. The native admission checks and the individual
run's `execution` / `coverage` report are authoritative. `fullGameParity` remains
false: the utility initializes a controlled scene instead of running all of Main.

| Area | Native path exercised | Boundary / remaining gap |
|---|---|---|
| Generated JSON | Production fresh or explicit local-cache reader; real registered item/projectile types | Not every valid item is admitted by a scene; source input is not rewritten |
| Use, charge, release, return, expiry | Actual ItemCheck, generated hooks, Projectile.Update/Kill and delayed scheduler | Scenario-specific assertions; no all-controller certification |
| Full player | Player.Update, gravity/floor, mana/health regeneration, supported held/buff/mobility clocks | Commanded input replaces keyboard polling; world systems are not complete |
| Native sentries | Full-player scene uses native sentry spawning and `Player.UpdateMaxTurrets`; `verify_sentry.py` checks replacement at the default cap | Item-check-only mode refuses sentries; the controlled single-player scene does not certify multiplayer, arbitrary equipment or every sentry composition |
| Equipment | Single-instance accessory and head/body/legs native equip/unequip/vanity; registered on-hurt/on-enemy-kill generated-buff reactions; original five equip-overlay draw layers and exact authored overlay PNGs | Not armor sets, multi-accessory interactions, enemy AI/loot tables, full armor atlases or multiplayer; draw dispatch alone does not prove visible pixels |
| Ammo | Native arrow/bullet/flare/fallen-star selection, source identity, consumption, slot priority and depletion | Generated ammo and other categories are not certified; fixtures are synthetic |
| Stack/long lifecycles | Native stack consumption, configured entity counts/caps, exact exhaustion checkpoints and up to 14,400 headless ticks | Assertions are scenario-specific; rendered captures remain capped at 600 ticks |
| Placement/mining | Native ItemCheck placement/mining, ledger commit/retirement and canonical-definition-preserving material return | Explicit tile scenarios only; break_tile is external native stimulus; no world save/ecology parity |
| Item-body contact | Original client use-style/contact and supported use/hit/crit events | Requires explicit client modes; unsupported effect combinations refuse |
| Authored VFX | Original supported ParticleLibrary resources, updates and draw wrapper | Not all visual-slot kinds, shaders, sound output or mod content |
| History ribbon | Original InfiniVfxRuntime.Draw/DrawTrail with live native projectile history; full PreDraw or explicit procedural-only pass; recorded segment submissions | Native MagicPixel assets required; procedural-only mode does not draw missing authored/player artwork; zero-motion histories need not emit geometry |
| Current history trail | Original full GeneratedProjectile.PreDraw/DrawExplicitTrail with live native samples; per-slot SpriteBatch segment counts | Only stroke/center with drawPlayer, exact artwork and native MagicPixel assets; sprite/tip and partial/procedural-only routes remain refused |
| Controlled hostiles | Native NPC.UpdateNPC and native projectile damage/hit callbacks; explicit dedicated-update phase events | Invisible controlled NPCs, AI disabled by scene setup; only NPC update uses dedServ=true to omit client FindFrame, restored before client damage/render; no visible enemy/client parity |
| Vanilla item geometry | Exact PNG lookup from complete pinned source inventory; Git blob/size/IHDR checks and original native PngReader | Assets must be supplied explicitly; source availability is not all-weapon gameplay certification or official-byte identity |
| Authored PNGs | Original sprite resolver and item/projectile drawing paths; publication identity checks | Baked/reused PNG subset; no silent geometry/asset fallback |
| Player artwork | Original player renderer/layer ordering, starter skin/hair, generated held layer once | No arbitrary armor, appearance variants, mounts, world background or complete Main.Draw |
| Training dummy | Original tile378 placement, tile entity, linked NPC488, native AI/frame and tile renderer | Native immortal target differs from damageable fixture; reactivation/respawn not certified |
| Vanilla projectile artwork | Opt-in original Main.DrawProj; pinned types1/14/91/92/357/485, actual sprite submissions and native dust trails | Default pose mode still omits sprites; unknown types/special draw passes refuse; Pulse Bolt is dust-rendered; no complete Main.Draw/world or Gore pass |
| Native dust | Original Dust.UpdateDust and Main.DrawDust with recorded state | Draw can deactivate particles; only exercised atlas/shader cases are evidenced |
| Vision | Real PNGs with hashes and tick-aligned HTML/GIF review | Schematic replay is separately labelled; no interpolated game frames |
| Determinism | Seeded input and recorded native state/draw-RNG comparisons | No multiplayer, arbitrary mods or universal cross-platform determinism claim |

## Refusal and coverage

Unknown input actions/assertions, missing dependencies, invalid publication assets,
unsupported requested lanes, unavailable render contexts and non-finite state must
not become successful empty output. Coverage separates exercised inputs from
untested or unsupported bindings. A passed primary use does not certify alternate,
passive effects, artwork or the entire item definition.

The ordinary fixture dummy deliberately has controlled dimensions, life and AI.
The explicit native training dummy instead retains native 18×40 geometry, AI92 and
immortality, and is drawn by the actual **tile renderer**, not an NPC sprite pasted
onto the collision box. Use native hit events rather than requiring its HP to drop.

## Known visual limitations

- Community player/dummy PNG integrity and native GPU readback were checked locally;
  official game asset byte identity is still unverified. No game bytes are shipped.
- NPC488 has 11 native frames. The provided 550-pixel community sheet gives a
  50-pixel FindFrame stride, while original vanilla and tML tile drawing use a
  hardcoded divisor55. The utility does not resize the asset or change native frame
  counts to hide this discrepancy. Official-installation wobble parity is not claimed.
- Lighting is an explicit controlled native lighting setup, not a loaded world save.
  Neutral backgrounds and omitted terrain/other NPCs are intentional scope limits.
- Native dust uses the original atlas and renderer. Partial-alpha atlas regions or
  arbitrary ModDust shaders are not validated simply because another dust type passes.
- Audio audibility, original charge HUD text, chat glyph rendering, multiplayer and
  the full Terraria scene are not certified. Telemetry labels are not replacements
  presented as those original renderers.

## Regression findings are not production fixes

The synthetic zero-distance return case now requires finite native motion after
the production coincident-seek fix. Negative controls must still fail only their
explicit intended assertions. Likewise,
an author composition that starts homing too late is an authoring defect, not a
reason for the utility to rewrite engine timing. Fixes belong to their actual owner
and require a separate positive test plus the original negative control.

Camera diagnostics use the actual native view matrix and report collision-bound
intersection and sampled center light per captured frame, not sprite visibility.
Lighting bounds follow that viewport; optional `lightingMode: viewport_fill`
uses a controlled native white-light grid. Neither illumination mode certifies a
loaded-world appearance. Fixed camera framing remains an explicit scenario input.

Authored material paths/elements and impact sprites use the original detached
renderer with exact selected publication assets. Their native state is recorded
separately from particle state. `impactRing` requires the original active projectile
and dust paths, through full artwork or explicit `drawProjectileVfx` mode.
`historyRibbon` requires the active native history/draw context. Source-only admission or a successful scenario with no matching
emission does not certify that visual lane. Full-player held-projectile rendering
must be checked separately from the partial authored-art lane.

Native world scenarios now admit explicitly selected `place_item` bindings through
full Player.Update/ItemCheck, production ledger maintenance and native material
return. Primary pickaxe mining is separately exercised through the client branch.
Tracked tiles and timed assertions are evidence, not world/render parity. The
`break_tile` command is an external native-world stimulus; it must not be described
as a player mining action. Reusable synthetic matrix: `verify_world.py`.

### Quality observations

| Surface | Native observation | Remaining boundary |
|---|---|---|
| Root held vs held projectile | Final native player DrawData / actual projectile SpriteBatch core; authored grip, rendered hand, displacement | Ordinary frame-arm hand getter not authoritative; intentional reach is not auto-invalid |
| Full use cycle | Explicit input hold/release, ammo, left/right, native move/jump | Check requested vs observed states; inverted gravity requires separate explicit buff scene |
| Placed support | Actual DrawBody transform, footprint, alpha-column support and median gap | Silhouette does not identify structural base; no aesthetic PASS |
| Dropped body | Actual generated PreDrawInWorld on native world instances | Neutral white/zero rotation diagnostic caller; optional original Item.UpdateItem settling; no full Main.DrawItem, pickup UI or world ecology parity |
| Equipped badge | Actual native layer/anchor plus authored mount, native player scale | Visibility alone does not establish good appearance |
| Context terrain | Optional configured tile boundary overlay | Clearly schematic, never native terrain art |
| Requested vanilla controls | Explicit stable identity, separate from authored parents; genuine PlayerRenderer/item PNG and native firing | No invented vanilla grip; projectile sprites omitted in default pose mode, bounded opt-in Main.DrawProj available; hold vs repeated native input distinguished |

The configured render camera applies before native gameplay updates as well as drawing. Original dust-emission culling remains active. Native Gore allocations required by Holy Arrow impacts are provisioned, but Gore update/rendering is not certified. A native draw attempt outside the camera is recorded separately from observed SpriteBatch submissions; neither alone is visual approval.
