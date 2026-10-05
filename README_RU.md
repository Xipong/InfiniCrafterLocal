# InfiniCrafterLocal v0.4.247

Мод Terraria/tModLoader и LocalGenerator создают предмет из двух выбранных входов. Gameplay Author составляет `runtimeProgram` v5; Python проверяет и технически компилирует его, Visual/VFX Directors оформляют принятые entities/events, image backend рисует PNG, C# исполняет typed DTO. Repair условен и ограничен отвергнутыми полями; код не выбирает механику из названия, категории или прозы.

## Начать

**[Документация по задачам — центральный индекс](docs/README_RU.md)**

- [Установка, настройки, запуск и MP — единый runbook](QUICK_START_RU.md).
- [Команды игрового чата и результаты диагностики](command.md).
- [Сборка мода и внешние DLL](BUILD_QOL_RU.md).
- [LocalGenerator: файлы, границы сервиса и offline QA](LocalGenerator/README_RU.md).

## Версия и обновление

**Поставка prerelease 0.4.247:** обновляй мод и LocalGenerator вместе, сохраняя личный `config.env`, cache, recipes/PNG и данные миров. В поставку входят принятые runtime-исправления: penetration/maxPenetrate, native root damage/knockback, явный tile collision и сохранение перековки; EN/RU tooltip показывает реальные bindings, цену и эффекты. Необычное `hold`-управление цепного шара сохранено. Также включены sprite-size/angle metadata для high-resolution PNG, обновление texture cache и Codex effective-wire cache/prefix refinements. Каталог остаётся **52 capabilities / 229 parameters**.

Модели, личный `config.env`, cache и `ParticleLibrary`/`Luminance` не входят в source-generator ZIP. Корректные старые recipes/PNG не мигрируют и не перерисовываются автоматически. Default лимит ответа VFX Director/Repair — 8000; явная настройка имеет приоритет.

**LocalGenerator 0.4.247:** [OpenRouter provider pin](docs/OPENROUTER_ROUTING_RU.md) включён в поставку и фиксирует upstream без обхода через другой профиль/fallback; в старом опубликованном ZIP 0.4.246 его нет. Новая guidance для held-body/collision помогает будущей генерации, но не переписывает исторические definitions/PNG и не означает, что прежние визуальные результаты исправлены.

## Контракты и приёмка

[Архитектура](PROJECT_ARCHITECTURE_RU.md) · [карта кода](PROJECT_MAP_RU.md) · [правила изменений](AGENTS.md) · [generated Author/Repair boundary](lowery.md) · [generated capabilities](docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) · [lossless lowering](TECHNICAL_LOWERING_AUDIT_RU.md) · [tModLoader mappings](docs/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md).

[Три LLM-стадии](docs/THREE_STAGE_LLM_PIPELINE_RU.md), [image lifecycle](docs/IMAGE_ASSET_LIFECYCLE_RU.md), [VFX](docs/VFX_MATERIAL_ELEMENTS_RU.md) и [владельцы тестов](docs/TEST_CONTRACT_OWNERS_RU.md) — специализированные контракты. Offline/native gates не доказывают успешный live craft, качество рисунка, Terraria/GPU или multiplayer.
