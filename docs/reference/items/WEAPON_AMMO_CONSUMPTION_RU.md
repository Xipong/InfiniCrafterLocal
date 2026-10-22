# Явное потребление боеприпасов generated оружием

`configure_weapon_ammo` восстанавливает weapon-side native ammo requirement и вклад выбранного ammo в combat stats. Она не использует bow/gun family classifier. Author вызывает capability на существующем `item_body`:

```json
{"id":"weapon_ammo","fn":"configure_weapon_ammo","target":"item","params":{"ammoCategory":"arrow","speedBasis":"native_shot"}}
```

Это фрагмент полного ответа: один explicit active `spawn_entity` binding и все required projectile components должны существовать отдельно. Поля owned [registry](../../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py), provider shape и Repair используют её данные. Полный текущий контракт отражён в [generated inventory](../generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md). Native ammo projectile AI этой реставрацией не заявляется.

## Реальные выборы Author

| Поле | Семантика |
|---|---|
| `ammoCategory` | Один exact canonical AmmoID token из registry. Native Terraria выбирает подходящий inventory ammo, включая существующий generated ammo с той же категорией. |
| `speedBasis="authored_spawn"` | Сохраняется начальная скорость `configure_spawn`; native ammo speed contribution не заменяет её. |
| `speedBasis="native_shot"` | Начальная скорость root равна модулю окончательного native shot velocity, включая ammo, prefix/player и late hook modifiers. Направление, placement и spread сохраняют самостоятельный authored contract. |

Для active root `native_shot` совместим только с `configure_spawn.velocity.constantSpeedBlocksPerSecond`: sampled min/max нельзя молча заменить native magnitude. `authored_spawn` сохраняет все явно выбранные sampled варианты. Ограничение относится только к target active primary/alternate `spawn_entity` binding; passive и event-child velocity не меняются. Конфликт диагностируется на exact `params.velocity` root call; единственный Repair может явно заменить этот полный typed union, не меняя ammo choice, count, aim или другие roots. Raw wire и runtime root override также должны отказать до spawning, не выбирать победителя.

При явной `activationDelaySeconds` root сохраняет фактический launch vector после native allocation и восстанавливает его на первой активной AI-update, включая нулевую native скорость. Ожидание не заменяет выбранную скорость на authored `constantSpeedBlocksPerSecond`. Snapshot принадлежит конкретному root instance; passive hold и event children его не наследуют. ExtraAI v5 переносит этот snapshot только для native-shot root с задержкой; остальные payloads сохраняют v4, включая sampled velocity. Hydration уже движущегося instance не запускает его заново. Это сохранение результата уже выбранного native speed owner, без изменения Author/wire grammar или compiler receipts.

Оба поля обязательны. Неверное значение, null, plural alias вроде `arrows`, произвольный category/family и неизвестная policy остаются RED. Отсутствие всей capability сохраняет прежнее поведение и не материализует `runtimeProgram.weaponAmmo`. Stationary entity сохраняет нулевую velocity; выбранная скорость не отменяет stationary lifecycle. Последующие movement/controller updates по-прежнему исполняют authored поведение.

## Что фиксирует сама capability

Выбор `fn="configure_weapon_ammo"` задаёт один обязательный контракт:

1. `Item.useAmmo` применяется ко всем active `spawn_entity` bindings этого предмета. При переходе к item-body, effects или placement use native поле очищается. Passive hold spawns и event child spawns не являются native ammo shots.
2. Выбор ammo, native saving rules и `CanConsumeAmmo`/`CanBeConsumedAsAmmo` остаются у Terraria/tModLoader. Код не вручную уменьшает ammo stack и не вызывает повторный PickAmmo из `Shoot`. [Официальный ModItem API](https://docs.tmodloader.net/docs/stable/class_mod_item.html) определяет отдельные hooks выбора и потребления ammo; `ConsumeItem` обслуживает расход самого использованного предмета.
3. `Shoot` получает окончательные native damage и knockback и передаёт их root spawn без повторного применения player modifiers. Существующая root-combat projection сначала подставляет явно authored combat basis выбранной runtime entity, затем восстанавливает исходный item для source inheritance. AmmoItemIdUsed сохраняется в исходном `EntitySource_ItemUse_WithAmmo`.
4. Projectile behavior всегда задаёт authored runtime entity. Native выбранный ammo projectile type проходит через native selection/hooks, но не подменяет entity, движение, collision или lifetime. Специальные native arrow/rocket/solution AI и их побочные эффекты не копируются.

У fixed semantics нет одноэлементных Author enum: модель выбирает capability, а не переписывает технические константы. Класс преобразования — **Alias Lowering**. Две authored choices имеют отдельные receipts; контейнер `runtimeProgram.weaponAmmo` имеет уникальный `fn`-selection receipt. Source-backed audit проверяет фактический originating call, а wire-only audit требует согласованные container и parameter receipts. Подмена association другим call и удаление одного choice receipt отклоняются.

## Расход и композиция

Один native shooting attempt выбирает/расходует ammo по правилам Terraria. Authored `configure_spawn.count` может создать несколько root projectiles внутри этого attempt; они не запускают дополнительные ammo picks. `usePolicy.stackCost` независимо управляет расходом собственного generated item. Equipment ammo-save chance остаётся отдельной player mechanic и не превращается в вероятность расхода собственного stack.

Native missing-ammo selection отказывает до runtime shot. Existing owner/projectile admission checks сохраняются. Если другой hook или состояние мира вызывает поздний отказ уже после native ammo commit, эта capability не возвращает ammo: она сохраняет native ordering и не обещает общей транзакции «успешный projectile spawn → расход». Для такого rollback понадобился бы отдельный identity/escrow contract; выдавать его за имеющийся нельзя.

Одна generated instance не может одновременно содержать `configure_vanilla_ammo_item` и `configure_weapon_ammo`: её native Item.shoot/shootSpeed и собственный ammo stack обслуживали бы несовместимые роли. Registry `ammo_role`, validator/Repair, strict wire и C# boundary отклоняют такую композицию. Другие generated ammo items остаются допустимыми inventory ammunition.

Поддерживается существующий finite vocabulary, включая arrow и bullet из исторического consumer. Sand не входит в этот контракт. Отсутствие weapon capability не добавляет требования ammo к generated ammo item, healing item или обычному runtime projectile launcher.

## Родительские наблюдения, не наследование механики

Native capture передаёт `useAmmoCategoryName` из `Item.useAmmo` отдельно от `ammoCategoryName` из `Item.ammo`. Пропуск в старом packet остаётся неизвестным, Python не декодирует категорию по имени/ID. `weapon_item.shoot_field`, даже под ключом `effectiveProjectile`, — наблюдение поля weapon, не результат реального выстрела или выбранного боеприпаса. Accepted generated parent передаёт полный `runtimeProgram`, включая `weaponAmmo`, homing и collision, без выбора одного «типичного» projectile.

`dart` — общая native категория семян и дротиков; она не требует дротикообразного спрайта. Weapon runtime entity сохраняет явно authored внешность/поведение независимо от выбранного ammo. `dropSeedsIfInInventory` остаётся буквальным source flag `ItemID.Sets.DropSeedsIfInInventory[type]`, а не командой наследования. Для generated определения существует независимая явная capability ниже; ни описание, ни выбор `dart` её не добавляют.

### Явный inventory passive сбора семян

```json
{"id":"seed_collection","fn":"collect_seeds_from_grass"}
```

Capability работает только на единственном `item_body`; можно явно передать его `target` и пустые `params:{}`, содержательных параметров нет. Она не требует use/hold/equipped binding, оружия, ammo category или buff. Author сам решает, сохранять ли этот смысл родителей: обязательного наследования нет. Это **Alias Lowering**: точный `fn` пишет только `gameplay.collectSeedsFromGrass=true` с единственным literal receipt от `.fn`. Отсутствие capability ничего не пишет; отсутствие wire поля или `false` не даёт passive. Native storage — nullable `GameplaySpec.CollectSeedsFromGrass`, `null` при отсутствии пропускается сериализатором: прежние network bytes/definition hash не получают новый default false. Явный wire `false` сохраняется как inert значение, present `null`/не-boolean отклоняется; compiler capability пишет только `true`. Normalize не материализует поле. Старые definitions/сохранения не переписываются.

Native consumer — [GeneratedInventorySeedSystem.HasItem](../../../ModSources/InfiniCrafterLocal/Common/Systems/Utility/GeneratedInventorySeedSystem.cs). Strongly typed `On_Player.HasItem_BooleanArray` сначала сохраняет результат original. Только при original=false и reference-equal `ItemID.Sets.DropSeedsIfInInventory` добавляется witness конкретной generated instance с полным текущим world-scoped definition и explicit flag. Native scan `[0,58)` и `stack>0` сохранён: equipment, mouse slot 58, банки/Void Bag и чужой игрок не считаются; air, placeholder, foreign-world и ещё не hydrated save reference не дают permission. Сам `Player.HasItem(bool[])` не проверяет active/dead; native `WorldGen.GetPlayerForTile` по-прежнему выбирает игрока. Обычный inventory hydration остаётся прежним, query не запрашивает definition и не пишет registry.

Ни один proxy type не помечается в глобальном set. Другие `HasItem` overloads и reference-distinct flag arrays не меняются. `WorldGen.KillTile_ShouldDropSeeds` оставляет исходный `Main.rand.Next(2)==0`, native допустимые grass tiles, owner selection, drop и SP/MP lifecycle. Нет второго seed-spawn hook, extra RNG/stack debit, нового ammo выбора, изменения mana/стоимости или inventory slots.

[Python seed regressions](../../../LocalGenerator/tests/test_inventory_seed_collection.py) проверяют actual Author/provider и frozen Repair, unique exact receipts (с исходником и без), strict final delivery и неизменные ammo/costs. [Native rows](../../../tools/native/EngineRuntimeChecks.InventorySeeds.cs) проверяют DTO/Normalize, настоящие `Player.HasItem` и `WorldGen.KillTile_ShouldDropSeeds`, vanilla positives, instance/container/player negatives и точный RNG stream. Они baseline-compilable для отдельного native RED replay; наличие source/test не означает выполненный native check или игровой MP smoke.

## Строгая граница и Repair

Present `RuntimeWeaponAmmoSpec` допускает только `ammoCategory` и `speedBasis`. Native DTO проверяет exact enum, обязательный active spawn binding и отсутствие двойной ammo role; null payload и неизвестные поля отклоняются. Нет normalization, выбирающей другую категорию или speed basis.

Неверный ammo category открывает Repair только `params.ammoCategory`: валидный speed basis, все projectile fields и binding costs остаются frozen. При отсутствии active consumer Repair может связать уже существующую готовую entity с active binding из registry-derived alternatives; не требуется создавать projectile design за модель. Единственный passive hold binding не удовлетворяет зависимости.

## Проверки

[Python regressions](../../../LocalGenerator/tests/test_weapon_ammo.py) проходят весь registry → compiler receipts → strict wire маршрут для каждой допустимой категории и двух speed choices, проверяют отсутствие capability, invalid/null/missing values, source receipt tampering, role conflict, frozen Repair и AST DTO surface. Source-mutation tests проверяют запрет утечки ammo requirement в другие actions и безусловной подмены authored speed.

Frozen SHA256 восьми прежних полных compiled fixtures не переписываются. Исходное ammo изменение добавляло только `ammo_role` и один registry requirement. Совмещённый replay отдельно проверяет и обращает только объявленные targeting/beam neutrals, child-combat selectors, constant-velocity source-path projection и новые registry diagnostics, затем сравнивает все оставшиеся bytes с прежними hashes. Sampled/native-shot conflict имеет RED→GREEN Author/raw-wire tests и реальный serialized frozen Repair в обоих response modes; passive sampled target остаётся допустимым, active alternate target отклоняется по его exact `params.velocity`. Повреждённые `binding.input` с массивом/объектом возвращают structured refusal без исключения.

[Native checks](../../../tools/native/EngineRuntimeChecks.WeaponAmmo.cs) используют настоящие `Player.PickAmmo`, `ItemCheck_Shoot`, root-combat bridge, late `ModifyShootStats` и `CanConsumeAmmo`. Они проверяют выбранный ammo, native damage/knockback, обе initial speed policies, source identity, saving, собственный stack, missing ammo, alternate effects и strict JSON roundtrip. `NewProjectileDirect` наблюдается на границе регистрации с остановкой перед отсутствующим loaded projectile registration; это не игровой spawn/MP smoke.

C# build, запуск `EngineRuntimeChecks` и игровые SP/MP smoke требуют .NET 8, stable tModLoader и внешних dependency assemblies. При отсутствии среды они отмечаются **`notRun`**; portable Python/static gates не заменяют эти проверки.
