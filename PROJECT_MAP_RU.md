# InfiniCrafterLocal v0.4.237 — repo map for agents

Цель файла: быстро направить агента к source-of-truth и не дать перепутать C# runtime, Python authoring и исторический мусор.

## Read order

1. `AGENTS.md` — hard rules and edit routing.
2. `PROJECT_ARCHITECTURE_RU.md` — C# mod architecture + boundaries.
3. `LocalGenerator/PROJECT_ARCHITECTURE_RU.md` — Python generator architecture.
4. Actual source files named in the tables below.
5. Tests/contracts only after source map; old reports are supporting history, not proof.

## Top-level map

```text
ModSources/InfiniCrafterLocal/       active Terraria/tModLoader C# runtime
LocalGenerator/                      Python LocalGenerator: LLM authoring, validation, assets, /combine
LocalGenerator/tests/                contract/regression tests for Python and C# surface assumptions
docs/                                supplemental design/TODO/reference docs, not always current runtime proof
agent_reports/                       historical agent reports and web research; never source of truth
.tml-build-cache/, .nuget/, obj/      build/dependency/generated cache; do not read as architecture
build_logs/                          logs only
```

## Core boundary

```text
LLM/Python authoring
  -> validates/normalizes/repairs explicit GeneratedItemData + VfxManifest
  -> C# tModLoader applies supported fields only
  -> Terraria runtime executes bounded item/projectile/VFX behavior
```

C# is not a generator, not a prompt interpreter, and not a fallback author.

## C# source-of-truth: `ModSources/InfiniCrafterLocal`

| Path | Role |
|---|---|
| `InfiniCrafterLocal.cs` | root `Mod`, version, singleton services, packet router, `Mod.Call`, cleanup |
| `Common/InfiniNetPacketIds.cs` | packet ids; MP request/ACK/cancel/projectile/held sync ids |
| `Common/InfiniRuntimeLimits.cs` | runtime API/current movement/effect/onHit limits; `NetProseMaxChars=0` |
| `Common/Models/GeneratedItemData*.cs` | game-facing DTO, normalize, apply, JSON profiles, debug/applied trace |
| `Common/Models/VfxManifestSpec.cs` | frozen VFX manifest DTO/normalization |
| `Common/Services/GeneratorClient.cs` | HTTP adapter to LocalGenerator `/combine`, cache recovery, deliverable checks |
| `Common/Services/GeneratedItemRegistryService.cs` | per-world registry and generated item sync |
| `Common/Services/GeneratedAssetSyncService.cs` | HTTP asset sync by final filenames; no packet bulk |
| `Common/Services/RuntimeSpriteCache.cs` | lazy PNG loader/cache/fallback validation |
| `Common/Players/InfiniCraftPlayer*.cs` | station transaction, refunds, MP authority, utility buff/mobility |
| `Content/Items/GeneratedItem.cs` | per-instance generated item proxy and gameplay hooks |
| `Content/Projectiles/GeneratedProjectile*.cs` | executable bounded projectile runtime + compact net sync |
| `Common/VFX/*`, `Common/Audio/*` | VFX manifest runtime, renderer registry, sound selection/bridges |

## Python source-of-truth: `LocalGenerator/infini_local`

| Path | Role |
|---|---|
| `services/combine_endpoint.py`, `web/server.py` | HTTP/API boundary including `/combine` and utility routes |
| `pipelines/combine_pipeline.py` | main combine orchestration, gameplay/runtime/visual assembly seams |
| `pipelines/llm_authoring_pipeline.py` | LLM authoring and targeted repair entrypoints |
| `core/runtime_authoring.py` | compiles `runtimePlan.engineCalls` into game-facing patches; validates runtime plan |
| `core/result_models.py` | typed helper result models (`RuntimeCompileResult`, `ClampRecord`, `RepairResult`, balance report) |
| `core/contract_versions.py` | contract stamp constants; observability, not automatic feature support |
| `core/balance_policy.py`, `core/balance_report.py` | soft-balance authority and debug report shape |
| `core/vfx_manifest.py`, `core/effect_catalog.py` | VFX/audio/runtime authoring contracts and compact enums/catalogs |
| `services/asset_sync_service.py`, `services/visual_asset_pipeline.py` | final asset filename selection and visual asset generation/serving |
| `storage/world_storage.py`, `storage/trace_tools.py` | world-scoped recipe storage and trace/debug helpers |

## Agent traps

- Do not summarize old `agent_reports/` as current behavior.
- Do not treat `docs/TODO*` or “future-disabled” ideas as implemented runtime.
- Do not claim “second model judge” exists unless a source file actually implements the call path.
- Do not assume typed data flow is complete: typed result models exist, but many internal stages still carry `dict[str, Any]`; be careful with field names and provenance.
- Do not turn visual or item names into mechanics. Explicit runtime contract only.
- Do not edit LocalGenerator and C# independently when changing runtime capabilities.

## Boundary matrix

| Boundary | Good | Bad |
|---|---|---|
| Python authoring -> C# | explicit fields + contract stamps + final assets | prompt/prose/name-driven mechanics |
| MP client -> server | request id + compact real input refs | client-authored `GeneratedItemData` commit |
| Server/client asset sync | final `.png/.json` filenames + `/get_asset` | raw asset bytes through Terraria packets |
| Registry/cache | current-world generated records | cross-world generated parent leakage |
| Repair path | code structural repair + targeted runtime retry with debug provenance | hidden second author silently rewriting item identity |

## Agent verification checklist

- Treat this file as navigation only; source code is source of truth.
- For C# runtime claims, read files under `ModSources/InfiniCrafterLocal`.
- For Python authoring claims, read files under `LocalGenerator/infini_local`.
- MP craft is **server-authoritative**; do not design a client commit path.
- If you change X, also check Y: use `AGENTS.md` and `PROJECT_ARCHITECTURE_RU.md` decision tables, not guesses.
- Do not claim a second model-judge exists unless source implements it.
