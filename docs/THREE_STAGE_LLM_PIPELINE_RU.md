# Трёхстадийный LLM pipeline

## Happy path

| стадия | baseline calls | результат |
|---|---:|---|
| Gameplay Author | 1 | validated low-level runtime program |
| Visual Director | 1 | canonical visual kit + required entity assets |
| VFX Director | 1 | finite slots over exact entity/event inventory |
| Repairs | 0 | не нужны при валидном output |

Итого: **3 LLM-вызова**.

## Conditional repairs

- Gameplay invalid → только Gameplay Repair;
- Visual invalid/missing required PNG → только Visual Repair;
- VFX invalid → только VFX Repair.

Repair не является обязательным judge-pass и не перезапускает предыдущую валидную стадию без причины.

Все три Repair используют leaf-local frozen patch protocol. Модель видит invalid fragments, exact missing dependencies, минимальный relevant capability subset и уже валидные детали как read-only context; полный ответ заново не генерируется. Даже если модель меняет frozen-поля, deterministic filter сохраняет старые значения, принимает только точные исправления и записывает лишние изменения в audit. Подробности: `TARGETED_REPAIR_PROTOCOL_RU.md`.

## Handoffs

Gameplay→Visual передаёт accepted entities/visual roles и parent facts, но не weapon family. Gameplay+Visual→VFX передаёт exact runtime event inventory и visual kit. C# получает только accepted final contracts.

Stage accounting хранит `gameplayAuthorCalls`, `gameplayRepairCalls`, `visualDirectorCalls`, `visualRepairCalls`, `vfxDirectorCalls`, `vfxRepairCalls`; tests проверяют happy path `1/0/1/0/1/0`.
