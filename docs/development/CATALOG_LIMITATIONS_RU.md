# Ограничения каталога и найденные пробелы контрактов

Повторно проверено 22 октября 2026 года на текущем main `c2899c79fe990583f4be8001721b6ba2f3a438c9`, каталог из 73 capabilities. Объединены прежние 42 первых ответа GPT-6 Luna, повторное исполнение validator/compiler, восстановленный исторический Live10 и новый аудит исходных фактов/C# consumer. Проверенные runtime-файлы совпадают с прежней базой `57c58d5`; все шесть исходных findings перепроверены. Предложенные доработки не реализованы. Игровой smoke новых предметов не выполнялся. **PR #138 остаётся HOLD.**

## 1. Валидная комбинация может содержать неисполняемое движение

**Тип:** пробел проверки композиции и ограничение исполнителя. **Приоритет: высокий.**

Карточка `target_and_fire` уже прямо описывает stationary entity. Поэтому речь о допустимой, но неисполняемой добавке движения, а не о полностью отсутствующем объяснении неподвижности.

Пример: `temporary_helper` с `move_orbit` и `target_and_fire` на одной сущности. В эксперименте JSON проходит `validate_runtime_program` и компиляцию, но орбитальное движение не исполняется.

Причина в `GeneratedProjectile.Executors.cs`: сначала вызывается `RunController()`. Если он возвращает `true`, ветка `RunMovement()` / `ApplyActiveModifiers()` пропускается. `ApplyTargetAndFire()` обнуляет скорость и возвращает `true`. Получается неподвижный помощник с прицеливанием, хотя движение тоже явно написано моделью.

**Последствие:** наличие capability в JSON и зелёный валидатор не доказывают сохранение её функции. Такая потеря особенно опасна для оценки роутинга: формально все нужные вызовы присутствуют.

**Обход сейчас:** выбрать неподвижную стреляющую сущность либо управляемую движущуюся сущность с периодическими выстрелами без встроенного автоприцеливания источника. Это разные механики; считать их равноценными нельзя.

**Доработка:** сначала явно описать и проверять исполнимость движения при выбранном контроллере на той же сущности. Проверять точную комбинацию и условия, не запрещать движения глобально для всего предмета. Отдельное расширение — отделить выбор цели/стрельбу от владения движением, если нужны движущиеся турели. Нельзя просто включить оба исполнителя без определения их совместного поведения.

Доказательство: [ответ с подавленным движением](experiments/capability_selection_2026-10-22/outputs/capabilities/trap.json), вызовы `trap_orbit` и `trap_target_fire`; [результаты валидатора](experiments/capability_selection_2026-10-22/results.json). Владельцы: [исполнитель](../../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Executors.cs), [реестр](../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py), [валидатор](../../LocalGenerator/infini_local/core/runtime_authoring/validator.py).

## 2. Общее событие `item_body.on_use` не различает основной и альтернативный ввод

**Тип:** ограничение выразительности событий. **Приоритет: средний, если нужны дополнительные эффекты конкретного ввода.**

`item_body.on_use` приходит после принятого непосадочного `primary_use` и `alternate_use`, включая `spawn_entity`. У `spawn_entity_on_event.when` нет фильтра по исходному input.

Пример: Author повесил бумеранг на `item_body.on_use`, рассчитывая дополнить альтернативное применение эффекта. Бумеранг появляется также при основной атаке. Это наблюдалось и с полным каталогом, и при выборе групп.

**Обход сейчас:** разные основные действия можно прямо привязать к двум inputs: основной — прямой снаряд, альтернативный — бумеранг. Это работает. Если же дополнительные события должны срабатывать лишь от одного из inputs, общей `on_use`-подписки недостаточно.

**Доработка:** рассмотреть явный, типизированный фильтр исходного input для событий или иной явный способ композиции действий конкретного binding. Не выводить input из имени вызова, текста предмета или категории.

Доказательство: [групповой вариант инструмента](experiments/capability_selection_2026-10-22/outputs/groups/tool.json), `blade_on_use`; [реестр событий](../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py), событие `on_use`; [исполнитель item-use](../../ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.Use.cs).

## 3. Описание требования для generated buff не отражает исключение для held/event activation

**Тип:** несогласованность model-facing требования с реальной проверкой. **Приоритет: высокий для уменьшения ложных ограничений при генерации.**

Производное требование `binding_action_present` у `apply_generated_buff_on_use` говорит, что эффект исполняется только через явный `apply_item_effects`. Однако валидатор разрешает именованную группу с совпадающим `refresh_generated_effect_group_while_held` либо `apply_generated_buff_on_event` без такого binding.

Это полезное исключение: оно позволяет сохранить оба активных inputs для разных атак и независимо обновлять баф в руках. В эксперименте ошибочное прочтение требования привело к ненужному `apply_item_effects` на альтернативном вводе и общему `on_use` для бумеранга.

**Обход сейчас:** использовать явный `effectGroupId` у определения generated buff и у held refresher. Отдельный активный binding для этой группы не нужен. Это не обход валидатора, а уже поддерживаемая ветка контракта.

**Доработка:** выразить альтернативные способы активации в каноническом требовании и его документации, чтобы selector и Author видели ту же логику, что валидатор. Проверить связь конкретной группы и способа её активации. Не дублировать исключение в отдельном роутере.

Доказательство: [успешный инструмент](experiments/capability_selection_2026-10-22/outputs/capabilities/tool.json), `held_survey_effect`, `refresh_survey_while_held` и два прямых spawn bindings. Владельцы: `_derived_requirements` в [реестре](../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py), ветка `binding_action_present` в [валидаторе](../../LocalGenerator/infini_local/core/runtime_authoring/validator.py), `RefreshHeldEffectGroup` в [исполнителе](../../ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.Use.cs).

## 4. Произвольная прибавка защиты только при удержании не выражается generated buff

**Тип:** отсутствующая возможность. **Приоритет: по потребности дизайна.**

В параметрах `apply_generated_buff_on_use` есть скорость добычи, свет, обнаружение сокровищ, движение/прыжок, восстановление маны и здоровья. Параметра прибавки защиты нет. `refresh_generated_effect_group_while_held` обновляет такую группу и не добавляет новых типов эффектов.

Поэтому пример «кирка даёт +10 защиты, пока находится в руках» нельзя выразить этой парой capabilities. `configure_accessory.defensePoints` даёт защиту при надевании; это другое условие, и автоматически заменять им удержание нельзя.

**Доработка:** при необходимости добавить явно авторуемую защиту в generated buff с полным проходом registry → schema → validator → compiler → C# executor → tests/docs. Не расширять общий контракт только ради экономии промпта.

Основание: параметры `apply_generated_buff_on_use`, `refresh_generated_effect_group_while_held` и `configure_accessory` в [реестре](../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py). Это проверка контракта, а не отдельная попытка генерации предмета в текущем наборе.

## 5. Некоторые обязательные поля легко принять за несущественные при нулевом эффекте

**Тип:** сложность заполнения параметров, не отсутствие механики. **Приоритет: после ошибок композиции.**

В первом ответе с полным каталогом Luna пропустила `lightStrength` и `lightColor` у бафа, которому нужны только ore detection и регенерация. Валидатор отклонил программу. В другом ответе были пропущены `bounceCount` у столкновений с `tileCollide=true`; эти поля в такой ветке обязательны.

**Обход сейчас:** передавать точные обязательные поля, включая `lightStrength=0` с разрешённым цветом для неиспользуемого света и `bounceCount=0` при отсутствии отскоков.

**Доработка:** сделать обязательность/условность заметнее в карточках. Отдельно оценить, какие пропуски действительно эквивалентны объявленной нейтрали; менять их контракт только по принятому в проекте правилу `default` + `neutral`, а не молча дописывать параметры после генерации.

Доказательство: [baseline/tool](experiments/capability_selection_2026-10-22/outputs/baseline/tool.json), [baseline/musket](experiments/capability_selection_2026-10-22/outputs/baseline/musket.json), [точные ошибки](experiments/capability_selection_2026-10-22/results.json).

При provider `json_schema` объявленные nullable optional поля сначала декодируются штатным `project_provider_author_item_to_local`: `null` может означать отсутствие. Нельзя считать сырой nullable transport невалидной gameplay-композицией до этой projection. Неизвестные/обязательные null и элементы массивов это правило не разрешает.

## 6. `live_parent` переносит величину урона, но не включает урон дочерней сущности

**Тип:** скрытая предпосылка композиции и пробел model-facing объяснения. **Приоритет: высокий.**

В повторной серии полный каталог с планом selector дал валидную программу: основной снаряд наносит урон и при попадании создаёт самонаводящуюся звезду с `damageBasis=live_parent`, `damageMultiplier=0.35`. У ребёнка отсутствует `set_projectile_damage`. Компилятор принимает программу, но не создаёт включённую damage-конфигурацию ребёнка.

В `GeneratedProjectile.cs::SpawnRuntimeEntity` применение damage override зависит от `entity.Damage.Enabled`. Дополнительные проверки в `GeneratedProjectile.DamageGate.cs` и `GeneratedProjectile.RuntimeEvents.cs` также запрещают повреждение при выключенной damage-конфигурации. Поэтому самонаведение работает, а задуманный дочерний урон теряется. Это вывод из компилятора и кода исполнителя; игровой прогон не проводился.

**Обход сейчас:** явно вызвать `set_projectile_damage` для ребёнка. Даже допустимый `damage=0` включает damage-конфигурацию; положительный `live_parent` override затем может дать фактический урон. Нельзя требовать строго положительный authored damage ребёнка как универсальное условие.

**Доработка:** явно объяснить различие выбора источника урона и включения damage-конфигурации в карточках spawn/damage. Рассмотреть проверку или диагностическое предупреждение для заявленного наследования урона без включённого damage у цели; намеренно безвредные дочерние сущности допустимы, поэтому общий запрет неверен.

Доказательство: [неизменённый ответ `325c90f89e75`](experiments/capability_selection_2026-10-22/followup/outputs/325c90f89e75.json), [ручное сравнение wire с добавленным damage=0](experiments/capability_selection_2026-10-22/followup/damage_gate_witness.json). Ручной пример не засчитан как успешный ответ модели. Владельцы: [компилятор](../../LocalGenerator/infini_local/core/runtime_authoring/compiler.py), [spawn](../../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.cs), [damage gate](../../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.DamageGate.cs), [runtime events](../../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs).

## Что ограничением не является

- Кирка может одновременно сохранять native mining и прямую основную атаку; альтернативный input может прямо запускать другой снаряд. Проверена композиция с независимым held buff.
- Движения, конфликтующие на одной сущности, могут использоваться на разных: гравитационный основной снаряд и самонаводящийся дочерний успешно скомпилированы.
- Активная атака и экипируемые защитные/регенерационные свойства могут сосуществовать. Все три варианта жезла это сохранили.
- Нативное размещение плиты и отдельная активная ловушка могут сосуществовать. Ограничение из пункта 1 относится к движению и контроллеру конкретной активной сущности, а не к размещению.

Полные результаты и оговорки: [отчёт эксперимента](experiments/capability_selection_2026-10-22/README.md), [разбор функций](experiments/capability_selection_2026-10-22/functional_review.json).

Повторная проверка и актуальный статус **HOLD**: [отчёт продолжения](experiments/capability_selection_2026-10-22/followup/README.md). Ошибки обязательных полей из пункта 5 наблюдались без provider-constrained decoding; их частоту нельзя напрямую переносить на production JSON-schema режим.


## 7. Generic helper не даёт полную native minion lifecycle

**Тип:** отсутствующая native возможность. **Пример Live10:** SpiderStaff + NimbusRod.

Каталог позволяет создать самостоятельного атакующего помощника, настроить summon damage, homing, события и ограничения числа копий. Но в проверенном API нет регистрации `Projectile.minion` и `Projectile.minionSlots` для такой сущности. `configure_accessory.minionSlotsBonus` увеличивает вместимость игрока, а не превращает helper в minion. Нельзя считать имя spider, summon-class или `temporary_helper` доказательством native upkeep/slot semantics.

При этом **native sentry поддерживается** через `set_projectile_sentry.enabled=true` — это нужно проверять в QueenSpiderStaff, не списывать все summons в неподдерживаемые. Обход сейчас — честно описанный generic боевой helper; доработка minion-регистрации требует отдельного полного vertical slice, включая native dismissal/slots/lifecycle.

## 8. Native ammo consumer и самостоятельный ammo item несовместимы на одном теле

**Тип:** явное ограничение композиции. **Пример Live10:** DaedalusStormbow + HolyArrow.

`configure_weapon_ammo` и `configure_vanilla_ammo_item` конфликтуют в `exclusiveGroup=ammo_role`. Синтетическая попытка совместить их на одном `item_body` действительно отклонена текущим validator с `exclusive_component_conflict`. Это не ограничение selector и не недостаток discovery index.

Сейчас можно сохранить bow, реально потребляющий стрелы, и явно создать hit-triggered звёзды; либо сделать самостоятельный native ammunition item. Сохранить обе native роли в одном generated item этим API нельзя. Вдобавок native ammo consumption не копирует AI/эффекты выбранного боеприпаса: hit-star behavior требует собственных событий, детей, движения и включённого damage.

## 9. Parent dump не содержит всех данных для точного восстановления эффектов

**Тип:** ограничение исходного контекста, отдельно от runtime-каталога.

ShadowFlameKnife tooltip сообщает on-hit flame, GoldenShower — снижение защиты, но в точном Live10 dump `buffType=0` и отсутствуют inflicted BuffIDs дочерней projectile AI. `apply_status_on_event` требует точный загруженный `buffId`; Author запрещено угадывать tile/wall/buff IDs. Угаданный числовой ID может пройти форму JSON и всё равно не быть обоснованным переносом функции.

Это означает **source-blocked exact status**, а не автоматическую ошибку reduced каталога. Generic armor penetration не тождествен Ichor debuff на цели. Доработка — расширить точный source dossier hit-status/child-AI фактами либо дать отдельно проверенную, одинаковую для всех arms vocabulary. Не брать догадку модели за источник истины.

Точная vanilla AI также не наследуется из `aiStyle` автоматически. `move_yoyo_hover` обеспечивает cursor-follow + return on release, а не полный клон Magic Missile. Для MeteorStaff локализованный tooltip буквально «Показывает метеоры»; направление, дождевую цепочку и происхождение каждой дочерней сущности нельзя доказать одним этим текстом.

## 10. Material identity не переносится автоматически во все native recipes

**Тип:** граница model-facing интерфейса; не игровой exhaustive-тест всех рецептов.

`material=true` у CrystalShard или SoulofLight не даёт generated item той же native ingredient identity. В исследованном каталоге нет capability, объявляющей универсальную подстановку исходного item type в vanilla recipes. Нельзя обещать её из названия или описания.

Это отличается от **нативного размещения**: CrystalShard имеет `createTile=129, placeStyle=0`; OrichalcumAnvil — `tileId=134, placeStyle=1`. Exact placement + исполняемый `place_item` binding сохраняют native tile interaction/station semantics по source/code, хотя здесь без game smoke. Soul of Light не заявляет наблюдаемую светимость: новый placed light допустим как авторское добавление, а не обязательная унаследованная функция.

## 11. Конечные budgets ограничивают граф и длительные дочерние эффекты

**Тип:** объявленные инженерные границы, не обнаруженная ошибка.

Текущий каталог задаёт максимум **12 entities, 8 bindings, 48 calls, child depth 3, 32 event spawns per activation**. Наличие периодического события и положительного интервала не доказывает бесконечный дождь: проверять lifetime, delay и общий spawn budget нужно вместе. Контроллерные volley/count и spawn.count имеют разные смыслы; нельзя складывать их только на глаз по именам.

Доработка при необходимости — сделать расход/остаток бюджета заметным в Author/диагностике. Нельзя объявлять runtime-функцию сохранённой лишь потому, что её capability присутствует в calls.

## 12. Базовые mana/ammo costs общие для item, а не произвольные per-input цены

**Тип:** объявленная область действия контрактов. **Примеры:** Night’s Edge + Magic Missile, Star Cannon + Meteor Staff.

`configure_item_stats.manaCost` задаёт единый Item.mana: native payment относится к старту use animation, а не к каждому отдельному projectile. `configure_weapon_ammo` требует native ammo для каждого активного `spawn_entity` данного item. Две разные bindings сами по себе не создают две независимые таблицы расхода ресурсов.

Поэтому формулировка «основной выстрел тратит только звёзды, альтернативный — только ману» должна подтверждаться конкретной исполняемой композицией, а не намерением в prose. Некоторые контроллеры имеют явно объявленные дополнительные mana payments; это отдельные ограниченные контракты, не универсальная per-binding цена. Нельзя приписывать им отсутствующий общий cost API или считать смешанные resource semantics автоматически точным сохранением обеих исходных экономик.

## Что Live10 подтвердил как доступное

- **FrostsparkBoots + ObsidianShield:** equipped `moveSpeedBonusPercent`, native sprint floor `accRunSpeedBlocksPerSecond`, `rocketBoots`, `iceSkate`, `noKnockback`, `fireWalk`, `defensePoints`. Все существенные наблюдаемые функции выразимы. Jump bonus не заменяет flight; lava immunity не заменяет hot-block immunity.
- **TitaniumPickaxe + MechanicalLens:** native mining + equipped `wireVision` могут сосуществовать. Ore detection не заменяет wire vision; equipped не равно held/inventory scope.
- **CrystalShard:** independent native placement не должно исчезнуть за декоративными кристальными снарядами.
- **OrichalcumAnvil:** точный native tile/style сохраняет станцию; Soul of Light может дать дополнительный авторский мотив, но не подтверждает native свет.

## Значение для роутинга и следующий порядок доработок

Первый приоритет — убрать расхождения prose/requirements и явно объяснить damage gate, подавление движения и event scope. Затем расширять source dossier там, где он не даёт точных фактов. Новые runtime-возможности minion/held-defense/совместимых ammo roles требуют самостоятельного дизайна; не добавлять их скрытым host fallback ради успешного benchmark.

73/73 discoverable IDs и полная JSON schema сохраняют форму/доступность, но не все значения единиц, ограничения совместимости и способы активации. `selected_only` не является доказанно lossless. Новый Compact full сохраняет все сведения обратимым кодированием; сохранение информации не доказывает одинаковую понятность модели.

Подробные новые результаты, matched controls, экономика и оговорки: [сводный отчёт Live10](experiments/capability_selection_2026-10-22/LIVE10_CONSOLIDATED_RU.md). В evidence bundle сохранены повторные witnesses, точные source hashes, frozen первые ответы и независимые reviews. Отдельно проверенный CI текущего runtime содержит 383 успешных native CPU checks; `tml_runtime_selftest=notRun`, поэтому это не игровой прогон новых предметов.
