# Terraria/tModLoader: units для low-level Author

Terraria runtime обычно обновляется 60 раз в секунду. Все authored time fields в `runtimeProgram` используют ticks, если parameter явно не объявляет другие units.

| ticks | seconds | назначение |
|---:|---:|---|
| 6 | 0.10 | минимальный период event action |
| 10 | 0.17 | очень быстрый use/cooldown |
| 20 | 0.33 | короткое действие |
| 30 | 0.50 | среднее действие |
| 60 | 1.00 | секунда |
| 120 | 2.00 | долгий charge/lifetime |
| 180 | 3.00 | поле/долгий projectile |

Дальность свободного projectile грубо оценивается как `speedPxPerTick * lifetimeTicks / 16` tiles, но movement controller может изменить траекторию.

Пример отдельной композиции:

```json
{
  "entities": [
    {"id": "bolt", "kind": "free_projectile"}
  ],
  "bindings": [
    {"id": "primary_bolt", "input": "primary_use", "action": "spawn_entity", "target": "bolt"}
  ],
  "calls": [
    {"id": "bolt_spawn", "fn": "configure_spawn", "target": "bolt", "params": {"speedPxPerTick": 9, "count": 1, "spreadRadians": 0, "offsetPx": 8, "aim": "cursor", "placement": "owner_center"}},
    {"id": "bolt_move", "fn": "move_gravity_arc", "target": "bolt", "params": {"gravityPerTick": 0.12}},
    {"id": "bolt_life", "fn": "set_projectile_lifetime", "target": "bolt", "params": {"lifetimeTicks": 90}}
  ]
}
```

Полные ranges/units берутся только из `capability_registry.py` и generated schema, не из этого human guide.
