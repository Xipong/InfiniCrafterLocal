# Common/Systems

- [Craft](Craft/FOLDER_DOCS_RU.md) — escrow/outcomes и world-exit lifecycle.
- [Placement](Placement/FOLDER_DOCS_RU.md) — единый material ledger со всеми partials и native adapter.
- [Combat](Combat/FOLDER_DOCS_RU.md) — native root-combat context.
- [Presentation](Presentation/FOLDER_DOCS_RU.md) — cursor и placed-body drawing.
- [Utility](Utility/FOLDER_DOCS_RU.md) — независимая quick heal/mana effect-entry lane.
- [Diagnostics](Diagnostics/FOLDER_DOCS_RU.md) — существующий opt-in runtime selftest.

- [Presentation/GeneratedCursorItemPresentationSystem.cs](Presentation/GeneratedCursorItemPresentationSystem.cs) — exact selected generated instance в native cursor preview, только готовый PNG и verified IL source/tint owner; foreign/missing icon остаётся native. Unload снимает hook. [Контракт](../../../../docs/CURRENT_WORLD_TECHNICAL_FIXES_RU.md).

- [Craft/InfiniCraftWorldExitSystem.cs](Craft/InfiniCraftWorldExitSystem.cs) — загрузка world registry и безопасное завершение transient craft state при выходе.
- [Craft/GeneratedStationEscrowStateSystem.cs](Craft/GeneratedStationEscrowStateSystem.cs) — world-owned escrow/outcome journal, а не ephemeral client cache.
- [Placement/GeneratedPlacementLedgerSystem.cs](Placement/GeneratedPlacementLedgerSystem.cs) — tile/wall placement groups, accepted-placement receipt для однократного списания stack, world save/load и client sync.
- [Placement/GeneratedPlacementLedgerSystem.PlacedLight.cs](Placement/GeneratedPlacementLedgerSystem.PlacedLight.cs) — независимый `add_placed_light`: exact authenticated definition/binding и persistent group footprint, один center-cell `Lighting.AddLight` в `PostUpdateEverything`; без held-light, новой ledger или PNG. Общая placed-body projection проверяет presence + literal NBT int identity/geometry до `GetInt`; explicit int-zero tile/style допустимы, missing/coercible values не дают света. Restore/suppression используют ту же typed selection admission, light читает удостоверенный tile type из view. Break/removal/world unload/mod unload прекращают emission; malformed witness остаётся literal material-owned, без света.
- [Placement/GeneratedPlacementLedgerSystem.Prefix.cs](Placement/GeneratedPlacementLedgerSystem.Prefix.cs) — server-observed instance prefix в material ledger: literal NBT, stable mod/name, legacy absence=0; не часть authored definition или client intent.
- [Combat/GeneratedRootCombatSystem.cs](Combat/GeneratedRootCombatSystem.cs) — два source/version-guarded native hooks: exact ItemCheck query receipt в локальной invocation epoch и отдельный shoot-only stat context. Реальный Item временно меняет только damage/knockBack/DamageType; body/source context восстанавливается перед root spawn и в finally. Unknown native version/pattern — явная ошибка, не поздний повторный query/fallback. Entity target берётся только из уже выбранного authored binding; нет held-item semantic router.

При разрушении зарегистрированного placement группа атомарно переходит в `PendingReturns` с ID, `DefinitionJson` и снимком native prefix, захваченным из exact held GeneratedItem до расхода stack. Prefix проходит save/load и quarantine/requeue отдельно от canonical definition; integer без mod/name разрешён только для vanilla, modded prefix разрешается по сохранённой устойчивой identity. Старое отсутствие поля означает unprefixed=0, не новый roll. Отсутствие записи в registry допускает восстановление из сохранённой definition; временная невозможность spawn повторяется. Клиент сообщает placement через `NotifyGeneratedPlacement`, авторитетный возврат выполняет server/singleplayer.

Это не vanilla-drop fallback: зарегистрированный placement подавляет vanilla drop. Постоянно повреждённые return records сохраняются буквально в world quarantine. Невалидная/недоступная prefix identity и отказ native применения не разрешают выдать unprefixed замену. Definition-only requeue не переписывает prefix. Случаи NBT/native prefix application зарегистрированы в `tools/EngineRuntimeChecks.PlacementPrefix.cs`; без .NET/tModLoader их запуск и реальный world-spawn/MP smoke остаются `notRun`. [Runtime boundaries](../../../../docs/ENGINE_RUNTIME_BOUNDARIES_RU.md).
