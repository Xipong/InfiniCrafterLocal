# Common/Audio

Sound selection and optional live cue bridge.

- `InfiniSoundLibrary.cs` — exact `infini.terraria-sound-catalog.v8` resolver: 92 acoustic-role ids mapped to at least 65 distinct vanilla Terraria `SoundID`; no item-name/tooltip/taxonomy classifiers. Preserves native `SoundStyle` volume/pitch/variance, then applies bounded authored multiplier/offset/minimum variance.
- `InfiniLuminanceSoundBridge.cs` — optional loop/live sound cue bridge; receives the same resolved audio controls.
- `InfiniFutureSoundCatalog.cs` — future explicit asset-catalog seam. Query fields are inert unless an implementation resolves a concrete catalog id/path; it must not become a prose classifier.

Authoritative order: exact authored catalog id -> future explicit catalog seam -> tiny fallback from compiled runtime family/effect/onHit. Search prose never selects the built-in catalog.
