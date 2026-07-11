# Content/Projectiles — bounded generated projectile runtime

Executable generated attack runtime split by concern.

- `GeneratedProjectile.cs` — shared state, texture/NAV map, asset catch-up helpers.
- `GeneratedProjectile.Runtime.cs` — defaults, `ApplyGeneratedSpec`, runtime validation, stat apply, AI loop, movement primitives.
- `GeneratedProjectile.Executors.cs` — movement executor dispatch for supported movement codes 0..18.
- `GeneratedProjectile.Impact.cs` — collision, on-hit/on-expire bounded child projectiles, AOE, kill/impact behavior.
- `GeneratedProjectile.OverheadBarrage.cs` — isolated target-marker + delay executor for authored projectiles descending from above; not a generic state machine.
- `GeneratedOverheadBarragePolicy.cs` — one exact owner for child-spec descent configuration and bounded placement geometry; never chooses projectile theme.
- `GeneratedProjectile.Visuals.cs` — registry hydration, sprite/VFX fallback drawing, dust/light polish.
- `GeneratedProjectile.NetSync.cs` — compact visual/spec/VFX sync and catch-up queues.
- `GeneratedVfxOverlayProjectile.cs` — timed overlay carrier for hit/kill VFX.

Rules:
- Runtime requires an authored/supported spec; it must not execute prose/script compatibility fields.
- Child projectiles use explicit `MaxChildProjectiles`/`MaxChildDepth`; spawned child specs reset child depth/count to prevent cascades.
- Projectile packets should be compact; registry/assets hydrate missing data by id.
