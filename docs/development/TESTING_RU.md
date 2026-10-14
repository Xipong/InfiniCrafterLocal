# Проверки контрактов и их владельцы

Новый regression сначала относится к **наблюдаемому инварианту**, а не к номеру релиза. Вариант существующего контракта добавляется в named table/corpus, не в отдельный bug-specific файл. Владельцы production-кода — в [карте задач](OWNERS_RU.md); правила изменения runtime — в [AGENTS.md](../../AGENTS.md).

## Где проверять

Пути семейств ниже относительны [LocalGenerator/tests](../../LocalGenerator/tests).

| Инвариант | Канонический вход / семейство |
|---|---|
| Registry → schema/card → validator → compiler → receipts/wire | [registry vertical](../../LocalGenerator/tests/test_registry_vertical_contract.py); [units и percent projection](../../LocalGenerator/tests/test_registry_author_units.py) — единый numeric owner; `test_registry_*` отдельно покрывают neutral provenance, receipt identity, wire/cache, Author packet и composition |
| Typed frozen merge, literal JSON members, captured Gameplay/Visual replay | [frozen Repair](../../LocalGenerator/tests/test_repair_frozen_contract.py) |
| Exact permissions → filter → apply → validator | [Gameplay Repair](../../LocalGenerator/tests/test_repair_gameplay_contract.py), [VFX Repair](../../LocalGenerator/tests/test_repair_vfx_contract.py) |
| Identity/binding/producer transactions и три реальные LLM-стадии | [pipeline Repair](../../LocalGenerator/tests/test_pipeline_repair_contract.py), [stage ordering/budgets](../../LocalGenerator/tests/test_low_level_three_stage_pipeline.py) |
| Visual metadata и serialized prompt/cache boundary | [presentation](../../LocalGenerator/tests/test_visual_presentation_metadata.py), [prompt prefix](../../LocalGenerator/tests/test_visual_vfx_prompt_prefix.py) |
| Explicit hand movement → frozen Repair → Visual grip → delivered DTO | `test_front_hand_movement.py`, `test_front_hand_visual_contract.py`, `test_front_hand_wire_integration.py`; native `EngineRuntimeChecks.FrontHand.cs` использует fresh compiler fixture `tools/fixtures/front-hand-compiled.json`, не исторический игровой предмет |
| VFX packet/material/frozen/selected PNG producer | `test_vfx_*`; [dependency/delivery](../../LocalGenerator/tests/test_vfx_dependency_delivery_contracts.py) |
| Image attempts, adapters, ingredients, pixels/UV | `test_image_*`, [ingredients](../../LocalGenerator/tests/test_vfx_ingredient_generation_contracts.py), [sprite render](../../LocalGenerator/tests/test_sprite_render_contracts.py) |
| Transfer byte authority и cache/quarantine | [asset transfer/cache](../../LocalGenerator/tests/test_asset_transfer_cache_contracts.py) |
| Complete builder-owned instruction/data segments, changed-tail identity и role-preserving provider wire | [craft instruction segments](../../LocalGenerator/tests/test_craft_instruction_segments.py); `prompt_packet_helpers.py` — только derived dossier observer в semantic tests |
| Profile pin, retry/failover, request semantics, HTTP и lifecycle | `test_provider_*`; [activity/real-route faults](../../LocalGenerator/tests/test_provider_activity_contract.py) — current stages, semaphore/rate waits, cache I/O recovery, actionable failures и sibling identity; [Codex subscription](../../LocalGenerator/tests/test_codex_subscription_contract.py) отдельно защищает auth/SSE/privacy/no-paid-fallback |
| Placement provenance, maxStack и use-policy | [placement](../../LocalGenerator/tests/test_item_placement_contracts.py), [dual-use transactions](../../LocalGenerator/tests/test_dual_use_placeable_contract.py) |
| Source-language policies и runner registration | Существующие [C# gate](../../tools/check_csharp_contracts.py), [hygiene gate](../../tools/check_project_hygiene.py); их synthetic positive/negative controls — [source audits](../../LocalGenerator/tests/test_source_audit_gates.py) |
| Studio HTTP/session и native controller: все поля, сохранение и unknown keys | [bridge/controller](../../LocalGenerator/tests/test_web_studio.py) |
| Browser draft: поздняя LAN-правка и polling до подтверждения преобразования | [delayed-response integration](../../LocalGenerator/tests/test_web_studio_browser.py) — настоящий Tk/controller + Chromium, не mock API |
| Реальная C#/tML/FNA CPU-семантика | [EngineRuntimeChecks.csproj](../../tools/EngineRuntimeChecks.csproj) и зарегистрированные partial checks |

Самостоятельные UI, multiplayer, trace и tooling-контракты сохраняют своих владельцев. Сходство названий не доказывает дублирование.

## Практический бюджет

- Проверяй вход → результат через настоящего владельца: compiler/validator/Repair, serialized provider request, asset bytes или native C# entry point. Обычный и невалидный пример важнее десятков одинаковых комбинаций.
- Не фиксируй private method names, порядок строк, количество guards или точные куски реализации. При внутреннем refactor поведение должно остаться GREEN без восстановления старых wrappers.
- Source tests нужны лишь для настоящих source-language policies (warning suppression, запрещённые gameplay routers, authored-field ownership) и регистрации runner. `test_source_audit_gates.py` проверяет lint API на маленьких synthetic inputs; scanner не доказывает runtime correctness.
- Frozen Repair, authority/security, literal wire identity и material claims остаются поведенческими контрактами. Native suite проверяет крафт, отмену, возврат/capacity, world persistence, asset lifecycle и representative invalid inputs через actual consumers. Exhaustive DTO/shape products, частные UI/storage observers и creative pixel/curve микропроверки сознательно убраны; чтение `.cs` в Python не заменяет runtime behavior.
- Удаляй низкоценные повторные проверки, не прячь их за skip/xfail, общим циклом или переименованным helper. Не обещай сохранение всех прежних assertions: узкое честное покрытие лучше дублирующего scanner framework.
- Для tests-only cleanup достаточно одного affected Python run; неизменённые native результаты можно повторно использовать. Не запускай full suite и mutation campaign по кругу. Full CI принадлежит интегрированному commit.

## Запуск

Из корня с test dependencies:

```bash
PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/<affected_module>.py
python tools/check_csharp_contracts.py
```

Для native Studio-проверок нужен Python с Tcl/Tk и доступным дисплеем (в Linux — Xvfb). Для browser integration дополнительно нужны `playwright` и установленный Chromium (`python -m playwright install chromium`). Без этих optional prerequisites соответствующая проверка явно пропускается; HTTP/security-контракт остаётся headless. Запуск:

```bash
PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_web_studio.py LocalGenerator/tests/test_web_studio_browser.py
```

Полная Python приёмка: `PYTHONPATH=LocalGenerator python tools/run_pytest_shards.py --shards 4` (оба test roots). Native:

```bash
dotnet build tools/EngineRuntimeChecks.csproj -c Release \
  -p:InfiniTmlReferenceDir="<tModLoader lib/net8.0>" \
  -p:InfiniExternalDepsRoot="<ParticleLibrary/Luminance root>"
dotnet tools/bin/Release/net8.0/EngineRuntimeChecks.dll --check-filter "<named behavior>"
```

Filter должен выбрать хотя бы одну проверку; compile и registration smoke не равны execution. Без .NET/tML/FNA/native DLL — `notRun`, не PASS. CPU/headless не доказывает GPU/game-loop или сетевой матч. Не меняй production, operator config, captured fixtures или generated artifacts ради tests-only GREEN.
