# Именованные эффекты основного, альтернативного и удерживаемого предмета

Это дополнение к прямому Author API: модель явно задаёт идентичность группы и связывает её с потребителем. Owner полей — [registry](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py), shape binding — [program_schema.py](../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py), точные проекции и receipts — [technical_lowering.py](../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py).

## Контракт и совместимость

Четыре существующие capability принимают optional `params.effectGroupId`:

| Capability | Эффекты внутри выбранной группы |
|---|---|
| `restore_resources_on_use` | `healLife`, `healMana`, `potion` |
| `apply_vanilla_buff_on_use` | append в `extraBuffs[]` с точными ID и длительностью |
| `apply_generated_buff_on_use` | `generatedBuff`, включая объявленные unit conversions и optional neutral omissions |
| `move_player_on_use` | выбранный mobility mode, range, cooldown и safe-tile policy |

ID соответствует `[a-z][a-z0-9_]{0,47}`. Одинаковый литерал складывает компоненты одной группы; разные литералы разделяют их. Single-компоненты проверяются отдельно в каждой группе, append-компонент сохраняет все authored native buffs. ID ничего не сообщает об оружейной family, категории, визуальном carrier или выборе способности.

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

`GeneratedItem` выбирает группу по точному активному binding. До использования native `Item.healLife`, `healMana`, `potion`, `buffType`, `buffTime` проецируются из этого выбранного источника; затем тот же источник обслуживает extra buffs, generated utility и mobility. Native healing/consumption продолжает выполнять Terraria.

Quick heal и quick mana выбирают только primary binding. Подготовка кандидатов обновляет native effect fields перед native selector, поэтому предыдущее альтернативное использование не прячет primary healing. Multiplayer quick-utility ticket по-прежнему фиксирует player/item/definition/primary binding; server admission и commit выбирают эту же primary group. Транспорт не повторяет native лечение или `UseItem`.

[Optional вероятность расхода собственного стека](OWN_STACK_CHANCE_RU.md) — независимая binding policy. Она не маршрутизирует group selection и не подавляет успешно выполненные эффекты; exact input Repair сохраняет одновременно frozen group selector и probability. Held-refresh dedup не заменяет completed-use receipt расхода.

Все группы и все предметы одного игрока используют прежний **единый player mobility cooldown**. Две разные группы recall/blink не создают независимые таймеры. Pure mobility attempt, отказанный после admission, не получает успешный stack-consumption receipt; удача primary не может оплатить отказавший alternate. Если группа содержит другие успешно выполненные эффекты, сохраняется прежняя mixed-use семантика без выдуманного общего rollback.

## Явный эффект удерживания

Новая capability `refresh_generated_effect_group_while_held` применяется к `item_body` и требует `params.effectGroupId`. Она компилируется в `runtimeProgram.heldEffectGroupId` и может ссылаться только на группу из **одного** `apply_generated_buff_on_use` call. Healing, native buffs и mobility нельзя незаметно превратить в ежетиковый эффект удерживания. Одна группа может также иметь explicit active-use consumer.

`HoldItem` обновляет тот же generated utility entry, когда игрок жив, активен и держит именно этот `Item`. Эффект выполняется локальным владельцем и сервером; remote clients не изменяют чужие player stats. Повторный `HoldItem` того же player/item/data/group в одном world tick ничего не добавляет. Существующий utility consumer объединяет одинаковый эффект, сохраняет независимые длительности разных эффектов и ограничивает список 32 entries.

Server snapshot запрашивается при первом refresh и затем не чаще одного раза в 30 world ticks для неизменной идентичности. Это частота транспортных снимков, а не задержка действия gameplay: авторитетные peers обновляют эффект каждый tick. После смены предмета refresh прекращается, а уже применённый эффект живёт оставшиеся authored `durationTicks`. Особенно короткая длительность может истекать между сетевыми снимками у remote presentation; эта ветка не обещает отдельный бессрочный passive-buff канал.

## Строгая граница и Repair

Present `effectGroups` содержит 1..48 групп; эта граница согласована с 48 Author calls. Named `extraBuffs` принимает до 48 authored rows без скрытого truncation. Legacy gameplay extra buffs сохраняют прежний контракт. Native DTO допускает только поля эффекта, строго проверяет ID, числовые bounds и generated-buff duration, отклоняет null/empty group arrays, неизвестные поля, orphan groups и неверные ссылки. Нейтральные поля, которые сериализует C# DTO, не превращаются в новый эффект.

Validator не выбирает группу по названию или payload. Ошибочная ссылка открывает Repair только её exact leaf; существующие definitions передаются как read-only context. Валидные calls, другая group reference, policy costs и другие params остаются frozen. Для действительно отсутствующего consumer разрешён новый binding только к существующей группе; Repair не придумывает missing effect design.

## Проверки и предел доказательства

[Contract regressions](../LocalGenerator/tests/test_item_effect_groups.py) проверяют независимые группы каждого вида, композицию, held-only маршрут, frozen Repair, строгий wire, нейтральные omission receipts, source/group identity и отсутствие новых групп в legacy output. AST surface audit сопоставляет `RuntimeItemEffectGroupSpec` с реальными registry/wire fields и отвергает незарегистрированное поле.

[Native checks](../tools/EngineRuntimeChecks.NamedItemEffects.cs) подключены к `EngineRuntimeChecks.csproj`: реальный native generic-use tail и quick selectors, shared mobility cooldown/consumption, exact-held identity/authority/expiry, ограничение snapshot requests и native DTO roundtrip/refusals. Счётчик snapshot requests проверяет production sender boundary с подавленным socket send; он не подменяет end-to-end multiplayer smoke.

При отсутствии .NET 8, stable tModLoader и внешних runtime dependencies C# build, запуск этих native checks и игровые SP/MP smoke записываются **`notRun`**. Успешные Python/static gates не означают выполненную игровую проверку.
