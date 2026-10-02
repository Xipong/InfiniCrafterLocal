# Объявленные нейтральные пропуски Gameplay Author

[Author](LOW_LEVEL_RUNTIME_AUTHORING_RU.md) · [Transformation classes](TECHNICAL_LOWERING_POLICY_RU.md#transformations) · [Frozen Repair](TARGETED_REPAIR_PROTOCOL_RU.md#frozen-first)

<a id="contract"></a>
## Условие разрешения

Только optional `ParamSpec` с объявленным `default`, **тем же типом** и равным `neutral` разрешает отсутствие как точный выбор этой нейтрали. Owner — [capability_registry.py](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py); точный predicate — [declared_neutral_omissions](../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py#L138). `neutral` без `default`, допустимый ноль и C# constructor default права не дают.

Это семантика **полного** Author JSON, не ремонт невалидного ответа и не classifier. После полной композиционной проверки compiler материализует объявленную нейтраль в прежний полный wire, не переписывая исходный Author. Explicit non-neutral value сохраняется; неверный type/range и недостающая dependency остаются RED.

Schema `default` — аннотация, не обещание provider constrained decoding. Только nullable-обёртка optional object property в **фактически применённом `json_schema`** кодирует omission через null перед local validation. В `json_object/off` null такой эквивалентности не имеет. Unknown keys, required non-null fields и null array elements не удаляются; provider relaxation не разрешает broader projection. Детали precision/null fixes — [исторический audit fixes](HISTORY_RU.md#audit-81509e2).

<a id="fields"></a>
## Узкое разрешение registry

| Capability | Поля → объявленная нейтраль |
|---|---|
| `configure_item_stats` | `manaCost → 0` при любом explicit damageClass; melee может потреблять mana, magic может иметь нулевой cost |
| `configure_item_use` | `holdoutOffsetX/holdoutOffsetY → 0` **независимо** друг от друга |
| `apply_generated_buff_on_use` | `miningSpeedMultiplier → 1`; `oreSenseEnabled → false` (wire `oreSenseRadiusTiles=0`); `moveSpeedBonusFactor/jumpSpeedBonusPxPerTick/manaRegenBonusPoints/lifeRegenHpPerSecond → 0` |

Это девять параметров в трёх capabilities текущего узкого изменения, не blanket optionality. Units и старые wire conversions не меняются; актуальный executable перечень — registry.

<a id="dependencies"></a>
## Совместные зависимости важнее optionality

Generated buff требует хотя бы один **ненейтральный исполняемый** эффект. Полностью отсутствующий/нейтральный набор с выключенным light — RED; цвет без light не эффект. `durationTicks/lightStrength/lightColor` и executable `apply_item_effects` binding остаются явными. Код не выбирает цвет.

Не распространять разрешение на damageClass/damage/useStyle/channel, геометрию, refs/target, events, lifetime, cooldown/immunity. `channel_beam/charge_then_release` всё ещё требуют explicit channel. Необъявленные группы требуют отдельного совместного доказательства:

- healLife/healMana: sparse вызов должен отдельно гарантировать ненулевое восстановление;
- pick/axe/hammer + mining multiplier: скорость без working tool power инертна;
- local immunity/cooldown: `0`, `-1`, owner mode не взаимозаменяемы;
- spawn/movement/lifetime: ноль скорости/count/range/timing не универсальная нейтраль;
- sparse equipment: требования active effect, light color и head/setKey для set bonus сохраняются.

Repair omission — **не менять**; accepted absence frozen. Repair соседнего damage не разрешает добавить manaCost. После exact merge снова валидируется **вся** программа; лишь тогда compile может материализовать defaults. Новый node проходит полный capability contract.

<a id="receipts"></a>
## Receipt provenance и coverage

`declared_neutral_omission` отличается от `delivered`: аудит проверяет declared default, точный output и происхождение. С исходным Author он доказывает факт отсутствия; standalone wire без Author лишь проверяет declaration/mapping/value и coverage присутствующих default fields, но не восстанавливает исходный omission. Если `runtimeContract` присутствует, пустой/повреждённый contract не освобождает от аудита. Delivery намеренно удаляет internal runtimeContract, поэтому final DTO не обязан содержать receipts.

Regressions из [registry/test owners](TEST_CONTRACT_OWNERS_RU.md): все absent/zero/negative/positive XY combinations; 64 modifier-presence masks со working light и 64 полностью neutral masks (reject); каждый sole active effect; invalid-present/type/range boundaries; sparse/explicit-neutral wire equality; unapproved optional groups/dependencies; altered status/value/path, lost output/receipt и numeric type подмены (`0` ≠ `false` ≠ `0.0`).

<a id="history"></a>
## Историческая проверка, не текущая гарантия

Исходная запись `81509e2`: Python 1110 passed, Ruff clean, Pyright 0/0; headless C# 67/0 на tModLoader 2026.6.3.6; DLL-only build 0 errors/warnings (`.tmod` packaging и игра не запускались). Replay против `8f2252f`: 52 witnesses + 18 accepted Gameplay docs, compiled structures/прежние receipts 70/70 без rewrite captured Author/Repair; 12 offline gates exit 0. Numeric-type/provenance adversarial checks были RED до fix; independent review дополнительно проверял 52 witnesses/2926 JSON-round-trip receipts, historical replay отдельно parent.

Соседний wire defect существовал и на explicit JSON: общий neutral set ошибочно считал `1` всегда нейтралью и любой non-white color эффектом; ore/jump/regen `1` исполняемы, color без light — нет. Разница C# epsilon около `0.001f` закрыта позже A5, `meteor_spacegun` Repair scope — позже A2 с offline replay в [audit fixes](HISTORY_RU.md#audit-81509e2). Эти поздние fixes не меняют исходные counts/captured Live20.

Нового Live20/provider/game/MP/GPU измерения здесь нет. `cf503d4` остаётся историческими 18/20 RED; offline/headless parity не улучшает сохранённую acceptance панель и не доказывает качество будущей генерации.
