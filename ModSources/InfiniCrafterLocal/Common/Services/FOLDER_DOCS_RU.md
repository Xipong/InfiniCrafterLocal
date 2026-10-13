# Common/Services

- [Generation](Generation/FOLDER_DOCS_RU.md) — helper HTTP boundary и world definitions.
- [Assets](Assets/FOLDER_DOCS_RU.md) — PNG validation/delivery, transfer queue, client texture cache.
- [Networking](Networking/FOLDER_DOCS_RU.md) — shared authority predicates и HTTP offline cooldown.

Registry hydration и PNG chunks остаются у своих state owners, не переносятся в новый transport facade.

- [Generation/GeneratorClient.cs](Generation/GeneratorClient.cs): snapshots и HTTP `/combine`; принимает только доставляемый GeneratedItemData.
- [Generation/GeneratedItemRegistryService.cs](Generation/GeneratedItemRegistryService.cs): world-scoped definitions и hydration по ID; клиент не становится авторитетным автором данных.
- [Assets/GeneratedAssetSyncService.cs](Assets/GeneratedAssetSyncService.cs): descriptors, проверка PNG/length/hash, HTTP-загрузка и bounded chunk transfer. Server asset request сверяет registry, читает/проверяет bytes и ставит bundle в очередь; это не произвольная пересылка клиентских файлов.
- [Assets/RuntimeSpriteCache.cs](Assets/RuntimeSpriteCache.cs): lazy PNG load, выбранный certified owner, backoff и bounded deferred GPU retirement.
- [Networking/InfiniRuntimeAuthority.cs](Networking/InfiniRuntimeAuthority.cs): authority predicates; [Networking/LocalHttpQuietFailure.cs](Networking/LocalHttpQuietFailure.cs): cooldown ожидаемых HTTP-сбоев.

Raw generation intermediates/prompts не становятся публичными ассетами. Временное клиентское отображение до hydration не заменяет обязательный PNG и не делает failed generation успешной. [Полный asset lifecycle](../../../../docs/IMAGE_ASSET_LIFECYCLE_RU.md).
