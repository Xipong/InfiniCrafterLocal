# InfiniCrafterLocal v0.4.234 — build/QoL notes для модовой части

## Сборка

Проект мода: `ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj`.

SDK: `Tomat.Terraria.ModLoader.Sdk/2.1.1`, `TmlVersion=stable`, `LangVersion=latest`.

Внешние compile-time references:
- `ParticleLibrary.dll`;
- `Luminance.dll`.

Пути задаются через:
- `/p:InfiniExternalDepsRoot=C:\path\to\tml-deps-src`
- `/p:InfiniParticleLibraryDll=C:\...\ParticleLibrary.dll`
- `/p:InfiniLuminanceDll=C:\...\Luminance.dll`
- env `INFINI_TML_DEPS_SRC`.

Без этих DLL target `InfiniValidateExternalModReferences` намеренно падает до ResolveReferences.

## Runtime QoL

- Generated sprites are runtime PNGs, not embedded tML assets; if missing/invalid, placeholder texture remains safe fallback.
- Runtime sprite cache limits are controlled by `InfiniGameplayQolConfig` and bounded in `RuntimeSpriteCache`.
- Inventory asset prefetch can warm generated assets while inventory is open.
- `/getinfini` requests generated registry/asset catch-up from server.
- `/infinicache` inspects/clears runtime sprite/asset cache.
- `/infinidump` and `/infinidumppicture` are diagnostic/report helpers.

## Multiplayer asset caveat

Steam/Terraria gameplay packets do not proxy the mod’s HTTP assets. MP peers need a reachable HTTP asset endpoint from the host:

- set `INFINI_ASSET_PUBLIC_BASE_URL` when auto LAN/Radmin guess is wrong;
- otherwise `GeneratedAssetSyncService.GuessLanBaseUrlFromEndpoint()` prefers Radmin `26.x` address if available;
- Terraria packets carry only base URL + filenames; clients download `/get_asset?file=...` in background.

## Safety/QoL invariants

- Clients never commit `GeneratedItemData` to server; MP crafting is server-authoritative.
- Fatal recipe failures refund ingredients; transient HTTP/cache races get bounded recovery.
- World unload tries to refund/save pending station inputs and clears presentation sync caches.
- C# runtime never executes prompt/prose/script fields as gameplay.
