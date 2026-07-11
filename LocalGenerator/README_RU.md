# LocalGenerator v0.4.239 — current runtime authoring boundary

LocalGenerator принимает parent/world facts, вызывает LLM authoring, компилирует explicit `runtimePlan.engineCalls`, валидирует bounded runtime contract и возвращает `GeneratedItemData`. Gameplay не выводится из name, tooltip, material или visual prose.

## Текущие finite capabilities

- `channel_beam` исполняется только при exact structured selection и компилируется в canonical `runtimeFamily=beam`.
- `overhead_barrage` исполняется отдельным marker/delay/descending-child executor'ом. Projectile theme остаётся authored; старые family tokens не мигрируются.
- `spawn_secondary_projectiles(trigger=on_hit|on_expire)` имеет один exact lifecycle trigger; смешанные triggers и скрытые dual-lifecycle комбинации отвергаются.
- `state_meter` и `triggered_action` читаются для старых/debug payloads, но скрыты из active planner prompt и не исполняют произвольный gameplay.
- `secondary_attack` и прочие неподдержанные advanced intents остаются preserved/unsupported, пока не получат отдельный finite vertical slice.

## Поддерживаемость

Новая механика добавляется только как небольшой вертикальный срез:

```text
exact authored enum/field
→ один Python policy/compiler owner
→ явная projection в result model
→ один C# executor owner
→ отдельный end-to-end test
```

Не создавать универсальный trigger/action/state framework и не делать derived/debug structures вторым writable contract. Sparse-output policy не меняется: явно authored zero/default сохраняет provenance. Подробно: `../docs/RUNTIME_VERTICAL_SLICES_RU.md`.

## Balance modes

`core/balance_mode.py` — единственный policy owner:

- `safety` (default): сохраняет authored soft-balance numbers, применяет только технический Python safety corridor и пишет advice;
- `normalize`: opt-in legacy soft normalization;
- `report`: diagnostic mode без Python soft/safety mutations, при сохранении C# hard clamps.

Переменная окружения: `INFINI_BALANCE_MODE`. LLM не выбирает режим и не получает дополнительную нагрузку.

## Проверенное состояние v10 snapshot

- Python tests: 330 passed.
- Planner prompt: 22 422 / 24 000 chars, 24 active functions; `state_meter`/`triggered_action` hidden.
- Static C# contracts and project hygiene: PASS.
- Реальный tModLoader build не запускался: в окружении отсутствует `dotnet`.
