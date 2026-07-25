# InfiniCrafterLocal 0.4.241 — test-suite и tooling audit

## Выполнено успешно

| gate | результат |
|---|---|
| `PYTHONPATH=LocalGenerator python -m pytest -q` | **85 passed** |
| `python -m compileall -q LocalGenerator/infini_local tools LocalGenerator/tests` | passed |
| `tools/audit_capability_library.py` | **100/100**, 52/52 Python→C# vertical slices, 185 typed params, 143/143 numeric bounded |
| `tools/audit_terraria_standardization.py --check` | **87/87** |
| `tools/generate_lowery.py --check` | `lowery.md` совпадает с canonical mapping owners |
| `tools/audit_targeted_repair.py --check` | 36/36 Repair policies; frozen merge; blocker-local catalog |
| `tools/export_contract_schemas.py --check` | 10 generated v5 contracts current |
| `tools/generate_low_level_runtime_docs.py --check` | capability inventory/audit/lowering docs current |
| `tools/check_delivery_contract.py` | **8/8** fixtures passed |
| `tools/contract_parity.py` | passed, 52/52 capabilities |
| `tools/mutation_contract_gate.py` | **5/5 mutations caught** |
| `tools/check_planner_prompt_usability.py` | **52/52** visible; обычный probe 70 729 / 96 000, rich fixture 82 532 / 96 000 |
| `tools/semantic_runtime_diff.py` | **8/8** non-archetypal fixtures passed |
| `tools/runtime_impact_report.py` | passed |
| `tools/check_csharp_contracts.py` | passed |
| C# Debug + Release | **0 warnings, 0 errors** |
| Ruff / Pyright | passed; **0 errors, 0 warnings** |
| `tools/check_project_hygiene.py` | passed |
| `tools/config_registry.py --check` | passed |
| `tools/validate_sandbox.py` | portable-static `ok=true`, syntax/JSON 169/22 |

## Standardization coverage

Постоянные gates проверяют:

1. один canonical Author token на одно точное tModLoader-значение;
2. отсутствие gameplay aliases и удалённого effect/weapon archetype catalog;
3. строгий built-in либо `ModName/ClassName` DamageClass без fallback;
4. разделение `Item.ammo`, `Item.useAmmo`, consumable и potion semantics;
5. Terraria defaults для projectile water/network/immunity полей;
6. loaded-content bounds для rarity/buff/tile/wall IDs;
7. Author↔C# range parity, включая `Item.axe`;
8. сохранение собственного proxy runtime только там, где статическая content registration неприменима.

## Mutation/locality coverage

Gate краснеет при:

1. новой capability без C# executor;
2. втором writer существующего component slot;
3. technical lowerer с недекларированным output;
4. новом final-wire field без C# DTO vertical slice;
5. drift C# runtime API version.

Все пять искусственных мутаций пойманы.

## Stage accounting и Repair

- happy path: Gameplay=1, Visual=1, VFX=1, repairs=0;
- invalid stage вызывает только свой conditional Repair;
- 36/36 semantic validator codes имеют явную policy;
- frozen старые значения восстанавливаются, полезные missing/broken leaves сохраняются;
- полный Author catalog не отправляется в Repair: dossier 11 133–29 831 символов в проверенных blocker-сценариях против 70 528 символов обычного полного Author payload;
- предыдущие валидные стадии без необходимости не перезапускаются.

## NotRun

| gate | причина | команда для полноценной среды |
|---|---|---|
| tModLoader self-test | нет runtime report из реально запущенного tML | запустить tML с `INFINI_AGENT_SELFTEST=1`, затем `python tools/check_tml_selftest_report.py <report>` |
| SP craft + PNG/VFX smoke | Live запуск явно не авторизован | выполнить реальный 3-stage craft и проверить mandatory assets |
| host/client sync smoke | не запускались две tML instances | проверить child/channel/deployed/entity/VFX sync на host/client |
| Calamity loaded-content smoke | Calamity/tML runtime не запускались | собрать и запустить с совместимой 1.4.4 веткой |
| real LLM crafts | Live20 остаётся на явной паузе | запустить normal combine endpoint только после отдельной команды пользователя |

`validate_release.py --skip-build` дал `ok=true`: все deterministic/source checks passed. Отдельные C# Debug/Release builds также прошли 0w/0e. `releaseReady=false` означает только отсутствие реального tModLoader self-test/игрового smoke; эти границы не маскируются под deterministic успех.
