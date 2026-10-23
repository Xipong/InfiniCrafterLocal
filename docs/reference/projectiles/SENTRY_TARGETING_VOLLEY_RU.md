# A6a/A6d — явный залп и выбор цели

`target_and_fire` принимает пять новых независимых параметров. Registry остаётся владельцем схемы, единиц, диапазонов и model-facing описаний. Compiler прямо проецирует выбранные значения в `entity.targeting` и сохраняет отдельный receipt для каждого поля.

| Параметр | Значение | Поведение |
| --- | --- | --- |
| `count` | integer 1–4 | Число снарядов в одном срабатывании контроллера; отдельный `configure_spawn.count` дочерней entity продолжает описывать другие способы её создания. Действующие ограничения бюджета и глубины остаются обязательными. |
| `spreadRadians` | number 0–0.75 radians | Полный угол симметричного веера. Для одного снаряда смещение равно нулю. Не выбирает скорость, aim или placement дочерней entity. |
| `targetPolicy` | `distance_score` / `player_assigned_first` | Во втором варианте приоритет получает конкретный `Projectile.OwnerMinionAttackTargetNPC`, если проходит те же фильтры. Затем применяется обычный поиск по distance score. |
| `requireLineOfSight` | boolean | Включает native `Collision.CanHit` между фактическими hitbox источника и NPC; действует и для назначенной, и для найденной цели. |
| `hardRange` | boolean | Проверяет геометрическую дистанцию до применения `sameTargetBias`. Предыдущая либо назначенная цель за пределами радиуса не проходит. Равенство радиусу допускается. |

Чтобы дочерний снаряд вылетал из контроллера к выбранной цели, Author выбирает у него `configure_spawn.aim=velocity` и `placement=item_use_origin`. Например, `count=4`, `spreadRadians=0.6` дают направления −0.3, −0.1, +0.1, +0.3 радиана относительно переданного направления. Явно выбранные `cursor`/`facing` или другая точка создания не заменяются.

## Классификация и сохранение старых контрактов

Это расширение прямой низкоуровневой проекции. Оно не определяет механику из названия, класса урона или stationary kind. Полный Author может опустить только новые поля с одинаковыми `default` и `neutral`: `1`, `0.0`, `distance_score`, `false`, `false`. Эти значения точно сохраняют прежнее поведение контроллера; compiler пишет `declared_neutral_omission`. Неверное присутствующее значение остаётся RED. Repair меняет лишь разрешённый invalid leaf, а ранее принятая пустота остаётся frozen.

Старый сохранённый v5 wire без новых полей принимается. Python wire validator не дописывает поля; C# DTO применяет прежние нейтральные значения при отсутствии. Отдельные новые числовые параметры строго отклоняют выход за диапазон, без clamp. `spreadRadians` сохраняется как JSON double до float32 границы движка; ненулевой угол, исчезающий при этой конверсии, отклоняется и в Author/wire, и в C# DTO. Это проверка сохранения ненулевой механики, а не обещание побитового float32 round trip.

`target_and_fire` не включает native sentry lifecycle, не меняет лимит событий за активацию, не создаёт скрытые дополнительные calls и не изменяет авторский урон. Восстановление native turret slots и активного бюджета потомков выделено в отдельную категорию аудита.

## Проверки

Python regression проверяет все 32 комбинации крайних count/spread, обеих policy и двух boolean-фильтров; точные receipts, provider nullable inverse, реальные Author packets, frozen Repair, ошибочные типы/диапазоны и mutation guard диапазонов C#.

`tools/native/EngineRuntimeChecks.SentryTargeting.cs` обращается к production `FindFiringTarget`, `ApplyTargetAndFire`, сериализации DTO и реальному spawn loop. Native вызовы наблюдаются через существующий harness detour: геометрия LOS, приоритет assigned NPC, радиус до bias, равенство радиусу, обратное переключение к soft score, точные аргументы четырёх выстрелов, один выстрел, возврат неиспользованного бюджета и запрет стрельбы remote peer. Headless observer возвращает незарегистрированный projectile и не утверждает, что игровой spawn выполнен.

В среде подготовки PR нет .NET/tModLoader/ParticleLibrary/Luminance: C# build, выполнение EngineRuntimeChecks и игровой/MP smoke имеют статус **notRun**. Portable pytest и структурные gates перечислены в PR description. Эти ограничения нельзя считать доказательством native поведения.

Исторический источник восстановления: `f04ee02`, `GeneratedProjectile.Sentry.cs` и `GeneratedItem.Sentry.cs`; canonical API: [tModLoader Projectile](https://docs.tmodloader.net/docs/stable/class_projectile.html).

## Движение и стрельба одной entity

`target_and_fire` отвечает за выбор цели и выстрел, а не заменяет явно выбранное движение. Для `temporary_helper`, `stationary_projectile`, `free_projectile` или `child_projectile` можно добавить обычный `move_orbit`, `move_straight` или другой допустимый для этого kind driver на ту же entity. Движение выполняется один раз перед проверкой выстрела; направление и origin выстрела берутся из текущего положения, без предсказания будущего положения после native интеграции скорости. Собственный movement дочернего снаряда остаётся независимым.

Для stationary/helper, если movement не задан, прежняя stationary-семантика сохраняется: compiler не добавляет driver, spawn не получает начальную скорость. При явно выбранном movement используется явно заданная constant launch velocity; задержка активации сохраняется. Sampled velocity distributions и velocity modifiers не расширяют прежние ограничения по entity kind. Это исправление исполнения существующей комбинации, без нового selector и без автоматического выбора движения по имени предмета.

Контроллер доступен также free/child projectile; для них сохраняется обязательный explicit movement. Velocity modifiers остаются только free/child и требуют movement. Native regression проходит сериализованный DTO, а не только прямой вызов AI на вручную изменённой entity.

Validator возвращает advisory `warnings`: `motion_owned_by_beam` объясняет подавленное движение, `inherited_damage_disabled` — что `live_parent` выбирает величину урона, но не включает отсутствующую damage lane ребёнка. Преднамеренно безвредный ребёнок остаётся допустимым; `set_projectile_damage` с явным `damage:0` может получать наследуемый урон. Предупреждения не меняют документ, не превращаются в ошибки и не дают Repair новых полномочий.
