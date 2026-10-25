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
| Equipment | Supported single-instance accessory equip/unequip/vanity paths | Not arbitrary armor sets, multi-accessory interactions or reactive equipment |
| Ammo | Native arrow/bullet selection, source identity, consumption, slot priority and depletion | Generated ammo and other categories are not certified; fixtures are synthetic |
| Item-body contact | Original client use-style/contact and supported use/hit/crit events | Requires explicit client modes; unsupported effect combinations refuse |
| Authored VFX | Original supported ParticleLibrary resources, updates and draw wrapper | Not all visual-slot kinds, shaders, sound output or mod content |
| Authored PNGs | Original sprite resolver and item/projectile drawing paths; publication identity checks | Baked/reused PNG subset; no silent geometry/asset fallback |
| Player artwork | Original player renderer/layer ordering, starter skin/hair, generated held layer once | No arbitrary armor, appearance variants, mounts, world background or complete Main.Draw |
| Training dummy | Original tile378 placement, tile entity, linked NPC488, native AI/frame and tile renderer | Native immortal target differs from damageable fixture; reactivation/respawn not certified |
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

A synthetic zero-distance return case has exposed non-finite native motion. Its
expected-failure regression can pass while the tested item remains broken. Likewise,
an author composition that starts homing too late is an authoring defect, not a
reason for the utility to rewrite engine timing. Fixes belong to their actual owner
and require a separate positive test plus the original negative control.
