# C#: сначала native entrypoint, затем конкретный owner

Корневой [AGENTS](../../AGENTS.md) сохраняет все runtime/authority инварианты. Папки и partial types не создают дополнительную wire schema.

- HTTP-запрос генератора: `Common/Services/Generation/GeneratorClient.cs`; parent context: `GeneratorClient.ParentFacts.cs` в той же папке. `ToWireItem` → `CaptureParentNativeFacts` один раз → root/fingerprint/runtimeFacts projections. Общий native fact меняй только в capture owner; различия envelopes явны, null/zero и player-dependent ammo не объединяй.
- Item lifecycle/save/net/draw: `Content/Items/GeneratedItem.cs`; use/held/hits — `GeneratedItem.Use.cs`, equipment — `GeneratedItem.Equipment.cs`, dispatch — `GeneratedItem.RuntimeEvents.cs` в той же папке. Prefix/root combat/tooltip имеют собственные partials. Не ищи эффект по имени предмета.
- Projectile activation/update: `Content/Projectiles/GeneratedProjectile.cs` и `.Executors.cs`; события — `.RuntimeEvents.cs`; action execution — `Common/Runtime/RuntimeProgramExecutor.cs`; delayed identity/budget — `RuntimeDelayedActionScheduler.cs` / `RuntimeSpawnBudget.cs` в той же папке. Изменяя age/delay/once-only flags, проверь также `ReceiveExtraAI` в `.NetSync.cs` и `Configure(... preserveSyncedState ...)` в основном partial.
- Station transactions: `Common/Players/InfiniCraftPlayer.CraftState.cs` + world escrow owner; placement claims: один `Common/Systems/Placement/GeneratedPlacementLedgerSystem` со всеми partials. Read-only presentation не становится вторым владельцем материала.
- DTO admission: `Common/Models/Contracts/`; accepted-data projection: `Common/Models/Runtime/`; drawing: `Common/Models/Presentation/` и native draw hooks.

Для изменения найди зарегистрированный native check в `tools/EngineRuntimeChecks.cs`, затем его implementation. Новый `EngineRuntimeChecks*.cs` автоматически компилируется через glob; сам check явно регистрируется в `RunChecks`. Compile/registration, linked-source CPU, GPU/game loop и multiplayer — разные уровни проверки. [Полная карта](../../docs/development/CODE_MAP_RU.md#csharp) · [tests](../../docs/development/TESTING_RU.md).
