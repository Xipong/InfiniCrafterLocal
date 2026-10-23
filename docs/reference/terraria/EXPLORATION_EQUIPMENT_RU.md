# Исследовательская экипировка

Все параметры ниже — независимые optional-параметры `configure_accessory`.
Они исполняются только через `equipped → equip_passive`. Пропуск остаётся
пропуском в сохранённом wire; false/0 не выдаёт эффект. Имена предметов не
выбирают механики. Проекция — identity Alias Lowering с exact receipt на каждый лист.

## Рыбалка

`fishingPower` (0–100 целых очков) прибавляет `Player.fishingSkill` до
нативных множителей удочки, наживки, погоды и времени. `fishingLine`
включает нативную защиту от обрыва лески; `lavaFishing` — возможность
рыбалки в лаве, без иммунитета к лаве. `fishingSonar` включает предпросмотр
улова, `fishingCrates` — нативный модификатор шанса ящиков.
Ни один параметр не создаёт удочку, наживку, поплавок или добычу.

Проверки: `test_exploration_equipment.py` проверяет реальный Author-пакет,
schema, compiler, receipts, strict wire и frozen Repair; native check
`Exploration Fishing` проходит DTO/network roundtrip и UpdateAccessory,
проверяет GetFishingConditions, native reset и отказ неверных чисел.
Это CPU-проверки, не запуск игрового мира или multiplayer.
