# Event Author API: ближайший урон и взаимное притяжение

## Damage nearby: один центр, до N ближайших целей

```json
{
  "id": "nearby_damage",
  "fn": "damage_nearby_on_event",
  "target": "bolt",
  "params": {
    "when": "on_hit",
    "maxTargets": 3,
    "radiusTiles": 8,
    "damageMultiplier": 0.5,
    "delaySeconds": 0
  }
}
```

Свежий Author выбирает `damage_nearby_on_event`: wire action с тем же именем,
opcode `10`. Все NPC ранжируются от одной записанной точки события по расстоянию,
затем по NPC slot при равенстве. Центр не переносится между целями; это не цепочка
прыжков. Chaseability и native damage/defense по-прежнему ограничивают результат.

- `maxTargets`: целое **1…16**. Пропуск явно означает технический предел **16**,
  не «без ограничений» и не отсутствие урона. Это нейтральное ограничение отбора
  в рамках общего cap, а не нейтральность всего эффекта. Compiler записывает
  `maxTargets=16` с отдельным `declared_neutral_omission` receipt.
- `radiusTiles`: **0.5…60**, точная сетка **1/16 блока**; граница включена.
- `damageMultiplier`: **0.05…4**, умножает authored base damage владельца события,
  не `damageDone` и не live damage уже усиленного снаряда.
- События: `on_hit`, `on_crit`, `on_tile_collision`, `on_expire`, `on_kill`,
  `on_hurt`, `on_enemy_kill`. Для двух реакций экипировки сохраняется явный cooldown
  в trigger object. Реальный producer обязателен.
- Direct target исключён **только** при `on_hit/on_crit`. При истечении срока или
  proximity detonation выбранная NPC не считается уже поражённой и не исключается.
- `delaySeconds` сохраняет существующие scheduler, snapshot и authority правила.

Это сознательно новый алгоритм для свежих предметов: прежний slot-first area cap16
не эквивалентен nearest selection, а прежний nearest имел cap12. Сохранённые
`damage_area_on_event`/opcode3 и `chain_damage_on_event`/opcode4 продолжают исполнять
старые algorithms. Их readers не перенаправлены на opcode10. Fresh карточки
`damage_area_on_event` и `damage_nearest_on_event` скрыты и fresh admission их отвергает;
существующие registry records сохранены для исходных принятых receipts.

## Pull: направление и независимые импульсы

```json
{
  "id": "grapple_both",
  "fn": "pull_on_event",
  "target": "bolt",
  "params": {
    "when": "on_hit",
    "mode": "both",
    "ownerImpulseBlocksPerSecond": 8,
    "targetImpulseBlocksPerSecond": 14
  }
}
```

| Mode | Явные поля | Смысл |
|---|---|---|
| `target_to_owner` | `impulseBlocksPerSecond`, `radiusTiles` | NPC к игроку |
| `target_to_entity` | `impulseBlocksPerSecond`, `radiusTiles` | NPC к записанному центру снаряда |
| `owner_to_target` | `impulseBlocksPerSecond` | Игрок к прямой цели попадания |
| `both` | `ownerImpulseBlocksPerSecond`, `targetImpulseBlocksPerSecond` | Обе стороны к одной и той же цели события |

Все impulse-поля имеют диапазон **0.0375…15 блоков/с**: однократная прибавка к
velocity, не перемещение. NPC impulse умножается на `knockBackResist`, player
impulse — нет. Поэтому неподвижный к отбрасыванию босс остаётся на месте,
а игрок может подтянуться к нему.

`owner_to_target` и `both` в свежем API требуют `on_hit/on_crit`: периодическое
событие без цели не заменяется поиском. В `both` оба коэффициента обязательны,
shared impulse и radius запрещены. Исчезнувшая/неактивная цель означает отсутствие
обоих импульсов; delayed reuse NPC slot отменяет действие. Нет автоматического
выбора другого врага. Движение игрока исполняет owner; движение NPC — server
через существующий hit bridge. Это не атомарная сетевая физика двух тел.

NPC-only modes сохраняют свои `on_hit`, `periodic`, `on_expire` и теперь принимают
также `on_crit`. Их старое radius-search поведение при отсутствии активной прямой
цели не изменено: запрет fallback относится к `both` и owner-only. Сохранённый
owner-only wire тоже не мигрируется. Старый fresh fn `pull_owner_to_event_target`
больше не предлагается, но его уже принятые receipts читаются.

## Same-target bias: диапазон различимых Author choices

Свежий `target_and_fire.sameTargetBias` принимает **0…0.9**. Значение определяет distance score предыдущей цели:

`score = distance × (1 − bias)`

Для остальных NPC score равен distance. При `hardRange=false` native selector выбирает минимальный score строго меньше `rangeTiles × 16`. Поэтому soft range для предыдущей цели является score threshold: предыдущая NPC на расстоянии 100 px с bias 0.9 может выиграть у NPC на 15 px при range 20 px. При явно выбранном `hardRange=true` геометрическая граница проверяется до discount; `requireLineOfSight` и `targetPolicy` остаются независимыми решениями Author. Это не вероятность повторного попадания. Текущий firing caller использует `FindFiringTarget`; retained `FindNearestNpc` сохраняет прежний soft-score consumer для других movement paths.

Для current strict wire действует тот же registry domain **0…0.9**, включая delivery без receipts. Прежние значения 0.95/1 и widened receipt domain больше не принимаются; значения не clamp-ятся и не переписываются. Единственный owner `params.sameTargetBias` задаёт schema, cards, validation, Repair и source-free scalar audit.

## Wire/source и frozen Repair

Каждый новый scalar сохраняет exact authored path и один owner call. `both` —
одна event row с двумя impulse leaves, не два действия с выдуманными ID. Новые
wire поля `ownerStrength/targetStrength` допустимы только вместе при mode `both`;
`maxTargets` — только для opcode10. Bool/null/foreign fields и выход за новые
bounds отвергаются, не лечатся clamp-ом. Сохранённый wire остальных opcodes
сохраняет прежние DTO defaults и исполнение.

Frozen Repair открывает только неверный или действительно отсутствующий leaf.
Исправление второго импульса не позволяет заменить первый, режим или соседний
валидный radius. Принятые отсутствия остаются frozen. Новая вложенность или
retirement fresh карточки не разрешает переписывать сохранённый предмет.

`fixtures/event_api_pre_simplification.json` хранит реальные исходные Author и
wire/receipts с head `723f0e1`: оба прежних damage и оба pull проверяются без
изменения байтовых значений, с исходным Author и без него. Более ранний
`event_domain_retained_wire.json` остаётся прежней отрицательной fixture для
уже отвергавшихся исторических contracts; эта работа не восстанавливает их.

## Проверки

`test_author_event_domains.py` проверяет registry/provider → validation → compiler
→ exact receipts → strict wire, omission cap16, режимы pull, неправильные branch
поля, ограничения событий, frozen leaf Repair и сохранённые определения.

Зарегистрированные native checks в `EngineRuntimeChecks.EventApi.cs` используют
реальные DTO/executor/scheduler: раздельная owner/server authority, observer,
knockback-immune NPC, отсутствующая и recycled цель; deterministic closest ties,
inclusive radius, ограничение 16 и реальный damage consumer для 3/16 целей.
Существующий `EngineRuntimeChecks.EventDomains.cs` продолжает проверять прежний
ChainDamage. Source-policy PASS не является native execution PASS; native build/run
проверяется интеграционным CI точного итогового дерева, не игровым UI smoke.

## Канонические владельцы

- `core/runtime_authoring/capability_registry.py`: fresh branch shapes, bounds,
  declared omission, скрытые сохранённые records.
- `technical_lowering.py`: общий scalar projector и audit receipts.
- `wire_validator.py`, `RuntimeProgramSpec.cs`: strict wire/DTO admission.
- `RuntimeProgramExecutor.cs`: новый nearby selector, оба старых damage executors,
  независимые authority checks `both`.
- `RuntimeHitPullBridge.cs`, `RuntimeDelayedActionScheduler.cs`: существующая
  проверка owner hit receipt и NPC incarnation, без нового router.

## Выбор кнопки для on_use и маны

`on_use` — одно принятое непостановочное использование предмета, а не нажатие
клавиши до проверок. Для эффекта только на одной кнопке задаётся trigger:

```json
"when": {"on": "on_use", "useInput": "alternate_use"}
```

`useInput` принимает `primary_use`, `alternate_use` или `both`. `both` означает
однократный запуск после каждого принятого использования любой из двух кнопок,
не два запуска. Прежнее `"when": "on_use"` сохраняет смысл `both`. Фильтр
относится только к `item_body.on_use`; попадания, периодические события и
события снаряда не получают выдуманную «текущую кнопку». При задержке выбор
фиксируется при постановке действия в очередь: переключение кнопки позже
не меняет уже принятое действие.

Отдельно `configure_item_stats.params.manaCostInput` выбирает, какая кнопка
оплачивает заданный `manaCost`: те же `primary_use`, `alternate_use`, `both`.
Пропуск явно эквивалентен `both`, поэтому старые предметы сохраняют общую цену.
Например, `manaCost: 12, manaCostInput: "alternate_use"` не берёт базовую ману
за основной удар и оставляет нативную оплату 12 базовых единиц для альтернативы.
Модификаторы игрока продолжают действовать. Это не новая ручная транзакция:
оплата остаётся нативной в начале анимации, не за каждый созданный снаряд или
повторный вызов внутри той же анимации. Явные периодические `manaPayment`
контроллеров этим полем не переопределяются.

Выбор кнопки эффекта и выбор кнопки цены независимы: модель должна явно
согласовать их с задуманным действием. Никакой выбор не выводится из названия,
категории предмета или класса урона.

## Раздельные input и бюджет spawn

Для `item_body` события `on_use` с `useInput:primary_use` и `useInput:alternate_use` не происходят в одной активации. Статическая проверка складывает общие event counts (включая `both`, прежний строковый `on_use`, projectile events и descendants) и **большую** из двух input-only сумм. Например, по два события `count:10` на каждый input дают бюджет `20`, а не `40`; четыре события на один input дают `40` и отвергаются. Сам runtime-предел остаётся `32`, общая очередь сохраняет ledger исходной активации, а повторные события и контроллеры не получают бесплатного пополнения. Другие события не объявляются взаимоисключающими по имени или по предполагаемому сценарию использования.
