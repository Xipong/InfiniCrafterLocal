# Typed primitives: границы рефакторинга и проверки

## Архитектурный результат

Canonical owner — `LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py`. Author выбирает entities, bindings, damage class, movement/controller и event links; compiler только проверяет и переводит явно выбранные значения в wire. Presets/family router и semantic fallback не добавлялись.

Прежняя проверка parity от списка известных Python capabilities не доказывала полноту C#. AST audit `primitive_loss_audit.py` отдельно перечисляет DTO-поля и reads executable consumers, сопоставляет их с Author и классифицирует intentionally hidden fields. Историческое сравнение и исключения — generated `PRIMITIVE_PARITY_RU.md`. Этот audit не является доказательством всего Terraria game loop.

Восстановлены equipment/accessory/armor modifiers, которые C# исполнял, но модель не могла выбрать: скорости, регенерация, иммунитеты, mana cost/ammo save/aggro/penetration, whip range/tagged summon source damage и set bonuses. Пять class damage полей представлены одной операцией `add_equipment_damage_bonus(phase, damageClass, bonusPercent)`; другие class-specific операции не выдуманы поверх generic-only consumers.

## Числа и компактность

Проверен каждый из 180 numeric params в 52 capability-карточках. Human-facing преобразования:

- `axePowerTooltipPercent`: целое 0…500 с шагом 5 → прежнее целое `gameplay.axePower = value / 5`;
- `lifeRegenHpPerSecond`: 0…60 с шагом 0.5 → прежнее целое `gameplay.generatedBuff.lifeRegen = value × 2`;
- equipment проценты → fractions через `/100`, crit остаётся в percentage points; source damage bonus не выдаётся за vanilla flat tag damage.

Старые Author-имена двух преобразованных полей отклоняются, старые wire-поля сохраняются. Исчерпывающие тесты проходят все 101 и 121 прежних целочисленных значений; frozen seed wire digest сохранён. Архивный Live20 Repair fixture не переписан: тест применяет к нему явно описанную обратимую адаптацию имени/единицы, не production alias.

Величины без точной физической конверсии оставлены в именованных engine units. `extraUpdates` отделяет world tick от projectile update; движение, gravity/turn/scale increment применяются за update. Время событий/длительностей — world ticks, raw local NPC cooldown обозначен отдельно. Raw mana regeneration/aggro/knockback не названы маной в секунду, вероятностью или расстоянием. `periodic` требует явный `periodTicks`, никакого default 6.

Компактный каталог сохраняет параметры, bounds, enum/pattern/reference, dependencies и numeric steps. Повторные required/units/нейтрали вынесены в field guide; одинаковое meaning armor ссылается на одноимённое accessory field, set-prefix объявлен один раз. Полная machine/audit projection отдельно от model-visible cards.

Замер actual `build_initial_author_request` на `{name:Workbench}` + `{name:Sword}`, ключе `workbench+sword`, модели `gemini-2.5-flash` (только локальный serializer fixture, не live-запрос), режиме `json_object`; baseline `fa52c4e`:

| Компонент | Символы до → после | BAAI/bge-small-en-v1.5 WordPiece proxy tokens до → после |
|---|---:|---:|
| System | 3457 → 3457 | 789 → 789 |
| Полный user | 89655 → 80263 | 33387 → 29019 |
| Вложенный catalog | 73540 → 63986 | 29042 → 24637 |
| Локальная response schema | 97607 → 100530 | 43340 → 44090 |
| Передаваемый response_format | 22 → 22 | 14 → 14 |

Это proxy tokenizer, **не точные Gemini tokens**. Локальная schema в `json_object` не передаётся. Результаты live-генерации оцениваются отдельно от размера запроса.

## Исправленные C# execution seams

- `maxRunSpeed` копится в equip hooks, сбрасывается каждый tick и применяется в `PostUpdateRunSpeeds`; `moveSpeed` остаётся в ранней фазе. Прежнее подавление бонуса маунтом сохранено.
- Generated ammo сохраняет свой `shoot/shootSpeed` после direct use; rocket/solution `PickAmmo` возвращает явно authored projectile ID после vanilla ID-offset. Более поздний `GlobalItem.PickAmmo` другого мода может изменить выбор.
- Generated whip geometry использует `Player.whipRangeMultiplier`; hit ставит same-owner tag на peer, который исполняет vanilla projectile hit (owner client/SP). Tag — multiplier source damage, не flat bonus.
- Proximity missile сохраняет существующее `on_expire`-исключение; VFX тоже испускается. AoE при proximity включает trigger NPC, поскольку proximity не является уже нанесённым direct hit; on_hit/on_crit по-прежнему исключают прямую цель из дополнительного AoE.
- Event-spawn ledger разделяется siblings/descendants, delayed actions резервируют budget при enqueue и возвращают неиспользованный резерв. Root Hold/Shoot capacity отдельно от event allowance, включая allowance=0. Peer snapshot не создаёт authority ledger.
- Delayed item-use source хранит snapshot Item с Context/AmmoItemIdUsed и исходными stats: расход последней единицы не отменяет событие. Projectile parent проверяется по экземпляру ModProjectile/слоту/owner/type/identity; неактивный прежний source допустим. При повторном использовании поколения действие отменяется и резерв возвращается: полная независимость terminal action от reuse ещё не реализована. Штатный item-periodic Misc source сохраняется, произвольный Misc не превращается в ложный ItemUse.

## Известный MP-дефект — не закрыт этим snapshot

Для player-owned projectile/item `on_hit/on_crit` установленный tML 2026.6.3.6 вызывает соответствующий hook на owner client. Infini NPC actions (`apply_status`, AoE, chain и NPC-pull) требуют server/SP authority. Vanilla strike packet #28 не повторяет item/projectile hook на сервере и не несёт его source identity. Поэтому такие NPC-эффекты owner-hit в MP теряются. Это подтверждённое несовпадение фаз по установленной DLL и RED headless observer, а не только отсутствие сетевого smoke.

Привилегированный client→server command не добавлялся: одного sender/slot/range/sequence недостаточно для подтверждения факта попадания. Требуется отдельная явно определённая trust boundary (server collision/hit receipt либо принятая vanilla owner-hit authority), source/target generation и no-duplication tests. Прямые серверные изменения NPC velocity также требуют надёжной sync. Эти ограничения нельзя считать устранёнными no-image Live20 или DLL build.

## Намеренно custom/hidden и acceptance

Custom остаются dynamic entity graph/proxy types, arbitrary delayed finite actions, budget accounting, hydration/storage, per-instance assets и authored movement/controllers. Type-wide sand ammo/ID-static immunity и weapon `Item.useAmmo` без полного PickAmmo vertical slice намеренно не exposed. Исторические удалённые executors не объявляются восстановленными просто по сходству названий; roster дан в `PRIMITIVE_PARITY_RU.md`.

Последние offline gates до live freeze: 719 Python/toolbox tests (после интеграции remote main и устранения duplicate periodic-required diagnostics); 56 C# headless checks (внутри есть дополнительные сценарии); mod DLL rebuild 0 errors/warnings, без `.tmod` packaging. C# source hooks/CPU observers не доказывают world loop, actual group spawn, GPU и multiplayer match. Live20 должен выполняться на отдельном чистом commit с явной конфигурацией; окончательные live/replay результаты хранятся отдельно, не предполагаются этим документом.
