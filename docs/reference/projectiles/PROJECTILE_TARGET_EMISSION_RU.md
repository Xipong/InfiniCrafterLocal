# Выбор последовательности NPC и выпуск физических снарядов

`emit_to_targets_on_event` явно задаёт последовательный поиск NPC и начальный transform отдельного child projectile для каждого найденного звена. Весь bounded plan строится в одном dispatch, а не после будущих попаданий children. Дальнейшие flight/collision/lifetime/damage принадлежат child entity.

`selectionAnchor=previous_target` переносит центр поиска к очередной NPC; `event_target` сохраняет исходный центр. `repeatPolicy` явно разрешает либо исключает revisits. Выбранная цель задаёт только начальное направление, не гарантированное попадание. Direct nearby damage — другая операция из [event contract](../authoring/AUTHOR_EVENT_DOMAINS_RU.md).

## Author API

Все девять параметров обязательны; capability можно не выбирать целиком.
Допустимы несколько calls на одной source entity с собственными IDs.

| Параметр | Область | Исполняемое значение |
|---|---|---|
| `when` | `on_hit`, `on_crit` | Реальный hit-event source entity |
| `entity` | ID `free_projectile` или `child_projectile` | Отдельно объявленная совместимая entity |
| `stepCount` | integer 1…12 | Максимум звеньев, один child на звено |
| `stepRangeTiles` | number 1…60 | Включительный геометрический radius каждого поиска; 1 tile = 16 px |
| `selectionAnchor` | `previous_target`, `event_target` | Перемещать search/emission origin к очередной цели либо сохранять dispatch-time event NPC |
| `repeatPolicy` | `allow_revisits`, `exclude_visited` | Разрешать более ранние NPC либо исключать source и все уже выбранные цели |
| `requireLineOfSight` | boolean | Native `Collision.CanHit` от hitbox anchor до hitbox candidate |
| `ignoreTargetUpdates` | integer 0…600 | Начальный native AI countdown исключения точного emission-anchor NPC; 0 отключает |
| `delay` | Секунды, registry domain | Задержка dispatch с проекцией в world ticks |

Радиус и порядок nearest сравниваются по точным квадратам расстояний фактических binary32 NPC Center. Координаты и разрешённый binary64 radius переводятся на общую dyadic решётку `2^-149`, после чего integer comparison сохраняет inclusive equality и различает любой положительный ортогональный компонент. Это не epsilon/расширение радиуса; слот разрешает только математически точную ничью.

Фрагмент calls для уже объявленных `bolt` и `arc_child`:

```json
{
  "id": "emit_arcs",
  "fn": "emit_to_targets_on_event",
  "target": "bolt",
  "params": {
    "when": "on_hit",
    "entity": "arc_child",
    "stepCount": 2,
    "stepRangeTiles": 22.5,
    "selectionAnchor": "previous_target",
    "repeatPolicy": "exclude_visited",
    "requireLineOfSight": false,
    "ignoreTargetUpdates": 10,
    "delay": 0
  }
}
```

Это фрагмент, не полный playable item. Source должна действительно испускать
выбранный event. У child обязательны собственные spawn/movement/lifetime/
collision и нужные ему damage/presentation choices. Entity graph остаётся
ациклическим; выбор NPC не добавляет self-reference или скрытый recursive
Author call.

## Точный поиск и snapshot

Планировщик ищет ближайший `CanBeChasedBy` NPC в `Main.ActiveNPCs`. Radius
проверяется геометрически без distance-score discount. При равной дистанции
выбирается меньший NPC slot index. Совпадающий центр и nonfinite direction
не создают подставной axis. Отсутствие подходящей цели завершает план.

Текущий anchor исключается при обеих repeat policies. При
`previous_target + allow_revisits` последовательность может вернуться к
исходному NPC. При `event_target + allow_revisits` каждый поиск снова
использует один центр и может выбрать того же ближайшего NPC. При
`exclude_visited` одна и та же NPC instance не выбирается повторно в этом
плане. Это ограничение выбора, а не global immunity для будущих попаданий.

Весь bounded path фиксируется до вызовов physical spawn. Каждый step хранит
origin, ненулевой direction и exclusion snapshot своего anchor. Изменение
мира после планирования не превращает выбранные цели в принудительный damage
список. LOS ограничивает первоначальный выбор; он не меняет child tileCollide
или ownerHitCheck и не гарантирует свободный путь во время полёта.

Referenced child должен иметь явные `position={at:activation_origin}`,
`aim=velocity`, `offsetBlocks=0`. Иначе его отдельный
origin adapter спорил бы с выбранной операцией. Registry requirements,
строгий wire и C# boundary отвергают такую композицию. Compiler не меняет
уже принятую child, чтобы сделать ссылку подходящей.

Один step создаёт ровно один child с нулевым fan spread. У этой операции нет
дополнительных count/spread/damageMultiplier решений. Child speed и combat
stats остаются его собственными authored значениями. A9 parent-combat
inheritance не включается неявно. Историческая готовая формула
`max(6, parentSpeed × 0.9)` также не подставляется. A10 восстанавливает
выбранную топологию поиска/выпуска, не все старые bundle-константы сразу.

## Exclusion, authority и задержка

Initial exclusion привязан к NPC slot **и** incarnation token, а при
захвате также проверяется текущая NPC instance. Повторное использование
слота не предоставляет immunity к новому NPC. Текущий anchor исключается
лишь пока положителен authored countdown; остальные collision rules
projectile продолжают действовать независимо.

Countdown уменьшается в начале native AI до collision. Поэтому значение
10 означает исключение до первого AI и ещё девять post-AI collision
opportunities, а не десять полных world ticks. `extraUpdates` увеличивает
частоту этих decrement. Source activation delay и world-tick event delay
имеют отдельные существующие часы и не объявляются эквивалентными этому
счётчику.

Dispatch и приём в delayed scheduler используют существующую owner/SP
authority. Remote peer/server не повторяет тот же owner spawn. Созданные
projectile получают native netUpdate и существующий shared activation
ledger; peer observations не создают новый local budget.

При `delayTicks>0` исходный NPC должен остаться активным с той же instance
и incarnation к моменту dispatch. Поиск использует его **тогдашний** центр
и тогдашние цели. Это отложенный поиск, а не сохранённый заранее маршрут.
Утрата source/owner identity, уход NPC или recycling его слота отменяют
операцию с возвратом pending reservation. Дополнительная нагрузка scheduler
может отложить исполнение; authored due time не переписывается.

## Лимиты и отказ

Новая операция участвует в том же aggregate event spawn budget, что и
существующий event-spawn. Declarative graph учитывает `stepCount`; максимум
глубины остаётся 3, а общего количества event children на activation — 32.
Native owner active slots и entity maxActive продолжают действовать.

Перед поиском резервируется не более доступного числа steps. Неиспользованная
часть возвращается при коротком маршруте, отсутствии целей, отказе native
spawn или отмене delayed action. При первом physical spawn refusal дальнейшие
steps этого плана не выпускаются. Уже созданные children сохраняются и
расходуют свои reservations. Ошибка configure деактивирует незавершённый
actor; exception path возвращает только неиспользованный резерв и сохраняет
исходную ошибку. Смерть успешно созданного child не пополняет total activation
budget: этот предел отличается от отдельного live-cap sentry PR.

## Контракт, Repair и совместное ревью

Классификация преобразования — lossless Alias Lowering явно выбранной
низкоуровневой операции. Registry владеет параметрами, dependencies и
budget metadata; compiler проецирует их в opcode 8 и выдаёт source receipts.
Пропущенные choices, null, неверный enum, тип или диапазон дают RED.

Frozen Repair различает shared child и exact dependency единственного ошибочного
consumer. При независимом binding, primary identity или другой typed reference
существующая child остаётся frozen; исправляется reference либо явно создаётся
полная совместимая child. Retarget/create принимается только при валидности
оставшегося frozen graph.

Если единственная incoming typed graph reference принадлежит ошибочному call,
а child не primary и не используется binding, Repair открывает только конфликтующие
params существующей capability, перечисленные в registry exact requirement.
Например, `spawn.params.aim/position/offsetBlocks` — только несовпадающие
leaves. Уже совместимые значения, скорость, урон, movement, lifetime, IDs, kind
и исходная reference остаются frozen; создание замены не предлагается, чтобы
не осиротить старую child. Никакое значение не вставляется автоматически:
модель должна явно передать исправленные leaves, затем проходят прежние
validator/compiler/wire gates. Удаление отдельной valid capability этим
parameter-only путём не разрешается. Логика общая по registry requirements,
без маршрутизации по family/event имени.

Velocity distribution и hit-target geometry используют общий transform/exact-NPC-exclusion owner. NetSync передаёт только текущие поддержанные protocol branches; отсутствие состояния не разрешает угадывать sampling или NPC incarnation. Shared spawn context/exception boundary остаётся одним владельцем.

## Проверка исполнения

Portable проверки охватывают registry/schema, Author request, strict wire,
receipt identity, referenced-entity Repair, budget/graph и исходный C#
consumer. Точные результаты фиксируются в описании PR на проверенном commit.

Native checks должны пройти actual DTO/executor/scheduler/spawn seams на проверяемом дереве. Исторический PASS и source pattern не являются текущей приёмкой. World loop, GPU, MP delivery и live LLM/image quality проверяются отдельно по [TESTING](../../development/TESTING_RU.md).
