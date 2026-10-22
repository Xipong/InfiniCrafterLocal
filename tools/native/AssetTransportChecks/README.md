# Native asset transport: linked-source CPU checks

Run with the .NET 8 SDK:

```sh
dotnet run --project tools/native/AssetTransportChecks/AssetTransportChecks.csproj --configuration Release
```

`LocalGenerator/tests/test_asset_transport_linked_source.py` also runs this executable
in the existing Python CI job. It fails rather than silently skipping when CI lacks
the SDK; outside CI, an unavailable SDK is explicitly `notRun`/skipped.

## What this proves

The project compiles the **complete production** `GeneratedAssetSyncService.cs`.
Its actual request scheduler, per-client queues, bundle encoder/decoder, PNG
validator, descriptor/SHA checks, and atomic file writer execute. Tests cover:

- Exact RGBA PNG bytes after a multi-chunk round trip, including 512x512 images.
- Coalescing repeated ensures without moving the original retry deadline.
- A lost initial request and all 32 missing files retried in one item-level request.
- Newly discovered sibling files and replaced manifests.
- World-reset/disposal retirement without deleting verified disk cache files.
- Per-item retry-state reset that preserves other items' in-flight native requests.
- Corrupt, impossible, repeated and reordered chunks; successful recovery.
- Descriptor mismatch and explicit HTTP mode refusing native payloads.
- Independent per-client pacing with the retained 16-chunk/sec budget and start credit.

The test-only types in `TmlBoundary.cs` replace the surrounding DTO registry,
packet sink, and clock. They do **not** replace or copy the transport algorithm.
They do not test production packet-ID assignments, definition hydration, crafting
transactions, the renderer, tML sockets, Steam authentication or Steam relays.
No game, model, socket listener, or external service is started.

## Live Steam acceptance (separate, not established by these checks)

Use two real tModLoader clients with identical mod versions. Start Host & Play
via Steam, select `native` asset transport, keep the generator on loopback, and
leave LAN/Radmin disabled. Verify:

1. A joining friend with an empty cache receives an existing item and every
   declared item/entity/impact/equipment/VFX PNG; compare source/cache SHA-256.
2. A new craft requested by either player arrives with matching behavior and art.
3. A warm-cache reconnect avoids unnecessary asset traffic; clearing one PNG
   refetches that missing asset without losing the definition.
4. Disconnect/rejoin during a large transfer and switch worlds; previous-world
   pending work must not be replayed against the new session.
5. Repeat over a constrained link, recording actual time-to-ready, bandwidth,
   Steam/tML logs and gameplay latency. The configured byte budget is not a
   measured throughput or latency guarantee.

Never report these linked-source checks as a successful Steam session or a full
native tML build. The existing `EngineRuntimeChecks.csproj` remains the separate
harness for checks against actual tModLoader and external mod assemblies.
