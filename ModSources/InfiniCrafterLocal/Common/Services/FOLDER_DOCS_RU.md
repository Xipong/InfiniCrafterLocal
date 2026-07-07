# Common/Services — generator boundary, registry, assets, caches

These services keep the hard boundary between LocalGenerator, world registry and client assets.

- `GeneratorClient.cs` — HTTP adapter to LocalGenerator `/combine`. It prepares input snapshots, sends world/player/context metadata, handles cache recovery/fatal recipe failures, and accepts only deliverable generated data. It is not the authoring implementation.
- `GeneratedItemRegistryService.cs` — per-world generated item registry. Server/host publishes generated items; clients hydrate by id. Do not leak cross-world generated parents.
- `GeneratedAssetSyncService.cs` — LAN/HTTP asset sync. Terraria packets carry base URL + sanitized final filenames; clients fetch bytes via `/get_asset`.
- `RuntimeSpriteCache.cs` — client lazy PNG loader with validation, dimension/size/cache limits and fallback texture.
- `InfiniRuntimeAuthority.cs` — predicates for singleplayer/server/client authority over side effects.
- `LocalHttpQuietFailure.cs` — cooldown/backoff for expected local HTTP failures.

Forbidden:
- raw PNG/JSON/prompt bulk in Terraria packets;
- accepting client-authored generated data as authority;
- turning missing assets into gameplay failure when placeholder fallback is safe.
