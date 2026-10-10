# A7 — удержание, рост и геометрия channel beam

`channel_beam` получает пять независимых низкоуровневых параметров. Они не выводятся из DamageClass, имени, категории, спрайта или VFX. Существующие `rangeTiles`, `widthPx` и `warmupTicks` остаются обязательными решениями Author.

| Параметр | Явная семантика | Нейтраль |
| --- | --- | --- |
| `manaPayment` | `initial_use_only` сохраняет оплату первоначального native item use; `each_use_time` дополнительно оплачивает удержание через `Player.CheckMana` с текущим HeldItem каждые `HeldItem.useTime` world ticks. | `initial_use_only` |
| `initialDamageMultiplier` | Number 0.01–1. Начальный множитель NPC source damage линейно растёт до 1 в течение `warmupTicks`. Применяется в `ModifyHitNPC`. | `1.0` |
| `initialWidthMultiplier` | Number 0.01–1. Начальная доля `widthPx` линейно растёт до 1. Collision и `runtime_geometry` используют одну ширину, включая размеры меньше пикселя. | `1.0` |
| `damageStartProgress` | Number 0–1. Доля warmup, с которой разрешается native friendly hit lane; граница включительна. | `1.0` |
| `raycastTiles` | Boolean. Native `Collision.LaserScan` делает три выборки поперёк текущей ширины. Длина общей линии равна кратчайшей выборке в диапазоне 0…authored range. | `false` |

При нулевом `warmupTicks` progress сразу равен 1: длина warmup-фазы равна нулю, поэтому ширина и damage multiplier сразу полные. В остальных случаях progress — bounded отношение возраста projectile в AI updates к `warmupTicks × (extraUpdates + 1)`. `damageStartProgress=1` сохраняет прежний запрет ударов до конца warmup. Чтобы наносить растущий урон во время разгона, Author явно выбирает меньший порог, например 0.08.

## Мана и authority

Дополнительная оплата включается только через `manaPayment=each_use_time` и выполняется только owner peer для каждого физического beam. Несколько одновременно созданных лучей имеют отдельные таймеры и каждый оплачивает своё удержание. Первый активный update начинает отсчёт без повторной оплаты native item use. Последующие оплаты используют текущий `HeldItem.useTime` с техническим нижним пределом один world tick. Дополнительные AI updates в одном world tick не повторяют платёж; uint world-clock wrap сохраняет интервалы.

Вызов — `owner.CheckMana(owner.HeldItem, amount: -1, pay: true, blockQuickMana: false)`. Стоимость определяет native `GetManaCost`, включая native modifiers; missing-mana эффекты остаются разрешены. Отказ завершает projectile до продолжения активного beam. Release, death, `noItems`, `CCed`, неактивный owner или несовпадающий удерживаемый GeneratedItem также завершают его существующим control path.

Owner hydration сохраняет таймер уже существующего физического host; fresh Configure начинает новый отсчёт. Remote client и server не создают второй платёж. Это правило authority существующей системы projectile, а не утверждение о серверной защите от недостоверного клиента.

## Урон, геометрия и VFX

Множитель урона применяется к `NPC.HitModifiers.SourceDamage`. Базой остаётся фактический `Projectile.damage` после native spawn и других изменений runtime; значение поля не перезаписывается и не захватывается повторно при hydration. Поэтому один hit получает множитель один раз, а A9 `live_parent` продолжает означать буквальное поле `Projectile.damage`, без добавления per-target hit modifiers. Native defense, crit, damage variation и округление следуют после source modifier. Этот параметр описывает NPC hit lane; он не объявляет новый PvP damage policy.

`GetChannelBeamGeometry` — общий владелец start, end и collision width. Его используют native line collision, отрисовка `runtime_geometry` и получение endpoint для VFX `texturedPath source=beam`. Ширина VFX path остаётся собственным явным решением VFX Director; она не заменяет collision width. PNG по-прежнему рисуется один раз в точке projectile, без автоматического растягивания вдоль луча.

При `raycastTiles=true` все потребители получают текущий clipped endpoint. Используется минимум трёх native samples без temporal smoothing: новая ближняя преграда сразу сокращает линию. Нулевая длина не создаёт collision segment или runtime body. Нефинитный результат native API завершает чтение ошибкой, без подстановки полной длины. Это ограниченная выборка native LaserScan, а не непрерывное доказательство очистки каждого пикселя объёма.

`damage.ownerHitCheck` — отдельная native проверка пути от owner до конкретной цели. Она не обрезает beam segment. `collision.tileCollide` относится к движению самого projectile. Ни один из этих флагов не включает raycast и не изменяется им.

Исторический A7 использовал фиксированные начальные доли ширины/урона, усреднение scan и сглаживание длины. Здесь доли и момент допуска ударов выбирает Author; явный raycast использует документированный кратчайший sample. Это восстановление выразимости и native границ, без заявления об идентичности каждой старой траектории или порядка округления.

## Классификация и совместимость

Новые поля — прямые literal projections в `controller.params`; finite opcode/name projection остаётся существующим Alias Lowering. Width/damage interpolation, native payment и tile scan исполняют явно выбранные параметры. Они не добавляют механики по категории и не исправляют отсутствующий дизайн.

Только полный Author может пропустить пять полей с одинаковыми registry `default` и `neutral`. Compiler материализует ровно объявленные нейтрали и пишет отдельные `declared_neutral_omission` receipts. Неверное присутствующее значение остаётся RED. Nullable provider projection удаляет только schema-owned optional nulls; произвольные malformed значения сохраняются для validation.

Сохранённый v5 wire без новых полей остаётся допустимым. Nullable C# свойства не сериализуют отсутствующие поля обратно как новые решения. Новые поля на другом controller, movement или item_body недопустимы даже при нейтральном значении. Nullable setters строго отклоняют явный null и неподходящие типы/границы; дробные multiplier, которые при переходе в float32 слились бы с нейтралью 1, также отклоняются. `damageStartProgress` хранится и сравнивается в binary64.

Repair остаётся exact-leaf и frozen-first: исправление неверной ширины не даёт права включить recurring mana, raycast или заполнить принятую пустоту соседнего параметра. Исторические frozen fixtures и SHA не переписаны; сравнение сначала доказывает ровно пять новых нейтральных полей с соответствующими omission receipts и исключает только эту объявленную дельту.

## Проверка

Portable tests охватывают 32 сочетания явных решений, 32 сочетания пропусков, типы/границы/consumer precision, реальные production Author packets в двух transport modes, provider inverse, strict wire без provenance, frozen Repair и mutation guards C# bounds.

В `EngineRuntimeChecks.ChannelBeam.cs` добавлены production/native сценарии: DTO и сохранённая пустота; фактический source damage при разных extraUpdates и hydration; геометрия включая ширину 0.02 px; native CheckMana с mana-cost modifier и world-clock wrap на четырёх сетевых ролях; прекращение при отсутствии маны/управления; scan boundary и одинаковые endpoints для collision/body/VFX. Native scan/kill boundary observers не выдаются за запуск Terraria world loop. В mana-сценарии observer вызывает исходный `Player.CheckMana`.

В среде подготовки нет .NET/tModLoader/native зависимостей. C# build, исполнение EngineRuntimeChecks, game smoke и multiplayer smoke — **notRun**. Portable результаты приводятся в PR description; native проверки остаются отдельным review gate.

Исторический источник: `f04ee02`, `ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs`, бывшие методы расчёта charge, beam scan и sustain mana. Первичные API: [Player.CheckMana](https://docs.tmodloader.net/docs/stable/class_player.html), [Collision.LaserScan](https://docs.tmodloader.net/docs/stable/class_collision.html), [ModProjectile.ModifyHitNPC](https://docs.tmodloader.net/docs/stable/class_mod_projectile.html), [NPC.HitModifiers.SourceDamage](https://docs.tmodloader.net/docs/stable/struct_n_p_c_1_1_hit_modifiers.html).
