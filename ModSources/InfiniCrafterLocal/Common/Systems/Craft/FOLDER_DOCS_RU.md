# Common/Systems/Craft — Craft lifecycle и escrow

`GeneratedStationEscrowStateSystem.cs` — persistent world-owned escrow/outcome journal. `InfiniCraftWorldExitSystem.cs` завершает transient workers и очищает derived caches при смене мира; не создаёт второй refund owner.

Namespaces и имена типов сохраняются. Папка обозначает владельца исходников, а не новый API/слой исполнения.
