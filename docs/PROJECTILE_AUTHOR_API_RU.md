# Projectile Author: точные формы position, immunity и when

Эта категория упрощает выбор уже существующего поведения снарядов. Канонические формы находятся в [`capability_registry.py`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py); compiler, provider schema, validator, Repair и generated inventory получают их из одного registry. Runtime wire и C# executors сохраняют прежние имена, opcodes и единицы.

Дополнение B15: [точное имя `damage_nearest_on_event` и fresh/wire диапазоны `sameTargetBias`](AUTHOR_EVENT_DOMAINS_RU.md) сохраняют те же consumers и прежнюю wire provenance, уточняя доступные новые решения Author.

## NPC immunity и число обновлений

Полный пример collision:

```json
{
  "id": "collision",
  "fn": "set_projectile_collision",
  "target": "projectile",
  "params": {
    "tileCollide": true,
    "ignoreWater": false,
    "bounceCount": 2,
    "pierce": -1,
    "updatesPerTick": 2,
    "immunity": {"localCooldown": 10}
  }
}
```

| Author | Точные поля collision в существующем wire |
|---|---|
| `immunity: "owner_shared"` | `npcImmunityMode: "owner"`, `localNpcHitCooldownTicks: -1` |
| `immunity: "once_per_npc"` | `npcImmunityMode: "local"`, `localNpcHitCooldownTicks: -1` |
| `immunity: {"localCooldown": n}` | `npcImmunityMode: "local"`, `localNpcHitCooldownTicks: n`; integer `0..600` |
| `updatesPerTick: n` | `extraUpdates: n - 1`; integer `1..6` ↔ `0..5` |

Owner immunity разделяет Terraria cooldown между снарядами владельца; consumer сам выставляет локальный engine cooldown в `-2`. Поэтому wire `-1` в этой ветви — объявленная неисполняемая техническая константа. В local ветви `-1` означает один hit по каждому NPC, а `0..600` передаются как сырые engine counts. `0` сохраняется; он не переименован в частоту по world ticks. `pierce`, lifetime и immunity независимы.

`updatesPerTick` меняет только способ записать число обновлений. Скорость, gravity, steering, drag и local cooldown сохраняют свои прежние единицы на projectile update. Таймеры сохраняют собственные conversions и фазу; compiler не масштабирует их вместе с этим параметром.

## Одна spawn position

`configure_spawn.params.position` имеет ровно две закрытые формы:

```json
{"at": "activation_origin"}
```

```json
{"above": "cursor", "heightTiles": 8, "activationDelayTicks": 15}
```

У обеих форм одинаковый список anchors:

| Anchor | Прежний wire placement и смысл |
|---|---|
| `activation_origin` | `item_use_origin`: origin вызывающего producer, включая event position или sentry origin |
| `owner_center` | `owner_center`: mounted center владельца |
| `cursor` | `cursor`: позиция курсора |
| `ground_at_cursor` | `ground_at_cursor`: прежний поиск земли под курсором |
| `native_resting_spot` | `native_resting_spot`: явный `Player.FindSentryRestingSpot` с native reachable-area clamp и выравниванием по половине hitbox height; не включает native sentry lifecycle |

`at` записывает нулевые `overTarget.heightTiles` и `overTarget.delayTicks`. `above` записывает явные `heightTiles` в диапазоне `1..80` и `activationDelayTicks` integer `0..600` в прежние `overTarget.heightTiles` / `overTarget.delayTicks`. Для отсутствия задержки в этой форме нужно написать `0`. Новая форма `at` с положительной задержкой не входит в этот контракт: это отдельное расширение прежнего Author, для которого нужна отдельная проверка runtime.

Вертикальный сдвиг происходит до расчёта `aim`, а forward `offsetPx` — после него. Поля `aim`, speed, offset и movement остаются самостоятельными решениями. Старый `above_cursor` выражается как `above: "cursor"`; старый вариант без явной высоты имел высоту один tile, которую теперь нужно написать явно.

Activation delay относится к уже созданному projectile: он занимает live slot, до активации не движется и не запускает `on_spawn`. Начальный `timeLeft` включает и authored lifetime, и дополнительные updates ожидания; задержка не вычитается из заданной активной lifetime. Это отдельный clock от `delayTicks` event action, где entity ещё не создана. Специальная capability `spawn_over_target` остаётся известна для старого wire/provenance и отсутствует в новом Author.

## Typed when и отдельная тяга владельца

В event capabilities ключ `when` задаёт обычное событие либо период:

```json
{"when": "on_hit"}
```

```json
{"when": {"everyTicks": 12}}
```

Каждая capability сохраняет прежний конечный набор допустимых events. Периодическая форма доступна только там, где раньше поддерживался `periodic`; `everyTicks` — integer `6..3600`. Она записывает `event: "periodic"` и `periodTicks: n`. Обычная строка записывает только прежний event. Ни старый ключ `event`, ни отдельный `periodTicks`, ни строка `when: "periodic"` не принимаются как новая Author форма.

Call IDs, порядок actions, producer dependencies, фаза item/projectile periodic, scheduler и бюджеты сохраняются. Optional `delayTicks` остаётся отдельным leaf event action. При Repair ошибочного `when.everyTicks` валидные siblings и остальные параметры frozen.

```json
{
  "id": "grapple_hit",
  "fn": "pull_owner_to_event_target",
  "target": "projectile",
  "params": {"when": "on_hit", "strength": 2}
}
```

Эта операция записывает старые `action: "pull_on_event"`, `actionCode: 5`, `mode: "owner_to_target"`, `radiusTiles: 1`. Константы связаны receipt с выбранным `fn`, а не с вымышленным authored числом. Strength сохраняет диапазон `0.01..4` и прежнюю точность.

Тяга направлена к active directTarget события. При отсутствии directTarget она ничего не делает; nearby NPC не выбирается. Поэтому periodic owner pull остаётся выразимым прежним no-op, а `on_expire` может иметь цель у proximity missile. Сетевая authority и executor не меняются.

`pull_on_event` теперь предлагает только NPC modes `target_to_owner` и `target_to_entity`; radius остаётся обязательным, поскольку используется fallback-поиском при отсутствии active directTarget. `target_to_entity` сохраняет прежнее назначение event position, которое на прямом hit может совпасть с центром NPC. Эта категория не добавляет новое назначение source projectile center.

## Радиусы в tiles на точной решётке

| Capability / Author leaf | Domain | Прежний integer wire |
|---|---|---|
| `damage_area_on_event.radiusTiles` | `0.5..48`, шаг `1/16` | `radiusPx = n × 16`, integer `8..768` |
| `move_proximity_missile.triggerRadiusTiles` | `0.25..32`, шаг `1/16` | `proximityRadiusPx = n × 16`, integer `4..512` |

Все 761 AoE и 509 proximity значений старого integer domain сохраняются точно. Дробь со знаменателем 16 и умножение на 16 не округляют эти значения. Произвольные дроби, например `0.1 tile`, отвергаются; compiler не округляет их. Event radius проходит тот же registry projection и receipt proof, что и movement radius. Damage basis, search, excluded direct target и authority не меняются.

## Только объявленные неисполняемые поля можно опустить

Для новой полной ваншотной композиции prompt рекомендует явно выбирать значения перечисленных ниже трёх полей, чтобы не вспоминать условие допустимости omission. Это рекомендация формы записи: перечисленные пропуски остаются допустимыми, requiredness и wire-проекции прежние. В Repair принятое отсутствие по-прежнему frozen; рекомендация не разрешает заполнять его нейтралью.

| Leaf | Когда omission разрешён | Материализованный wire |
|---|---|---|
| `configure_spawn.count` | target kind строго `child_projectile` | `1` |
| `configure_spawn.spreadRadians` | target kind строго `child_projectile` | `0` |
| `set_projectile_collision.bounceCount` | `tileCollide` строго `false` либо тот же target имеет `move_boomerang`, `move_returning_glaive`, `move_flail_tether` | `0` |

Свободная entity, на которую указывает child event, остаётся `free_projectile` и обязана явно задать root count/spread. Это правило не зависит от текущей достижимости entity через binding. У `child_projectile` порождающий event или `target_and_fire` задаёт count/spread своими параметрами.

Для `child_projectile` с `velocity.radial` или `velocity.disk` разрешённое отсутствие `configure_spawn.spreadRadians` удовлетворяет требованию нулевого fan spread через уже объявленный `default=neutral=0`. Validator учитывает эту нейтраль только для отсутствующего leaf и допустимого контекста omission: явные `null`, неверный тип или ненулевой spread остаются ошибкой. Отдельный `spreadRadians` порождающего event по-прежнему обязан быть явно задан числом `0`; Author source сохраняет отсутствие, нейтраль появляется только в wire.

У обычного движущегося projectile с `tileCollide: true` число bounce обязательно. `N` отражает N tile contacts; следующий контакт убивает. В трёх перечисленных return movements обработчик возвращается до чтения bounce counter. Явно заданные `count`, `spreadRadians` или `bounceCount`, включая игнорируемый `bounceCount: 17`, сохраняются без переписывания.

Validator проверяет контекст omission до compiler. Каждый добавленный neutral получает отдельный `declared_neutral_omission` receipt. Audit проверяет и exact output/value, и объявленную ветвь. Без Author ветвь проверяется по final-wire entity kind, selector и имени movement. Если контекст отсутствует или изменён, audit закрывается ошибкой.

Repair сохраняет отсутствие как frozen состояние. Если разрешённое исправление selector, kind или movement делает поле исполняемым, scope разрешает явно дописать только этот ставший обязательным leaf. Окончательный frozen-first merge проверяет уже принятый контекст всех rows; если ветвь осталась неисполняемой, случайное добавление прежде отсутствовавшего поля игнорируется с audit.

## Один fresh gravity movement и сохранённые записи

Новый Author выбирает `move_gravity_arc`, wire opcode `2`. Дублирующий `move_bounce` с opcode `6` сохраняется для ранее записанных программ; он отсутствует в fresh schema, cards и Repair alternatives. И gravity, и отсутствие horizontal friction между contacts, и collision bounce остаются прежними. Название movement не задаёт bounce count.

Сохранённые `runtimeProgram` и `runtimeContract.finalWireReceipts` не переписываются. Registry хранит конечные старые scalar projections для wire-only receipt audit, включая прежние immunity, spawn placement, extraUpdates, event/period и pixel radii. Неизвестный старый path, неверный тип/domain или неподтверждённый output отклоняется. Если исходный Author передан в audit, он проверяется по текущему canonical contract; retained metadata не расширяет Author grammar.

[`test_author_projectile_aliases.py`](../LocalGenerator/tests/test_author_projectile_aliases.py) проверяет реальные compiler, strict wire, source/wire-only receipts, provider-facing формы и Repair boundaries. Отдельный frozen corpus хранит старый wire с receipts от compiler до смены API. Два прежних seed/replay JSON и их hashes остаются архивными; только test helpers выражают их известные authored choices текущими формами, сохраняя ошибки диагностических случаев. Эти helpers не входят в production storage или import path.
