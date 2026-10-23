# Точное имя nearest damage и разделение fresh/wire domain

Категории аудита **B15.2–B15.3** уточняют низкоуровневый Author API. Они не добавляют новый combat algorithm и не меняют native DTO/consumer.

## Damage nearest: один центр, несколько ближайших целей

```json
{
  "id": "nearby_damage",
  "fn": "damage_nearest_on_event",
  "target": "bolt",
  "params": {
    "when": "on_hit",
    "maxTargets": 3,
    "rangeTiles": 8,
    "damageMultiplier": 0.5,
    "delayTicks": 0
  }
}
```

| Fresh Author | Прежний wire / исполняемый смысл |
|---|---|
| `damage_nearest_on_event` | `action="chain_damage_on_event"`, `actionCode=4` |
| `maxTargets: 1…12` | `count`: максимум дополнительных NPC |
| `rangeTiles: 1…60` | Та же физическая область вокруг одного recorded event center; граница включена |
| `when: "on_hit" / "on_crit"` | Прежний event; нужен действительный item-body или projectile producer |
| `damageMultiplier: 0.05…2` | Один multiplier authored base damage для каждой выбранной цели |
| `delayTicks: 0…600`, optional | Прежняя задержка действия; существующие scheduler и authority правила |

`RuntimeProgramExecutor.ChainDamage` собирает chaseable NPC внутри одного радиуса, исключает directTarget, сортирует по расстоянию от того же центра и применяет урон первым `count`. Центр не переносится на следующую цель. Damage не уменьшается с расстоянием или порядком выбора. Результирующая потеря HP может различаться из-за native defense и других действующих правил Terraria. Порядок NPC на совершенно одинаковом расстоянии не получает нового обещания tie-break.

Поэтому слово `chain` убрано из свежего имени и model-facing пояснения количества. Технический discriminator остаётся прежним. Это **Alias Lowering**: `fn` выбирает одну точную action/opcode пару, `maxTargets` дословно передаёт `count`; контекст, название предмета и family не участвуют. Fn-selected literal receipts продолжают использовать общий статус `technical_projection`, scalar count receipt — `delivered` с источником `params.maxTargets`.

Старый receipt owner `chain_damage_on_event` удалён из registry. Current `damage_nearest_on_event` продолжает писать `action=chain_damage_on_event`, opcode `4` и исполняться через `ChainDamage`. Удаление старых receipts не удаляет текущую механику, authority или strict wire action4.

## Same-target bias: диапазон различимых Author choices

Свежий `target_and_fire.sameTargetBias` принимает **0…0.9**. Значение определяет distance score предыдущей цели:

`score = distance × (1 − bias)`

Для остальных NPC score равен distance. При `hardRange=false` native selector выбирает минимальный score строго меньше `rangeTiles × 16`. Поэтому soft range для предыдущей цели является score threshold: предыдущая NPC на расстоянии 100 px с bias 0.9 может выиграть у NPC на 15 px при range 20 px. При явно выбранном `hardRange=true` геометрическая граница проверяется до discount; `requireLineOfSight` и `targetPolicy` остаются независимыми решениями Author. Это не вероятность повторного попадания. Текущий firing caller использует `FindFiringTarget`; retained `FindNearestNpc` сохраняет прежний soft-score consumer для других movement paths.

Для current strict wire действует тот же registry domain **0…0.9**, включая delivery без receipts. Прежние значения 0.95/1 и widened receipt domain больше не принимаются; значения не clamp-ятся и не переписываются. Единственный owner `params.sameTargetBias` задаёт schema, cards, validation, Repair и source-free scalar audit.

## Wire/source и Repair граница

Scalar receipt с исходным Author проверяется по текущему ParamSpec и точной проекции. Без Author проверяются только текущие declared paths, тип/domain, literals и согласованность с wire (`authoredSourceChecked=false`); прежние parameter paths/domains не принимаются.

Для wire без provenance present bias проверяется по current 0…0.9; bool, null, strings, nonfinite и значения вне domain отвергаются без записи нового значения. Current optional absence не получает новый default.

Owner-only pull по-прежнему выбирается current `pull_owner_to_event_target`. Старый `pull_on_event.mode=owner_to_target` receipt больше не принимается; current NPC modes `target_to_owner / target_to_entity` сохранены. Frozen prior fixture не переписан.

Repair открывает только ошибочный leaf: invalid `maxTargets` или `sameTargetBias`. Попытки переписать валидный range одновременно с полезной поправкой игнорируются и попадают в audit. Неверное значение на разрешённом leaf остаётся RED. Никакого fallback выбора числа или преобразования вероятности в discount нет.

## Доказательства и пределы проверки

`test_author_event_domains.py` проходит registry→provider/cards→validator→compiler receipts→strict wire. Матрицы включают оба event и item/projectile producers, 1/3/12 targets, явные delay/radius/damage значения, forged/missing/duplicate literals, неверный count source/path/domain, malformed fresh inputs, wire с/без receipts и frozen leaf Repair.

`fixtures/event_domain_retained_wire.json` хранит неизменённые original compiler records и hashes как отрицательную provenance evidence. Current aliases сохраняют gameplay/runtime projections. Source-backed и source-free current receipts проверяются отдельно, включая missing/duplicate/source-owner attacks и targeting-neutral omissions.

`EngineRuntimeChecks.EventDomains.cs` подготовлен для native проверки двух фактов. Radial check вызывает настоящий `ExecuteAction`/`ApplyDamageToNPC`, сравнивает с native damage control, проверяет исключённый directTarget, сортировку, count, inclusive boundary и NPC вне исходного радиуса, находящуюся рядом с выбранной целью. Bias check читает реальный строгий JSON DTO, вызывает actual `FindNearestNpc` при четырёх ролях, проверяет сохранение 0.95/1, одинаковую saturation и previous target вне физического range. Source gate связывает эти methods с реальными callers, включая текущий `ApplyTargetAndFire → FindFiringTarget`; восемь isolated native-source mutations обязаны его нарушить.

Это method-level checks, не полный world/network loop. Текущая Python retirement проверка не запускает C# build, EngineRuntimeChecks или SP/MP smoke; native acceptance принадлежит отдельному parent-owned integration.

## Канонические владельцы

- [`capability_registry.py`](../../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py): current параметры и exact wire action4 alias; retired receipt metadata удалена.
- [`technical_lowering.py`](../../../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py): scalar projection и source/wire receipt checks.
- [`wire_validator.py`](../../../LocalGenerator/infini_local/core/runtime_authoring/wire_validator.py): present saved targeting domain без provenance.
- [`RuntimeProgramExecutor.cs`](../../../ModSources/InfiniCrafterLocal/Common/Runtime/RuntimeProgramExecutor.cs): прежний `ChainDamage` и authority.
- [`GeneratedProjectile.Executors.cs`](../../../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Executors.cs): current `ApplyTargetAndFire`/`FindFiringTarget` и retained `FindNearestNpc`.
- [`RuntimeProgramSpec.cs`](../../../ModSources/InfiniCrafterLocal/Common/Models/Contracts/RuntimeProgramSpec.cs): прежние action 4 и обе DTO границы bias 0…1.

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
