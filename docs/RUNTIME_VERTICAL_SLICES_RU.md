# Runtime vertical slices — правила расширения без спагетти

Этот документ описывает **как добавлять одну исполняемую механику**, не превращая проект в универсальный state-machine, гигантскую semantic-table или набор скрытых derivation-правил.

## Основной принцип

Одна gameplay-возможность должна читаться сверху вниз как короткий вертикальный срез:

1. **LLM-контракт** — одно точное поле/enum или уже существующая engine function.
2. **Python owner** — один небольшой модуль, который проверяет и компилирует только эту возможность.
3. **Genome/AttackSpec projection** — явные поля без скрытого вывода из prose/name/tooltip/material.
4. **C# owner** — один конкретный executor или policy-класс.
5. **Net sync** — только необходимые компактные scalar/string fields.
6. **Отдельный end-to-end тест** — доказывает, что поле проходит все границы.

Если для понимания механики нужно прочитать половину репозитория, срез сделан неправильно.

## Запрещённые способы расширения

- Универсальная trigger/action state-machine «на будущее».
- Автоматический gameplay routing по имени, tooltip, concept, material или visual prompt.
- Параллельные владельцы одного enum/поля.
- Скрытая генерация контракта, которую следующий агент может начать редактировать вручную.
- Один мегакомпилятор, в который добавляется каждая новая механика.
- Смешивание двух lifecycle-механик в одном неявном state graph.
- Изменение sparse-output поведения: явно authored defaults должны сохраняться как раньше.

## Текущие примеры

### Secondary projectile trigger

- Python vocabulary owner: `core/runtime_secondary_policy.py`.
- Python compile owner: `core/runtime_authoring/secondary.py`.
- C# vocabulary owner: `Common/Models/GeneratedSecondaryTriggerPolicy.cs`.
- C# execution owner: `GeneratedProjectile.Impact.cs`.
- Поддерживаются только `on_hit` и `on_expire`.
- Одновременно разрешена одна trigger family; смешанный lifecycle явно отклоняется.

### Overhead barrage

- Python defaults/limits owner: `core/runtime_overhead_barrage_policy.py`.
- Runtime family registration: `core/runtime_family_policy.py` и `GeneratedRuntimeFamilyPolicy.cs`.
- C# owners: `GeneratedOverheadBarragePolicy.cs` и `GeneratedProjectile.OverheadBarrage.cs`.
- Механика содержит только target marker, один delay timer и bounded authored projectiles, появляющиеся над зоной цели.
- Это delivery geometry, а не тема: Daedalus-like `delivery=shoot` сохраняет arrows; Starfury-like `delivery=swing` сохраняет melee hitbox и authored `star` shape/effect; magic carrier использует `delivery=cast`.
- Только exact `overhead_barrage` является текущим contract value; старые family tokens не мигрируются.
- Не расширять этот файл в generic charge/trigger/mode framework.


### Charge-release

- Python policy owner: `core/runtime_charge_release_policy.py`.
- Existing calls author the mechanic through exact `family/runtimeFamily=charge_release`; only `chargeTicks` and `chargePowerMultiplier` are new knobs.
- C# owner: `GeneratedProjectile.ChargeRelease.cs`.
- Released shots become ordinary `shoot|cast|throw` projectiles and keep authored onHit/secondary/VFX.
- No vanilla ammo, no stage graph, no generic scheduler.

### Sentry

- Python policy owner: `core/runtime_sentry_policy.py`.
- Exact engine call: `deploy_sentry`.
- C# owners: `GeneratedItem.Sentry.cs` for placement and `GeneratedProjectile.Sentry.cs` for target/fire lifecycle.
- Sentry shot is an ordinary projectile, not a nested authored AttackSpec and not another sentry.
- One bounded lifetime shot budget; child-producing sentry triggers are rejected.
- Shared projectile static-set limitation is documented in `CHARGE_RELEASE_SENTRY_RUNTIME_RU.md`; do not hide it behind runtime inference.

## Чек-лист для следующего агента

Перед добавлением функции ответить:

- Можно ли выразить её одним существующим engineCall + 1–2 полями?
- Есть ли ровно один owner enum и один owner executor?
- Не создаётся ли новый classifier/alias table?
- Не выводится ли gameplay из presentation данных?
- Можно ли удалить функцию целиком, не ломая несвязанные механики?
- Есть ли тест `prompt/compiler → genome → DTO → runtime/net`?

Если на последние два вопроса ответ «нет», сначала упростить дизайн.
