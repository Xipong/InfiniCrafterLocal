# Исторический runtime audit — 10 октября 2026

Это **зафиксированный результат исследования**, не второй capability registry и не утверждение о текущем merge status последующих PR. Проверенный код: `ff039fc54b76a6b29f18dcb0f36180b932721fd9`; HEAD `62762da1831771b376eb83efbab80530411ff3f1` отличается только документацией и лицензией.

Реализации по результатам этого аудита вынесены в отдельные PR. Их ссылки, зависимости, проверки и ограничения собраны в [карте PR для выборочного ревью](AUDIT_PR_REVIEW_MAP_RU.md).

## Граница доказательства

Проверены 159 Git commits и 20 исходных архивов до Git, с 17 мая по 6 июля. Старейший доступный архив — `InfiniCrafterLocal_v1_3_1_dllfix.zip`, регистрация 2026-05-17T11:34:09.493979Z, SHA-256 `2533b9b17ad1d5359030d786c592507d60c1f07fa3a0f0d5088aa1e3ef9b42d0`. Дата регистрации не считается точной датой появления функции. Исходников v1.0 нет; успешный запуск ранней сборки не доказывается наличием C# consumer.

Первый Git — `019ff01f8dec195acfd92ff559eb42a93fe29ab2` (8 июля). Последний pre-v5 — `f04ee02b456947379bdebc82047237069715ecce`. Импорт v5 `25caddf0cd32baeb8eef3f710d25933f85506d29` датирован 25 июля UTC / 26 июля +03:00. Ниже `old` означает f04ee02, `snapshot` — ff039fc. Пути C# относительно `ModSources/InfiniCrafterLocal`.

Классы: K1 — утрачено; K2 — consumer есть, fresh Author не экспонирует; K3 — точная композиция сохраняет возможность; K4 — внутренняя замена/восстановлено; K5 — сужение или изменение семантики; K6 — заявленный working path не доказан, в том числе обнаружен конкретный дефект.

## Подтверждённые различия

| ID | Класс и точная механика | Старое доказательство | Состояние snapshot / граница восстановления |
|---|---|---|---|
| A1 | K1: RNG собственного стека | v156 от 23 июня `Content/Items/GeneratedItem.cs:263–269`; 019ff01 тот же файл:588–594, `Main.rand.Next(100)` | В v5 chance ещё был. Удаление Author/DTO `3831d93`, consumer `7f4e86a`, 2 августа. Binding-owned probability должна бросаться после успеха, один раз. Ammo saving другой механизм. |
| A2 | K1: refresh generated utility buff при удержании | v139 от 20 июня Item:316–317; 019ff01 Item:688–689 | Удалено 25caddf. Held light/mining speed — только подмножество. Нужны explicit effects и refresh/duration, не скрытый projectile. |
| A3 | K5: отдельные primary/alternate utility bundles | v139 Item:265–276; 019ff01 Item:603–637 | Удалено 25caddf. Разные spawn targets сохранены. Старые main/alt cooldown values использовали общий player timer: независимые timers не доказаны. |
| A4 | K1: weapon `Item.useAmmo` | v71 от 15 июня `Common/Models/GeneratedItemData.cs:417`; old `GeneratedItemData.Apply.cs:235–247` | Удалено 25caddf. Нынешний ammo-side `PickAmmo` существует, но не делает оружие потребителем ammo. Старый Shoot:1222–1227,1258–1268 заменял speed и ammo projectile type: full special-ammo AI не был сохранён. |
| A5 | K6: arbitrary per-instance Extractinator output | v139 `Content/Items/GeneratedExtractinatorMaterial.cs:118–128`; 019ff01:170–181 | Proxy и spawn route были, но output хранился в instance Data, а hook неинстансный. Мост consumed instance → callback отсутствует. Удалено 5adb9fa 15 июля, до v5. |
| A6a | K1: sentry volley count/spread | 146df87 от 11 июля; old `GeneratedProjectile.Sentry.cs:42–53` содержит цикл shotCount 1–4 | Snapshot `GeneratedProjectile.Executors.cs:170–191` запрашивает count 1. Child spawn count не заменяет per-volley count. |
| A6b | K1: native sentry slots/placement | old `GeneratedProjectile.Runtime.cs:590–611`, `GeneratedItem.Sentry.cs:14–33` | `Projectile.sentry`, `FindSentryRestingSpot`, `UpdateMaxTurrets` утрачены 25caddf. Stationary kind сам не включает native lifecycle. |
| A6c | K5: live children budget | old `GeneratedProjectile.Impact.cs:355–365` | Snapshot `RuntimeSpawnBudgetExecutor.cs:19–31`: монотонный общий budget активации 32, смерть детей его не пополняет. Live cap и total budget различны. |
| A6d | K1/K5: assigned target, LOS | old Sentry:58–74 | Snapshot Executors:270–281 выбирает по distance score без прежнего assigned-target-first/LOS; bias может допустить цель дальше обычного range. |
| A7 | K1/K5: beam sustain mana, width/damage ramp, wall raycast | old Runtime:442–515, Impact:165–169 | Snapshot warmup бинарный; segment geometry не обрезается LaserScan. `ownerHitCheck` существует и может ограничить hit по owner LOS, но не клиппирует луч. |
| A8 | K5 palette, K1 variance, K2 fresh pitch | old `Common/Audio/InfiniSoundLibrary.cs:23–172`: 92 IDs / 71 unique SoundID | a49458d частично вернул звук: 20 samples, 7 старых + 13 новых, 64 старых отсутствуют. Runtime phaseOffset pitch есть, fresh VFX schema его не передаёт; диапазон текущего pitch уже старого. |
| A9 | K5: actual parent combat inheritance | May17 Projectile:223–248,305; old Impact:404,443,583/Sentry:52 | Snapshot `GeneratedProjectile.cs:278–289` использует authored child damage и его knockback. Нужен explicit basis, без double application modifiers. |
| A10 | K5: projectile-hop chain | May17 Projectile:236–248; old Impact:430–446 | Snapshot `RuntimeProgramExecutor.cs:203–222` наносит instant damage списку вокруг исходного центра. 0→300→550 при hop range 360 отличается от radius 360. Старый visited-set отсутствовал. |
| A11a | K1: random initial child velocity | May17 Projectile:251–302; old Impact:450–488,504–564 | Position scatter не заменяет velocity distribution. Нужны authored bounds и ownership/sync. |
| A11b | K5: NPC-relative split origin/ignore | old Impact:393–426,569–590 | Старый Bernoulli SameTargetBias, before/after NPC offsets и ignore initial NPC 10 updates отличаются от нынешнего score discount. Это не гарантированная вероятность попадания в ту же цель. |
| A12 | K1/K5: expanding gameplay hitbox | 3a0569a от 14 июля; old Impact:85–100 | Snapshot Expand:380–384 меняет scale, но не прежнюю damage geometry. Gameplay curve должна быть явной, не выводиться из VFX. |
| A13 | K5: составные motion semantics | old Runtime/Impact: spiral acceleration, vortex phases, pull distance falloff, multiplicative expansion; whip gravDir | Один movement slot и нынешние формулы не воспроизводят все старые сочетания. Возвращать нужно выбранные orthogonal modifiers/curves, не семьи оружия. |

В A1 ранний Python `or 100` ломал явно заданный 0; диапазон 1–99 всё равно работал. В A5 [официальный ModItem API](https://docs.tmodloader.net/docs/stable/class_mod_item.html) прямо определяет `ExtractinatorUse` как неинстансный hook. Возврат старого proxy не является исправлением этого дефекта.

## Что исключено из списка текущих потерь

- K3: basic fan, простой hit split, status effects и proximity→event→children выражаются нынешними primitives.
- Uniform ring не потерян целиком: fan spread `2π(N−1)/N` создаёт равномерные направления; точное совпадение ориентации зависит от aim и чётности N.
- K4: whip tag/range восстановлены `aa51a48` 26 сентября; это исторический gap, не текущая потеря.
- K6: native minion lifecycle и state meters/triggers не имеют найденной старой рабочей вертикали. Чтение vanilla minion source facts не является generated consumer.
- Old timed-yoyo return branch существовала, но не поддерживала необходимый timeLeft при возвращении. Полная прежняя исправность не доказана.
- Более широкие C# Normalize domains (negative gravity/scale growth, maxScale, returnSpeed) не доказывают историческую регрессию и не разрешают автоматически публиковать весь defensive envelope Author.

## Почему нынешний AST PASS не доказывает историю

`primitive_loss_audit.py` анализирует поля текущих DTO и названные consumers. Поле, удалённое вместе с consumer, исчезает из сравниваемого множества. Поэтому **PASS текущей поверхности не означает отсутствия исторической потери**. Новые restoration PR должны ссылаться на старый consumer и явно проверять восстановленную комбинацию.

Snapshot source proof не заменяет native build/world/MP smoke. Во время аудита выполнены 2 410 Python boundary/projection/composition tests и отдельные witnesses; game/MP и live LLM quality не запускались. Нельзя переносить эти counts на будущий HEAD без нового запуска.

## Контрпримеры для будущих упрощений

| Кажется несущественным | Исполняемое различие на snapshot |
|---|---|
| Цвет generated buff при lightStrength=0 | `InfiniCraftPlayer.Mobility.cs:47–55,75–95,113–133`: цвет входит в SameEffect; два buffs +0.2 разных цветов дают +0.4, canonical color превращает второй в refresh и +0.2. |
| disableMeleeHitbox и binding contactDamage как один effective flag | Item:424–437 читает исходный contactDamage для pure mobility; ConsumeItem:368–391 меняет расход при failed blink. |
| ID как чистая metadata | Item:512–518 использует hash ID в periodic phase. Переименование и изменение порядка calls требуют сохранения timing/provenance. |
| Speed при aim=none | Charge release Executors:156 всё равно читает Spawn.Speed. |
| Activation delay как event delay | Уже созданный projectile занимает slot и расходует lifetime; scheduler ещё не создал entity и имеет другие cancellation rules. |
| Один percent-of-damage | Child authored damage, source authored AoE/chain base и actual damageDone — разные базы. |
| Любой on-hit pull не нуждается в radius | Неактивная direct target даёт area fallback в NPC branch; owner pull возвращается раньше и является отдельным доказанным случаем. |
| target_to_entity значит к projectile.Center | RuntimeProgramExecutor:236 использует eventPosition; on-hit она обычно равна NPC.Center, вектор нулевой. |
| Draw scale определяет collision | Ordinary/tile/whip/beam geometry имеют отдельные consumers. Owner LOS не клиппирует beam segment. |
| Rescale velocity компенсирует extraUpdates | Меняются частота homing/gravity/collisions и timers, а не только расстояние за tick. |
| Vortex/blackhole/periodic pull эквивалентны | Drag 0.99/0.985, continuous cadence, resistance и authority различны. |
| on_expire и on_kill взаимозаменяемы | Различаются причина, порядок, direct-target context и AoE exclusion. |
| Equipment maxStack всегда неисполняемый | Native stack 1 не отменяет Gameplay.MaxStack в craft-yield cap (Multiplayer:1352–1353). |

Ни один контрпример не предлагает новый запрет пользовательского дизайна. Они сохраняют уже существующие независимые решения и устанавливают границу доказательства конкретного alias.
