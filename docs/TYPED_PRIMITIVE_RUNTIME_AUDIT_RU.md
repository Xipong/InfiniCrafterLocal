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

## История live acceptance: quota и смена тестовой конфигурации

Проверенный исходный snapshot: `aa51a48654f6a697b855d8b51eabe6a9aec02b78`; публикация `6fbb51a` добавила только отчёт о квоте. No-image preflight прошёл с `gemini-3.5-flash-lite`, `chat_completions`, `json_object`, concurrency=3, 20 cases, minFirstAuthor=10, case transport retries ≤10 с интервалом ≥60 s; fallback и image calls запрещены. Frozen temperatures: Author/Visual=0.5, VFX=0.34, Repair=0.12; token budgets: Author/Visual=12000, VFX=4000.

26 сентября 2026 перед full panel выполнены два коротких availability probes, не входящих в Live20: прямой маршрут вернул HTTP 400 `FAILED_PRECONDITION` / `User location is not supported for the API use`; прежний локальный HTTP proxy `127.0.0.1:10808` вернул HTTP 429 `RESOURCE_EXHAUSTED`. Точное quota violation: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, metric `generativelanguage.googleapis.com/generate_content_free_tier_requests`, model `gemini-3.5-flash-lite`, quotaValue=500. Ответ содержит RetryInfo=52 s, но конкретная исчерпанная квота — **суточная**, поэтому минутные повторы не запускались.

[Официальная документация Gemini](https://ai.google.dev/gemini-api/docs/rate-limits) определяет RPD reset как midnight Pacific; ближайшая к этому probe граница — 26 сентября 2026, 10:00 МСК. Доступность после reset необходимо проверить заново. На этом этапе платный маршрут, смена модели и обход quota не использовались; full panel на 3.5 не стартовал. Последующее разрешённое переключение на 3.1 и его неуспешные/прерванные прогоны описаны ниже. Accepted результатов текущего snapshot для C# replay нет. Старый `fa52c4e` panel не засчитывается за этот snapshot; полной acceptance нет.

## oneOf diagnostics: установленный дефект Repair guidance

После явного разрешения пользователя тестовая модель заменена на `gemini-3.1-flash-lite`. Затем пользователь разрешил для теста `reasoning_effort=medium` и максимальный ответ 18000 на всех стадиях. Постоянный provider config не менялся. Прогоны с прежними настройками сохранены отдельно и не суммируются в acceptance.

В пилоте на `6fbb51a` исходный Author правильно указывал `fn=set_projectile_collision`, но пропускал часть обязательных params. `strict_schema_errors` при несовпадении всех `oneOf` branches выбирал для подробной диагностики ветку с наименьшим числом ошибок. Ветка `configure_accessory` ошибочно выигрывала у явно выбранной collision: Repair-dossier требовал сменить корректный fn и удалить корректные `tileCollide`/`pierce`. Это **ошибка deterministic guidance**, а не доказательство того, что модель сама придумала смену capability. Проба всех capabilities с обязательными params и пустым params выявила ложный fn-диагноз в 49 из 50 случаев до исправления.

Диагностика теперь привязана к уникальным exact `const` discriminators самой schema, включая вложенные binding discriminators; имя capability не классифицируется и новые значения не выбираются. Validity `oneOf` по-прежнему требует ровно одну валидную ветку. При неоднозначном/неизвестном discriminator чужая ветка не подставляется. Проверены реальные validator → Repair permissions → frozen filter → compiler, попытки удалить правильные collision params или заменить fn, а также весь registry. На сохранённом ошибочном Author повторная локальная проверка теперь разрешает только недостающие collision params: ложных fn-диагностик и удалений правильных полей нет. Это offline replay диагностики, не новый успешный LLM Repair.

Независимое ревью выявило дополнительный frozen-first дефект: при пропущенном `usePolicy.action.kind` общая `oneOf`-ошибка теряла точный missing-field path. Общие для совместимых schema branches `required`-ошибки теперь сохраняются без выбора варианта за модель. Отдельно actual Repair filter принимал целиком совпавший registry transaction, обходя leaf permissions и разрешая менять корректные `contactDamage`/`stackCost`. Воспроизведение на `6fbb51a` подтвердило, что этот обход существовал и до текущего изменения диагностики. Shortcut теперь требует явного права на весь `usePolicy`; leaf repair проходит frozen-subtree merge, а право на kind использует точный `usePolicy.action.kind` вместо устаревшего `action`. Локально 12 focused regressions проверяют восстановление отсутствующих/неизвестных discriminators и сохранение валидных соседних полей. Независимое повторное ревью дало bounded PASS: 18 focused tests и дополнительные read-only probes проверили missing/invalid input, kind и target, frozen contactDamage и atomic transaction shortcut. Это не полный перебор всех программ. Общая проверка интегрированного snapshot завершена обычным и sandbox-sharded pytest (результаты ниже).

Новый полный panel на прежнем snapshot остановлен после подтверждения дефекта; его partial results не являются acceptance. После исправления требуется свежий clean-head Live20 и C# replay принятых результатов. MP-ограничения выше остаются открытыми.

## Приведение тестов и runner selection в порядок

Чистка не дала основания массово удалять сценарии: 354 из исходных 728 collected cases были параметризованными, в том числе исчерпывающая проверка прежних integer domains для axe/regen. Удалены один отдельный дублирующий case и повторные contract assertions; CLI/auth/PNG/registry-проверки заменены или усилены исполняемыми проверками вместо совпадения строк исходников. Registry-mutation test теперь реально вызывает validator и строит Repair scope; in-memory mutants подтвердили, что обход consumers замечается. AST gate распознаёт обычные и qualified вызовы contract runner. Historical replay JSON не изменён: прежний диагностический путь `action` преобразуется в точный `usePolicy.action.kind` только при сравнении frozen ожиданий в тесте.

Найдены и исправлены ошибки самих раннеров: `toolbox/tests` теперь входит в default pytest discovery, focused и sharded selection; production/shared/config changes консервативно выбирают оба offline test roots. Нулевой выбор имеет `not_selected`, а непокрытые changed paths явно перечисляются и не выдают частичный прогон за полную проверку. Все runners принудительно отключают project-config/live режим для offline тестов. Добавлены 18 focused runner-selection regressions, включая реальный sandbox subprocess.

После объединения изменений обычный `pytest -q` завершился **748 passed in 20.95s**. Это не сокращение количества: сохранены полезные numeric cases и добавлены регрессии на обнаруженные дефекты. Время измерено в одном локальном запуске, не является контролируемым performance benchmark. Полный sandbox-sharded прогон также прошёл: **748 tests**, 65 файлов, 4 shards, 28.125s; в нём реально исполнены toolbox tests. C# runtime в этой дополнительной пачке не менялся.

## Намеренно custom/hidden и acceptance

Custom остаются dynamic entity graph/proxy types, arbitrary delayed finite actions, budget accounting, hydration/storage, per-instance assets и authored movement/controllers. Type-wide sand ammo/ID-static immunity и weapon `Item.useAmmo` без полного PickAmmo vertical slice намеренно не exposed. Исторические удалённые executors не объявляются восстановленными просто по сходству названий; roster дан в `PRIMITIVE_PARITY_RU.md`.

Последние offline gates до live freeze: 719 Python/toolbox tests (после интеграции remote main и устранения duplicate periodic-required diagnostics); 56 C# headless checks (внутри есть дополнительные сценарии); mod DLL rebuild 0 errors/warnings, без `.tmod` packaging. C# source hooks/CPU observers не доказывают world loop, actual group spawn, GPU и multiplayer match. Live20 должен выполняться на отдельном чистом commit с явной конфигурацией; окончательные live/replay результаты хранятся отдельно, не предполагаются этим документом.
