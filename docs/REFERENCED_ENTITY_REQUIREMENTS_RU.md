# Совместимость ссылок между authored entities

В `RequirementSpec` добавлены два общих ограничения для явных emission adapters:

- `referenced_entity_capability_params` требует одну конкретную capability на
  referenced child и полное совпадение перечисленных authored params.
- `referenced_entity_without_capability` запрещает второй, конфликтующий adapter
  на referenced child; это отрицательное требование, не supporting dependency.

`param` указывает именно typed entity-reference параметр текущего вызова.
Registry остаётся owner значения и диапазонов. `equals` не материализует
отсутствующие параметры. Для `number` равные JSON numbers `0`/`0.0` допустимы;
`integer`, boolean, string и остальные типы сохраняют точную идентичность,
поэтому `false` и `0.0` не заменяют integer `0`.

Оба вида reference requirements исключены из dependency closure **текущей**
source entity. Требуемый `configure_spawn` принадлежит referenced child, поэтому
исправление одного range leaf у source не даёт права добавлять ей spawn/movement.
Только reference blocker открывает отдельный complete-child create slice.

Это **validation**, не изменение authored программы. Реальный emission adapter
классифицирует собственную детерминированную проекцию отдельно как Alias Lowering.
Никаких новых gameplay capabilities данный framework сам не регистрирует.

## Frozen-first Repair

Ошибка `reference_requirements_unsatisfied` принадлежит точному leaf
`calls[index].params.<reference>`. Existing child может быть валиден сам по себе,
поэтому его spawn, movement и другие настройки не размораживаются.

Модель может выбрать совместимую существующую entity либо явно создать новую
entity допустимого kind с полным набором компонентов и position driver. Create
permissions для её calls распространяются только на **новые** entities; existing
calls остаются read-only. Capability cards включают support для нового child,
а запрещённая capability не добавляется в dependency closure. Полная validation
после merge проверяет reference constraints, reachability, event graph, depth и
общий budget; Repair не достраивает недостающие choices.

Regression проверяет новые requirement kinds на изолированной registry entry,
числовую/boolean идентичность, точные allowed references, retarget и полноценный
create child с hostile изменениями уже валидных siblings. Интеграционные witnesses
принадлежат использующим framework реальным capabilities A10/A11.
