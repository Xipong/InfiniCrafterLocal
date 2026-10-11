# Проверки контрактов и их владельцы

Новый regression сначала относится к **наблюдаемому инварианту**, а не к номеру релиза. Вариант существующего контракта добавляется в named table/corpus, не в отдельный bug-specific файл. Владельцы production-кода — в [карте задач](../AGENT_INDEX_RU.md); правила изменения runtime — в [AGENTS.md](../AGENTS.md).

## Где проверять

Пути семейств ниже относительны [LocalGenerator/tests](../LocalGenerator/tests/).

| Инвариант | Канонический вход / семейство |
|---|---|
| Registry → schema/card → validator → compiler → receipts/wire | [registry vertical](../LocalGenerator/tests/test_registry_vertical_contract.py); [units и percent projection](../LocalGenerator/tests/test_registry_author_units.py) — единый numeric owner; `test_registry_*` отдельно покрывают neutral provenance, receipt identity, wire/cache, Author packet и composition |
| Typed frozen merge, literal JSON members, captured Gameplay/Visual replay | [frozen Repair](../LocalGenerator/tests/test_repair_frozen_contract.py) |
| Exact permissions → filter → apply → validator | [Gameplay Repair](../LocalGenerator/tests/test_repair_gameplay_contract.py), [VFX Repair](../LocalGenerator/tests/test_repair_vfx_contract.py) |
| Identity/binding/producer transactions и три реальные LLM-стадии | [pipeline Repair](../LocalGenerator/tests/test_pipeline_repair_contract.py), [stage ordering/budgets](../LocalGenerator/tests/test_low_level_three_stage_pipeline.py) |
| Visual metadata и serialized prompt/cache boundary | [presentation](../LocalGenerator/tests/test_visual_presentation_metadata.py), [prompt prefix](../LocalGenerator/tests/test_visual_vfx_prompt_prefix.py) |
| VFX packet/material/frozen/selected PNG producer | `test_vfx_*`; [dependency/delivery](../LocalGenerator/tests/test_vfx_dependency_delivery_contracts.py) |
| Image attempts, adapters, ingredients, pixels/UV | `test_image_*`, [ingredients](../LocalGenerator/tests/test_vfx_ingredient_generation_contracts.py), [sprite render](../LocalGenerator/tests/test_sprite_render_contracts.py) |
| Transfer byte authority и cache/quarantine | [asset transfer/cache](../LocalGenerator/tests/test_asset_transfer_cache_contracts.py) |
| Profile pin, retry/failover, request semantics, HTTP и lifecycle | `test_provider_*`; [Codex subscription](../LocalGenerator/tests/test_codex_subscription_contract.py) отдельно защищает auth/SSE/privacy/no-paid-fallback |
| Placement provenance, maxStack и use-policy | [placement](../LocalGenerator/tests/test_item_placement_contracts.py), [dual-use transactions](../LocalGenerator/tests/test_dual_use_placeable_contract.py) |
| Source-language и структурные межъязыковые ограничения | Существующие [C# gate](../tools/check_csharp_contracts.py), [hygiene gate](../tools/check_project_hygiene.py); их positive/decoy/mutation controls — [source audits](../LocalGenerator/tests/test_source_audit_gates.py) |
| Реальная C#/tML/FNA CPU-семантика | [EngineRuntimeChecks.csproj](../tools/EngineRuntimeChecks.csproj) и зарегистрированные partial checks |

Самостоятельные UI, multiplayer, trace и tooling-контракты сохраняют своих владельцев. Сходство названий не доказывает дублирование.

## Данные и изменение покрытия

1. Используй machine-readable registry и [QA witnesses](../LocalGenerator/infini_local/qa/FOLDER_DOCS_RU.md), не ручную копию каталога. Capability изменяется в своём declaration/vertical slice и generated projections; поиск по множеству family tables — признак дрейфа.
2. Перед удалением сопоставь **assertions и варианты входов** с retained observer/case. Сохрани failure modes, frozen siblings, before/after и call budgets. Callback-таблица старых функций или переименование в `_check_*` не снижает сопровождение.
3. Докажи причинный RED на прежней регрессии/изолированном consumer mutant и GREEN на рабочем runtime. Import/collection error не считается пойманной мутацией. Oracle единиц должен быть независим от проверяемого `to_wire`.
4. Не переписывай captured responses/replay ради GREEN. Объявленный rename/unit transform — узкая тестовая проекция. Отсутствие ≠ null, zero style ≠ отсутствие, bool ≠ int, array ≠ множество.
5. [VFX fixtures](../LocalGenerator/tests/vfx_material_fixtures.py) и [image fixtures](../LocalGenerator/tests/vfx_image_fixtures.py) — общие builders. Два `fixtures/vfx_image_*.json` содержат literal boundary/merge cases, не второй production registry и не автоматически обновляемые snapshots.
6. После переноса проверь imports, selection, обязательные CLI и изоляцию. Удалённый filename не должен остаться исполняемой командой. Считай реальные defs/helpers/принимающие gates и corpus bytes отдельно от pytest items.

## Сокращение независимых матриц (2026-10-11)

От базы `a9237fa` (7 291 collected cases) сокращены **524 реальных pytest cases**: остаётся 6 767. Изменение fixture из PR #51 само по себе количество cases не меняет. Параметры не перенесены в цикл внутри теста, не скрыты markers/skip/CI selection; production-код не меняется.

| Прежнее семейство | Осталось | Что покрывает удалённые повторы |
|---|---:|---|
| `test_renderer_route_admission`: 595 положительных + 27 отрицательных | 149 + 27 | Каждый renderer × допустимый channel, каждый renderer × допустимый lane и каждый channel × lane внутри семейства с одинаковыми допустимыми domains остаются отдельными именованными cases. |
| `test_selected_sample_survives_director_compiler_and_wire`: 84 item samples + projectile Item4 | 6 + 1 | `Item1`, `Item4`, `Item169`, `Coins`, `ResearchComplete`, `Unlock` проверяют default/non-default, numeric endpoints и named selectors; projectile Item4 сохраняет отдельный binding. Полный palette проверяется равенством serialized schema/vocabulary, тестом inventory и `check_vfx_sound_contract` для каждого C# SoundID mapping. |

Основание route-факторизации — независимые ограничения channel/lane в `_director_schema`, `material_slot_clauses` и renderer requirements. `_admitted_route_witnesses` сначала покрывает оба renderer-пересечения, затем добавляет отсутствующие channel/lane pairs внутри каждого domain-семейства. У двух material renderers общий channel-clause; у libraryParticle — отдельные channel/lane enums. Все 27 прежних forbidden-channel/lane случаев остаются без изменений.

Sound admission проверяет membership в полном enum, а normalizer копирует `soundId` без ветвления по имени. Native instrument `Item26` дополнительно проходит пять неизменённых integration cases в `test_vfx_sound_controls`. Null/unknown/foreign payload, explicit silence, legacy absence, frozen Repair и scalar boundaries не сокращаются.

Это **не доказательство всех произвольных трёхфакторных взаимодействий**. Если появится содержательная связь renderer + channel + lane либо отдельная обработка имени soundId, ей нужен новый явный regression. При сокращении проверены причинные consumer mutations: исчезновение обязательного cue channel/lane, ошибочное ограничение допустимой channel/lane пары, подмена Item4 на Item1 и потеря Item2 из полного palette. Рабочие controls GREEN, каждая мутация RED.

Для этих двух семейств сравнён Python execution trace до/после: 707 → 183 cases, те же 1 010 source lines и 1 388 line-transition arcs в `vfx_manifest.py`, `vfx_material_contract.py` и `schema_validation.py`. Это ограниченная проверка текущих исполненных ветвей, не оценка полного покрытия проекта и не замена проверкам поведения.

Подход следует конкретным примерам, а не приписывает upstream универсальный pairwise-алгоритм: [Hermes убирает независимые оси и повторные boundary rows](https://github.com/NousResearch/hermes-agent/commit/fe422a690a2f75342b814a3aa854a6bc4d260718), [Codex оставляет command semantics и один owner rendering layout](https://github.com/openai/codex/commit/e57fc9ea5a7ccdf1d45b5c9d50047ebd8e344b05).

## Запуск и сила доказательства

Из корня репозитория, в окружении с test dependencies:

```bash
PYTHONPATH=LocalGenerator python -m pytest --collect-only -q
PYTHONPATH=LocalGenerator python tools/run_pytest_shards.py --shards 4
python tools/validate_release.py
```

Discovery охватывает `LocalGenerator/tests` **и** `toolbox/tests`. Hosted CI запускает оба roots один раз через canonical shard runner, без отдельного повторного toolbox pytest. [Workflow](../.github/workflows/ci.yml) запускает полные проверки на PR, push в `main` и вручную; branch push не дублирует PR. Отменяются только устаревшие runs того же PR, main/manual runs независимы. Это сокращение повторных CI executions, не semantic test corpus. Runner не пропускает параметры: обычные модули идут пакетами до четырёх файлов с конечным timeout, process-global случаи изолируются. GitNexus/cache metadata в sandbox не копируется. При нехватке зависимостей [validate_sandbox.py](../tools/validate_sandbox.py) даёт только ограниченную structural-проверку.

Штатные gates защищают registry/schema/prompt/C# parity, refs/kinds/inputs/events, receipt paths, bounds, strict unknown-field rejection, non-archetypal witnesses, stage accounting и отсутствие semantic routers. [mutation_contract_gate.py](../tools/mutation_contract_gate.py) проверяет missing executor, duplicate writer, undeclared lowering output, missing DTO field и API-version drift; актуальный roster принадлежит самому gate.

`validate_release.py --skip-build` **не доказывает C# execution**. При доступных .NET/tML/FNA и внешних DLL нужны обычная сборка мода и headless-проект:

```bash
dotnet build tools/EngineRuntimeChecks.csproj -c Release \
  -p:InfiniTmlReferenceDir="<tModLoader lib/net8.0>" \
  -p:InfiniExternalDepsRoot="<ParticleLibrary/Luminance root>"
dotnet tools/bin/Release/net8.0/EngineRuntimeChecks.dll
```

Запускай DLL из корня; reference paths в примере — placeholders. C# отдельно защищает versions, relationships, components/producers, cycles, depth/spawn/rate/lifetime и effect authority. CPU/headless не равно game loop, GPU или сетевому матчу. Missing dependencies и необязательный игровой self-test — `notRun`, не PASS; hosted CI без игровых DLL не заменяет этот уровень. Меньше строк или функций само по себе не доказывает сохранённого покрытия.

## Удаление доказанных дублей (2026-10-11)

Этот небольшой проход переносит практику удаления redundant-neighbour и mock-echo проверок из
[Codex](https://github.com/openai/codex/commit/82461c99903c473d6ba1be0791ae4fdd1b52b9a5) и
[Hermes](https://github.com/NousResearch/hermes-agent/commit/8c0568ee73d0f852fb5020156c79752c937e8ab2).
Одинаковый результат не означает одинаковую точку входа: как в
[предостережении Hermes](https://github.com/NousResearch/hermes-agent/commit/20f4879d302c284faba7118bfd1dd578b9e6c6e8),
самостоятельные entry-path, frozen Repair, security и C# source guards сохранены.

Отдельный diff от `a9237fa729b9a5d60337c43033cb116f2306ee9c`: pytest items **7291 → 7284**;
`test_*` defs **1166 → 1164**; исполняемые `_check_*`/`_contract_check_*` **90 → 88**.
Счёт охватывает оба test roots. Четыре функции удалены, три повторных набора входов больше не создаются;
нет skips, deselection или переноса старых кейсов в цикл/переименованный helper.
Один новый локальный callback в сохранённой WSL-проверке записывает аргументы внешней команды.

| Удалённая проверка / все её assertions | Сохранённый owner и причина |
|---|---|
| `test_registry_author_units.py::test_discrete_units_pin_schema_lattice_and_every_wire_destination` — `zero` для `configure_tool.axePowerTooltipPercent`, `apply_generated_buff_on_use.lifeRegenHpPerSecond`, `apply_generated_buff_on_use.manaRegenBonusPoints` (3 items) | `minimum` в той же функции для каждого из этих трёх параметров. Все `unit`, `value=0`, `accepted=True` буквально совпадали, выполнялся один и тот же код со всеми assertions. Отдельный interior-zero остаётся для подписанных диапазонов; остальные boundaries не изменены. |
| `test_low_level_three_stage_pipeline.py::test_repair_transport_stage_names` (3 items) | `test_single_format_repair_preserves_recoverable_design[author-syntax-only]` проверяет реальный Author caller и sequence `planner, author_repair`; `test_three_stage_wire_and_conditional_repairs[conditional-local-visual-and-vfx-repair]` проверяет реальных Visual/VFX callers, sequence, accounting и бюджеты. Удалена только проверка re-read имени, переданного напрямую `with_llm_stage`. |
| `test_provider_union_proof.py::test_scoped_singleton_does_not_decode_unknown_function_by_object_type` (1 item) | `test_repair_request_compaction.py::test_single_function_schema_never_decodes_an_unknown_function_by_object_type` сохраняет неизвестный `fn` и его `manaCost=None` в настоящей scoped Repair schema; `test_parameter_repair_uses_exact_scoped_schema_and_retains_accepted_omission` проверяет positive known-fn inverse через реальный caller в обоих formats. Удалён искусственный schema-only singleton; оба его assertions имеют владельца. |
| `test_config_registry_diagnostics_contract.py::_contract_check_real_tool_reports_a_named_difference_not_only_stale` | `_contract_check_added_and_removed_fields_are_named` проверяет тот же `_stale_registry_report` и точный `addedFields`, дополнительно removed fields и инструкцию исправления. Удалённый helper, несмотря на имя и docstring, не запускал CLI: записывал/читал собственный JSON и напрямую вызывал тот же function. Обязательный `tools/config_registry.py --check` сохранён. |
| `test_csharp_compile_surface_contract.py::_check_tml_build_helper_converts_wsl_project_for_windows_dotnet` | `_check_tml_build_helper_converts_wsl_external_deps_for_windows_dotnet` вызывает тот же `msbuild_path_value`; production не ветвится по расширению или назначению пути. Оба старых mocks игнорировали всю команду и только возвращали ожидаемый stdout. Сохранённый owner теперь также проверяет единственный вызов `wslpath -w <resolved input>` и subprocess options, поэтому неправильный путь или направление преобразования дают RED. |

Доказательство после удаления: отдельные process-local consumer mutants заменяли каждую из трёх
repair stage labels на `planner`, обходили singleton discriminator, убирали `addedFields`, меняли
`wslpath -w` на `-u` и передавали посторонний путь. Все **7/7** дали причинный RED в перечисленных
retained assertions; collection/import failures не засчитывались. Нормальные owners с тремя
сохранёнными minimum-zero cases проверяются отдельно; production-файлы мутациями не изменяются.
