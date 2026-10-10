# PR18 — единственная Author v5 и текущая композиция #27/#25/#22/#12

## Текущий checkpoint

Единственный fresh Gameplay Author — `infini.runtime-program.authoring.v5`:
private exact view, flat bindings, независимые input/action/stackCost/contactDamage
и optional own-stack chance. Saved wire `infini.runtime-program.wire.v3` и его
исторические receipt domains сохранены; fresh v4 admission, публичного importer,
semantic router и выбора gameplay defaults нет.

Предыдущий принятый checkpoint `88610055a85832bd1719045fb610bd5dcaa147ee`
(tree `b9228b7f42f96db31912ca325ed15c19e0c85990`) имеет отдельную проверку
8693/103 files и 14 parent acceptance cases. Это **историческая** full-suite
проверка, не full-suite verdict новой композиции. Текущий checkpoint объединяет
его с `1eb5854622c7d331c4598557ba7a8c1008dac956`; bounded final-tree evidence,
source freeze и release manifest находятся в
`artifacts/pr-ideology-review-2026-10-10/pr18/current27-composition/` вне checkout.
Текущая bounded проверка: 693 PASS через canonical sandbox (11 files),
110 PASS registry consumers, 48 PASS combined modifier/historical curve,
14 PASS unchanged parent acceptance; 16/16 gates PASS. Ранние неуспешные
попытки сохранены отдельно. Это source-checkpoint GREEN, не native/game
release verdict. Parent выполняет один общий all-PR full run после финальной alias integration.

Исполняемый combined observer в `test_projectile_target_emission_contract.py`
проводит real serialized Author → v5 prepare/compiler → strict wire + source
receipt audit → hostile exact-leaf Repair в `json_object` и `json_schema`.
Одновременно сохранены sampled child velocity, hit-target geometry, physical
emission, live-parent combat, item aliases, named effects и stack chance.

Сильный полный historical wire observer и отдельный delivery observer имеют
разные имена: оба действительно собираются pytest. Original placed fixture SHA256
`41c670ba3fd12a44a2436bc6226bf815628e3d4c64d04f4efd3cc586b628a43a`
не переписан candidate output. Все восемь original hashes независимо подтверждены
исполнением pinned `cec64b6` Python sources. `c3d0d3d` — уже следующий archive
inventory (другой hash), а не источник исходного `41c670…` oracle. Test-local
reverse projections проверяют только точные neutral/provenance/registry deltas;
исходный свежий compile сначала проходит source-backed audit.

Python/docs/generated reconciliation не редактирует native sources и не запускает
C# compilation/game/live/provider/external AI. Native 184-input parity проверяется
с parent-owned #27/#25 run; remote approval/publication принадлежит parent.

## Исторический исходный неполный checkpoint (не текущий verdict)

Следующие секции сохраняют первоначальные RED/blocker receipts и путь ремонта.
Их 15 failures и формулировки «не release GREEN» относятся к исходному checkpoint,
а не отменяют позднее принятое состояние или текущие bounded GREEN receipts.

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


## Интеграция accepted main `88dbddb17f60f9ddc044c8cefb4f5c3d4efd0472`

Новый source checkpoint сохраняет единственную Author v5, private exact view и wire v3.
Python/docs/generated merge согласован с independent own-stack chance, named groups,
optional component presence proof и типизированными параметрами. C# автоматически
слит parent-ом; этот source repair не редактировал C# и не запускал native/compiler/game.

Все девять прежних pipeline Repair failures воспроизведены (`integration-red.log`) и
закрыты canonical permission/deletion/created-declaration owners либо source-native
adversarial constructors. Исторические diagnostic oracles явно проецируют placement
`shape_const` в exact forbidden-property diagnostic; captured JSON/hashes не менялись.
Full-byte ammo oracle сохраняет прежние SHA после проверяемой test-local проекции
child/beam/targeting, source provenance и конечных registry deltas.

Два дополнительно найденных parent-ом механизма имеют RED/GREEN observers в
`test_canonical_author_notation.py`: omission-only passive input получает только input
scope без synthetic action/target; no-op Repair сохраняет malformed whole array.
Оба actual serialized provider formats проходят parse→scope→filter→merge→compile;
hostile frozen named-group sibling игнорируется с audit.

До final source freeze: `focused-final.log` 394 PASS; `parent-blockers-green.log` 26 PASS;
`accepted-features-green.log` 723 PASS (пересекающиеся subsets, не суммировать).
`gates-integration.json`: 11 gates PASS + pyright 0 errors. Полный canonical four-shard
acceptance привязывается к следующему frozen merge head отдельным artifact report;
эта запись сама по себе не заменяет полный acceptance verdict.
