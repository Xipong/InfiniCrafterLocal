# Явное потребление боеприпасов generated оружием

`configure_weapon_ammo` восстанавливает weapon-side native ammo requirement и вклад выбранного ammo в combat stats. Она не использует bow/gun family classifier. Author вызывает capability на существующем `item_body`:

```json
{"id":"weapon_ammo","fn":"configure_weapon_ammo","target":"item","params":{"ammoCategory":"arrow","speedBasis":"native_shot"}}
```

Это фрагмент полного ответа: один explicit active `spawn_entity` binding и все required projectile components должны существовать отдельно. Поля owned [registry](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py), provider shape и Repair используют её данные. Полный текущий контракт отражён в [generated inventory](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md). Native ammo projectile AI этой реставрацией не заявляется.

## Реальные выборы Author

| Поле | Семантика |
|---|---|
| `ammoCategory` | Один exact canonical AmmoID token из registry. Native Terraria выбирает подходящий inventory ammo, включая существующий generated ammo с той же категорией. |
| `speedBasis="authored_spawn"` | Сохраняется начальная скорость `configure_spawn`; native ammo speed contribution не заменяет её. |
| `speedBasis="native_shot"` | Начальная скорость root равна модулю окончательного native shot velocity, включая ammo, prefix/player и late hook modifiers. Направление, placement и spread сохраняют самостоятельный authored contract. |

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

## Строгая граница и Repair

Present `RuntimeWeaponAmmoSpec` допускает только `ammoCategory` и `speedBasis`. Native DTO проверяет exact enum, обязательный active spawn binding и отсутствие двойной ammo role; null payload и неизвестные поля отклоняются. Нет normalization, выбирающей другую категорию или speed basis.

Неверный ammo category открывает Repair только `params.ammoCategory`: валидный speed basis, все projectile fields и binding costs остаются frozen. При отсутствии active consumer Repair может связать уже существующую готовую entity с active binding из registry-derived alternatives; не требуется создавать projectile design за модель. Единственный passive hold binding не удовлетворяет зависимости.

## Проверки

[Python regressions](../LocalGenerator/tests/test_weapon_ammo.py) проходят весь registry → compiler receipts → strict wire маршрут для каждой допустимой категории и двух speed choices, проверяют отсутствие capability, invalid/null/missing values, source receipt tampering, role conflict, frozen Repair и AST DTO surface. Source-mutation tests проверяют запрет утечки ammo requirement в другие actions и безусловной подмены authored speed.

Frozen SHA256 восьми прежних полных compiled fixtures подтверждают, что при отсутствии capability меняются только глобальные diagnostics `registryDrivenChecks.requirements` (28 → 29) и `exclusiveGroups` (добавляется `ammo_role`). Тест отдельно сверяет новые diagnostics и восстанавливает прежние два значения только в копии для сравнения с неизменёнными base627 hashes; любое изменение gameplay, receipts или другого поля нарушит эту проверку. Общий placed-body golden обновлён ровно из-за этих двух audit fields. Повреждённые `binding.input` с массивом/объектом возвращают structured refusal без исключения.

[Native checks](../tools/EngineRuntimeChecks.WeaponAmmo.cs) используют настоящие `Player.PickAmmo`, `ItemCheck_Shoot`, root-combat bridge, late `ModifyShootStats` и `CanConsumeAmmo`. Они проверяют выбранный ammo, native damage/knockback, обе initial speed policies, source identity, saving, собственный stack, missing ammo, alternate effects и strict JSON roundtrip. `NewProjectileDirect` наблюдается на границе регистрации с остановкой перед отсутствующим loaded projectile registration; это не игровой spawn/MP smoke.

C# build, запуск `EngineRuntimeChecks` и игровые SP/MP smoke требуют .NET 8, stable tModLoader и внешних dependency assemblies. При отсутствии среды они отмечаются **`notRun`**; portable Python/static gates не заменяют эти проверки.
