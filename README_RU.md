# InfiniCrafterLocal v0.4.246

Мод Terraria/tModLoader и LocalGenerator создают предмет из двух выбранных входов. Gameplay Author составляет `runtimeProgram` v5; Python проверяет и технически компилирует его, Visual/VFX Directors оформляют принятые entities/events, image backend рисует PNG, C# исполняет typed DTO. Repair условен и ограничен отвергнутыми полями; код не выбирает механику из названия, категории или прозы.

## Начать

**[Документация по задачам — центральный индекс](docs/README_RU.md)**

- [Установка, настройки, запуск и MP — единый runbook](QUICK_START_RU.md).
- [Команды игрового чата и результаты диагностики](command.md).
- [Сборка мода и внешние DLL](BUILD_QOL_RU.md).
- [LocalGenerator: файлы, границы сервиса и offline QA](LocalGenerator/README_RU.md).

## Версия и обновление

**Опубликованная поставка — 0.4.246:** обновляй мод и LocalGenerator вместе. Image-attempt lifecycle имеет одного владельца; промежуточные файлы приватны, итоговые PNG публикуются атомарно под immutable именами. Общая VFX PNG dependency projection проверяет исполнимые ссылки, не меняя механику/Visual. Включены deferred disposal текстур, retirement Item-эффектов при смерти и exact-leaf Repair пустого asset-domain.

Модели, личный `config.env`, cache и `ParticleLibrary`/`Luminance` не входят в source-generator ZIP. Корректные старые recipes/PNG не мигрируют и не перерисовываются автоматически. Default лимит ответа VFX Director/Repair — 8000; явная настройка имеет приоритет.

**Текущий unreleased LocalGenerator:** [OpenRouter provider pin](docs/OPENROUTER_ROUTING_RU.md) фиксирует upstream без обхода через другой профиль/fallback. Это не часть опубликованного ZIP 0.4.246 и не требует изменения мода 0.4.246.

## Контракты и приёмка

[Архитектура](PROJECT_ARCHITECTURE_RU.md) · [карта кода](PROJECT_MAP_RU.md) · [правила изменений](AGENTS.md) · [generated Author/Repair boundary](lowery.md) · [generated capabilities](docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) · [lossless lowering](TECHNICAL_LOWERING_AUDIT_RU.md) · [tModLoader mappings](docs/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md).

[Три LLM-стадии](docs/THREE_STAGE_LLM_PIPELINE_RU.md), [image lifecycle](docs/IMAGE_ASSET_LIFECYCLE_RU.md), [VFX](docs/VFX_MATERIAL_ELEMENTS_RU.md) и [владельцы тестов](docs/TEST_CONTRACT_OWNERS_RU.md) — специализированные контракты. Offline/native gates не доказывают успешный live craft, качество рисунка, Terraria/GPU или multiplayer.
