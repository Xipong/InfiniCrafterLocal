# Выбор последовательности NPC и выпуск физических снарядов

Категория аудита A10. Новая `select_targets_and_emit_on_event` явно задаёт
поиск NPC и начальный transform отдельного дочернего projectile для каждого
найденного звена. Источником механики служит Author call; название предмета,
damage class, цвет и описание эффекта не выбирают этот consumer.

## Отличие, которое восстанавливает категория

В историческом `ChainProjectiles` весь цикл работал внутри одного callback:
поиск начинался с `last.Center`, очередной child создавался там же, затем
`last` становился выбранным NPC. Следующего попадания для продолжения цикла
он не ждал. Источник: [f04ee02, GeneratedProjectile.Impact.cs](https://github.com/Xipong/InfiniCrafterLocal/blob/f04ee02b456947379bdebc82047237069715ecce/ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs).

Сохранённый opcode 4 `chain_damage_on_event` выполняет другую операцию:
мгновенно наносит урон нескольким целям около одного event position. В этом
PR он сохраняет своё прежнее поведение. Новая операция имеет opcode 8 и
создаёт настоящие движущиеся projectile; дальнейшие movement, collision,
lifetime, penetration и damage принадлежат явно указанной child entity.

Например, исходная цель находится в x=0, следующие — в x=300 и x=550.
При radius 360 px и `selectionAnchor=previous_target` второй поиск идёт
из x=300 и может выбрать x=550. Поиск с фиксированным центром x=0 эту цель
не видит. Оба children создаются в момент dispatch: первый в x=0 с начальным
направлением на x=300, второй в x=300 с направлением на x=550. Второй не ждёт,
попадёт ли первый в цель.

У старого цикла не было visited-set: он исключал лишь текущий anchor и мог
вернуться к более ранней цели. Author теперь выбирает repeat policy явно.
Выбранный NPC задаёт начальное направление, а не гарантированное попадание.
Child может встретить стену, промахнуться или столкнуться с другим NPC по
своим отдельным native collision/immunity rules.

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
| `initialIgnoreCountdownUpdates` | integer 0…600 | Начальный native AI countdown исключения точного emission-anchor NPC; 0 отключает |
| `delayTicks` | integer 0…600 | Задержка dispatch в world ticks |

Радиус и порядок nearest сравниваются по точным квадратам расстояний фактических binary32 NPC Center. Координаты и разрешённый binary64 radius переводятся на общую dyadic решётку `2^-149`, после чего integer comparison сохраняет inclusive equality и различает любой положительный ортогональный компонент. Это не epsilon/расширение радиуса; слот разрешает только математически точную ничью.

Фрагмент calls для уже объявленных `bolt` и `arc_child`:

```json
{
  "id": "emit_arcs",
  "fn": "select_targets_and_emit_on_event",
  "target": "bolt",
  "params": {
    "when": "on_hit",
    "entity": "arc_child",
    "stepCount": 2,
    "stepRangeTiles": 22.5,
    "selectionAnchor": "previous_target",
    "repeatPolicy": "exclude_visited",
    "requireLineOfSight": false,
    "initialIgnoreCountdownUpdates": 10,
    "delayTicks": 0
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
`aim=velocity`, `offsetPx=0`, без `spawn_over_target`. Иначе его отдельный
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
Сохранённые opcode 1…7 не получают новый selection protocol автоматически.

Frozen Repair может исправить invalid call/reference или создать ровно
недостающую совместимую зависимость по scope. Он не вправе менять валидный
spawn существующей child ради удобства нового call. Проверка referenced
capability params общая и декларативная, без маршрутизации по family/event
имени в Repair.

Retarget/create проходит только если остальной frozen graph остаётся валиден.
Если old child был достижим только из ошибочной ссылки, её замена оставляет
новую ошибку `unreachable_entity`: targeted Repair отказывает. Он не удаляет
валидную child, не добавляет новый producer для её сохранения и не отключает
общую проверку достижимости. Успешный retarget/create проверяется для child с
независимым существующим producer; изменение всего связанного graph требует
согласованного полного Author draft.

Композиция с A11 использует общий transform/exact-NPC-exclusion helper.
ExtraAI writer версии 4 и reader версий 2/3/4 сохраняют общий v3 exclusion
segment и owner replay guard, затем optional A11 sampled-velocity state.
Отсутствие нового состояния в historical constant wire не дополняется.
Выбор всего старшего по git времени файла
`GeneratedProjectile.NetSync.cs` не является проверкой этого protocol.
Общий spawn context/exception boundary должен остаться в одном экземпляре.
Opcode A10=8 отличается от A11 alias для event-spawn opcode 1.

## Проверка исполнения

Portable проверки охватывают registry/schema, Author request, strict wire,
receipt identity, referenced-entity Repair, budget/graph и исходный C#
consumer. Точные результаты фиксируются в описании PR на проверенном commit.

При локальной композиции #27/#25/#22/#12 родитель отдельно выполнил linked
canonical C#/tModLoader/FNA headless build и полный `EngineRuntimeChecks`:
329 PASS, 0 FAIL, 0 compiler warnings/errors. Первый build отказал на
byte-identical auto-merge duplicate `HasExactTargetEmissionOrigin`; удалена
только вторая копия, затем fresh build и полный native rerun прошли.
Receipt: `pr-27/native/combined25-parent/rerun-1/verified.json` в review
artifacts; точные 184 compile inputs закреплены отдельным SHA256 manifest.
Это не Terraria world loop, GPU, SP/MP game smoke или network-delivery
проверка: эти режимы и Live LLM/image quality остаются **notRun**.
