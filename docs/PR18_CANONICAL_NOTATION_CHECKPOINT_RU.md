# PR18 current canonical notation — исполняемый неполный checkpoint

## Статус

Не release GREEN и не законченная замена всех regression observers. Реальный existing pipeline уже использует единственный `infini.runtime-program.authoring.v5`; новая параллельная API не создана. Wire v3 неизменён. Локальный baseline `0b94d2b524bcd6b0f08783c73f1f6ea4efadfd95` включает accepted main7a6b3b4 и released #12 e31c758, #14 1496a5d, #22 b15baf6. Parent-owned поздние runtime commits не интегрировались вслепую.

## Реализовано

- Flat action/stackCost/contactDamage, branch-fixed constants forbidden in fresh source, unique declared item-body-only reference omission, zero-arg params omission, ordinary calls[]. plannedIntent/concept/report сохранены.
- Один canonical source validator/compiler/Repair и private exact view; malformed rows не sanitizes, semantic diagnostics сохраняют исходные индексы, unresolved body лечится declaration, не synthetic target.
- Technical lowering проверяет typed direct lanes, sorted binding/entity identities, primary, exact body dependencies, placement associations; никаких compactSource receipts. Сохранены wire-only исторические receipt specs.
- Real initial/format/scoped Repair builders; source constructors, DTO/wire readers явно раздельны. Замена подсказок и generated exports/docs.
- RED/GREEN tracer logs 01..12, включая boolean/int receipt mutation, malformed input+frozen effect group, original-index deletion, actual serialized Repair.

## Исполненная проверка

`artifacts/pr18-canonical-tdd/checkpoint-report.json` фиксирует exact pins/hashes/nodeids. Все 99 selected test files исполнены через canonical sandbox runner: четыре shards + только ранее неисполненные batches/isolation. **8190 passed, 15 failed = 8205 collected**; нет повторного зачёта focused subset. `checkpoint-finished-core.log`: 2488 passed (subset). Pyright 0 errors. `gates-checkpoint.json`: 11/11 PASS, включая generated freshness, contract parity, delivery, mutation, C# source scanner, hygiene, prompt usability. Native compilation/game/live/provider/external AI/remote — notRun/forbidden.

Полный current Author пример: `complete-current-author-candidate.json`; реальный compiler output: `complete-current-compiled-wire.json`. Оба прошли canonical admission. Архивные JSON fixtures и saved wire bytes не менялись; только explicit test-local projection.

## Оставшиеся blockers

1. `test_item_effect_groups.py::test_every_existing_item_effect_can_partition_explicit_main_and_alternate_groups[move_player_on_use]`: известный parent/#12 exclusive owner defect; narrow released repair b722c524 не дублировать здесь.
2. 9 nodeids `test_pipeline_repair_contract.py`: foreign-wrapper deletion Repair не закрыт; часть старых adversarial constructors/requirements всё ещё требуют explicit item-body target или старые passive fields. Multi-body/declaration ownership, foreign-owner tests и same-path scope требуют завершённого source-native порта, а не suppress/xfail. Exact nodeids в report.
3. `test_repair_frozen_contract.py::test_captured_gameplay_repair_replay[ropebound_spear|jester_bow|silt_extractinator]`: historical diagnostic oracle требует точной test-local projection (`shape_const` → forbidden-property diagnostics; permission paths), captured bytes не менять.
4. `test_weapon_ammo.py::test_legacy_complete_wire_recovers_only_declared_successor_notation_and_neutrals`: frozen full-byte oracle не завершён для changed registry counts + новой source provenance; старые hashes не заменены.
5. `test_weapon_ammo.py::test_hold_only_spawner_is_not_a_native_ammo_consumer_and_repair_uses_existing_entity`: legacy-style hold mutation сохраняет ныне forbidden fields, и создание active lane не закрывает source shape errors; current constructor/Repair observer надо завершить.
6. Parent accepted #11 chance lane, #20 runtime, #27 typed malformed guard, native harness fixes и final #12 требуют отдельной parent integration. Здесь group selector сохраняется, но поздняя независимая chance lane ещё не baseline и её parity не заявляется.

## Scope

C# feature diff отсутствует; native source baseline совпадает с approved b15baf6. Нет native conflicts, но native compile не выполнялся. Не менялись чужие worktrees, remote, saved fixtures, Visual/VFX exports. Это checkpoint implementation для review/продолжения, не утверждение полного acceptance.
