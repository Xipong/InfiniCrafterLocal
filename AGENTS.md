# AGENTS.md — read this before touching InfiniCrafterLocal

This repository is easy to break by "reasonable" agent guesses. Do not infer architecture from old reports, build caches, or generated artifacts. Code is the source of truth.

## Start here

1. `PROJECT_ARCHITECTURE_RU.md` — full repo mental model and hard invariants.
2. `PROJECT_MAP_RU.md` — where things live and what is *not* source of truth.
3. `ModSources/InfiniCrafterLocal/FOLDER_DOCS_RU.md` — C# tModLoader runtime entry map.
4. `LocalGenerator/PROJECT_ARCHITECTURE_RU.md` — Python generator/boundary map.
5. Then read the actual source files named below before editing.

Do not pin hand-counted source/test totals here: use the live tree when a count matters. Manual counts become stale after every extraction and are not architecture.

## One-sentence architecture

`LLM/Python authors and validates GeneratedItemData + VfxManifest; C# tModLoader runtime only applies explicit supported fields with bounded execution, multiplayer authority, registry sync, asset HTTP sync, and safety clamps.`

## Absolute rules — do not violate

- **No prose/name/tooltip/prompt gameplay router in C#.** Names, flavor, prompt text, ToyIdentity, debug strings and tooltip prose are presentation/debug only.
- **C# executes only explicit contract fields**: `gameplay`, `attack`, `accessory`, `armor`, `visual`, `vfxManifest`, exact `attack.sound*`, asset paths, runtime enums/codes.
- **MP client never commits authoritative `GeneratedItemData`.** Client sends craft intent; host/server consumes real inventory slots, generates, registers, ACKs.
- **No PNG/JSON bulk through Terraria packets.** Packets carry ids/baseUrl/filenames/compact visual state; bytes move via HTTP `/get_asset`.
- **Generated registry is world-scoped.** Do not leak generated parents/items/assets across worlds.
- **Unknown/future fields are inert until wired.** Preserve for local cache/debug if useful; do not silently map to gameplay.
- **No internal legacy compatibility by default.** This is a private single-instance project that may start clean: do not keep old import/re-export facades, deprecated internal payload shapes, or data migrations unless a current external contract demonstrably requires them.
- **Runtime child projectiles are bounded.** Explicit count/depth only; no nested generated mini-item authoring; no prose fallback.
- **Do not add movementCode/effectCode/onHitCode by vibes.** Update Python authoring contract, C# limits, normalize/apply/runtime, tests, and docs together.
- **Do not claim a second model-judge exists unless code implements it.** Architecture ideas are not runtime facts.
- **New gameplay capability must be a small vertical slice.** Read `docs/RUNTIME_VERTICAL_SLICES_RU.md`: one exact authored field/enum, one Python owner, one C# executor owner, one end-to-end test. Do not build a generic trigger/action/state framework to host unrelated mechanics.
- **Keep ownership obvious.** Derived/debug views may describe authored mechanics, but they are not a second writable contract. Do not hide gameplay derivation behind metaprogramming, reflection or cross-module semantic graphs.
- **Do not change sparse-output semantics.** Explicitly authored defaults/zeroes remain meaningful and must keep provenance; the compiler may fill omitted fields but must not erase intentional explicit values.
- **Prompt compaction must preserve sentinel semantics.** Never collapse fields such as `pierce`, use timing, `on_expire`, family-only knobs or explicit zeroes to bare numeric ranges. Keep `criticalValueSemantics` and its prompt-contract tests current.
- **Balance modes have one policy owner:** `LocalGenerator/infini_local/core/balance_mode.py`. Default is `safety`; `normalize` is opt-in legacy soft normalization; `report` is diagnostic. Do not copy mode strings or balance formulas into new modules.
- **Planner helpers must describe executable truth.** `spawn_temporary_helper_projectile` is a short-lived generated projectile, not a persistent minion/sentry. Do not re-advertise unsupported buff/slot/persistence lifecycle.
- **One authored visual contract.** The Visual Director writes strict `visualKit`: one top-level prompt per visual role plus shared style/palette/silhouette/VFX intent. Only `visualKit.bakedAssets` decides optional asset delivery mode; nested role prompts and non-canonical mirrors are legacy-only and must be migrated or rejected. Do not add another writable mirror.
- **Stage handoffs use optimal redundancy.** Visual receives accepted item intent plus raw parent physical/visual facts. VFX+Sound receives accepted concept/gameplay/attack/audio facts plus the full canonical `VisualAssetKit`. Repeat clean facts needed by the stateless role, but never pass repair/debug/compiler receipts, classifier/tag packets, prior transcripts, or parallel visual mirrors. VFX owns bounded event slots (including `soundCue`); Planner-authored sound catalog IDs remain accepted runtime facts.
- **Code does not author parent fusion.** Pass parent facts and preserve planner/Visual Director fields, but never decide whether a parent stays literal, is attached, fused, disassembled, or represented by parts. Do not add material locks, parent-type visual routers, or per-item fusion `if` chains. Code may enforce JSON/asset-role/technical sprite constraints and reject unsupported gameplay promises only.
- **Runtime multiplicity is not sprite multiplicity.** `shotCount`/`splitCount` create runtime copies; projectile and child PNG prompts describe one body unless an explicit composite projectile family is authored.
- **Weapon image topology preserves authored structure.** Read `docs/ZIMAGE_WEAPON_TOPOLOGY_RU.md`: Visual Director authors a positive physical topology contract, and Python must deliver it to the image backend without adding negative `mirror`/`duplicate` topology words or imposing one grip, one blade, one continuous body, or any other preferred construction. Literal furniture attachments, disassembled parent parts, paired/double-ended forms, and other weird authored structures are all valid. Do not add weapon-name tables, VL judges, or automatic semantic retry loops.
- **Read the pre-livetest traces before changing author/image contracts:** `docs/PRE_LIVETEST_MANUAL_TRACES_V12_RU.md`.
- **Charge-release and sentry are separate finite slices.** Read `docs/CHARGE_RELEASE_SENTRY_RUNTIME_RU.md`. Do not merge them into a generic scheduler/state graph or author nested AttackSpec.
- **Shared GeneratedProjectile static-set limit:** do not set sentry/minion static sets globally on the shared projectile type; that would affect every generated projectile. A dedicated projectile type is required before promising those vanilla synergies.

## Source-of-truth files

### C# tModLoader runtime

- Root/packets/limits: `ModSources/InfiniCrafterLocal/InfiniCrafterLocal.cs`, `Common/InfiniNetPacketIds.cs`, `Common/InfiniRuntimeLimits.cs`, `Common/InfiniTerrariaSentinels.cs`.
- Data contract: `Common/Models/GeneratedItemData*.cs`, `Common/Models/VfxManifestSpec.cs`.
- Generator boundary/assets/registry: `Common/Services/GeneratorClient.cs`, `GeneratedItemRegistryService.cs`, `GeneratedAssetSyncService.cs`, `RuntimeSpriteCache.cs`.
- Craft/MP/player state: `Common/Players/InfiniCraftPlayer*.cs`, `GeneratedHeldItemDrawLayer.cs`.
- Runtime item/projectile: `Content/Items/GeneratedItem.cs`, `GeneratedArmorItems.cs`, `Content/Projectiles/GeneratedProjectile*.cs`.
- VFX/audio: `Common/VFX/*`, `Common/Audio/*`.

### Python LocalGenerator

- Endpoint/boundary: `LocalGenerator/infini_local/services/combine_endpoint.py`, `web/server.py`.
- Main pipeline: `pipelines/combine_pipeline.py`, `llm_authoring_pipeline.py`, `final_normalize.py`, `generation_debug.py`.
- Runtime compiler/contracts: `core/runtime_authoring/`, `core/result_models.py`, `core/contract_versions.py`, `core/balance_mode.py`, `core/balance_policy.py`, `core/balance_report.py`, `core/vfx_manifest.py`, `core/effect_catalog.py`.
- Assets/storage: `services/asset_sync_service.py`, `services/visual_asset_pipeline.py`, `storage/world_storage.py`, `storage/trace_tools.py`.
- Contract tests: `LocalGenerator/tests/test_*contract*.py`, MP tests, replay tests, typed-result tests.

## If you change X, also check Y

| Change area | Must inspect/update |
|---|---|
| New runtime family / movement / effect / onHit | canonical names/opcodes in `core/runtime_executor_vocabulary.py`, family profiles in `core/runtime_family_policy.py`, authoring-only aliases in `core/runtime_authoring/vocabulary.py`, schema/compiler, `GeneratedRuntimeFamilyPolicy.cs`, executor code, tests, docs. Do not add downstream alias tables or re-export barrels. |
| Generated item stats/equipment/tool behavior | Python `set_item_stats` compile path, `GeneratedItemData.Apply.cs`, `GeneratedItem.cs`, save/net JSON profiles |
| Multiplayer craft | `InfiniNetPacketIds.cs`, `InfiniCrafterLocal.HandlePacket`, `InfiniCraftPlayer.Multiplayer.cs`, registry sync tests |
| Asset delivery/sprites | Python `asset_sync_service.py`, C# `GeneratedAssetSyncService.cs`, `RuntimeSpriteCache.cs`, `/get_asset`, `RecipeMeta.AssetFiles` |
| VFX/audio | Python `vfx_manifest.py`, `sound_catalog.py`, exact VFX vocabulary owners; C# `VfxManifestSpec.cs`, `VfxCanonicalVocabulary.cs`, `RuntimeColorPolicy.cs`, `InfiniVfxRuntime.cs`, `InfiniSoundLibrary.cs`. Do not add profile/prose fallbacks. |
| Balance/repair/provenance | `balance_mode.py`, `balance_policy.py`, `balance_report.py`, `result_models.py`, `core/runtime_authoring/`, debug/applied trace docs. Keep mode selection out of formula owners. |
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


## Restricted/dependency-poor sandbox: first command

Run this before pytest in ChatGPT/web sandboxes or unknown containers:

```bash
python tools/validate_sandbox.py
```

- The tool uses only the Python standard library, never loads operator config, never starts LLM/image/server backends, and bounds every child check.
- Read its JSON. If `fullSuiteAvailable=false`, **do not run full pytest or release validation in that environment**. Missing pytest/Pydantic/Pillow/Hypothesis is an environment limitation, not a product failure.
- `ok=true` with `coverage="portable-static"` proves syntax/JSON, config-registry drift, C# static contracts, project hygiene, bounded subprocesses/no import-time environment mutation in `test_*.py`, plus the exact allowlisted import-time sandbox bootstrap in `tests/conftest.py` only.
- Portable success is never release readiness: `releaseReady` remains false. Run `python tools/validate_release.py` in the dependency-complete project environment for full pytest/parity/mutation/runtime gates.
- Do not retry dependency failures, install packages from the network without permission, or replace unavailable dynamic gates with invented output.


## Contract safety stack (v18)

- Raw LLM calls валидируются до repair через `core/runtime_authoring/engine_call_contracts.py`; compiled/wire JSON — через `core/boundary_models.py`.
- `core/runtime_authoring/function_contract_registry.py` — canonical owner function/param inventory, provider/prompt projection, wire obligations, repair groups, normalized IR grammar and typed lowerer edges. `schema.py` owns family/affordance/numeric and cross-param policies, not the catalog.
- `contracts/schemas/` и `contracts/config_registry.json` — generated evidence, не writable gameplay contract и не C# codegen.
- Critical field policy живёт в `contracts/field_lifecycle.json`; фактические compiler/projection/DTO/normalize/network/executor/child stages извлекает `tools/contract_parity.py`.
- При runtime-contract правке обязательны `contract_parity`, `mutation_contract_gate`, `semantic_runtime_diff`, `historical_replay` и `runtime_impact_report`.
- `agentctl verify --changed` использует impact-focused pytest-наборы; полный sharded pytest оставлен для финальной/release-проверки. C# diff должен идти через parity/delivery/mutation/static-C# gates и настоящий build, а не через глобальный Python suite. Не возвращай full suite в `alwaysChecks` или C# inner-loop.
- Hypothesis tests проверяют общие invariants, не библиотеку примеров оружия. Тест нельзя привязывать к старому façade/partial-файлу, если canonical owner и результат сохраняются.
- `tools/agentctl.py verify --changed` выбирает gates по diff. C#-чувствительная правка без реального tML build остаётся `blocked`; её нельзя назвать runtime-ready.
- Новый engine call должен расширяться через canonical catalog; новый executable field — через полный применимый lifecycle. См. `docs/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md`.
- Ruff/Pyright нельзя делать зелёными массовыми ignore. Pyright coverage расширяется постепенно через явные contract-boundary типы.
- Перед передачей snapshot запускай `05_VALIDATE_RELEASE_STACK.bat` на Windows. `releaseReady=true` возможно только после настоящего tML build.
