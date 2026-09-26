# Author: прямое построение вместо проверочного цикла

## Контракт изменения

Baseline: `1358fa02c45c2d0ea22fdbe1dec39153d30d4fc0`.

Author выдаёт один immutable JSON. `concept` задаёт начальную траекторию генерации; `runtimeProgram` — единственный источник исполняемой механики; `realization` и завершающий `selfEvaluation` — интерпретация и диагностика для человека, не свидетельство наблюдавшегося исполнения. Обе диагностические группы, их поля, verdict/result/intentionality и ссылки сохранены. Расхождение с концепцией не превращено в запрет craft.

Удалены отдельный `selfCheck`, `structureCheck`, `preEmissionCheck`, повторный primary self-check и системные требования «проверь ссылки/отклони draft/перед ответом». Это не замена имени чеклиста: содержательные правила распределены по владельцам построения.

- `requiredJsonShape.runtimeProgram.calls`: существующий совместимый target, точные поля выбранной capability, все non-optional и условно обязательные параметры.
- `catalog.fieldGuide`: общие обозначения параметров, допустимость ссылок по `targetKinds/allowSelf/graphEdge`, event source, единицы и ограничения исходных значений. Нейтральные значения не вставляются автоматически.
- `catalog.entityKinds`: прежние `requiredComponents`/`positionRequirement`; только соответствующим видам добавлены пояснения ownership, stationary contact и независимых projectile instances.
- `catalog.inputs` и `bindingActions`: единственный action root, hold/equipped, placement/escrow; общий binding contract сохраняет независимую контактную damage lane и её реальные suppressors. `apply_item_effects` уже объяснял совместное применение эффекта и on_use spawn — повтор системной инструкции удалён.
- `catalog.events`: источники on_use/on_hit/on_crit, различия on_expire/on_kill и `periodTicks` для periodic.
- Соответствующие capability cards: charge/release и channel, reusable hybrid maxStack, use cadence/animation.
- Глобально остаются архитектурное владение, уникальность ID, primary ownership и межобъектные graph/spawn budgets.

`realization_execution_truth_for_llm()` продолжает обслуживать существующий Repair: его сведения о runtime не удалены при сокращении первоначального Author. Первоначальный Author получает оттуда только диагностические требования к selfEvaluation. Схемы, validator, compiler, runtime, defaults и алгоритм Repair не изменены.

## Замер настоящего request builder

Одинаковые входы: `A={"name":"Workbench"}`, `B={"name":"Sword"}`, `ca=A`, `cb=B`, `key="workbench+sword"`, `model_name="gemini-2.5-flash"`. Вызван `build_initial_author_request` в отдельных свежих процессах до/после. Это офлайн-вызов production builder, не LLM-запрос. Замер обоих режимов выполнен через `llm_transport.LLM_RESPONSE_FORMAT_MODE`.

| Представление | До, символов | После, символов | Сокращение |
|---|---:|---:|---:|
| System message | 3 457 | 634 | 81,66% |
| User message — реальная compact JSON строка | 90 641 | 84 528 | 6,74% |
| System + user | 94 098 | 85 162 | **8 936 / 9,50%** |
| Request-builder JSON, `json_object` | 102 028 | 93 040 | 8,81% |
| Request-builder JSON, `json_schema` | 206 048 | 197 060 | 4,36% |

Request-builder JSON сериализован с `ensure_ascii=False`, `separators=(",", ":")`, без внутренних `_...` полей; включает экранирование message content и фактический `response_format`. Это не замер адаптированного HTTP body провайдера. JSON Schema не сокращалась: её вклад одинаков до/после и уменьшает относительную экономию полного schema-mode запроса.

Каталог вырос с 68 429 до 75 446 символов: туда перенесены локальные construction facts из глобальных инструкций. Это перераспределение, **не** рост набора возможностей. Все исходные поля каждой capability/entity/input/action/event card, параметры, ограничения и graph limits сравнены по значениям и сохранены. Добавлены только presentation notes; `parents`, `recipeKey`, `balanceCorridor` совпадают.

Локальный proxy `BAAI/bge-small-en-v1.5` WordPiece: system+user **32 605 → 30 594** (−6,17%). Это **не** Gemini tokenizer и не число оплаченных токенов. Основной результат измерения — фактическая длина сериализованного текста, а не оценка эффективности генерации.

Provider schema до/после: **103 939 символов**, SHA-256 `554cdf976220fe6fa285ad1851006d4de23afe862bbbf747c35bd354ee3cb75f`. Оба `response_format` побайтно неизменны. Сохранены **52 capabilities / 229 параметров**. Cache prefix теперь включает `diagnosticReport` вместо удалённого `selfCheck`; динамические входы по-прежнему следуют после статической части.

## Проверки

- Полный Python/toolbox suite: **872 passed**.
- Ruff и Pyright: passed.
- Новые проверки используют настоящий serialized Author packet и подтверждают отсутствие процедурного цикла, локальность правил, сохранение концепции/diagnostic shape и статической cache boundary.
- Generated targeted-Repair audit пересоздан штатным генератором после изменения размеров/общей prompt grammar.
- Registry, schema/validator/compiler и C# source не изменены. Наблюдаемая schema identity проверена отдельно от зелёного тестового набора.

Новые live-генерации (включая noreasoning), game/MP и замеры latency не проводились. Сокращение текста и сохранение контракта не доказывают улучшение first-Author success rate.
