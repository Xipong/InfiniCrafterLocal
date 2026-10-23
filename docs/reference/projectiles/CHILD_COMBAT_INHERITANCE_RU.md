# Явное наследование текущего combat state родителя

`spawn_entity_on_event` и `target_and_fire` задают `damageBasis`, `knockbackBasis` и `damageMultiplier`. Оба basis обязательны в Author и в активном wire consumer и выбираются независимо:

| Значение | Урон ребёнка | Отбрасывание ребёнка |
|---|---|---|
| `authored_child` | `damage` явно указанной child entity × `damageMultiplier` | `knockback` явно указанной child entity |
| `live_parent` | Текущий `Projectile.damage` event-owning/firing родителя × `damageMultiplier` | Текущий `Projectile.knockBack` того же родителя |

`damageMultiplier` имеет Author range `0..4`. Ноль сохраняет нулевой урон и не отменяет создание ребёнка. `Damage.Enabled=false` у ребёнка продолжает запрещать его damage. `DamageClass`, hitbox, collision/immunity, movement, velocity и lifetime принадлежат явно описанной child entity.

Пример параметров event call:

```json
{
  "when": "on_hit",
  "entity": "child_shard",
  "count": 3,
  "spreadRadians": 0.75,
  "damageBasis": "live_parent",
  "knockbackBasis": "authored_child",
  "damageMultiplier": 0.5,
  "delayTicks": 0
}
```

Это выбор конкретного источника чисел. Compiler сохраняет selector и multiplier по literal identity с отдельными receipts; Author → wire относится к Alias Lowering и не выбирает отсутствующее решение. Runtime исполняет эту явную политику. В `item_body` нет live projectile: `live_parent` даёт `unsupported_param_target_kind` на соответствующем basis. Repair разрешает заменить только этот invalid leaf, сохраняя target, count, multiplier и другой валидный basis.

## Величина урона и включение damage — разные решения

`damageBasis` выбирает только число. Чтобы дочерняя entity наносила урон, Author отдельно выбирает для неё `set_projectile_damage`. С `live_parent` её authored `damage` может быть `0`: положительное текущее значение родителя придёт при spawn. Без `set_projectile_damage` дочерняя entity остаётся без damage, даже при положительном `live_parent` и multiplier. Это допустимо для декоративных частиц и helpers; compiler не включает урон автоматически и не требует положительный authored damage.

## Момент чтения и применение модификаторов

Для immediate event snapshot берётся при выполнении события из его точного `EntitySource_Parent`. Для `target_and_fire` — при конкретном выстреле после выбора NPC. Для `delayTicks > 0` snapshot сохраняется при admission в очередь, до резервирования spawn budget; dispatch использует сохранённые значения, даже если parent позднее изменил damage/knockback.

`charge_then_release` изменяет текущие parent damage/knockback до `on_release`/`channel_complete`, поэтому event видит partial/full charge, уже применённый к родителю. Native player/prefix/root modifiers, вошедшие в эти live fields ранее, переносятся один раз. Inheritance не вызывает `GetWeaponDamage`/`GetWeaponKnockback` и не умножает классовые бонусы повторно. `damageDone`, `originalDamage` и per-target hit modifiers не являются источниками `live_parent`: например, эффект, применённый только через NPC hit modifiers, не обязан присутствовать в `Projectile.damage`.

Final inherited damage округляется к ближайшему целому с midpoint-to-even. Выход за `Int32`, отрицательный live damage, отрицательный/нечисловой live knockback или отсутствие точного parent source отменяет spawn без подстановки child stats; отказ возвращает уже зарезервированные slots. Невалидный невыбранный parent field не влияет на независимый authored basis.

Terminal `on_kill`/`on_expire` может сохранить уже неактивного родителя. Queue продолжает проверять owner session, slot/object/identity/type и `ModProjectile` generation. Reuse родителя отменяет старую action и возвращает reservation. Время delay остаётся в world ticks; extra updates его не сокращают. Child spawn остаётся owner-local, с существующими depth, per-activation и owner concurrency budgets. Готовые damage/knockback идут в существующий native spawn seam; отдельная peer-side переоценка не вводится.

## Сохранённые определения и provenance

Активные `spawn_entity_on_event` и `target_and_fire` требуют явных `damageBasis`/`knockbackBasis` в Author и доставленном wire. `target_and_fire` также требует явный `damageMultiplier`: его отсутствие не означает `1`. Неполное определение отвергается без миграции, выбора authored-child политики и дописывания решения при save/network round-trip. Nullable DTO storage остаётся техническим состоянием неактивного `RuntimeTargetingSpec`, не совместимостью активного выстрела.

Настоящие optional targeting параметры сохраняют объявленные нейтральные пропуски: `count=1`, `spreadRadians=0`, `targetPolicy=distance_score`, `requireLineOfSight=false`, `hardRange=false`. Они не становятся обязательными; присутствующие значения и gameplay/resource bounds не меняются.

Присутствующие поля проверяются строго: `null`, иная капитализация, пробелы, неизвестный enum и нечисловой/выходящий за range targeting multiplier отвергаются. Новые поля допустимы только у своего spawn consumer. `ParamSpec.wire_presence_requires_receipt` требует единственный receipt для каждого присутствующего нового поля в полном wire с provenance; receipt должен принадлежать exact entity/event call. Отсутствие обязательного selector остаётся RED и после удаления provenance из delivery. При наличии исходного Author проверяются его actual path/value/target; wire-only audit не утверждает восстановление отсутствующего Author.

`damage_area_on_event` и `chain_damage_on_event` продолжают использовать свой documented authored source-entity base. Это отдельные direct-damage actions, их семантика данным расширением не меняется.

## Владельцы и проверки

Registry и требования: [capability_registry.py](../../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py). Exact projection/receipt audit: [technical_lowering.py](../../../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py). DTO admission: [RuntimeProgramSpec.cs](../../../ModSources/InfiniCrafterLocal/Common/Models/Contracts/RuntimeProgramSpec.cs). Snapshot/selection: [RuntimeChildCombat.cs](../../../ModSources/InfiniCrafterLocal/Common/Runtime/RuntimeChildCombat.cs). Producers используют существующие executor, delayed scheduler и `GeneratedProjectile.ApplyTargetAndFire`.

[test_runtime_parent_combat.py](../../../LocalGenerator/tests/test_runtime_parent_combat.py) проходит реальный schema/provider inverse/compiler/receipt/Repair путь, проверяет current positive, malformed/missing/source-tampering cases и refusal архивного wire без изменения его байтов. Отдельные delivery tests удаляют provenance и каждый обязательный combat leaf, сохраняя RED; positive control допускает declared optional targeting omissions и неактивные placeholders. Архивы seed/Live20 не переписываются и не мигрируют в поддерживаемый контракт.

[EngineRuntimeChecks.ChildCombat.cs](../../../tools/native/EngineRuntimeChecks.ChildCombat.cs) включён в canonical engine harness: strict JSON admission, immediate/terminal events, charge/delay, sentry firing, authority и reservation refusal. Наблюдатель останавливается на настоящем `NewProjectileDirect` в headless процессе; он не возвращает fake spawn и не заменяет game/MP smoke. Для исполнения этого harness нужны .NET 8, tModLoader и declared external references; portable source checks не считаются его выполнением.
