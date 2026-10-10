# Предметные формы Author: точные проекции в прежний runtime wire

Категория аудита: B3, B4, B5, B13, B14. Зависимость: общая поддержка [типизированных параметров](TYPED_AUTHOR_PARAMETER_PROJECTIONS_RU.md).

Все изменения ниже — lossless Alias Lowering. Модель явно выбирает вариант. Ни имя предмета, ни DamageClass, ни описание не выбирают механику. C# DTO и исполняемые поля сохраняются; registry, compiler и receipts задают новую форму полного Author. Repair пропуск по-прежнему означает «не менять».

## Размещение одного слоя

| Author operation | Author params | Runtime placement |
|---|---|---|
| `configure_tile_placement` | `tileId`, `placeStyle` | выбранные поля и `wallId=-1` |
| `configure_wall_placement` | `wallId`, `placeStyle` | выбранные поля и `tileId=-1` |

Активный ID: целое 0…65535; style: целое 0…255. Выключающий −1 не является вариантом активного ID. Два включённых слоя нельзя выразить одной новой operation. Их общий exclusive component также не позволяет записать два placement payload на один item body.

Binding сохраняет exact `placementCallId`, `stackCost=1`, `contactDamage=false` и прежнюю транзакцию accepted placement/возврата из ledger. `present_placed_item_sprite` ссылается только на `configure_tile_placement`. Wall operation не приобретает tile presentation.

Неактивный ID — зарегистрированная `CapabilitySpec.fixed_wire_literals` константа. Receipt ссылается на реальный `.fn`, имеет статус `technical_projection` и проверяется по точному значению, output и originating call. Старый `configure_placeable` остаётся внутренним владельцем сохранённой wire provenance; новый provider catalog его не предлагает.

## Видимость собственного held sprite

| `customHeldSprite` | Прежний wire `releaseTiming` | Смысл |
|---|---|---|
| `hidden` | `immediate` | Скрыть собственный held root |
| `visible` | `on_release` | Сохранить root во время активного использования |
| `inherit` | пустая строка | Существующее поведение по presentation metadata |
| поле отсутствует | поле отсутствует | Существующее поведение отсутствующего hint |

Это только собственный held root. `hideUseGraphic` отдельно управляет vanilla sprite. Для presentation с `visual.renderSizePx` inherit следует этому флагу; без такой metadata сохраняется историческое поведение. Новый Author не выбирает между `on_release` и `after_charge`: они не задавали разное scheduling. Старые сохранённые значения, включая `after_charge`, остаются неизменными при wire-only проверке.

## Recall без параметров blink

```json
{"id":"recall","fn":"recall_home_on_use","target":"item","params":{"cooldownTicks":60}}
```

Проекция: `mobilityMode="recall_home"`, `mobilityCooldownTicks=60`, `mobilityRangeTiles=0`, `mobilitySafeTileOnly=false`. Последние два поля не исполняются в recall branch и имеют отдельные fn-selected receipts. Cooldown остаётся общим для player mobility, а не индивидуальным cooldown конкретного binding. Требуется явный `apply_item_effects` binding.

Существующий `move_player_on_use` теперь допускает только `mode="blink_to_cursor"`, сохраняя range, safe-tile policy и cooldown. Общий exclusive slot не позволяет двум operations перезаписать один mobility component.

## Бонусы комплекта брони

```json
{"slot":"head","setKey":"coral","setBonuses":{"moveSpeedBonusPercent":25,"lifeRegenHpPerSecond":0.5,"minionSlotsBonus":1}}
```

В `configure_armor.params.setBonuses` находятся те же 11 independently authored stats с обычными именами. Все units, bounds, signed values, percent/100 и HP/s×2 проекции сохранены. Объект, если выбран, содержит хотя бы одно поле. Любой ненейтральный set bonus требует head slot и непустой exact setKey для реально надетых head/body/legs. Нулевые выбранные значения не превращаются в бонусы.

Compiler пишет отдельный receipt на каждый `params.setBonuses.<stat>`, а прежние `ArmorSpec.SetBonus…` поля сохраняются. Генератор equipment bounds и AST-проверка исполняемых DTO теперь разворачивают registry leaf paths; прежние C# safety clamps не исчезают из-за группировки Author.

## Условия с включительной границей

`require_use_condition.params.condition` — ровно один вариант:

```json
"grounded"
"not_wet"
{"lifeAtLeast":50}
{"manaAtLeast":100}
```

Resource thresholds — целые 0…1000; сравнение сохраняет `>=`. Нет противоположного неиспользуемого threshold, неявного AND или нового per-binding scope. Пустой объект и два resource keys одновременно не проходят strict shape.

Неверный известный threshold получает точный nested Repair path. Полностью отсутствующий или невыбранный вариант открывает только `params.condition`; модель должна явно передать полный допустимый вариант. Исправление другого компонента не меняет уже корректное условие.

## Совместимость и проверка

Canonical owners: `capability_registry.py`, `program_schema.py`, `compiler.py`, `technical_lowering.py`, `validator.py`, `repair_scope.py`. Их generated schema/cards обновляются штатными generators. Provider получает ту же взаимоисключающую форму через доказанное disjoint-union преобразование, а nullable inverse использует тот же контракт.

`retained_receipt_params` разрешает проверять только конечный список прежних сохранённых путей. При наличии исходного Author проверка требует новую canonical форму; неизвестный параметр, изменённый output, потерянный literal receipt и неверное значение остаются RED. Production migration/importer не добавлен.

Frozen seed/replay JSON и исторические hashes сохранены. Только тестовые helpers выражают исторический Author sample новой формой перед повторным compile; delivery wire сравнивается с прежним без изменения mechanics или metadata. Отдельные regressions проверяют все visibility states, placement limits, recall constants, 11 set projections, отрицательные варианты и frozen nested Repair. Native build/game smoke в текущей среде — `notRun`.
