# Content/Projectiles

One shared generated projectile executes an explicit runtime entity instance:

- `GeneratedProjectile.cs` — load entity by generated item id/entity id;
- `.Executors.cs` — movement/controller finite dispatch;
- `.RuntimeEvents.cs` — exact event actions and limits;
- `.NetSync.cs` — required authored/state fields only;
- `.Visuals.cs` — visual kit entity role.

Old charge/sentry/child/family whole-weapon partials were removed. Flail/yoyo/whip/beam/targeting remain reusable controller patterns selected explicitly by capability opcode.
