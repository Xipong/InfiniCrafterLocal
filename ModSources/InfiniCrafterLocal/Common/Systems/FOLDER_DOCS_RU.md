# Common/Systems

World lifecycle systems.

- `InfiniCraftWorldExitSystem.cs` reloads current-world generated registry on world load, protects/refunds transient craft state on unload, and clears projectile/held presentation sync caches.
- `GeneratedPlacementLedgerSystem.cs` records which world tile was created by which generated item id, so breaking a tile placed through a `place_item` binding returns that exact authored item instead of the vanilla stand-in. The ledger is world-persistent (`SaveWorldData`/`LoadWorldData`), synced to joining clients (`NetSend`/`NetReceive`), and updated from the placing client over `NotifyGeneratedTilePlacement` because the server owns tile-break drops. It also issues the accepted-placement receipt that authorizes exactly one stack debit in `GeneratedItem.ConsumeItem`. When a recorded definition can no longer be resolved, the entry is dropped and vanilla drop behaviour is left untouched rather than substituting a different item.
