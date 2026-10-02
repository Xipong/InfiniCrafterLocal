# Прямое построение Author — исторический request-builder замер

Текущие construction/diagnostic constraints принадлежат [Author contract](LOW_LEVEL_RUNTIME_AUTHORING_RU.md#construction). Эта запись хранит измерение отдельного изменения, не current prompt size, latency или acceptance guarantee.

<a id="change"></a>
## Что было изменено

Baseline `1358fa02c45c2d0ea22fdbe1dec39153d30d4fc0`. Убраны `selfCheck/structureCheck/preEmissionCheck`, повторный primary self-check и процедуры «проверь/отклони draft/перед ответом». Правила перенесены к `requiredJsonShape`/fieldGuide/entity/input/action/event/capability owners, не удалены. `concept`, обе diagnostic groups с verdict/result/intentionality/refs и Repair execution truth сохранены. Schemas, validator/compiler/runtime/defaults и Repair algorithm этим prompt-only изменением не менялись.

<a id="measurement"></a>
## Замер настоящего builder

Offline `build_initial_author_request` в свежих до/после процессах: `A={"name":"Workbench"}`, `B={"name":"Sword"}`, `ca=A`, `cb=B`, `key="workbench+sword"`, `model_name="gemini-2.5-flash"`; оба режима через `llm_transport.LLM_RESPONSE_FORMAT_MODE`.

| Представление | До, символов | После, символов | Сокращение |
|---|---:|---:|---:|
| System | 3 457 | 634 | 81,66% |
| User compact JSON | 90 641 | 84 528 | 6,74% |
| System + user | 94 098 | 85 162 | 8 936 / 9,50% |
| Builder JSON, json_object | 102 028 | 93 040 | 8,81% |
| Builder JSON, json_schema | 206 048 | 197 060 | 4,36% |

Serialization: `ensure_ascii=False`, `separators=(",", ":")`, без internal `_...`; escaping messages и actual response_format учтены. Это **не provider-adapted HTTP body**. Неизменный schema вклад уменьшает относительную экономию schema-mode.

Catalog 68 429 → 75 446 symbols: перенос local construction facts, не рост capabilities. Все прежние capability/entity/input/action/event fields/limits/graph facts сравнивались по значениям; только presentation notes добавлены. Parents/recipeKey/balanceCorridor совпали. Local `BAAI/bge-small-en-v1.5` WordPiece proxy: 32 605 → 30 594 (−6,17%) для system+user; **не Gemini tokenizer и не billing tokens**.

Provider schema: 103 939 symbols, SHA-256 `554cdf976220fe6fa285ad1851006d4de23afe862bbbf747c35bd354ee3cb75f`; оба response_format byte-identical, 52 capabilities/229 params в том снимке. Cache prefix получил diagnosticReport вместо selfCheck, dynamic inputs остались после static boundary.

<a id="evidence"></a>
## Проверки и предел

Тогда: Python/toolbox 872 passed, Ruff/Pyright passed; serialized packet tests проверяли отсутствие procedural loop, locality, concept/diagnostic shape и cache boundary. Generated Repair audit штатно обновлён после изменения prompt размера. Registry/schema/validator/compiler/C# sources не менялись; schema identity проверена отдельно от green tests.

Новые live/noreasoning генерации, game/MP и latency не запускались. Сокращение serialized текста не доказывает повышение first-Author success rate; актуальные offline commands — [test owners](TEST_CONTRACT_OWNERS_RU.md).
