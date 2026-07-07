# Common/VFX

Runtime VFX execution layer for `VfxManifestSpec`.

- `InfiniVfxRuntime.cs` — executes slots on tick/hit/kill/draw, applies renderer/channel budgets.
- `VfxFoundation.cs` — backend abstraction and command structs; vanilla Dust + ParticleLibrary backend.
- `VfxParticleSystemRegistry.cs` — ParticleLibrary systems and particle behavior.
- `VfxRendererRegistry.cs` — renderer kind normalization and draw-cost estimates.
- `VfxParticleAddress.cs` — canonical ParticleLibrary particle system addresses.
- `VfxContext.cs` — projectile context snapshot.
- `InfiniVfxClientOptions.cs` — client config-derived multipliers/options.

VFX manifests are frozen data. Runtime should not parse `EffectName`/style prose as mechanics.
