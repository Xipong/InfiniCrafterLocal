# Зарядка, орбита и отскоки

Новые параметры — точные scalar/unit projections (Alias Lowering), без выбора механики кодом и дополнительных LLM-стадий. Registry формирует одинаковые Author/Repair cards и provider schemas.

## Независимая зарядка

`charge_then_release.params` задаёт `chargeSeconds`, `damageMultiplier`, `knockbackMultiplier`, `speedMultiplier`. Все три коэффициента явные: частичная зарядка линейно интерполирует каждый от 1 к его значению на полном заряде. Урон допускает 1–4, отбрасывание 0–4, скорость 0.1–4. Пример: 3 / 0.25 / 0.5 даёт сильный, медленный выстрел со слабым отбрасыванием. Полёт, столкновения и события по-прежнему задаются отдельно.

`damageMultiplier` без потерь проецируется в новое nullable wire-поле `chargeDamageMultiplier`. Все три nullable wire-поля обязаны присутствовать вместе и принадлежать точному контроллеру зарядки. Они проверяются до исторической normalization; present null, выход за точные raw-границы и ненейтральное значение, округляющееся во float32 к 1, отклоняются. Отсутствие всех трёх у сохранённого v5 оставляет прежнее совместное усиление через `powerMultiplier`; свежий Author его не пишет. При новых контролах старое поле может быть только отсутствующим либо нулевым bag-полем. Чтение не дописывает поля. Rehydrate/ExtraAI не применяет усиление повторно.

При удержании заряжаемого предмета возле прицела показывается процент фактического заряда. Полный заряд отмечается золотой полоской, надписью «Готово» и одним коротким звуком. Индикатор читает существующий controller counter с учётом `extraUpdates`; не изменяет урон, момент отпускания или gameplay-событие `channel_complete`. Сигнал привязан к физическому поколению снаряда: повторные чтения, hydration и ExtraAI того же экземпляра не воспроизводят его заново. После отпускания, смены предмета или смерти индикатор скрывается. Меню, карта и скрытый UI не показывают индикатор и не воспроизводят отложенный звук после закрытия.

## Орбита

`move_orbit.params.turnRadiansPerSecond` — signed мировая угловая скорость, независимо от скорости запуска. Положительное значение вращает по часовой стрелке на экране, отрицательное против неё, 0 сохраняет угол относительно владельца. 6.283185307179586 рад/с — один оборот в секунду. `radiusTiles` остаётся расстоянием от владельца; индивидуальная начальная фаза по projectile identity сохраняется.

Lowering: `orbitRadiansPerUpdate = turnRadiansPerSecond / 60 / updatesPerTick`. `updatesPerTick` берётся из явно выбранного collision call, поэтому дополнительные AI updates не ускоряют орбиту. В native executor угол = active update age × выбранный increment + initial phase. У сохранённого wire без нового поля остаётся прежние 0.055 радиана за update. Драйвер, как и прежде, отключает tile collision.

## Отскоки

`set_projectile_collision.params.bounceSpeedRetention` — коэффициент 0–1 **только столкнувшейся компоненты скорости**. 1 отражает её без потерь, 0 останавливает эту ось. Касательная компонента не меняется; трение, качение, гравитация и взрыв не подразумеваются. Пропуск в свежем Author — объявленная точная нейтраль 1 с отдельным omission receipt.

`bounceCount=N` допускает N отражений; следующее столкновение отдаёт native уничтожение. Boomerang/returning-glaive/flail по-прежнему переходят в возврат до проверки bounce count и не используют коэффициент. Старый сохранённый wire без нового поля сохраняет исторические 0.78; отсутствующая метка не материализуется.

## Проверенная граница tModLoader 1.4.4

- [`ModProjectile.OnTileCollide`](https://docs.tmodloader.net/docs/stable/class_mod_projectile.html) получает скорость **до** столкновения; `Projectile.velocity` уже изменена native collision. Возврат false отменяет стандартное уничтожение. [`ExampleBullet`](https://github.com/tModLoader/tModLoader/blob/1.4.4/ExampleMod/Content/Projectiles/ExampleBullet.cs) показывает отражение изменившихся осей через `oldVelocity`.
- [`SparklingBall`](https://github.com/tModLoader/tModLoader/blob/1.4.4/ExampleMod/Content/Projectiles/SparklingBall.cs) дополнительно тормозит весь вектор; IFC намеренно сохраняет собственную точную collided-axis семантику, которая явно описана модели.
- [`Projectile.extraUpdates`](https://docs.tmodloader.net/docs/stable/class_projectile.html) повторяет AI и уменьшение `timeLeft`; готовых native-полей orbit rate/restitution нет. Прямые `Vector2`/collision hooks сохраняют композицию IFC, без переключения на чужой `aiStyle`.

Найденные возможности для отдельных будущих задач: `TileCollideStyle` задаёт прохождение платформ и collision-only хитбокс; [`Utils.GetChaseResults`](https://docs.tmodloader.net/docs/stable/class_utils.html) вычисляет перехват движущейся цели. Они не включаются автоматически этим изменением. `FlailStats`/`FlailSpinCollisionRange` вызываются только native AI flail, поэтому были бы инертны у custom IFC AI.

Проверки: Python actual outgoing Author cards/schema, compiler receipts, strict wire/retained absence и frozen Repair; source-linked native CPU checks — full/partial charge, hydration, signed orbit при N=1/3/6, отражения осей и exact nullable DTO. Реальная игра/GPU/host-client smoke — отдельная граница.
