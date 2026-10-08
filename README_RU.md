# InfiniCrafterLocal v0.4.250

**0.4.250:** сохранены точные механики и принятая внешность generated-родителей в следующих Author/Visual/Repair; настоящий craft snapshot передаёт literal tooltip с языком/identity и проверенную source-motion reference. Image backend получает exact display pixel budget и grip/topology framing. Исправлены прямой расход stackCost и identity независимых generated buffs; добавлен явный finite sound selector. Удалён host-рекомендуемый damage, обновлён Codex catalog protocol для SOL 6.1. Сохранены [placed PNG capability](docs/PRESENT_PLACED_ITEM_SPRITE_RU.md), durable material/net lifecycle, полная sanitized запись stage-builder requests и runtime fixes 0.4.249.1–.3. Старые recipes/PNG не переавторствуются; gameplay design по-прежнему выбирает модель.

Мод Terraria/tModLoader и LocalGenerator создают предмет из двух выбранных входов. Gameplay Author составляет `runtimeProgram` v5; Python проверяет и технически компилирует его, Visual/VFX Directors оформляют принятые entities/events, image backend рисует PNG, C# исполняет typed DTO. Repair условен и ограничен отвергнутыми полями; код не выбирает механику из названия, категории или прозы.

## Начать

**[Документация по задачам — центральный индекс](docs/README_RU.md)**

- [Установка, настройки, запуск и MP — единый runbook](QUICK_START_RU.md).
- [Команды игрового чата и результаты диагностики](command.md).
- [Сборка мода и внешние DLL](BUILD_QOL_RU.md).
- [Качество контекста родителей, source physics и image brief](docs/ITEM_QUALITY_CONTEXT_RU.md).
- [LocalGenerator: файлы, границы сервиса и offline QA](LocalGenerator/README_RU.md).

## Версия и обновление

**0.4.249 — реальные библиотечные VFX:** новые явные `libraryParticle` / `particle` и `screenShakeCue` / `screenShake` используют ParticleLibrary V3 и Luminance. Модель выбирает движение, размеры, цвет, timing и событие; runtime применяет native lifecycle/authority и существующие budgets. Подробный контракт и настройки — [библиотечные primitives](docs/VFX_MATERIAL_ELEMENTS_RU.md#libraries). Старые `pl:*` остаются Terraria Dust, корректные recipes/PNG не переписываются. Сохранены hotfix.2, Default/Terraria Like, GUI-профили и прежняя механика. Обновляй мод и генератор вместе; пользовательская установка не меняется автоматически. Подтверждённый сбой texture origin старой установленной 0.4.248 уже исправлен в hotfix.2 и сохранён здесь; общий full-game flicker остаётся нерешённым, отдельного предположительного renderer patch нет.

**Сохранённая основа prerelease 0.4.248:** обновляй мод и LocalGenerator вместе, сохраняя личный `config.env`, cache, recipes/PNG и данные миров. В поставку входят принятые runtime-исправления: penetration/maxPenetrate, native root damage/knockback, явный tile collision и сохранение перековки; EN/RU tooltip показывает реальные bindings, цену и эффекты. Необычное `hold`-управление цепного шара сохранено. Также включены sprite-size/angle metadata для high-resolution PNG, обновление texture cache и Codex effective-wire cache/prefix refinements. Каталог gameplay остаётся **52 capabilities / 229 parameters**.

Модели, личный `config.env`, cache и `ParticleLibrary`/`Luminance` не входят в source-generator ZIP. Корректные старые recipes/PNG не мигрируют и не перерисовываются автоматически. Default лимит ответа VFX Director/Repair — 8000; явная настройка имеет приоритет.

**LocalGenerator 0.4.248:** [OpenRouter provider pin](docs/OPENROUTER_ROUTING_RU.md) включён в поставку и фиксирует upstream без обхода через другой профиль/fallback; в старом опубликованном ZIP 0.4.246 его нет. Новая guidance для held-body/collision помогает будущей генерации, но не переписывает исторические definitions/PNG и не означает, что прежние визуальные результаты исправлены.

В 0.4.248 снята ошибочная привязка root-combat bridge к версии/MVID DLL: загрузка проверяет реальные API/signatures и IL callsite, не номер сборки. Исправленный `.tmod` проверен на фактически установленной Steam tModLoader 2026.8.3.0; контрактные guards сохраняются. BOX + premultiplied resize — явная базовая настройка; GUI позволяет отдельно сбросить resize без смены модели/провайдера. `BG color=transparent` означает native-alpha промпт/request и отключает локальный chroma-keyer; opaque chroma-профили сохраняют прежнюю обработку. Проверка alpha-request здесь offline, не обещание entitlement или фактического alpha от текущего OAuth endpoint.

Управляющие запросы GUI к loopback обходят системный прокси Windows; внешние provider-запросы сохраняют прежний прокси. `/health` больше не опрашивает отдельный sd.cpp сервер: его `serverAlive=null` означает «не проверялся», явный `/sdcpp_debug` сохраняет live probe. Несовпадающая ручная конфигурация отображается как `Custom`, а hover-подсказка не заменяет результат запуска и не раздувает панель состояния. `Alpha threshold` остаётся доступен для обработки item alpha и при `transparent`. Рабочий конфиг — `LocalGenerator/config.env`, не одноимённый файл в корне поставки.

**Обновление GUI `0.4.248-gui.1`:** изменение полей автоматически переключает профиль в `Custom`. «Сохранить как…» создаёт отдельный именованный профиль в `LocalGenerator/gui_user_presets.json`; ключи/токены не копируются, лимиты `*_TOKENS` и неизвестные настройки сохраняются. Выбери `Мой: <название>` → «Применить», затем «Сохранить» для записи рабочего `config.env`. По умолчанию показаны основные активные поля; «Расширенные настройки» раскрывает остальные без удаления значений. Runtime и `.tmod` остаются 0.4.248: этот GUI-only выпуск не меняет игровой код.

**Hotfix `0.4.248-hotfix.2`:** строгие provider-схемы Gameplay Author/Repair получают явные типы `const`; доказанно непересекающиеся `oneOf` и конечные условные требования представлены поддерживаемыми конструкциями Structured Outputs. Локальные ограничения, capabilities и выбор механик не меняются; provider-only null удаляется только там, где схема явно кодирует пропуск optional-поля. Отказ провайдера от исходящей схемы возвращается как `424 llm_request_rejected`, без ложного сообщения о невалидном ответе модели и без повторного cache-poll. GUI больше не обрывает запуск до завершения штатного Windows closed-port probe; остановка использует оставшийся общий бюджет ожидания. Игровая загрузка PNG исправлена: SinglePlayer/сервер обращается к настроенному generator endpoint, а не к advertised адресу для друзей; MP-client сохраняет полученный peer URL. Поэтому в hotfix нужен новый `.tmod` с тем же номером 0.4.248, а не старый бинарник GUI-only выпуска. VFX Director/Repair теперь явно получает сведения, что native use sound отключён и `soundCue` — отдельный выбор, независимый от сдержанности визуальных эффектов; сохранённые пустые slots не переписываются и не получают звук автоматически. Offline wire/roundtrip tests не являются подтверждением принятия схемы внешним API или успешного игрового крафта.

## Стиль генерации

В GUI, в основных настройках генерации, выбери **Стиль промпта: Default / Terraria Like**. Это отдельный выбор, не профиль модели или image backend. Сохрани настройки и перезапусти генератор; именованные GUI-профили сохраняют этот выбор, а встроенный provider/backend preset не сбрасывает его.

- **Default** — обычная творческая подача. Во всех Author/Visual/VFX промптах, включая условный Repair и image prompts, явно указан контекст: создаётся предмет или его assets для **Terraria (tModLoader)**.
- **Terraria Like** — тот же контекст плюс направление к ванильной Terraria: читаемый силуэт в игровом размере, компактная палитра, крупные осмысленные пиксельные группы, дискретные тени/блики, меньше зерна и близких оттенков. Эффекты поддерживают образ предмета; намеренные мягкие свечения и выразительные эффекты остаются допустимыми.

В `LocalGenerator/config.env`: `INFINI_PROMPT_STYLE=Default` либо `INFINI_PROMPT_STYLE=Terraria Like`. Общий game/style brief добавляется вне прежнего лимита authored/technical image prompt, в том числе при техническом retry: он не вытесняет описания формы или исправления прозрачности и не теряется при compaction. Guidance не выбирает DamageClass, movement, inputs или weapon presets, не меняет схемы и не разрешает Repair переписывать frozen-поля. Старые recipes/PNG автоматически не меняются. Доставка выбранного текста в реальные request builders проверена offline; изменение качества новых рисунков не измерялось live.

## Контракты и приёмка

[Архитектура](PROJECT_ARCHITECTURE_RU.md) · [карта кода](PROJECT_MAP_RU.md) · [правила изменений](AGENTS.md) · [generated Author/Repair boundary](lowery.md) · [generated capabilities](docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) · [lossless lowering](TECHNICAL_LOWERING_AUDIT_RU.md) · [tModLoader mappings](docs/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md).

[Три LLM-стадии](docs/THREE_STAGE_LLM_PIPELINE_RU.md), [image lifecycle](docs/IMAGE_ASSET_LIFECYCLE_RU.md), [VFX](docs/VFX_MATERIAL_ELEMENTS_RU.md) и [владельцы тестов](docs/TEST_CONTRACT_OWNERS_RU.md) — специализированные контракты. Offline/native gates не доказывают успешный live craft, качество рисунка, Terraria/GPU или multiplayer.
