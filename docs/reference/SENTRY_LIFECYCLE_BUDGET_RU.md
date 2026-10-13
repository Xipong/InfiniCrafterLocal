# A6b/A6c — native sentry и активный бюджет потомков

Восстановление разделено на независимые низкоуровневые решения Author. Наличие stationary entity не включает ни одно из них автоматически.

| Явный выбор | Проекция и потребитель |
| --- | --- |
| `set_projectile_sentry {enabled: true/false}` | `entity.nativeSentry`; `GeneratedProjectile.Configure` устанавливает `Projectile.sentry`. Активный item binding проецирует `Item.sentry` из своего точного target. После каждого успешного создания зарегистрированной sentry вызывается `Player.UpdateMaxTurrets`. |
| `configure_spawn {placement: "native_resting_spot", ...}` | `spawn.placement`; вызывает `Player.FindSentryRestingSpot`. Native метод ограничивает точку достижимой областью игрока и находит площадку под курсором. Итоговая center Y равна worldY минус половина явно заданной hitbox height. `pushYUp` игнорируется для modded projectile. |
| `set_descendant_concurrency {maxActive: N}` | `spawn.descendantMaxActive`, integer 1–96; создаёт ограниченный пополняемый пул для ожидающих spawn reservations и живых потомков данного физического источника. |

Native регистрация сохраняет явно заданные lifetime, hitbox, damage, collision и targeting. `UpdateMaxTurrets` использует действующий `Player.maxTurrets`; native tML выбирает старейшую sentry по `timeLeft`. Новый код не заменяет эту политику собственным счётчиком. Опция placement доступна как самостоятельный native координатный примитив и не выбирает sentry lifecycle. Дополнительные `offsetPx` и `spawn_over_target` продолжают применяться явно поверх выбранного anchor.

## Чем новый пул отличается от прежнего бюджета

По умолчанию сохраняется прежний общий монотонный event budget активации, ограниченный 32 успешными дочерними spawn. Смерть projectile не возвращает его расход. Свободные root binding spawns по-прежнему не тратят этот event budget.

Author может явно назначить root entity `set_descendant_concurrency`. Каждый физический root получает собственный пул; сам root в нём не учитывается. Все созданные им потомки и их pending spawns разделяют пул. После смерти пули слот освобождается, поэтому длительная sentry может сделать больше 32 выстрелов за время жизни при конечном числе одновременно живых и ожидающих пуль. Глобальный owner cap 96, максимальная глубина, authored entity concurrency и статический лимит сложности event calls остаются отдельными ограничениями.

Если новый пул выбран также на дочерней entity, он добавляет ограничение к родительским. Родительская ёмкость не заменяется: каждый descendant reserve проходит всю цепочку. Если в цепочке есть старый lifetime ledger, успешная смерть не возвращает его расход. Так вложенная опция не может обойти ограничение предка.

`RuntimeSpawnBudget.Reserve` резервирует ёмкость, `Return` возвращает только неиспользованную/отменённую часть, а `RuntimeSpawnLease` описывает успешно созданный живой descendant. Lease освобождается один раз до terminal events. Пул также проверяет фактическое `active` и incarnation host при следующем reserve, чтобы direct retirement либо переиспользование host не оставили занятый слот. Ожидающие действия scheduler используют те же reservations; отказ при dispatch, отмена и `Clear` возвращают их.

## Классификация и transport

Оба новых capability — прямая проекция явно выбранной механики, с точным receipt каждого параметра. `native_resting_spot` — объявленный вариант существующего координатного контракта; native reachable-area clamp входит в его документированную семантику. Ни alias macro, ни выбор по prose, имени, DamageClass или kind не добавляются.

Отсутствие новых calls ничего не материализует. Отсутствующие новые поля старого v5 wire остаются отсутствующими, в том числе после C# сериализации: nullable presence хранится отдельно от явных `false` и числового лимита. Присутствующий `null`, неверный тип или выход за диапазон отклоняется. Repair исправляет только exact invalid leaf и не включает native lifecycle при исправлении соседнего лимита.

Пулы принадлежат только исполняющему owner peer. `SendExtraAI` передаёт наблюдение оставшейся ёмкости; metadata hydration не создаёт новый ledger и не восстанавливает расход. Snapshot допускает 0–96 для новых concurrent pools и остаётся только наблюдением. Условие `preserveSyncedState` сохраняет исходный owner ledger и его ancestry.

## Проверки и предел доказательства

Python тесты проверяют все 36 комбинаций presence/false/true native flag, absence/1/3/96 pool и трёх anchor, точную проекцию и receipts, malformed wire без Author provenance, сохранение старого wire, настоящие production Author packets, frozen Repair и mutation numeric guard.

`tools/EngineRuntimeChecks.SentryLifecycle.cs` содержит сценарии на production C# типах и методах: native флаги и точный active binding; `FindSentryRestingSpot` и порядок `UpdateMaxTurrets`; native retirement старейшей sentry; 100 последовательных дочерних spawns с освобождением occupancy; direct `active=false` и смена incarnation; повторный `OnKill`; nested/ancestor limits; scheduler cancellation и late refusal; owner/remote hydration. Boundary observers создают только изолированные headless hosts, без заявления о запуске Terraria world loop.

В среде подготовки PR отсутствуют .NET, tModLoader и native зависимости, поэтому C# build, запуск EngineRuntimeChecks и игровой/MP smoke — **notRun**. Portable pytest и structural gates перечислены в PR description. Native/game validation остаётся отдельным review gate.

Исторические источники: `f04ee02`, `GeneratedItem.Sentry.cs`, `GeneratedProjectile.Sentry.cs`, `GeneratedProjectile.Impact.cs`. Native API: [tModLoader Player](https://docs.tmodloader.net/docs/stable/class_player.html), [tModLoader Projectile](https://docs.tmodloader.net/docs/stable/class_projectile.html).
