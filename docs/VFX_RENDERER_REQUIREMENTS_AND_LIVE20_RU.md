# VFX renderer requirements и сравнение Live20

## Подтверждённый дефект model-facing контракта

Исходный срез: `cf503d483baa87323bdab9c5d8871084391612c4`. Панель: `direct-construction-cf503d4-flash35lite-medium-live20` в соседнем `InfiniCrafterLocal/artifacts/tool-runs/`.

В восьми первоначальных ответах VFX Director выбран `rendererKind=lightCue` и **правильный `channel=light`**, но `lane=primary` в семи случаях и `lane=support` в одном. Требование `lane=cue` существовало в Python validator и C# DTO, но не было указано в переданных правилах или inline outputSchema. Модель получала независимые enum-списки. В запросах использовался `response_format=json_object`: provider не применял передаваемый внутри сообщения outputSchema как enforced structured-output schema.

Затронутые случаи: `bee_boomstick`, `astral_minishark`, `infernal_boomerang`, `lens_finch_staff`, `jester_bow`, `obsidian_pickaxe`, `torch_mining_helmet`, `glowing_healing_potion`.

Отдельное противоречие: общая инструкция предлагала `impactSprite` значения textureRole=item/entity, хотя validator требует impact. Оно проявилось в `spider_sentry`.

## Исправление

Canonical owner остаётся `LocalGenerator/infini_local/core/vfx_manifest.py`:

- Единая таблица существующих зависимостей: lightCue → channel=light/lane=cue; soundCue → channel=sound/lane=cue; impactSprite → textureRole=impact.
- Таблица передаётся в runtimeSurface и превращается в условные ограничения схемы slot. Обычный Director и оба конструктора Repair schema используют один источник.
- Описание rendererKind отличает world lighting от рисуемого glow/trail. impactSprite исключён из противоречащего ему общего совета по textureRole.
- Общий локальный `strict_schema_errors` получил исполнение `allOf`, которого раньше не поддерживал. Условные нарушения дают leaf diagnostics, без нового object-level union error и без расширения Repair до всего slot.
- Существующие semantic diagnostics используют ту же таблицу. C# renderer, DTO, Gameplay Author, wire и значения полей не менялись. Пропущенные/невалидные значения не дописываются и не исправляются автоматически; остальные renderer/lane/channel сочетания сохраняются.

Это исправление сообщаемого контракта, а не доказанный рост first-pass модели. Новый live-запуск не выполнялся.

## Проверки

- Шесть проверок реальных сериализуемых Director/Repair packets сначала упали: schema допускала сочетания, которые validator отвергал. После исправления — GREEN.
- Десять новых тестов включают перебор renderer × channel × lane и точное сохранение остальных значений при Repair. Дополнительный RED→GREEN regression защищает frozen-first: несовместимая попытка изменить замороженный lane не должна отменять полезное исправление event. До merge проверяется структура patch; полные renderer-ограничения применяются к результату merge. Итоговая schema/validator не ослаблены. Отдельный тест public attach_hybrid_vfx_manifest подтверждает: если tuple после единственного Repair всё ещё невалиден, manifest не создаётся.
- Полный Python suite: **882 passed**. Ruff, Pyright, schema export check, lowery check, targeted Repair audit, contract parity и project hygiene прошли.
- Офлайн повторно обработаны исходные сохранённые ответы всех 18 успешных VFX-цепочек, включая 10 ответов Repair: **18/18 финальных manifest совпали полностью**. Все 10 первоначально невалидных ответов по-прежнему отвергаются. Это parity replay, не свежая генерация.
- Игра/GPU/MP не запускались. Отдельный Gameplay Repair scope defect из meteor_spacegun этим изменением не исправлялся.

## Были ли раньше более высокие PASS?

Да. Счётчики ниже родительский агент повторно вычислил из results.ndjson и actual logical request/response ledgers, а не только из отчёта исследователя.

| Панель | HEAD label | Final | Без Gameplay Repair | Без любых Repair | Gameplay / Visual / VFX Repair |
|---|---|---:|---:|---:|---:|
| primitive-proxy-flashlite35-live20-impact-fixed-20260925 | 27d5c40052786cd39088eacf94e16cbf2f5fdb6a, dirty | 20/20 | 16/20 | 14/20 | 4 / 1 / 2 |
| primitive-proxy-flashlite35-reusable-no-echo-live20-20260925 | тот же HEAD label, dirty | 20/20 | 14/20 | 10/20 | 6 / 4 / 1 |
| typed-ir-flashlite35-live20-2715c93-20260925 | 2715c93f45165d347a2499020ead5e21ec54db7f, clean | 14/20 | 10/20 | 4/20 | 6 / 1 / 5 |
| direct-construction-cf503d4-flash35lite-medium-live20 | cf503d483baa87323bdab9c5d8871084391612c4, clean | 18/20 | 10/20 | 3/20 | 9 / 0 / 10 |

**Важное уточнение конфигурации:** во всех четырёх панелях actual initial Author requests использовали `gemini-3.5-flash-lite`, **reasoning_effort=medium**, temperature=0.5. Отсутствие expectedReasoningEffort в старом manifest не означает отсутствия effort на wire. В старых панелях max_tokens=12000, в текущей =18000.

### Что объясняется имеющимися данными

1. **VFX содержит реальный пробел интерфейса.** В первой старой панели было 4 lightCue slot, из них 1 с неверным tuple; во второй — 10/1; в typed-ir — 6/5; в текущей — 10/8. Таким образом, ошибка существовала до последних изменений, но теперь проявилась значительно чаще. Таблица ограничений устраняет скрытое условие, не маскирует ошибку validator.
2. **Пропуски Gameplay-полей нельзя целиком списать на новые обязательные параметры.** В actual старой и текущей карточках configure_item_stats совпадает набор обязательных параметров; manaCost, damage, damageClass и другие поля уже были required. holdoutOffsetX/Y также требовались раньше. Минимум local NPC cooldown был −1 в обоих контрактах: значение −2 не стало ошибкой только из-за переименования единиц.
3. **Представление обязательности изменилось.** Раньше каждое обязательное поле несло required:true; теперь используется общее правило «все перечисленные, кроме optional:true». Информация формально сохранена, но ухудшение её заметности для модели — обоснованная гипотеза для matched-теста, не установленная причина. В данном исправлении Author-подача не менялась.
4. **Есть новые семантические ограничения.** Например, durable placeable hybrid требует maxStack=1; это отдельный источник нынешних Gameplay Repairs, а не проблема C# исполнения примитива.
5. **Два текущих Final FAIL — не два доказанных провала примитивной архитектуры.** astral_mirror не получил HTTP-ответ из-за timeout; meteor_spacegun имел ошибки Author, но корректное исправление ссылки затем заблокировал воспроизведённый harness scope/filter defect.
6. **Старые и новые панели не являются контролируемым A/B.** Старые деревья dirty; точного HEAD недостаточно для восстановления исполнявшегося кода. Recipe key, parents и balance corridor совпали только у 17/20 пар: родители различались у infernal_boomerang, meteor_spacegun и corrupt_yoyo. Менялись prompts, budget, ограничения и прочий код; есть стохастика модели.

В старых сохранённых Author-запросах тоже был runtimeProgram из entities/bindings/calls, который исполнялся C# DTO/executors. Данные указывают прежде всего на качество model-facing интерфейса, соблюдение обязательных полей и корректность harness; они не изолируют преимущество или недостаток самого перехода к typed primitives. Для причинного вывода нужен отдельно разрешённый matched screen с одинаковыми входами, моделью и настройками, а не повтор всей панели с одновременно меняющимися условиями.
