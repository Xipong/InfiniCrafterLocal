# InfiniCrafterLocal 0.4.241 — test-suite и tooling audit

## Выполнено успешно

| gate | результат |
|---|---|
| `PYTHONPATH=LocalGenerator python -m pytest -q` | **77 passed**, 6 multiprocessing deprecation warnings |
| `python -m compileall -q LocalGenerator/infini_local tools` | passed |
| `tools/audit_capability_library.py` | **100/100**, 52/52 Python→C# vertical slices, 185 typed params, 143/143 numeric bounded |
| `tools/audit_terraria_standardization.py --check` | **87/87** |
| `tools/generate_lowery.py --check` | `lowery.md` совпадает с canonical mapping owners |
| `tools/audit_targeted_repair.py --check` | 33/33 Repair policies; frozen merge; blocker-local catalog |
| `tools/export_contract_schemas.py --check` | 10 generated v5 contracts current |
| `tools/generate_low_level_runtime_docs.py --check` | capability inventory/audit/lowering docs current |
| `tools/check_delivery_contract.py` | passed |
| `tools/contract_parity.py` | passed |
| `tools/mutation_contract_gate.py` | **4/4 mutations caught** |
| `tools/check_planner_prompt_usability.py` | **52/52** visible, 70 685 / 80 000 chars, headroom 9 315 |
| `tools/semantic_runtime_diff.py` | **8/8** non-archetypal fixtures passed |
| `tools/runtime_impact_report.py` | passed |
| `tools/check_csharp_contracts.py` | passed |
| `tools/check_project_hygiene.py` | passed |
| `tools/config_registry.py --check` | passed |
| `tools/validate_sandbox.py` | portable-static `ok=true`, syntax/JSON 167/18 |
| packaged ZIP re-unpack | manifest 368/368 before and after tests; 77 pytest and key gates repeated from extracted copy |

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
4. новом final-wire field без C# DTO vertical slice.

Все четыре искусственные мутации пойманы.

## Stage accounting и Repair

- happy path: Gameplay=1, Visual=1, VFX=1, repairs=0;
- invalid stage вызывает только свой conditional Repair;
- 33/33 semantic validator codes имеют явную policy;
- frozen старые значения восстанавливаются, полезные missing/broken leaves сохраняются;
- полный Author catalog не отправляется в Repair: dossier 9 401–29 506 символов в проверенных blocker-сценариях против 70 484 символов полного Author payload;
- предыдущие валидные стадии без необходимости не перезапускаются.

## NotRun

| gate | причина | команда для полноценной среды |
|---|---|---|
| Ruff | executable/module отсутствует | `ruff check LocalGenerator/infini_local tools` |
| Pyright | executable/module отсутствует | `pyright` |
| Hypothesis property suite / full release runner | module отсутствует; `validate_release.py` возвращает unavailable до запуска full stack | `python -m pip install -r LocalGenerator/requirements-dev.txt && python tools/validate_release.py` |
| C# / tModLoader build | `dotnet`, tML install и external mod DLL отсутствуют | `python tools/try_tml_build_check.py --project <InfiniCrafterLocal.csproj> --external-deps-root <deps>` |
| tModLoader self-test | нет собранного мода и runtime report | запустить tML с `INFINI_AGENT_SELFTEST=1`, затем `python tools/check_tml_selftest_report.py <report>` |
| SP craft + PNG/VFX smoke | нет tML/runtime/provider | выполнить реальный 3-stage craft и проверить mandatory assets |
| host/client sync smoke | нет двух tML instances | проверить child/channel/deployed/entity sync на host/client |
| Calamity loaded-content smoke | Calamity/tML отсутствуют | собрать и запустить с совместимой 1.4.4 веткой |
| real LLM crafts | provider credentials/endpoints не настроены | запустить normal combine endpoint с Gameplay/Visual/VFX providers |

`releaseReady=false`: все доступные portable/source/contract gates зелёные, но реальная C# сборка и игровой smoke не заявляются.
