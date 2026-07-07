# Common — contracts and shared runtime infrastructure

This folder holds the C# contract/runtime spine. It is not a place for ad-hoc name routers.

Top-level files:
- `InfiniNetPacketIds.cs` — all packet ids; add packet ids only with router + handler + tests/docs.
- `InfiniRuntimeLimits.cs` — runtime API/current opcode limits; `NetProseMaxChars=0` means prose is not network gameplay state.
- `InfiniTerrariaSentinels.cs` — named Terraria/tML numeric sentinels; avoid scattered magic numbers.

Subfolders:
- `Models/` — `GeneratedItemData` and `VfxManifestSpec` DTO/normalize/apply/debug contracts.
- `Services/` — generator HTTP boundary, generated registry, asset sync, sprite cache, runtime authority.
- `Players/` — station/player transaction state, refunds, MP craft protocol, utility buffs/mobility, held draw sync.
- `VFX/`, `Audio/`, `Commands/`, `Config/`, `UI/`, `Systems/` — runtime subsystems.

Before changing a field or capability, trace both directions: Python authoring emits it, C# normalizes/applies/executes it, tests/docs cover it.
