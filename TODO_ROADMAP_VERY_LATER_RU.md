# Future backlog after low-level runtime refactor

Этот файл не является разрешением менять production architecture.

Текущая обязательная основа: один Gameplay Author, один Visual Director, один VFX Director; conditional repairs; bounded typed `runtimeProgram` v5; никакого weapon-family router или обязательного judge-pass.

Возможные будущие vertical slices только по отдельному запросу пользователя:

- новые конечные world-interaction capabilities;
- дополнительные controller patterns, если они не требуют arbitrary VM;
- расширение VFX renderer catalog;
- фактические tModLoader singleplayer/host-client regression fixtures;
- performance telemetry для spawn/event budgets;
- optional visual-model experiments без изменения gameplay contract.

Любая новая механика проходит `registry → schema/prompt → validator/compiler → wire → C# DTO/executor → tests/docs`.
