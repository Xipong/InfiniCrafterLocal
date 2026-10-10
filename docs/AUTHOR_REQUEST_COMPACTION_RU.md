# Сокращение production-запроса Gameplay Author

## Изменение и граница

Начальный Author повторял одинаковые numeric consumer rules в 30 параметрах,
полный справочник units всех возможных родителей и длинные annotations внутри
provider schema. Conditional schema повторяла одинаковую форму отдельно для
каждого event. Это занимало контекст до выбора игровых механик.

Теперь packet использует четыре изменения:

1. `consumerConstraint` в compact Author card ссылается на packet-local
   `fieldGuide.consumerConstraints`. Определения выводятся из полных registry
   правил по literal JSON identity. Новый consumer rule получает отдельное
   определение; storage, neutral и wireProjection не классифицируются эвристикой.
   Полные machine/audit cards и `ParamSpec.consumer_value_error` сохраняются.
2. `sourceWireUnits` находится в динамической части после родителей. В нём только
   declared numeric wire paths, реально присутствующие в raw parent packets;
   полный namespace и `[]` сохраняются. Значения `0`, `null`, raw floats, tooltips
   и generated graphs не переписываются. Это фильтрация справочника имеющихся
   фактов; все Author capabilities остаются в статическом каталоге. Standalone
   guide и Gameplay Repair по-прежнему могут получать полный registry glossary.
3. Provider-only schema projection исключает `description` и `x-infini-*`
   annotations. Local schema и cards сохраняют эти сведения. Bounds, enums,
   required, references в local validator и все JSON assertions сохраняются.
   Поля JSON с такими именами внутри `properties`, `const` или `enum` не удаляются.
4. Required-only conditional с обязательным конечным selector объединяет enum
   значения с одинаковым required set. У spawn event десять branches становятся
   двумя, у pull три — двумя. Periodic по-прежнему требует non-null periodTicks;
   остальные events сохраняют optional semantics. Непроверенные композиции
   по-прежнему отклоняются provider projection.

Классификация — **Normalization формы prompt/provider transport с точной
эквивалентностью**, без преобразования authoritative gameplay/wire. Compiler,
receipts, C# DTO/executors, IDs, budgets и numeric domains не изменяются.

## Nullable inverse

Annotation removal и conditional grouping выполняются внутри общего
`author_item_contract._provider_strict_projection`, который также использует
nullable inverse. Отдельная очистка только outgoing JSON была бы ошибкой:
inverse больше не распознал бы собственный optional wrapper и оставил `null`.
Gameplay Author/Repair явно включают удаление annotations; Visual сохраняет
свою прежнюю schema guidance. Inverse принимает два точных supported projections
(с annotations и без них), но не wrapper с изменёнными validation constraints.
Literal discriminators сохраняют выбор ветви даже при неверном соседнем
параметре. Singleton union также проверяет имеющийся literal discriminator;
неизвестная fn не выбирается лишь потому, что ответ является object.

`json_object/off` не превращает explicit null в omission. Array null, unknown
keys, required null и чужая schema wrapper не удаляются.

## Offline production measurements

База: код `62762da` (исполняемые файлы идентичны `ff039fc`). Настройки фиксированы:
Default prompt style, route label `gpt-6.1`, reasoning off с существующим minimum
medium для Author, max tokens 9000. Родители — имеющиеся synthetic fixtures,
включая результаты реального compiler и generated-parent summary.

Размеры — символы полного сериализованного HTTP body Chat Completions, включая
system/user/schema и transport fields. Используется production serializer
`json.dumps(ensure_ascii=False)` с его обычными пробелами.

| Рецепт | User до → после | HTTP json_schema до → после |
|---|---:|---:|
| Workbench + Blade fixture | 118 120 → 101 513 | 277 538 → 171 467 |
| Generated workbench_blade + Blade | 121 639 → 105 763 | 281 489 → 176 243 |
| Generated held_and_deployed + equipment_tool_combat | 125 145 → 109 758 | 285 427 → 180 720 |

Compact provider schema: **138 811 → 54 537** символов. Первый полный strict
request уменьшается на **106 071 символ / 38,22%**. Размер немного отличается
от исследовательского прототипа: production packet также явно объясняет ссылки
на numeric profiles и уточняет `on_use` emitting source.

Общий provider projection применяется и к Repair schemas: для приведённого
missing-useStyle Repair полный strict HTTP уменьшается 192 873 → 105 126. Scope
grammar и удаление повторного Author context из Format Repair — отдельный PR.

Воспроизведение из корня:

```bash
PYTHONPATH=LocalGenerator python tools/measure_llm_request_sizes.py --out request-sizes.json
PYTHONPATH=LocalGenerator python tools/measure_llm_request_sizes.py --repo /path/to/base-checkout --out base-request-sizes.json
```

Скрипт блокирует network/LLM calls и измеряет также Responses/Codex adapters.
Он фиксирует SHA256 исходных owners, settings и происхождение fixtures. Он не
измеряет billed tokens, latency, cache hit rate или качество ответов модели.

## Проверка

`test_author_request_compaction.py` проверяет точное раскрытие каждого numeric
profile, новые незнакомые правила, сохранение JSON literals и полный nullable
round-trip каждого capability witness. Существующие subscription boundary
controls проверяют event/period acceptance, unknown discriminators и invalid
neighbours; source-unit tests проверяют отсутствие преобразования raw facts и
независимость cache prefix от родителей. `on_use.summary` уточнён у registry
owner: emitting item_body отличается от binding action target.

Полный offline suite: **7156 passed**. Все 11 portable gates из `AGENTS.md`
пройдены; generated capability inventory и targeted Repair audit обновлены
каноническими generators. Dependency-free sandbox gate также пройден.

Native build/game/MP smoke и live LLM quality comparison: **notRun**; эта правка
не меняет native execution, а offline serializers не доказывают model quality.
