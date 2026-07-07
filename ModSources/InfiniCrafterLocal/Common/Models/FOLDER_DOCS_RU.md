# Common/Models — game-facing generated contracts

Source-of-truth DTOs for what C# can safely receive/apply/execute.

- `GeneratedItemData.Model.cs` — identity, recipe meta, gameplay, accessory, armor, attack, visual, presentation genome, sound profile, extension data.
- `GeneratedItemData.Normalize.cs` — compatibility migrations, clamps, runtime API/path/status normalization.
- `GeneratedItemData.Apply.cs` — transfers explicit fields into Terraria `Item` stats/flags/proxy behavior.
- `GeneratedItemData.cs` — JSON profiles: full/local-cache/network/player-save and stripping of bulk/prose.
- `GeneratedItemData.Debug.cs` — applied trace/debug JSON for authored-vs-applied audits.
- `VfxManifestSpec.cs` — frozen VFX manifest data/slot normalization.

Rules:
- Adding a field here does not make it gameplay. It must also be authored/validated in Python, normalized/applied here, executed in item/projectile/VFX/audio runtime, and covered by tests/docs.
- Unknown/future fields may be preserved for local cache/debug, but must stay inert until supported.
- Do not parse prose/debug/flavor fields to recover mechanics.
