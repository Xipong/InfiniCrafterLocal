# Common/VFX

Исполнение принятого [VfxManifestSpec](../Models/VfxManifestSpec.cs), не интерпретация style/prose:

- [InfiniVfxRuntime.cs](InfiniVfxRuntime.cs) — active slot events/draw и общий budget.
- [InfiniItemVfxRuntime.cs](InfiniItemVfxRuntime.cs), [InfiniItemVfxRuntime.MaterialEvents.cs](InfiniItemVfxRuntime.MaterialEvents.cs) — Item producers/material events.
- [InfiniDetachedVfxSystem.cs](InfiniDetachedVfxSystem.cs) и partials — bounded detached simulation/draw; [VfxSourceBinding.cs](VfxSourceBinding.cs) — attachment/lifecycle identity.
- [VfxOrderedPeerStream.cs](VfxOrderedPeerStream.cs) — bounded ordered peer sequence ownership.
- [VfxRendererRegistry.cs](VfxRendererRegistry.cs), [VfxCanonicalVocabulary.cs](VfxCanonicalVocabulary.cs) — конечные renderer/token domains.
- [VfxFoundation.cs](VfxFoundation.cs), [VfxParticleSystemRegistry.cs](VfxParticleSystemRegistry.cs), [VfxParticleAddress.cs](VfxParticleAddress.cs) — command/particle backends; [InfiniVfxClientOptions.cs](InfiniVfxClientOptions.cs) — client quality controls.
- [Sound contract](../../../../docs/VFX_SOUND_PALETTE_RU.md) — exact finite samples и явные volume/pitch/variance; общий `VfxSlotSpec.ResolveSoundStyle`, прежний alpha/phase путь только при saved absence.

[Материалы и авторский контракт](../../../../docs/VFX_MATERIAL_ELEMENTS_RU.md). Наличие context-типа внутри foundation не означает существование отдельного `VfxContext.cs`.
