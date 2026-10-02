# Common/Services

- [GeneratorClient.cs](GeneratorClient.cs): snapshots и HTTP `/combine`; принимает только доставляемый GeneratedItemData.
- [GeneratedItemRegistryService.cs](GeneratedItemRegistryService.cs): world-scoped definitions и hydration по ID; клиент не становится авторитетным автором данных.
- [GeneratedAssetSyncService.cs](GeneratedAssetSyncService.cs): descriptors, проверка PNG/length/hash, HTTP-загрузка и bounded chunk transfer. Server asset request сверяет registry, читает/проверяет bytes и ставит bundle в очередь; это не произвольная пересылка клиентских файлов.
- [RuntimeSpriteCache.cs](RuntimeSpriteCache.cs): lazy PNG load, выбранный certified owner, backoff и bounded deferred GPU retirement.
- [InfiniRuntimeAuthority.cs](InfiniRuntimeAuthority.cs): authority predicates; [LocalHttpQuietFailure.cs](LocalHttpQuietFailure.cs): cooldown ожидаемых HTTP-сбоев.

Raw generation intermediates/prompts не становятся публичными ассетами. Временное клиентское отображение до hydration не заменяет обязательный PNG и не делает failed generation успешной. [Полный asset lifecycle](../../../../docs/IMAGE_ASSET_LIFECYCLE_RU.md).
