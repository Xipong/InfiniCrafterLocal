# ModSources/InfiniCrafterLocal — active tModLoader C# runtime

This is the game runtime, not the generator. Read `../../AGENTS.md` and `../../PROJECT_ARCHITECTURE_RU.md` before editing.

Key files:
- `InfiniCrafterLocal.cs` — root `Mod`, services, packet router, `Mod.Call`, cleanup.
- `Common/InfiniNetPacketIds.cs` — packet id registry.
- `Common/InfiniRuntimeLimits.cs` — runtime API/code limits; `NetProseMaxChars=0`.
- `Common/Models/` — game-facing `GeneratedItemData` + `VfxManifestSpec` contracts.
- `Common/Services/` — LocalGenerator HTTP boundary, world registry, asset HTTP sync, sprite cache.
- `Common/Players/` — station transaction, refunds, MP server-authoritative craft, held draw sync.
- `Content/Items/` — `InfiniCore` and per-instance generated item proxies.
- `Content/Projectiles/` — bounded generated projectile runtime and compact net sync.

Hard rules:
- C# applies explicit generated contracts; it must not infer gameplay from names, prompts, tooltip prose or debug strings.
- Multiplayer clients send craft intent only; host/server commits generated items.
- PNG/JSON asset bytes are not Terraria packet payloads; use registry + `/get_asset` by filename.
- New runtime capabilities require Python contract + C# support + tests + docs together.

Charge/sentry owners:
- `Common/Models/GeneratedDamageClassPolicy.cs` — one exact damage-class resolver for item and projectile.
- `Content/Projectiles/GeneratedProjectile.ChargeRelease.cs` — held charge and ordinary projectile release.
- `Content/Items/GeneratedItem.Sentry.cs` — sentry placement and maxTurrets.
- `Content/Projectiles/GeneratedProjectile.Sentry.cs` — target scan, bounded fire lifecycle and non-recursive shot spec.
- `Content/Projectiles/GeneratedProjectile.NetSync.cs` — protocol 14 scalar state.

Do not set sentry-only `ProjectileID.Sets.*` globally on the shared GeneratedProjectile type.
