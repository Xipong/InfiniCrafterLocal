# Именованные эффекты основного, альтернативного и удерживаемого предмета

Это дополнение к прямому Author API: модель явно задаёт идентичность группы и связывает её с потребителем. Owner полей — [registry](../../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py), shape binding — [program_schema.py](../../../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py), точные проекции и receipts — [technical_lowering.py](../../../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py).

## Контракт и совместимость

Пять существующих capability принимают optional `params.effectGroupId`:

| Capability | Эффекты внутри выбранной группы |
|---|---|
| `restore_resources_on_use` | `healLife`, `healMana`, `potion` |
| `apply_vanilla_buff_on_use` | append в `extraBuffs[]` с точными ID и длительностью |
| `apply_generated_buff_on_use` | `generatedBuff`, включая объявленные unit conversions и optional neutral omissions |
| `move_player_on_use` | blink-to-cursor, range, cooldown и safe-tile policy |
| `recall_home_on_use` | recall с authored cooldown и точными registry literals `mobilityMode="recall_home"`, `mobilityRangeTiles=0`, `mobilitySafeTileOnly=false` в выбранной группе |

ID соответствует `[a-z][a-z0-9_]{0,47}`. Одинаковый литерал складывает компоненты одной группы; разные литералы разделяют их. Single-компоненты и exclusive ownership проверяются отдельно в каждой группе, append-компонент сохраняет все authored native buffs. Blink и recall занимают один exclusive `item_mobility` slot внутри одинаковой или default-группы; разные явно названные группы и named/default пара независимы. Разный input сам по себе не разделяет slot. ID ничего не сообщает об оружейной family, категории, визуальном carrier или выборе способности.

У `apply_item_effects` action появляется optional `effectGroupId`. Пример двух binding-фрагментов:

```json
[
  {"id":"drink","input":"primary_use","usePolicy":{"action":{"kind":"apply_item_effects","targetId":"item","effectGroupId":"healing"},"stackCost":1,"contactDamage":false}},
  {"id":"blink","input":"alternate_use","usePolicy":{"action":{"kind":"apply_item_effects","targetId":"item","effectGroupId":"escape"},"stackCost":0,"contactDamage":false}}
]
```

Calls с `effectGroupId:"healing"` и `effectGroupId:"escape"` должны явно существовать. Binding выбирает только названную группу; содержимое другой группы или ungrouped `gameplay` не дополняет её. Group selectors запрещены у `spawn_entity`, `use_item_body`, placement и passive equipment actions.

Если поле отсутствует и в calls, и в action, сохраняется прежняя ungrouped семантика `gameplay`. Compiler не создаёт именованные группы для старого ответа, не добавляет optional binding receipts и не меняет старый wire из-за самого наличия новой возможности. Отсутствие selector в binding не означает «выбрать первую группу».

Класс преобразования — **Alias Lowering**: только буквальная, без потерь проекция уже выбранных calls в отдельный контейнер. Compiler записывает `runtimeProgram.effectGroups[]` в порядке первого появления ID и selector в окончательный, отсортированный binding. Каждый component field, group ID и selector имеет source receipt; для объявленных нейтралей сохраняется отдельное доказательство отсутствия. Создание entity или невидимого projectile не требуется.

## Native use и общая задержка перемещения

`GeneratedItem` выбирает группу по точному активному binding. До использования native `Item.healLife`, `healMana`, `potion` проецируются из этого выбранного источника; `Item.buffType/buffTime` очищаются, потому что текущие vanilla-бафы исполняются только через явные `ExtraBuffs` записи. Тот же источник обслуживает generated utility и mobility. Native healing/consumption продолжает выполнять Terraria.

Quick heal и quick mana выбирают только primary binding. Подготовка кандидатов обновляет native effect fields перед native selector, поэтому предыдущее альтернативное использование не прячет primary healing. Multiplayer quick-utility ticket по-прежнему фиксирует player/item/definition/primary binding; server admission и commit выбирают эту же primary group. Транспорт не повторяет native лечение или `UseItem`.

[Optional вероятность расхода собственного стека](OWN_STACK_CHANCE_RU.md) — независимая binding policy. Она не маршрутизирует group selection и не подавляет успешно выполненные эффекты; exact input Repair сохраняет одновременно frozen group selector и probability. Held-refresh dedup не заменяет completed-use receipt расхода.

Все группы и все предметы одного игрока используют прежний **единый player mobility cooldown**. Две разные группы recall/blink не создают независимые таймеры. Pure mobility attempt, отказанный после admission, не получает успешный stack-consumption receipt; удача primary не может оплатить отказавший alternate. Если группа содержит другие успешно выполненные эффекты, сохраняется прежняя mixed-use семантика без выдуманного общего rollback.

## Явный эффект удерживания

Новая capability `refresh_generated_effect_group_while_held` применяется к `item_body` и требует `params.effectGroupId`. Она компилируется в `runtimeProgram.heldEffectGroupId` и может ссылаться только на группу из **одного** `apply_generated_buff_on_use` call. Healing, native buffs и mobility нельзя незаметно превратить в ежетиковый эффект удерживания. Одна группа может также иметь explicit active-use consumer.

`HoldItem` обновляет тот же generated utility entry, когда игрок жив, активен и держит именно этот `Item`. Эффект выполняется локальным владельцем и сервером; remote clients не изменяют чужие player stats. Повторный `HoldItem` того же player/item/data/group в одном world tick ничего не добавляет. Существующий utility consumer объединяет одинаковый эффект, сохраняет независимые длительности разных эффектов и ограничивает список 32 entries.

Без предметной усталости server snapshot запрашивается при первом refresh и затем не чаще одного раза в 30 world ticks для неизменной идентичности. Это частота транспортных снимков, а не задержка действия gameplay: авторитетные peers обновляют эффект каждый tick. После смены предмета refresh прекращается, а уже применённый эффект живёт оставшиеся authored `durationTicks`. Особенно короткая длительность может истекать между сетевыми снимками у remote presentation; эта ветка не обещает отдельный бессрочный passive-buff канал.

## Баланс будущей utility-генерации

Author оценивает **effective uptime**, а не только длительность одного применения: бесплатное повторное применение может поддерживать короткий эффект постоянно. `durationTicks` — время жизни эффекта, не КД повторного использования. Повтор идентичного generated-эффекта сохраняет большую из оставшейся и новой длительности, без повторного умножения силы; разные эффекты сосуществуют, и их статы объединяются под player caps.

`oreSenseEnabled` включает native Spelunker treasure highlighting: подходящие руды, сундуки и кристаллы жизни. Это не ore-only фильтр и не радиус детектора. Модель должна учитывать реальную широту utility, текущую стоимость применения и доступность постоянного эффекта; разовая стоимость рецепта не является recurring cost. Ограничение, расход или намеренно более слабый длительный эффект выбирает Author явно из поддерживаемых механик. Намеренно бесплатная sustained utility допустима, но её нельзя оценивать как ограниченный краткий burst или описывать неисполняемые charges/КД.

В этой ветке **не добавлен общий activation cooldown API**: существующий mobility cooldown не является КД generated-бафа. Инструкции применяются к будущим Author-запросам и не меняют сохранённые рецепты. Gameplay Repair остаётся leaf-local: новая рекомендация баланса не даёт права менять валидные эффекты, их длительности или принятые отсутствия при исправлении другой ошибки. Проверки serialized Author/Repair — [test_author_prompt_clarity.py](../../../LocalGenerator/tests/test_author_prompt_clarity.py).

## Предметная усталость generated-бафа

`apply_generated_buff_on_use.params.exhaustionTicks` — один optional integer 0..21600 world ticks. Считается от успешного применения или refresh, независимо от `durationTicks`. Отсутствие остаётся отсутствием; literal `0` остаётся `0`, оба не запускают усталость. Invalid present значение не заменяется нейтралью. Сам параметр — reuse policy, не полезный stat: он не делает пустой generated-баф исполняемым. При unrelated Repair принятые значение/отсутствие frozen; omission в patch означает не менять.

Усталость относится к определению предмета у конкретного игрока: копии, слоты и generated-группы этого определения разделяют срок; разные предметы и игроки независимы. Пять exhausted definitions показываются пятью отдельными статусами с одной утверждённой нейтральной иконкой, названием соответствующего предмета и его оставшимся временем. Неудачный повтор не освежает ни баф, ни усталость, действующий баф не снимается. Группа без/с нулём `exhaustionTicks` не обходит уже начатую усталость этого же определения.

Политика ограничивает **только generated utility buff**, не всё использование предмета. Она не меняет native лечение/бафы, mobility, события/VFX и прежнюю стоимость; смешанное использование может выполнить эти независимые части при подавленном generated-бафе. Основная атака и добыча сохраняют собственные authored параметры темпа; возможность медленной мощной атаки и возможность без отдельного КД остаются независимыми решениями модели. Политика не вводится автоматически и не ретрофитит сохранённые предметы.

Held-refresh также проходит source-item gate: положительная усталость делает повтор периодическим, а не непрерывным. Quick Utility применяет тот же generated-баф на server Commit без повторного native heal/consume; существующий post-use handshake не превращается в предварительное разрешение всей активации. Новый scalar losslessly проецируется в default или exact named `generatedBuff.exhaustionTicks` со своими receipts; отсутствие не создаёт поле бафа или receipt. Диагностический audit roster отражает текущий контракт без специальной ветки ради старых compiled bytes.

Таймеры session-only: очищаются при смерти, Initialize/входе и выходе из мира; они не сохраняются в player save и не переносятся физическим предметом. Таблица ограничена 64 активными определениями: при заполнении новое положительное exhaustion-применение отклоняется, старый таймер не вытесняется. Quick Commit вычитает уже прошедшее от Prepare время независимо для бафа и усталости: истёкший за время доставки баф не исполняется снова, но ещё действующая усталость сохраняется. Отказ по усталости фиксируется для данного Prepare и не превращается в успешное применение, если таймер закончился до Commit; native лечение/расход не повторяются и не откатываются.

Сервер хранит авторитетные сроки. Существующий utility snapshot **v5** передаёт отдельные строки; клиентские значения сервер только читает/отбрасывает, включая коррекцию владельцу при отказе. Generator/mod и все host/client peers должны обновляться согласованно. CPU native codec/consumer checks не доказывают живую SP/MP-сессию.

## Строгая граница и Repair

Present `effectGroups` содержит 1..48 групп; эта граница согласована с 48 Author calls. Named `extraBuffs` принимает до 48 authored rows без скрытого truncation. Legacy gameplay extra buffs сохраняют прежний контракт. Native DTO допускает только поля эффекта, строго проверяет ID, числовые bounds и generated-buff duration, отклоняет null/empty group arrays, неизвестные поля, orphan groups и неверные ссылки. Нейтральные поля, которые сериализует C# DTO, не превращаются в новый эффект.

Validator не выбирает группу по названию или payload. Ошибочная ссылка открывает Repair только её exact leaf; существующие definitions передаются как read-only context. Валидные calls, другая group reference, policy costs и другие params остаются frozen. Для действительно отсутствующего consumer разрешён новый binding только к существующей группе; Repair не придумывает missing effect design.

## Проверки и предел доказательства

[Contract regressions](../../../LocalGenerator/tests/test_item_effect_groups.py) проверяют независимые группы каждого вида, композицию, held-only маршрут, frozen Repair, строгий wire, нейтральные omission receipts, source/group identity и отсутствие новых групп в legacy output. AST surface audit сопоставляет `RuntimeItemEffectGroupSpec` с реальными registry/wire fields и отвергает незарегистрированное поле.

[Native checks](../../../tools/native/EngineRuntimeChecks.NamedItemEffects.cs) подключены к `EngineRuntimeChecks.csproj`: реальный native generic-use tail и quick selectors, shared mobility cooldown/consumption, exact-held identity/authority/expiry, ограничение snapshot requests и native DTO roundtrip/refusals. Счётчик snapshot requests проверяет production sender boundary с подавленным socket send; он не подменяет end-to-end multiplayer smoke.

При отсутствии .NET 8, stable tModLoader и внешних runtime dependencies C# build, запуск этих native checks и игровые SP/MP smoke записываются **`notRun`**. Успешные Python/static gates не означают выполненную игровую проверку.


## Временные боевые бонусы

Необязательный объект `combat` у `apply_generated_buff_on_use` содержит все пять явных полей: `defensePoints` (0–100), `attackSpeedPercent` (0–100), `critChancePoints` (0–100), `damagePercent` (0–200), `damageClass` (`generic`, `melee`, `ranged`, `magic`, `summon`, `throwing`). Нулевые числа сами по себе не образуют эффект. Отсутствующий объект не материализуется; явно переданный null или неполный объект недопустимы.

Defense прибавляется в native `statDefense`, speed и damage делятся на 100 один раз, crit измеряется процентными пунктами. Damage применяется к выбранному native классу; generic наследуется классами по правилам Terraria. Совпадающий эффект обновляет длительность без повторного сложения. Разные эффекты суммируются с лимитами defense/speed/crit 100 и damage 200 на каждый класс. Истечение удаляет вклад. Активный HUD показывает значения и длительности; tooltip предмета показывает объявленные бонусы.

Для активации достаточно одного из трёх путей: активная `apply_item_effects` кнопка с exact group; `refresh_generated_effect_group_while_held` для named generated-buff-only группы; equipment reaction `apply_generated_buff_on_event` с тем же effectGroupId. Held/reaction путь не требует добавлять активную кнопку.

Utility snapshot protocol v6 передаёт combat внутри каждой записи, проверяет конечные диапазоны и передаёт класс ограниченным enum-byte. После полного успешного чтения агрегат пересобирается из записей. Подделанные клиентские числа продолжают отбрасываться сервером. Все peers должны использовать одну версию мода. Старые JSON определения без combat сохраняют отсутствие поля.

## Событие от конкретной кнопки

Используется единый контракт `when:{"on":"on_use","useInput":"primary_use"|"alternate_use"|"both"}`. Wire сохраняет `useInput`; прежний `when:"on_use"` означает обе кнопки. Executor фильтрует originating input до постановки delayed action в очередь. Второго поля `input`/`sourceInput` нет.
