# InfiniCrafterLocal v0.4.237 — архитектура Terraria/tModLoader части

Этот документ описывает именно `ModSources/InfiniCrafterLocal`: C#-мод tModLoader, runtime предметов, projectile/VFX/audio, UI станции, multiplayer и asset sync. Build cache, `.tml-build-cache`, `.nuget`, `build_logs`, `agent_reports` и Python-реализация генератора здесь не считаются архитектурой мода.

## READ THIS FIRST — чтобы агент не сломал архитектуру

Если ты агент и хочешь что-то менять, сначала прочитай это, потом source-файлы. Не угадывай по названиям и старым отчётам.

**Ментальная модель:** Python/LLM авторит предмет как данные; Python валидирует/нормализует/ремонтирует contract; C# только исполняет поддержанный подмножество contract в Terraria.

Жёсткие правила:

1. **C# не prose parser.** Нельзя выводить gameplay из `name`, tooltip, prompt, flavor, `ToyIdentity`, debug/prose/script строк.
2. **Runtime исполняет только явные поля:** `Gameplay`, `Attack`, `Accessory`, `Armor`, `VfxManifest`, `Visual`, `SoundProfile`, sprite paths, bounded enum/code fields.
3. **MP server-authoritative:** клиент отправляет craft intent; host/server берёт реальные inventory slots, генерирует, регистрирует, отправляет ACK/FAIL.
4. **Assets не идут bulk-packet’ами:** Terraria packets несут id/baseUrl/filenames/compact visual state; `.png/.json` bytes скачиваются через HTTP `/get_asset`.
5. **Registry world-scoped:** generated parents/items/assets нельзя смешивать между мирами.
6. **Future/unknown fields inert:** можно сохранять в local cache/debug, но нельзя тихо превращать в gameplay.
7. **Child projectile runtime bounded:** explicit count/depth only, без nested generated mini-item authoring и без prose fallback.
8. **Новый runtime capability = синхронный контракт:** Python authoring + C# limits/Normalize/Apply/runtime + tests + docs.
9. **RuntimeArchetype/runtimeContract are data contracts:** `runtimeArchetype` may enrich supported finite families (currently boomerang/yoyo/flail/whip/held), `runtimeContract` records feel/sync/promise truth, and unsupported families stay inert/preserved.
10. **Если docs спорят с code, code wins.** Обнови docs после проверки source.

## Коротко

InfiniCrafterLocal — tModLoader-мод, который добавляет ручную станцию InfiniCraft. Игрок кладёт два предмета в UI, мод собирает компактный снимок входов, отправляет его в локальный HTTP `LocalGenerator` (`/combine`), получает `GeneratedItemData`, затем выдаёт один из runtime-proxy предметов. C# не является генератором дизайна: он применяет уже скомпилированный и провалидированный контракт, держит safety, синхронизацию, визуализацию и gameplay execution.

Главный инвариант:

```text
LLM/Python authoring -> validated GeneratedItemData/VfxManifest -> C# hard-runtime apply
```

C# runtime НЕ должен:
- парсить prose/tooltip/prompt/script-like поля в gameplay;
- принимать `GeneratedItemData` от multiplayer-клиента как authoritative commit;
- пересылать PNG/JSON bulk через Terraria packets;
- silently менять authored mechanics, кроме bounded normalization/safety clamp.

C# runtime должен:
- применять только явные числовые/enum/runtime поля (`runtimeFamily`, movement/effect/onHit codes, stats, VFX slots);
- сохранять unknown/future top-level JSON в local cache/debug, но вырезать bulk из network/player-save payloads;
- держать generated item registry world-scoped;
- в MP генерировать только на host/server, а клиенту отправлять intent + получать ACK.

## Входные точки мода

### `InfiniCrafterLocal.cs`

`InfiniCrafterLocalMod` — корневой `Mod`:
- `ModVersion = "0.4.237"`.
- `Load()` создаёт singleton-сервисы:
  - `GeneratorClient` — HTTP boundary к LocalGenerator;
  - `RuntimeSpriteCache` — lazy PNG loader;
  - `GeneratedAssetSyncService` — LAN/HTTP asset sync;
  - `GeneratedItemRegistryService` — per-world registry generated items.
- `HandlePacket()` маршрутизирует все mod packets по `InfiniNetPacketIds`.
- `Call()` даёт внешний API другим модам: `IsGeneratedItem`, `TryGetGeneratedItemData`, `GetGeneratedSummary`; `RegisterGeneratedParentHint` зарезервирован, runtime mutation пока нет.
- `Unload()` чистит MP caches, draw sync caches и сервисы.

### Packet ids (`Common/InfiniNetPacketIds.cs`)

Единый реестр packet ids:

| id | Имя | Назначение |
|---:|---|---|
| 1 | `NotifyGeneratedAssets` | peer notification: base URL + asset filenames |
| 2 | `NotifyGeneratedItem` | registry item sync server -> client |
| 3 | `RequestGeneratedRegistry` | client catch-up registry request |
| 4 | `CraftCommitResult` | ACK/FAIL server-authoritative craft |
| 5 | `RequestServerCraft` | MP client craft intent -> host/server |
| 6 | `RequestGeneratedRegistryForceAssets` | registry catch-up + retry assets |
| 7 | `SyncGeneratedUtilityBuff` | generated utility buff/cooldown state |
| 8 | `SyncGeneratedProjectileVisual` | compact projectile visual context |
| 9 | `SyncGeneratedProjectileVfxEvent` | hit/kill VFX event relay |
| 10 | `RequestGeneratedItemById` | one generated item catch-up |
| 11 | `SyncGeneratedHeldItemPresentation` | remote held id+pose only; registry/cache restores sprite/style |
| 12 | `CancelServerCraft` | client cancel/timeout for server craft |

## High-level runtime flow

```text
InfiniCore in inventory
  -> inventory UI station appears
  -> player moves two explicit inputs into A/B slots
  -> TryStartCraftFromStation()

Singleplayer / host path:
  -> GeneratorClient.Prepare(a,b,player)
  -> Task.Run(GeneratorClient.GeneratePreparedBlocking)
  -> POST http://127.0.0.1:5055/combine
  -> GeneratedItemData.FromJson + Normalize + StampCurrentWorld
  -> SpawnGeneratedItemServerSide()
  -> GeneratedItems.PublishGeneratedItem(data)
  -> AssetSync.NotifyNewItemCrafted(data)
  -> Terraria item sync / local reveal

Multiplayer client path:
  -> BeginRemoteServerCraft(a,b)
  -> packet RequestServerCraft(requestId, compact item refs)
  -> server reconstructs/takes real inventory slots
  -> server runs same GeneratorClient path
  -> server commits generated item and sends CraftCommitResult
  -> clients hydrate registry/assets in background
```

## Data contracts

### `GeneratedItemData` (`Common/Models`)

`GeneratedItemData` — главный wire/runtime contract. Он разделён partial-файлами:

| Файл | Роль |
|---|---|
| `GeneratedItemData.Model.cs` | DTO/schema: identity, recipe meta, gameplay, accessory/armor, attack, visual, presentation genome, sound profile, extension data |
| `GeneratedItemData.Normalize.cs` | clamps, compat migrations, runtime API support, path/status normalization |
| `GeneratedItemData.Apply.cs` | перенос DTO в Terraria `Item`: damage class, use style, stats, armor/accessory/material/tool/proxy fields |
| `GeneratedItemData.cs` | JSON profiles: full/local-cache/network/player-save, placeholder, stripping bulk |
| `GeneratedItemData.Debug.cs` | applied trace/debug JSON для анализа applied-vs-authored |

Ключевые поля:
- `RuntimeApiVersion` должен соответствовать `InfiniRuntimeLimits.RuntimeApiCurrent` (`v0.4.47`) или быть совместимым пустым legacy.
- `RecipeMeta.WorldScoped/WorldId` отделяет generated registry по миру.
- `RecipeMeta.AssetBaseUrl/AssetFiles` — транспортные поля, не authorship.
- `Gameplay` — concrete Terraria item stats/utility behavior: kind, damage, use times, use style, buffs, alt use, tools, mobility, extractinator, conditions.
- `Accessory` / `Armor` — applied equipment stats and armor set info.
- `Attack` — explicit generated attack executor contract. `Attack.Enabled` означает generated runtime executor, а не сам факт damage. Melee/tool hitbox может быть vanilla-only.
- `Visual` / `PresentationGenome` — inventory/world/held visual identity and sprite metadata.
- `VfxManifest` — frozen VFX manifest for projectile lifecycle.
- `ExtensionData` сохраняет Python-authored future fields в local cache/debug, чтобы C# не стирал неизвестный контракт.

### Runtime limits (`Common/InfiniRuntimeLimits.cs`)

```text
RuntimeApiCurrent = v0.4.47
MaxSupportedMovementCode = 18
MaxSupportedEffectCode = 15
MaxSupportedOnHitCode = 18
NetProseMaxChars = 0
```

`NetProseMaxChars = 0` — важный архитектурный сигнал: descriptive/script-like strings не являются executable network state.

### Terraria sentinels (`Common/InfiniTerrariaSentinels.cs`)

Named constants for numeric Terraria fields with no public `None`: buff type 0, prefix 0, first valid item/projectile type, max supported use style. Не размазывать magic numbers по коду.

## Craft station and player state

### `Content/Items/InfiniCore.cs`

`InfiniCore` — key item/station key:
- recipe: 20 wood + 1 Fallen Star;
- right click открывает inventory and points user to station panel;
- itself cannot be ingredient;
- favorited/air/invalid items are rejected.

### `Common/UI/InfiniCraftStationUISystem.cs`

Client-only `ModSystem` рисует inventory station:
- two explicit slots A/B;
- button Craft;
- Clear inputs;
- progress bar up to 240s;
- no hidden “first two inventory items” behavior.

UI only manipulates `InfiniCraftPlayer.InputA/InputB`; actual generation starts in player logic.

### `Common/Players/InfiniCraftPlayer*.cs`

`InfiniCraftPlayer` is the craft transaction state machine:

| Partial | Роль |
|---|---|
| `InfiniCraftPlayer.cs` | state fields, constants, inventory asset prefetch, registry catch-up |
| `InfiniCraftPlayer.Station.cs` | A/B slot moves, station start, refunds |
| `InfiniCraftPlayer.CraftState.cs` | lifecycle, retry/cache recovery, world-exit protection, spawn commit, audio guard |
| `InfiniCraftPlayer.Multiplayer.cs` | server-authoritative craft protocol, generated buff sync, dedupe/cancel/ACK |
| `InfiniCraftPlayer.Mobility.cs` | generated utility buff and mobility execution (`recall_home`, `blink_to_cursor`) |

Important craft constants:
- `CraftDurationTicks = 240 * 60` — UI estimate/progress, not artificial delay after ready result.
- `CraftRecoveryTimeoutTicks = 20 * 60 * 60` — recovery window for long/cache-delayed generation.
- `RemoteServerCraftTimeoutTicks = CraftRecoveryTimeoutTicks`.

World-exit safety:
- pending station inputs/in-flight refunds are saved or returned;
- `AbortTransientCraftForWorldExit()` cancels remote server craft if needed;
- world unload clears presentation sync caches.

MP authority:
- client sends only compact item refs: item type, prefix, stack, generated id, display name;
- server finds and consumes real inventory slots 0..49;
- generated parent ids must match server registry;
- client-side generated commits fail closed.

## Generator boundary

### `Common/Services/GeneratorClient.cs`

`GeneratorClient` is not the authoring implementation. It is a C# HTTP adapter:
- endpoint default: `http://127.0.0.1:5055/combine`;
- request body contains `itemA`, `itemB`, `player`, `worldId`, `worldName`, `modVersion`, `multiplayer`, `craftInputPolicy`;
- `ToWireItem()` dumps base item identity/stats and generated parent data if input is already generated;
- reforge prefixes are intentionally ignored for recipe identity/cache/balance, while refund item keeps real prefix;
- generation uses cache-first/cached recovery paths so completed recipes can be delivered after HTTP timeout races.

Fatal recipe failures:
- 409, 422, 424, 428, 500 are treated as explicit non-retry commit failures by this client path.
- Returned payload must pass `IsDeliverableGeneratedData`: non-empty name, non-placeholder id, no fallback/failed source mode.

Asset sharing:
- `AssetBaseUrlForSharing()` uses `INFINI_ASSET_PUBLIC_BASE_URL` if set;
- otherwise guesses LAN/Radmin-friendly URL from endpoint (`26.x` preferred if present).

## Registry, save, asset sync

### `GeneratedItemRegistryService`

Per-world registry, stored under Terraria save path:

```text
<Main.SavePath>/InfiniCrafterLocal/generated_items/*.json
```

Contracts:
- `RegisterLocal()` accepts only current-world non-placeholder generated data.
- `PublishGeneratedItem()` syncs `GeneratedItemData` once when item is created/discovered.
- Projectile/held packets then carry compact ids/state only.
- `/getinfini` catch-up sends transport clones with host asset metadata but does not overwrite server authoritative full records.
- Persisted local cache uses `ToLocalCacheJson()` to keep debug/prompt/future info useful after restart.

### `GeneratedAssetSyncService`

LAN HTTP asset sync:
- Terraria packets carry only `baseUrl + filenames`.
- Actual `.png`/`.json` bytes are downloaded in background via `GET /get_asset?file=...`.
- Cache path:

```text
<Main.SavePath>/InfiniCrafterLocal/asset_cache/*
```

Safety:
- only `.png`/`.json` filenames after `Path.GetFileName` sanitization;
- no path traversal;
- PNG magic header validation;
- max 8 MB per downloaded asset;
- no asset downloads on dedicated server.

`AssetFilesFromData()` intentionally includes final gameplay-facing files only: item sprite, asset manifest, projectile/impact/child/field sprites. Raw intermediates are not synced.

### `RuntimeSpriteCache`

Client-side lazy PNG loader:
- resolves original path, then asset cache fallback;
- validates `.png`, file size, dimensions;
- default max dimension 192 px, default max file 8 MB, default max 512 cached textures;
- caches hits and missing/bad records with retry backoff;
- placeholder texture remains fallback if runtime asset cannot load.

## Runtime item proxies

### `Content/Items/GeneratedItem.cs`

Main generated item proxy, one `ModItem` type with per-instance `GeneratedItemData`.

Responsibilities:
- clone/save/load/net payloads safely;
- `SetData()` applies DTO to `Item`, registers current-world data and optionally ensures assets;
- `CanStack()` allows stack only for same generated id + recipe key;
- tooltips show parent recipe, merge/source, flavor, generated combat summary, debug details on Shift;
- `UseItem()` applies explicit extra buffs, generated buffs, generated mobility and alt-use behavior;
- equipment hooks apply accessory/armor stats and set bonuses;
- vanilla item hitbox path remains separate from generated projectile executor;
- `Shoot()` creates `GeneratedProjectile` only when `Attack.RuntimePlanAuthored` and runtime family is projectile-like; swing stays melee-core unless explicit bounded secondary exists;
- runtime sprite draw hooks draw per-instance inventory/world PNG + visual soul aura.

### Other item proxies

| Файл | Роль |
|---|---|
| `GeneratedArmorItems.cs` | dedicated head/body/legs proxy classes inheriting `GeneratedItem` so Terraria armor slots work |
| `GeneratedExtractinatorMaterial.cs` | material proxy that supports `ExtractinatorUse` and generated data serialization |
| `InfiniCore.cs` | station key item |

## Generated projectile runtime

`Content/Projectiles/GeneratedProjectile*.cs` is split by concern. Together it is the executable generated attack runtime.

| Partial | Роль |
|---|---|
| `GeneratedProjectile.cs` | state fields, texture, NAV map, asset catch-up helper |
| `GeneratedProjectile.Runtime.cs` | defaults, `ApplyGeneratedSpec`, runtime validation, stat apply, AI loop, movement primitives |
| `GeneratedProjectile.Executors.cs` | movement executor dispatch for movement codes 0..18 |
| `GeneratedProjectile.Impact.cs` | collision, OnHit, debuffs, child projectiles, AOE, kill/impact behavior |
| `GeneratedProjectile.Visuals.cs` | registry hydration, sprite/presentation fallback, dust/light/drawing |
| `GeneratedProjectile.NetSync.cs` | lean projectile sync, visual context packets, VFX event packets, pending catch-up |
| `GeneratedVfxOverlayProjectile.cs` | timed local/remote overlay carrier for hit/kill VFX |

Runtime validation:
- projectile disables itself if it lacks authored runtime spec;
- movement/effect/onHit codes are clamped to `InfiniRuntimeLimits`;
- legacy prose/script fields are explicitly not executable;
- gameplay children are sanitized: no prompt/prose/VFX manifest inheritance, no nested generated mini-items.

Movement families:
- `0` straight;
- `1..15` basic movement variants: homing, gravity, drift, orbit, boomerang, bounce, sine, phase, accelerate, spiral, vortex, blackhole, proximity missile, returning glaive, expanding wave;
- `16` flail tether;
- `17` yoyo hover/channel;
- `18` whip lash.

OnHit families include bounded burst/split/chain/debuff/radial/aura/spore/mini-missile/vortex/blackhole/lifesteal effects. Child count/depth limits come from explicit `AttackSpec.MaxChildProjectiles` and `MaxChildDepth`.

MP projectile sync:
- Terraria vanilla projectile sync handles core projectile state;
- `SyncGeneratedProjectileVisual` sends only owner/identity + generated id; presentation is restored from registry/cache;
- `SyncGeneratedProjectileVfxEvent` relays hit/kill visual events;
- missing registry/assets trigger per-id retry-gated catch-up (`RequestGeneratedItemById` or full registry retry).

## VFX/audio layer

### `Common/Models/VfxManifestSpec.cs`

Frozen generated VFX manifest (`infini.vfx.hybrid.v14`): root + motif + emergency budget + slots + baked commands. Runtime normalizes channels/lanes/renderers and never parses `EffectName` prose as gameplay.

Slots are lifecycle-oriented:
- event/group: live/tick/hit/kill/expire;
- renderer kind: afterimage, ribbon, beam, field, particles, light, sound, etc.;
- channel/lane: motionTrail/coreGlow/ambientParticles/impactShape/impactParticles/decaySmoke/light/sound, primary/support/accent/ornament/cue;
- optional baked commands.

### `Common/VFX`

| Файл | Роль |
|---|---|
| `InfiniVfxRuntime.cs` | executes manifest slots on tick/hit/kill/draw, selects renderers, budgets channels |
| `VfxFoundation.cs` | backend abstraction: Null, vanilla Dust, ParticleLibrary backend, command structs |
| `VfxParticleSystemRegistry.cs` | ParticleLibrary system registration and particle behavior |
| `VfxRendererRegistry.cs` | renderer kind normalization and draw-cost estimates |
| `VfxParticleAddress.cs` | canonical ParticleLibrary system ids |
| `VfxContext.cs` | per-projectile VFX context snapshot |
| `InfiniVfxClientOptions.cs` | config-derived client multipliers/options |

### `Common/Audio`

| Файл | Роль |
|---|---|
| `InfiniSoundLibrary.cs` | maps explicit sound profiles/effects/codes to Terraria `SoundStyle` |
| `InfiniLuminanceSoundBridge.cs` | optional live/loop cue bridge for Luminance-style audio when available |
| `InfiniFutureSoundCatalog.cs` | future catalog seam; catalog query fields are inert unless explicit ids/paths are authored |

## Configs and commands

### Configs

`Common/Config`:
- `InfiniGameplayQolConfig` — inventory asset prefetch, runtime sprite cache limits, generated melee on-hit toggle, etc.
- `InfiniVfxClientConfig` — client VFX quality/visibility multipliers.

### Commands

`Common/Commands`:
- `/getinfini` — registry/asset catch-up;
- `/infiniitem`, `/infinicore`, `/infinidummy` — item/core/test helpers;
- `/infinicache` — sprite/cache stats, clear/reset/warm helpers;
- `/infinidump` — item/projectile runtime snapshots;
- `/infinidumppicture` — source/runtime texture bundle and HTML reports.

Commands are diagnostic/dev convenience, not the gameplay authority path.

## Where to edit — decision table for agents

| Если меняешь | Сначала читай | Обязательно проверить |
|---|---|---|
| Item stats / equipment / tools | `GeneratedItemData.Model.cs`, `GeneratedItemData.Apply.cs`, `GeneratedItem.cs` | Python `set_item_stats` compile path, save/net JSON profiles, tooltips/debug trace |
| Runtime attack family / movement / effect / onHit | `runtime_authoring.py`, `GeneratedProjectile*.cs`, `InfiniRuntimeLimits.cs` | Python contract enums, C# normalize/apply/runtime, projectile net sync, contract tests |
| Multiplayer craft | `InfiniCraftPlayer.Multiplayer.cs`, `InfiniNetPacketIds.cs`, `InfiniCrafterLocal.HandlePacket()` | client sends only intent, server consumes slots, ACK/FAIL, cancel/timeout, registry catch-up |
| Generated registry | `GeneratedItemRegistryService.cs`, `world_storage.py` | world id/scope, transport clones, no cross-world parent leakage |
| Asset/sprite sync | `GeneratedAssetSyncService.cs`, `RuntimeSpriteCache.cs`, `asset_sync_service.py` | final-only filenames, `/get_asset`, PNG validation, max sizes, no raw intermediates in packets |
| VFX/audio | `VfxManifestSpec.cs`, `InfiniVfxRuntime.cs`, `InfiniSoundLibrary.cs`, Python `vfx_manifest.py` | slot/channel/renderer normalization, sound ids, no effect-name gameplay routing |
| Repair/balance/provenance | `runtime_authoring.py`, `result_models.py`, `balance_policy.py`, `balance_report.py` | typed result models, clamp reasons, debug.applied trace, no hidden second author |
| Documentation | source files above | no stale version markers, no claims that are only in `agent_reports`, no invented model-judge |

## Boundary matrix

| Boundary | Allowed | Forbidden |
|---|---|---|
| LLM/Python -> C# | validated `GeneratedItemData`, `VfxManifest`, asset filenames, explicit runtime enum/code fields | prose-as-gameplay, prompt-script execution, hidden keyword/name routers |
| Client -> Server | craft request id + compact refs to real input items/generated parent ids | authoritative generated item JSON commit from client |
| Server -> Client | registry item sync, ACK/FAIL, compact projectile/held/VFX sync | raw PNG/JSON/prompt bulk in Terraria packets |
| Cache -> Runtime | current-world generated records + sanitized final assets | cross-world generated parents/assets, stale placeholder/fallback as deliverable result |
| Future fields -> Runtime | preserve/debug/report until implemented | silently treating unknown fields as supported mechanics |

## Directory map for agents

```text
ModSources/InfiniCrafterLocal/
  InfiniCrafterLocal.cs              root Mod singleton + packet router
  InfiniCrafterLocal.csproj          tML SDK project + ParticleLibrary/Luminance refs
  Assets/                            static placeholder/core/armor/proj PNGs
  Localization/                      en/ru hjson strings
  Common/
    Models/                          GeneratedItemData + VfxManifest contracts
    Services/                        generator HTTP, registry, asset sync, sprite cache, authority
    Players/                         station/player transaction state + MP + mobility + held draw
    VFX/                             VFX backend/runtime/renderer registries
    Audio/                           sound style mapping and optional bridge
    Commands/                        diagnostics/dev commands
    Config/                          ModConfig classes
    UI/                              inventory station UI
    Systems/                         world load/unload cleanup
  Content/
    Items/                           InfiniCore + generated item/material/armor proxies
    Projectiles/                     generated projectile runtime and overlay projectile
```

## Architecture rules for future agents

1. Start from `ModSources/InfiniCrafterLocal`, not from old top-level summaries.
2. Treat `GeneratedItemData.Model.cs`, `GeneratedItemData.Normalize.cs`, `GeneratedItemData.Apply.cs`, `VfxManifestSpec.cs`, `GeneratorClient.cs`, `InfiniCraftPlayer*.cs`, `GeneratedItem.cs`, `GeneratedProjectile*.cs`, `GeneratedItemRegistryService.cs`, `GeneratedAssetSyncService.cs` as source of truth.
3. Do not reintroduce a name/prose router in C# runtime. Names, prompt text, `ToyIdentity`, script strings and tooltip prose are debug/presentation only.
4. Do not accept client-authored `GeneratedItemData` in multiplayer. Client sends craft intent; host/server commits.
5. Do not send PNGs, raw manifests or prompt bulk per projectile packet. Use registry + asset HTTP + compact visual sync.
6. Keep generated registry world-scoped. Cross-world cache leaks create wrong generated parents and asset mismatch.
7. Use central sentinels/limits, not scattered magic numbers.
8. Runtime child projectiles must be bounded and sanitized: explicit depth/count, no prose, no nested generated mini-item authoring.
9. If adding runtime capabilities, update both Python authoring contract and C# hard support (`InfiniRuntimeLimits`, `Normalize`, `Apply`, projectile/item execution, tests/docs). Do not silently map unknown future fields to gameplay.
10. If docs disagree with code, code wins; update docs immediately.

## Agent verification checklist

Before claiming you understand or before editing, verify these in source:

- `InfiniCrafterLocal.cs` has `ModVersion` and routes packets through `HandlePacket()`.
- `InfiniRuntimeLimits.cs` has `RuntimeApiCurrent`, movement/effect/onHit caps and `NetProseMaxChars=0`.
- `InfiniCraftPlayer.Multiplayer.cs` proves MP is **server-authoritative**: client request -> server slot consume/generate -> `CraftCommitResult`.
- `GeneratedAssetSyncService.cs` and Python `asset_sync_service.py` prove assets are final filename + HTTP `/get_asset`, not packet bulk.
- `GeneratedProjectile.Impact.cs` and `GeneratedItemData.Model.cs` prove child projectiles are bounded by explicit count/depth fields.
- `LocalGenerator/infini_local/core/result_models.py` proves typed helper results exist, but Python still has `dict[str, Any]` paths; do not invent fields casually.
- Search for a second model-judge before claiming one exists. If only docs mention it, it is not implemented runtime.

If you change a field/capability, update the `Where to edit — decision table for agents` path, tests and docs in the same patch.

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

