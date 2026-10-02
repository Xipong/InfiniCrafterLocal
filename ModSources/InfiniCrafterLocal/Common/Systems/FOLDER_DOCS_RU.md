# Common/Systems

- [InfiniCraftWorldExitSystem.cs](InfiniCraftWorldExitSystem.cs) — загрузка world registry и безопасное завершение transient craft state при выходе.
- [GeneratedStationEscrowStateSystem.cs](GeneratedStationEscrowStateSystem.cs) — world-owned escrow/outcome journal, а не ephemeral client cache.
- [GeneratedPlacementLedgerSystem.cs](GeneratedPlacementLedgerSystem.cs) — tile/wall placement groups, accepted-placement receipt для однократного списания stack, world save/load и client sync.

При разрушении зарегистрированного placement группа атомарно переходит в `PendingReturns` с ID и `DefinitionJson`. Отсутствие записи в registry допускает восстановление из сохранённой definition; временная невозможность spawn повторяется. Клиент сообщает placement через `NotifyGeneratedPlacement`, авторитетный возврат выполняет server/singleplayer.

Это не vanilla-drop fallback: зарегистрированный placement подавляет vanilla drop. Текущая реализация логирует и удаляет постоянно повреждённые return records; такую corruption-границу нельзя объявлять гарантированным возвратом или незаметно подменять другим предметом. [Runtime boundaries](../../../../docs/ENGINE_RUNTIME_BOUNDARIES_RU.md).
