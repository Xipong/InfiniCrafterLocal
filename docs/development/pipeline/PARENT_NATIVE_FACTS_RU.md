# Native parent facts: границы проверяемых наблюдений

Это read-only контекст родителей для Gameplay Author, а не наследуемое исполнение,
изменение старых предметов или обещание полного анализа Terraria. Accepted
`generatedParent` по-прежнему передаёт исходные механические графы и значения;
этот путь не классифицирует их и не перебалансирует.

## Источники фактов

- **Snapshot:** `GeneratorClient.ParentFacts.cs` читает выбранные поля native Item
  и нового Projectile после `SetDefaults`. `lifeRegen` — сырой вклад Item;
  `armorPenetration` отдельно сохраняется у Item и Projectile;
  `itemScale` — базовое `Item.scale` без reforge prefix, не размер PNG.
  `useLimitPerAnimation` — буквальный native лимит применений внутри одной
  анимации: `null` означает отсутствие явного лимита, отсутствие поля в старом
  пакете остаётся неизвестным. Число выстрелов не выводится из одного отношения
  `useAnimation / useTime`: например, у BookStaff и FairyQueenMagicItem native
  лимит равен 4, у FairyQueenRangedItem — 5. Это не итоговый player regen,
  не результат выстрела и не полное описание AI. Ноль сохраняется, неизвестное
  поведение не становится отрицательным утверждением.
- **Certified source reference:** существующий offline IL extractor читает
  assembly без исполнения игровых hooks. Runtime допускает наблюдения только при
  точном совпадении SHA256 тела метода **и** ModuleVersionId, только для vanilla
  объектов. Новый/неподдержанный binary или modded объект не заимствует сертификат.
  Эти ссылки, исходные offsets и scope проходят до Author целиком: точные
  повторы могут иметь `sourceSameAs: N` — точный индекс полного значения в
  `nativeSourceFacts[N]` того же dossier. Это lossless sharing, не удаление фактов или выбор «лучшего»
  наблюдения. Порядок/кратность массивов и типы сохраняются после раскрытия;
  literal tooltip и accepted generated-parent packets остаются inline.
- **Ammo observations:** `playerInventoryAmmoRaw` / `playerInventoryProjectileRaw`
  и `fallbackAmmoRaw` / `fallbackProjectileRaw` остаются отдельными компактными
  списками. Native producer ограничивает каждый набор тремя кандидатами; Python
  сохраняет порядок, кратность, provenance, slots и наблюдённую пустоту. Это не
  «лучший патрон» и не effective DPS. Текущее количество `stack` намеренно
  не передаётся Author: временный запас игрока не является механикой родителя.
  `playerInventoryObservation` отличает завершённый bounded scan (`observed`)
  от `unavailable` (`no_player` / `inventory_scan_failed`). Только наблюдённый
  пустой инвентарь даёт `[]`; отсутствие наблюдения даёт `null` в native wire и
  отсутствие массива в model-facing packet. Player-free fingerprint не выдаёт
  отсутствие игрока за пустой инвентарь. Явный request-local `ammoRaw`, даже
  пустой, не заимствует fingerprint-примеры. Это category-match scan в порядке
  inventory, не исполнение native PickAmmo и не обещание пригодности к выстрелу.
  При отсутствии собственного `shoot` weapon
  effective projectile теперь остаётся неизвестным, а не выбирается из инвентаря.
  Это исправление информации о родителе, не изменение игрового выстрела.

## Source-derived ammo configurations

`native_ammo_sources.md` в `contracts/reports/` описывает полный source contract;
производитель — `GeneratorClient.AmmoFacts.cs`, offline owner —
`tools/generate/generate_native_ammo_facts.py`. Правила извлекаются из native
`PickAmmo` / `ItemCheck_Shoot`, а не из item-name/family таблицы. Exact SHA256
метода и MVID обязательны; неизвестные method/dispatcher certificates не
разрешают заявлять прежний call order.

`projectileSemanticsReference` сохраняет source stages, точные input-projectile
условия, source spawn sites и неразобранные gates. `candidateProjectileBindings`
связывает наблюдаемый/representative ammo input с этими правилами. Произвольный
hook, неизвестная ветка или неполный roster остаются unknown, не «обычной стрелой».
Поддержанные ModItem/GlobalItem override shapes читаются из metadata без
исполнения; ammo-owned `PickAmmo` отдельно от weapon `ModifyShootStats`/`Shoot`.
При подтверждённых сертификатах `PickAmmo` и его lookup читается текущая
`AmmoID.Sets.SpecificLauncherAmmoProjectileMatches`: моды могут изменять эту
таблицу. Offline-анализатор проверяет всю цепочку с общим join и отсутствием
посторонних входов: таблица → category offset → положительный ammo.shoot либо
сохранённый weapon.shoot. Поэтому отсутствие пары в таблице разрешает только
подтверждённую следующую ветку. Нулевой ammo.shoot не исключает кандидата
(Rocket I, гель); это поле не обязано само быть итоговым projectile ID.

Регрессии закреплённого binary: Pulse Bow заменяет projectile любого arrow
input на 357; Hellwing меняет только current projectile 1 на 485, сохраняя
специальные inputs отдельно; Daedalus сохраняет projectile identity, но имеет
собственный aerial delivery с constructor Y `MountedCenter−600` и консервативным
условным spawn-count range 2–4. Это не полный aim/spread, итоговая скорость,
вероятности, cadence, guaranteed hits или обещание неизменённых mod hooks.

При доказанной замене входной projectile profile исключается, отдельно
передаётся source-output reference. **Ammo-item damage, speed и knockback
сохраняются независимо от замены projectile.** Это вклады, а не универсальная
формула сложения или итоговый DPS. Неизвестный transfer поведения не удаляет
известный вклад ammo damage. Specials не получают механики базовой стрелы
по умолчанию.

Для будущего Author конфигурации сравниваются раздельно, без автоматического
среднего или выбора «сильнейшей» стрелы. Inventory observation показывает
фактические inputs, не весь доступный progression; fallback examples не
доказывают владение или доступность. Source-подтверждённая условная способность
оружия остаётся отдельным ориентиром даже без её ammo в текущем inventory.
Нет нового progression solver, recommended damage corridor или скрытого
перебаланса сохранённого ребёнка при смене патронов.

## Неопределённость не запрещает новый дизайн

Заявление «родитель накладывает X» требует подходящего source-наблюдения с
его условиями. Явно выбранная **новая** способность ребёнка не требует, чтобы
родитель ею обладал. Отсутствие source certificate не означает отсутствие
механики и не запрещает Author составить её из доступных primitives. Код
не дописывает эффект за Author и не превращает необязательный self-check в gate.

### Эффекты баффов и дебаффов, а не каталог имён

Глобальный словарь загруженных buff-ID не передаётся ни Author, ни Repair.
Он идентифицировал чужие готовые эффекты, но не раскрывал их механику и не
добавлял исполнимых решений. Существующие native-ID calls остаются явной
интеграцией с native поведением и совместимы с принятыми definitions;
новая авторская механика не требует такого ID.

`nativeBuffEffectReference` описывает source-подтверждённое действие native
self-use buff на **игрока**. `buffEffectReference` внутри конкретного hit-status
описывает поддержанное действие на **NPC**. Получатель, операция, native
числовое значение/единицы, исходные условия и границы анализа остаются
read-only фактами. Это локальный контекст наблюдённого эффекта родителя,
не список всех доступных баффов и не готовый runtime preset.

Подтверждение `AddBuff(id, duration)` отдельно от расшифровки самого эффекта:
ID, proc probability и duration не теряются, если downstream действие
распознано частично либо неизвестно. Неизвестные binary/mod hooks, AI,
иммунитет и неподдержанные ветки не получают выдуманное числовое описание.
Сертификаты проверяются до выдачи source-фактов; hooks не исполняются.

Author явно составляет бафф/дебафф из зарегистрированных generated-effect
примитивов: выбирает получателя, характеристики, триггер, длительность и
поддержанный шанс. Знаковые player modifiers выражают также штрафы и обмены;
`apply_npc_effect_on_event` выражает временные NPC эффекты без нативного
buff-ID. Код не переводит имя родителя или source-reference в автоматически
выбранную механику. Точные значения нового эффекта — решение Author,
а не исправление факта о родителе. См. [construction contract](../../reference/authoring/LOW_LEVEL_RUNTIME_AUTHORING_RU.md#полезная-композиция-баффов-и-дебаффов).

Практическая ценность уточняется в существующем Author contract: основной
режим должен иметь понятную пользу в обычной ситуации, вторичный — достижимую
пользу либо осознанную нишу; повторяющиеся затраты и реальный риск оцениваются
вместе с наградой. Это guidance, не числовой balance corridor, обязательная
синергия/гиммик или повод Repair менять уже валидные механики. Простые предметы,
осмысленные sidegrades и сильные заслуженные выгоды остаются допустимыми.

## Что именно сертифицируется

`native_hit_status_analysis.py` сохраняет безусловные `effects` и отдельно
`randomOutcomes`: альтернативы одного RNG вызова взаимоисключающие и исчерпывающие,
включая пустую альтернативу. Их нельзя суммировать как одновременные эффекты или
независимые proc rolls. Каждый новый request доказывается при фиксации только
одного small-range RNG вызова; остальные player/world/AI/random условия остаются
неизвестными. Диапазон ограничен 16 исходами, кандидаты — 32 вызовами, без
декартова перебора. Прямой random `switch` сохраняет все взаимоисключающие ветви
и пустой default. Если один draw задаёт proc и duration либо несколько durations,
они идут одним совместным choice; превышение proof budget отказывает от таких
связанных ranges, а не изображает их независимыми. В закреплённом binary это, в частности:

- Grass projectile: Poisoned 20, 420 ticks с вероятностью 1/4; иначе нет этого
  запроса. Projectile `StatusNPC` и sword-contact `StatusToNPC` имеют отдельные
  source certificates и sourceKind. У Grass оба канала подтверждают эти
  параметры; это не обещание, что оба попадут в одного NPC.
- Flare: OnFire 24 на 600 ticks с вероятностью 1/3 либо 300 ticks с вероятностью
  2/3. Это разная длительность, а не 1/3 вероятность самого статуса.

`native_attack_fact_analysis.py` распознаёт только узкие source shapes:
явный item-type guard, аргументы единственного прямого NewProjectile call,
branch-local count по CFG либо canonical `i=0; i<limit; i++`. Limit должен
быть bounded literal, его единственным прямым присваиванием local либо одним
`rand.Next(lo,hi)`; один прямой spawn на итерацию. Неизвестные control transfers
(включая throw/leave), alias записи, дополнительные входы и неподдержанные циклы
отказываются от наблюдения. Fixed-loop recognizer добавляет source-ветки
TacticalShotgun (6), PiranhaGun/ReleaseDoves/BubbleGun (3), не таблицу семейств.

`nativeShootReference.damageMultiplierAtSpawn` относится к **текущему native
shot-damage local** после ammo/player/mod и branch-local изменений, не к base
Item.damage. `explicitSpawnCount` — прямые calls внутри достигнутой native ветки
на завершающихся путях, не cadence, guaranteed hits или весь attack graph.
Grass даёт multiplier 0.25, Light's Bane 0.5 с явным флагом возможного изменения
local внутри ветки (включая crit), Boomstick — 3–4 calls с multiplier 1. Не
выводится полный DPS, гарантия одновременного sword-contact и projectile-hit,
полный crit algorithm или наследование AI.

`collisionReference` сертифицирует аргументы native line test: для Light's Bane
center ±46×**live projectile.scale** вдоль rotation, width 8×scale. Это не
безусловная длина 92 px: AI/crit меняют scale; native broadphase, NPC geometry
и mod hooks продолжают влиять на результат. Snapshot width/height не заменяет
этот дополнительный reference.

## Экипировка, полные комплекты и окружение

`nativeEquipmentReference` отделяет вклад одного функционально надетого предмета
от `conditionalArmorSets`. Offline recognizer распознаёт только прямолинейные
прибавления native stats под явным item-ID guard, включая OR вариантов и bounded
literal ID ranges из исходного native кода. Весь блок должен быть распознан:
неизвестный call, внешний вход или loop не становятся «безусловным бонусом».
Один доказанный Boolean gate может сохраняться как `conditionalEffects` отдельно
от независимых `effects`, с полным native member/equals и `observed=false`.
Например, Wizard Hat сохраняет magic contribution и дополнительный minion slot
при `tenthAnniversaryWorld`, не объявляя это условие текущим состоянием мира.
Поддержаны также native pick-time, fishing-power и whip-range contributions.
В текущем закреплённом binary распознаны 151 предмет и 29 полных set-веток,
не все предметы игры.

У комплектов сохраняются одновременно head/body/legs и все разрешённые OR
варианты. Это **equip-slot IDs, не ItemIDs**. Смешанный Ancient/обычный Shadow
поддерживается исходной веткой; неполный комплект и vanity её не удовлетворяют.
Каждая Ancient Shadow часть отдельно добавляет 5 процентных пунктов generic crit;
полный set отдельно устанавливает `shadowArmor`. Последний boolean не превращается
в выдуманное «+15% moveSpeed»: actual native движение меняет другие поля.
Локализованный set tooltip передаётся буквально с source key/language/status,
не парсится в числовые механики. Ограничение строки отказывает от целой строки,
не обрезает её и не теряет остальные проверенные facts.

Вклад в `StatModifier.Additive`, attackSpeed или moveSpeed не означает ровно тот
же процент итогового урона, частоты кадров анимации или скорости бега. У всех
reference остаётся partial scope: неизвестные hooks, runtime gates и конечные
stats игрока не вычисляются. Ни один equipment hook не вызывается при Prepare.

`nativeEnvironmentReference` описывает условия native tile scan и banner settings,
а не активный эффект от лежащего в инвентаре предмета. Для tile aura сохраняются
frame predicates, функционально поставленная active tile и прямоугольный scan.
Точный source certificate `TileObject.Place` и связанных metadata getters
разрешает сопоставить current `TileObjectData` с initial tile-cell frames:
Heart Lantern получает только Heart aura, Star in a Bottle — только Star aura,
обычный lantern — ни одну. Доказанные Campfire/fireplace/Bast styles не ограничены
нулём. Передаются alternate, matching cell frames и metadata provenance.
Произвольная изменённая item tile/style пара, legacy placement dispatch,
custom hooks, random styles, frame overflow или неподдержанные metadata
отказываются от наблюдения. Успешная placement, текущее включение/wiring и
активный world buff не наблюдаются. Banner требует именно matching
opponent-banner buff и правильного BannerToItem; raw registry не доказывает
активацию, а multipliers описывают компоненты, не конечный damage.

Equipment/environment дополнительно проверяют SHA256 **всей native assembly** и
ModuleVersionId, включая зависимые getters/helpers. Хеширование кешируется;
неподдержанный binary и modded/generated родители не заимствуют native поведение.
Сертификат относится к исходной assembly на диске, а не доказывает отсутствие
in-memory detours сторонних модов.
Это не утверждение полного анализа модовых hooks. Существующие literal tooltip,
item snapshots и полные accepted generated graphs продолжают работать независимо.
Новые references проходят Python compact packet с полными conditions, нулями,
false, пустыми альтернативами и независимой копией данных.

## Воспроизведение и ограничения

```bash
python tools/generate/generate_native_hit_status.py --assembly /path/to/tModLoader.dll --check
python tools/generate/generate_native_attack_facts.py --assembly /path/to/tModLoader.dll --check
python tools/generate/generate_native_equipment_facts.py --assembly /path/to/tModLoader.dll --check
python tools/generate/generate_native_environment_facts.py --assembly /path/to/tModLoader.dll --check
```

Зависимости offline анализа: `tools/generate/native-hit-status-requirements.txt`.
Generated catalogs — точная проекция source reports в `contracts/reports/`;
это не вручную поддерживаемая таблица item names. Offsets используют координаты
методного тела dncil (с header), SHA256 считается только по IL bytes.

Native regression checks выполняют реальный `StatusNPC` с независимым seeded RNG
oracle; реальный `ItemCheck_Shoot` до наблюдаемой spawn boundary; реальный
`Projectile.Colliding`; request capture и отрицательные certificate controls.
Python проверяет synthetic CFG отказы и полный Author packet. Это не live-world
DPS, multiplayer, arbitrary C# semantics или доказательство всех use/equipment,
AI, tile/buff/banner и всех остальных contact-status hooks. Новые equipment/set
checks сравнивают source-факты с реальными GrantArmorBenefits/UpdateArmorSets,
включая mixed/incomplete slots и отсутствие изменения владельца при Prepare. Непокрытое остаётся неизвестным.
