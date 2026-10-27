# Native tModLoader observer fixture

This source is an independent test mod, not part of InfiniCrafterLocal. Build
`../../fixture-mod/WorkbenchObserverFixture.Standalone.csproj` against matching
tModLoader DLLs; no IFC reference or `.tmod` packaging is required. Supply the
resulting DLL and this directory through `loader-run --probe-dll` and
`--probe-mod-root`. The workbench must not register or call these classes by name.

Set `IFC_WORKBENCH_OBSERVER_OUTPUT` to an absolute JSON file path whose parent
directory already exists **before starting tModLoader**. When unset, no file is
written. After a world loads the fixture clears its counters, writes snapshots
every ten world updates, and writes a final snapshot when the world unloads.
The file contains `schemaVersion`, `mod`, `gameUpdateCount`, and a `counts`
object. A fresh output path prevents an old file being mistaken for a new run.

Use the native content names:

* `WorkbenchObserverFixture/ProbeItem`
* `WorkbenchObserverFixture/ProbeProjectile`
* `WorkbenchObserverFixture/ProbeNpc`

The NPC is a stationary, high-life target. Fire the item at it in a sufficiently
long scene and read the fixture's file independently of the driver. The
expected nonzero keys are `ModSystem.PostUpdateEverything`,
`ModPlayer.PostUpdate`, `ModPlayer.ModifyWeaponDamage`,
`GlobalItem.ModifyWeaponDamage`, `ModItem.CanUseItem`, `ModItem.Shoot`,
`GlobalProjectile.OnSpawn`, `ModProjectile.AI`, `GlobalProjectile.PostAI`,
`GlobalNPC.OnSpawn`, `ModNPC.AI`, `GlobalNPC.ModifyHitByProjectile`,
`ModProjectile.OnHitNPC`, and `GlobalProjectile.OnHitNPC`. Verify an actual hit
in the driver's trace as well; a counter alone is not evidence of its effect.

`item-scene.json` is an example for a real local client. `projectile-scene.json`
only exercises the projectile and target lanes and cannot verify item or player
input hooks. Both scenes require a fresh isolated world with suitable terrain;
they are candidate scenarios until run in the real game process.

The GlobalItem and ModPlayer add flat damage to this test item, and the
GlobalNPC increases source damage for this test projectile against this test
NPC. These modifications make dispatched hooks observable beyond registration.
They do not alter unrelated content. This fixture makes no claim about loading
or executing every other mod's dependencies, client rendering, or multiplayer.
The `.Any` counters also record those global hook calls for other items and
projectiles. They allow a second scene using IFC or another mod's content to
check cross-mod dispatch without changing the driver or the item under test.
