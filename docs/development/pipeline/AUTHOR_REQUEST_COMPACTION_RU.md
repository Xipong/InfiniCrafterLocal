# Сокращение production-запроса Gameplay Author

## Текущая граница

Packet строится из canonical owners без повторного копирования numeric definitions и не меняет authored gameplay:

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

## Offline production capture

```bash
PYTHONPATH=LocalGenerator python tools/diagnostics/measure_llm_request_sizes.py --out request-sizes.json
```

Скрипт блокирует network/LLM calls и захватывает actual production builders/Chat/Responses/Codex serializers. Он фиксирует SHA256 owners, settings и synthetic-fixture provenance. Размеры wire JSON — не billed tokens, latency, cache hit или качество ответа; optional baseline comparison выполняется через `--repo /path/to/base-checkout` без compatibility grammar в runtime.

## Проверка

`test_author_request_compaction.py` проверяет точное раскрытие каждого numeric
profile, новые незнакомые правила, сохранение JSON literals и полный nullable
round-trip каждого capability witness. Существующие subscription boundary
controls проверяют event/period acceptance, unknown discriminators и invalid
neighbours; source-unit tests проверяют отсутствие преобразования raw facts и
независимость cache prefix от родителей. `on_use.summary` уточнён у registry
owner: emitting item_body отличается от binding action target.

Актуальные команды — [TESTING](../TESTING_RU.md). Offline serializers не доказывают model quality, native game-loop/GPU или MP; эти уровни проверяются отдельно.
