# Native parent facts: границы проверяемых наблюдений

Это read-only контекст родителей для Gameplay Author, а не наследуемое исполнение,
изменение старых предметов или обещание полного анализа Terraria. Accepted
`generatedParent` по-прежнему передаёт исходные механические графы и значения;
этот путь не классифицирует их и не перебалансирует.

## Три разных источника

- **Snapshot:** `GeneratorClient.ParentFacts.cs` читает выбранные поля native Item
  и нового Projectile после `SetDefaults`. `lifeRegen` — сырой вклад Item;
  `armorPenetration` — исходное значение Projectile. Это не итоговый player regen,
  не результат выстрела и не полное описание AI. Ноль сохраняется, неизвестное
  поведение не становится отрицательным утверждением.
- **Certified source reference:** существующий offline IL extractor читает
  assembly без исполнения игровых hooks. Runtime допускает наблюдения только при
  точном совпадении SHA256 тела метода **и** ModuleVersionId, только для vanilla
  объектов. Новый/неподдержанный binary или modded объект не заимствует сертификат.
  Эти ссылки, исходные offsets и scope проходят до Author целиком.
- **Ammo observations:** `playerInventoryAmmoRaw` / `playerInventoryProjectileRaw`
  и `fallbackAmmoRaw` / `fallbackProjectileRaw` остаются отдельными компактными
  списками. Native producer ограничивает каждый набор тремя кандидатами; Python
  сохраняет порядок, кратность, provenance, slots и наблюдённую пустоту. Это не
  «лучший патрон» и не effective DPS. При отсутствии собственного `shoot` weapon
  effective projectile теперь остаётся неизвестным, а не выбирается из инвентаря.
  Это исправление информации о родителе, не изменение игрового выстрела.

## Что именно сертифицируется

`native_hit_status_analysis.py` сохраняет безусловные `effects` и отдельно
`randomOutcomes`: альтернативы одного RNG вызова взаимоисключающие и исчерпывающие,
включая пустую альтернативу. Их нельзя суммировать как одновременные эффекты или
независимые proc rolls. Каждый новый request доказывается при фиксации только
одного small-range RNG вызова; остальные player/world/AI/random условия остаются
неизвестными. Диапазон ограничен 16 исходами, кандидаты — 32 вызовами, без
декартова перебора. В закреплённом binary это, в частности:

- Grass projectile: Poisoned 20, 420 ticks с вероятностью 1/4; иначе нет этого
  запроса. Projectile `StatusNPC` и sword-contact `StatusToNPC` имеют отдельные
  source certificates и sourceKind. У Grass оба канала подтверждают эти
  параметры; это не обещание, что оба попадут в одного NPC.
- Flare: OnFire 24 на 600 ticks с вероятностью 1/3 либо 300 ticks с вероятностью
  2/3. Это разная длительность, а не 1/3 вероятность самого статуса.

`native_attack_fact_analysis.py` распознаёт только узкие source shapes:
явный item-type guard, аргументы единственного прямого NewProjectile call,
branch-local count по CFG либо canonical `i=0; i<rand.Next(lo,hi); i++`.
Неизвестные выражения, дополнительные входы, неоднозначные guards, изменение
loop locals по адресу и неподдержанные циклы отказываются от наблюдения.

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
прибавления native stats под явным item-ID guard, включая OR вариантов. Весь блок
должен быть распознан: неизвестный call, внешний вход, вложенное условие или loop
не становятся «безусловным бонусом». В текущем закреплённом binary распознаны
137 предметов и 26 полных set-веток, не все предметы игры.

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
frame predicates, функционально поставленная active tile и прямоугольный scan;
размер scan не называется круглым радиусом. Runtime передаёт только однозначные
style-0 Campfire/fireplace/Bast: source rows для Heart/Star tile42 пока остаются
offline-only, потому что createTile без проверенного style mapping недостаточен.
Banner требует именно matching
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
