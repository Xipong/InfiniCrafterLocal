# Начальная скорость и создание дочерних снарядов вокруг поражённого NPC

[Author contract](../authoring/LOW_LEVEL_RUNTIME_AUTHORING_RU.md) · [Capability inventory](../generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) · [Combat inheritance](CHILD_COMBAT_INHERITANCE_RU.md) · [NPC exclusion](INITIAL_NPC_EXCLUSION_RUNTIME_RU.md)

Контракт предоставляет два независимых низкоуровневых выбора: распределение начальной скорости и точные origin/direction дочерних снарядов относительно NPC из `on_hit`/`on_crit`. Author задаёт каждый параметр. Название предмета, семейство оружия и текст запроса не выбирают ветку или формулу.

Канонические владельцы: [`capability_registry.py`](../../../generator/infini_local/core/runtime_authoring/capability_registry.py), [`technical_lowering.py`](../../../generator/infini_local/core/runtime_authoring/technical_lowering.py), [`RuntimeProgramSpec.cs`](../../../mod/InfiniCrafterLocal/Common/Models/Contracts/RuntimeProgramSpec.cs), [`RuntimeSpawnVelocity.cs`](../../../mod/InfiniCrafterLocal/Common/Runtime/RuntimeSpawnVelocity.cs), [`RuntimeHitTargetSpawn.cs`](../../../mod/InfiniCrafterLocal/Common/Runtime/RuntimeHitTargetSpawn.cs). Provider schema, cards, strict inverse, requirements, receipts и inventory выводятся из того же registry.

## `spawn.velocity`: один явный вариант

Текущий Author v7 выбирает обязательный `velocity` в блоках/с. Объекты закрыты; одновременно выбрать две ветки, пропустить обязательный предел или передать `null` нельзя. Старые pixel/update Author keys не являются aliases. Полная [таблица единиц](../authoring/MODEL_FACING_UNITS_RU.md#authority) задаёт границу с неизменённым native wire.

| Значение `velocity` | Начальная скорость |
|---|---|
| `{"speed":40}` | Прежний детерминированный веер с постоянной величиной скорости. |
| `{"fanSpeed":{"minSpeed":20,"maxSpeed":40}}` | Сохраняет каждый луч authored веера; независимо выбирает его скорость равномерно между пределами. |
| `{"radial":{"minSpeed":20,"maxSpeed":40}}` | Для каждого ребёнка выбирает направление по всей окружности и равномерную величину скорости. |
| `{"disk":{"maxSpeed":40}}` | Выбирает вектор равномерно по площади диска скоростей: радиус `max * sqrt(U)`. |
| `{"cone":{"minSpeed":20,"maxSpeed":40,"halfAngleRadians":0.2}}` | Добавляет независимое равномерное угловое отклонение к каждому лучу authored веера и независимо выбирает скорость. |

Author speed domain зависит от N этого projectile: `0..300×N` блоков/с при N=1..6. Canonical lowering сохраняет прежний wire domain `0..80` пикселей за **native projectile update**; emitter N не используется вместо child N. `min <= max`; равные пределы сохраняют точную постоянную величину. `halfAngleRadians` — половина угловой ширины, `0..π`. Native хранит скорости/углы как `float32`; нечисловые, бесконечные значения и потеря ненулевого значения в storage отвергаются каноническими проверками.

Случайные ветки допустимы для `owner_attached_projectile`, `free_projectile`, `child_projectile`. `stationary_projectile`, `field`, `temporary_helper` требуют constant-вариант: их consumer не исполняет такую начальную скорость. Selected motion/release components сохраняют свои explicit constraints; допустимость комбинации проверяется до compile и на strict wire/C# boundary.

`fanSpeed`/`cone` требуют ось `aim=cursor|facing|velocity`. `radial`/`disk` требуют `spawn.spreadRadians=0`: независимое полное распределение не должно молча поглощать authored fan spread. То же ограничение действует на `spawn_on_event.spreadRadians`, если он ссылается на radial/disk child. Ошибка разрешает Repair исправить только event spread; корректное определение ребёнка остаётся frozen. Runtime проверяет actual override до clamp.

После начального native spawn дальнейшую траекторию определяют явно выбранные movement, gravity, collisions и controller. Распределение не создаёт скрытый movement и не обещает неизменную скорость в полёте.

## `spawn_at_hit`: геометрия одного события

Новый вызов принадлежит снаряду и принимает только `on_hit` или `on_crit`. Он создаёт явно названную entity вида `free_projectile` либо `child_projectile`. Пример полного вызова:

```json
{
  "id": "impact_children",
  "fn": "spawn_at_hit",
  "target": "parent",
  "params": {
    "when": "on_hit",
    "entity": "child",
    "count": 3,
    "damageBasis": "live_parent",
    "knockbackBasis": "authored_child",
    "damageMultiplier": 0.5,
    "delay": 0.1,
    "geometry": {
      "beforeProbability": 0.85,
      "hitboxMaxSideFactor": 0.6,
      "clearanceBlocks": 0.625,
      "beforePositionJitterRadiusBlocks": 0.5,
      "beforeDirectionJitterRadians": 0.2,
      "afterFanSpreadRadians": 1.2,
      "initialIgnoreCountdownUpdates": 10
    }
  }
}
```

Все листья `geometry` обязательны. `beforeProbability` лежит в `0..1` и хранится как `double`; `hitboxMaxSideFactor` — в `0..2`; clearance и positional jitter — в `0..8` блоков; before direction jitter — в `0..π`; after fan spread — в `0..2π`; countdown — целое `0..600`. `count=1..12`, multiplier `0..4`, delay `0..10` секунд, с объявленной world-tick quantization. Damage и knockback независимо выбирают `authored_child|live_parent` по [контракту A9](CHILD_COMBAT_INHERITANCE_RU.md).

Ребёнок должен явно иметь `spawn(position={at:activation_origin}, aim=velocity, offsetBlocks=0)`. Его velocity остаётся самостоятельным выбором. Эти reference requirements проверяют правильную entity, не дописывают ей новую конфигурацию. Missing или несовместимый reference даёт Repair право выбрать совместимую entity либо создать полный новый child, если исходная child имеет независимого consumer и остаётся frozen/reachable. Для sole-reference child без primary/binding использования открываются только конфликтующие registry-exact dependency leaves существующего spawn; остальные значения и reference frozen, замена не создаётся. Модель явно пишет поправку, compiler её не достраивает. C# проверяет исходные presence и exact значения **до** legacy normalization, поэтому отсутствующие поля, другой регистр, отрицательный over-target offset и `null` не становятся валидными за счёт defaults/clamp.

### Точная формула

Native формула ниже использует world pixels: lowerer заранее пишет `clearancePx = 16 × clearanceBlocks` и такой же scale для positional jitter. На admission сохраняются центр `C`, `max(width,height)` поражённого NPC и ось события `D`. Ось события — нормализованная текущая velocity родителя; при её отсутствии используется сохранённая initial direction существующего event producer. Геометрический радиус равен `R = max(width,height) * hitboxMaxSideFactor + clearancePx`.

Для каждого ребёнка независимо выбирается before-ветка с вероятностью `beforeProbability`. При `0` она отключена, при `1` выбрана всегда:

- **Before:** origin `C - D*R` плюс равномерный по площади disk jitter; direction — `D` с равномерным отклонением в пределах заданного before half-angle.
- **After:** direction повёрнута на `(i/(N-1)-0.5)*afterFanSpreadRadians`, origin `C + direction*R`. Здесь `i` — индекс в полном эффективном batch, включая before children. При `N=1` угол равен нулю.

`beforeProbability` выбирает сторону рождения, а не вероятность повторного попадания. Radial/disk velocity ребёнка может изменить направление относительно переданной оси. Отдельные hitbox, movement, immunity, tile collision и NPC movement продолжают определять реальное столкновение.

Старая готовая split-формула также использовала скорость вида `max(4,parent.speed*0.78)`. **Этой формулы здесь нет:** скорость задаёт `child.spawn.velocity`. A11 не обещает полного old-split parity или прежней вероятности повторного попадания.

## Owner, задержка, бюджеты и сеть

Выбор случайного состояния принадлежит firing owner. Один seed после admission определяет batch; отдельные child velocity streams не меняют геометрию siblings. Constant-вариант не читает RNG. При delayed target action snapshot и seed фиксируются при постановке в bounded queue: изменение позиции/размера NPC, скорости/урона родителя или общего RNG не изменяет уже принятое действие. A9 parent combat snapshot передаётся вместе с геометрией. Pressure может уменьшить эффективный count согласно существующему activation/owner budget; deterministic fan строится по этому count.

Target geometry не требует, чтобы NPC всё ещё был жив при dispatch. При положительном `initialIgnoreCountdownUpdates` snapshot дополнительно хранит slot и incarnation token; reuse slot с другим token отказывает всему ещё не созданному batch и возвращает reservation. При **нуле** используется `Exclusion.None`: центр, ось и seed остаются frozen, но отсутствует generation cancellation guard. Даже в этом случае новая NPC не выбирается как новый источник геометрии.

Countdown убывает **перед collision** на каждом native AI update. `10` исключает contact до первого AI и девять последующих post-AI collision opportunities; `1` — только до первого AI; `0` отключает исключение. `extraUpdates` ускоряет расход, activation telegraph тоже расходует countdown. Это не десять полных world ticks или десять полных collision updates. Исключение касается только exact исходного NPC; остальные hit consumers сохранены.

Multi-emission резервирует bounded batch. Перед каждым native вызовом caller передаёт одну reservation. Обычный отказ возвращает её caller-у; exception возвращает её внутри `SpawnRuntimeEntity`, а caller `finally` возвращает только ещё не начатые попытки. Частично сконфигурированный host деактивируется без terminal effects. Успешные дети используют один activation ledger; peer observation не создаёт capacity.

Projectile ExtraAI **v4** добавляет к v3 presence-byte и выбранный initial velocity vector, когда distribution активна. V2/v3 отвергаются; active writer/reader branches перечислены в `GeneratedProjectile.NetSync.cs`. Для новой distribution отсутствие sampled state, invalid presence-byte, non-finite vector или обрезанный payload оставляют actor inert до нового валидного payload. Owner сохраняет собственный countdown/vector при observation той же generation. Activation delay восстанавливает выбранный vector один раз; повторная hydration не запускает движение заново и не бросает RNG.

## Lowering, provenance и сохранённые определения

Выбор структуры и literal kind — **Alias Lowering**; physical unit scales и явная секундная quantization принадлежат canonical `ParamSpec`. Constant-вариант точно пишет старый `spawn.speedPxPerTick`. Случайная ветка пишет зарегистрированные `spawn.velocityDistribution.*`, literal kind и inactive constant slot `0`. Target geometry пишет `hitTargetSpawn.*` и literal ordinary spread `0`, сохраняя canonical wire action `spawn_entity_on_event` и opcode `1`. Runtime исполняет эти явные параметры; compiler не вычисляет trajectory, не выбирает branch и не изобретает child.

Каждый leaf и literal имеет exact source/call ID/target receipt. Новый `wire_action` связывает fn alias с сохранённым opcode; fixed action/name receipts исходят от `.fn`. Strict audit требует единственного полного consistent variant и не позволяет подменить новый fn старым, скрестить radial/cone paths, удалить geometry вместе с receipts или приписать новому distribution старый speed receipt.

`_wire_projection_witness` проверяет конечную current проекцию и возвращает exact rows для audit. Он не восстанавливает Author и не является importer. Source-backed audit требует current source paths; source-free подтверждает только consistent current wire. Constant-speed source path — `.params.velocity.speed`; старые receipts не принимаются. Archived bytes не являются шаблоном нового Author.

## Проверки и предел доказательства

Python acceptance проходит действительные provider strict schema/inverse, validator, compiler, final-wire audit и frozen Repair: все пять velocity variants, branch/range/ref constraints, receipt loss/spoofing, current positive/refusal inputs, exact child creation и ignored attempted edits. Native tests отдельно проверяют retained seed, raw references, sampled vector после delay, malformed ExtraAI, reused incarnation и reservation ownership.

[`EngineRuntimeChecks.SpawnDistributions.cs`](../../../tests/native/gameplay/EngineRuntimeChecks.SpawnDistributions.cs) содержит шесть native сценариев: strict DTO; seeded sampler с disk-area moment; actual `NewProjectileDirect` boundary во всех authority roles; delay/ExtraAI/hydration; frozen hitbox geometry/branch endpoints; delayed target emission с точными combat snapshots, slot reuse и refund on exception. Native interception наблюдает аргументы настоящего spawn entry и останавливается exception; фиктивный успешный actor не создаётся.

Native execution требует .NET/tModLoader и игровых references. Отсутствующая среда означает `notRun`, не current PASS; команды — [TESTING](../../development/TESTING_RU.md).
