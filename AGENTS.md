# AGENTS.md — read this before touching InfiniCrafterLocal

This repository is easy to break by "reasonable" agent guesses. Do not infer architecture from old reports, build caches, or generated artifacts. Code is the source of truth.

## Start here

1. `PROJECT_ARCHITECTURE_RU.md` — full repo mental model and hard invariants.
2. `PROJECT_MAP_RU.md` — where things live and what is *not* source of truth.
3. `ModSources/InfiniCrafterLocal/FOLDER_DOCS_RU.md` — C# tModLoader runtime entry map.
4. `LocalGenerator/PROJECT_ARCHITECTURE_RU.md` — Python generator/boundary map.
5. Then read the actual source files named below before editing.

Current source scan for this snapshot: C# mod source has 55 `.cs` files; `LocalGenerator/infini_local` has 52 `.py` files; `LocalGenerator/tests` has 72 `test*.py` files. If counts differ, trust the live tree and update docs.

## One-sentence architecture

`LLM/Python authors and validates GeneratedItemData + VfxManifest; C# tModLoader runtime only applies explicit supported fields with bounded execution, multiplayer authority, registry sync, asset HTTP sync, and safety clamps.`

## Absolute rules — do not violate

- **No prose/name/tooltip/prompt gameplay router in C#.** Names, flavor, prompt text, ToyIdentity, debug strings and tooltip prose are presentation/debug only.
- **C# executes only explicit contract fields**: `gameplay`, `attack`, `accessory`, `armor`, `visual`, `vfxManifest`, `soundProfile`, asset paths, runtime enums/codes.
- **MP client never commits authoritative `GeneratedItemData`.** Client sends craft intent; host/server consumes real inventory slots, generates, registers, ACKs.
- **No PNG/JSON bulk through Terraria packets.** Packets carry ids/baseUrl/filenames/compact visual state; bytes move via HTTP `/get_asset`.
- **Generated registry is world-scoped.** Do not leak generated parents/items/assets across worlds.
- **Unknown/future fields are inert until wired.** Preserve for local cache/debug if useful; do not silently map to gameplay.
- **Runtime child projectiles are bounded.** Explicit count/depth only; no nested generated mini-item authoring; no prose fallback.
- **Do not add movementCode/effectCode/onHitCode by vibes.** Update Python authoring contract, C# limits, normalize/apply/runtime, tests, and docs together.
- **Do not claim a second model-judge exists unless code implements it.** Architecture ideas are not runtime facts.

## Source-of-truth files

### C# tModLoader runtime

- Root/packets/limits: `ModSources/InfiniCrafterLocal/InfiniCrafterLocal.cs`, `Common/InfiniNetPacketIds.cs`, `Common/InfiniRuntimeLimits.cs`, `Common/InfiniTerrariaSentinels.cs`.
- Data contract: `Common/Models/GeneratedItemData*.cs`, `Common/Models/VfxManifestSpec.cs`.
- Generator boundary/assets/registry: `Common/Services/GeneratorClient.cs`, `GeneratedItemRegistryService.cs`, `GeneratedAssetSyncService.cs`, `RuntimeSpriteCache.cs`.
- Craft/MP/player state: `Common/Players/InfiniCraftPlayer*.cs`, `GeneratedHeldItemDrawLayer.cs`.
- Runtime item/projectile: `Content/Items/GeneratedItem.cs`, `GeneratedArmorItems.cs`, `GeneratedExtractinatorMaterial.cs`, `Content/Projectiles/GeneratedProjectile*.cs`.
- VFX/audio: `Common/VFX/*`, `Common/Audio/*`.

### Python LocalGenerator

- Endpoint/boundary: `LocalGenerator/infini_local/services/combine_endpoint.py`, `web/server.py`.
- Main pipeline: `pipelines/combine_pipeline.py`, `combine_orchestrator.py`, `llm_authoring_pipeline.py`, `repair_orchestrator.py`, `final_normalize.py`, `generation_debug.py`.
- Runtime compiler/contracts: `core/runtime_authoring/`, `core/result_models.py`, `core/contract_versions.py`, `core/balance_policy.py`, `core/balance_report.py`, `core/vfx_manifest.py`, `core/effect_catalog.py`.
- Assets/storage: `services/asset_sync_service.py`, `services/visual_asset_pipeline.py`, `storage/world_storage.py`, `storage/trace_tools.py`.
- Contract tests: `LocalGenerator/tests/test_*contract*.py`, MP tests, replay tests, typed-result tests.

## If you change X, also check Y

| Change area | Must inspect/update |
|---|---|
| New runtime family / movement / effect / onHit | `core/runtime_authoring/`, `GeneratedItemData.Model/Normalize/Apply.cs`, `InfiniRuntimeLimits.cs`, `GeneratedProjectile*.cs`, tests, docs |
| Generated item stats/equipment/tool behavior | Python `set_item_stats` compile path, `GeneratedItemData.Apply.cs`, `GeneratedItem.cs`, save/net JSON profiles |
| Multiplayer craft | `InfiniNetPacketIds.cs`, `InfiniCrafterLocal.HandlePacket`, `InfiniCraftPlayer.Multiplayer.cs`, registry sync tests |
| Asset delivery/sprites | Python `asset_sync_service.py`, C# `GeneratedAssetSyncService.cs`, `RuntimeSpriteCache.cs`, `/get_asset`, `RecipeMeta.AssetFiles` |
| VFX/audio | Python `vfx_manifest.py`/sound profile path, C# `VfxManifestSpec.cs`, `InfiniVfxRuntime.cs`, `InfiniSoundLibrary.cs` |
| Balance/repair/provenance | `balance_policy.py`, `balance_report.py`, `result_models.py`, `core/runtime_authoring/`, debug/applied trace docs |
| Folder docs | Read source first, then update docs. Never copy stale `FOLDER_DOCS_RU.md` wording forward. |

## What not to treat as architecture

- `.tml-build-cache/`, `.nuget/`, `obj/`, `bin/`, `build_logs/`.
- `agent_reports/` and old web research dumps — useful history, not current source truth.
- Generated recipe/sprite outputs — artifacts, not contracts.
- Old `FOLDER_DOCS_RU.md` placeholders — if found, replace or ignore until source-verified.

## Extra architecture risk notes

- This is a **server-authoritative** multiplayer design: the phrase means host/server owns craft commit and generated registry authority.
- Internal Python flow still has `dict[str, Any]` / dicts / dictionaries in many stages. Typed result models are helper boundaries, not a full type-safe pipeline yet.
- If you change runtime contracts, do not stop at one layer. Follow the “If you change X, also check Y” table above and verify code anchors exist.

## Native gameplay sync contract

Generated items must behave like normal tModLoader items after hydration.

Hydration phase:
- server sends sanitized generated item definition / registry entry;
- server exposes baked assets through `/get_asset`;
- client downloads and caches required PNG/JSON/VFX assets;
- client stores generated item spec by `generatedItemId` / runtime id.

Gameplay phase:
- item use and projectile spawning use normal tModLoader/Terraria hooks;
- Terraria/tML syncs projectile/world state natively;
- generated projectiles carry only compact ids/scalar state needed to resolve local cached specs;
- no full `GeneratedItemData`, full `AttackSpec`, `VfxManifestJson`, `visualKit`, prompts, debug data, or PNG bytes in normal combat/projectile packets.

Missing data:
- if local spec/assets are missing, request hydration and use safe fallback/pending behavior;
- do not stream full definitions repeatedly through combat packets.

Allowed full/sanitized data:
- initial registry sync;
- item definition / plan hydration as background sync;
- explicit debug/export commands;
- rare emergency fallback behind config.

Full definition / plan hydration requirements:
- keyed per `generatedItemId` / `specHash`-equivalent identity;
- deduplicated against local cache;
- coalesced while request is in-flight;
- cached after success;
- never repeated per projectile, per hit, or per VFX event;
- debug counters expose `inFlight`, `cacheHit`, `cacheMiss`, `retry`, and `duplicateSuppressed` for definitions and assets.

