# Common/Services/Assets — Asset lifecycle

`GeneratedAssetSyncService.cs` проверяет и доставляет PNG/descriptors/chunks; `GeneratedTransferSystem.cs` обслуживает его queue на main thread. `RuntimeSpriteCache.cs` владеет клиентскими texture load/cache/retirement. Chunk transport не вынесен из asset owner.

Namespaces и имена типов сохраняются. Папка обозначает владельца исходников, а не новый API/слой исполнения.
