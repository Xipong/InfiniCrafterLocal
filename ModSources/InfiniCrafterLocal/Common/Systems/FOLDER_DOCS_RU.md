# Common/Systems

- [GeneratedCursorItemPresentationSystem.cs](GeneratedCursorItemPresentationSystem.cs) — exact selected generated instance в native cursor preview, только готовый PNG и verified IL source/tint owner; foreign/missing icon остаётся native. Unload снимает hook. [Контракт](../../../../docs/CURRENT_WORLD_TECHNICAL_FIXES_RU.md).

- [InfiniCraftWorldExitSystem.cs](InfiniCraftWorldExitSystem.cs) — загрузка world registry и безопасное завершение transient craft state при выходе.
- [GeneratedStationEscrowStateSystem.cs](GeneratedStationEscrowStateSystem.cs) — world-owned escrow/outcome journal, а не ephemeral client cache.
- [GeneratedPlacementLedgerSystem.cs](GeneratedPlacementLedgerSystem.cs) — tile/wall placement groups, accepted-placement receipt для однократного списания stack, world save/load и client sync.
- [GeneratedRootCombatSystem.cs](GeneratedRootCombatSystem.cs) — два source/version-guarded native hooks: exact ItemCheck query receipt в локальной invocation epoch и отдельный shoot-only stat context. Реальный Item временно меняет только damage/knockBack/DamageType; body/source context восстанавливается перед root spawn и в finally. Unknown native version/pattern — явная ошибка, не поздний повторный query/fallback. Entity target берётся только из уже выбранного authored binding; нет held-item semantic router.

При разрушении зарегистрированного placement группа атомарно переходит в `PendingReturns` с ID и `DefinitionJson`. Отсутствие записи в registry допускает восстановление из сохранённой definition; временная невозможность spawn повторяется. Клиент сообщает placement через `NotifyGeneratedPlacement`, авторитетный возврат выполняет server/singleplayer.

Это не vanilla-drop fallback: зарегистрированный placement подавляет vanilla drop. Текущая реализация логирует и удаляет постоянно повреждённые return records; такую corruption-границу нельзя объявлять гарантированным возвратом или незаметно подменять другим предметом. [Runtime boundaries](../../../../docs/ENGINE_RUNTIME_BOUNDARIES_RU.md).
