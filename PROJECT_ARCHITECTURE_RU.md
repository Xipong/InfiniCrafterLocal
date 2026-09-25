# InfiniCrafterLocal v0.4.241 — целевая архитектура

## Суть

Модель не выбирает «меч/лук/посох/турель». Gameplay Author за один LLM-вызов получает parent facts, broad balance corridor, строгую schema и весь конечный каталог реально исполняемых capabilities. Он возвращает полноценную программу из entities, input bindings, calls и event links.

Deterministic code только:

- проверяет shape, types, ranges, references, target kinds, dependencies, exclusivity, cycles и budgets;
- выполняет технический lowering без дизайнерских решений;
- проецирует typed wire DTO;
- исполняет точные opcodes/capabilities в C# с fail-closed поведением.

Canonical equipment/event primitive registry дополнительно порождает C# numeric bounds, Author schemas, prompt cards, wire/receipt expectations и [`docs/PRIMITIVE_PARITY_RU.md`](docs/PRIMITIVE_PARITY_RU.md). Классоспецифичные equipped damage fields представлены одним `add_equipment_damage_bonus(phase, damageClass, bonusPercent)`; compiler переводит точный selector и процент в сохранённый C# DTO без выбора класса/фазы за Author. Исторические DTO clamps сохранены отдельной registry-owned технической таблицей, включая generic damage и generic armor set damage. AST loss audit проверяет C# DTO/executor surface против модели и фиксирует причины скрытых legacy-полей; прежний audit только известных wire-путей не доказывал полноту C#.

## Три baseline-стадии

1. **Gameplay Author** — авторит `runtimeProgram`.
2. **Visual Director** — оформляет inventory item и ровно те runtime entities, которые приняты gameplay validator.
3. **VFX Director** — привязывает finite effects к существующим `entityId + event`.

Gameplay/Visual/VFX Repair вызываются только после фактического отказа валидатора своей стадии. Успешный путь: `1 + 1 + 1`, repairs `0`. Repair не пересобирает полный stage output: deterministic scope передаёт модели invalid fragments, exact missing dependencies, минимальный blocker capability subset и валидный read-only context. Существующие корректные значения frozen; из полного возвращённого узла применяются только exact broken/missing leaves. Scope-escape игнорируется с audit, а не отменяет полезное исправление.

## Контракты

- runtime API: `infini.runtime-program.v5`;
- Author schema: `infini.runtime-program.authoring.v4`;
- wire schema: `infini.runtime-program.wire.v3`;
- Visual: entity-based visual kit/asset manifest;
- VFX: exact runtime entity/event slots.

Старые schema/cache/replay не принимаются и не мигрируются.

## Python source of truth

`LocalGenerator/infini_local/core/runtime_authoring/`:

- `capability_registry.py` — entity/input/action/event/capability grammar;
- `terraria_vocabulary.py` — единственные canonical mappings в stable tModLoader values;
- `program_schema.py` — strict Author/Repair JSON schemas;
- `validator.py` — deterministic semantic validation без design authorship;
- `compiler.py` — exact component projection и receipts;
- `technical_lowering.py` — только declared lossless adapters;
- `wire_validator.py` — strict final-wire rejection неизвестных полей.

Schema, prompt catalog, machine manifest, docs inventory и audit проецируются из registry.

## Multi-dev craft (operational, not Author surface)

`/multidevcraft 2` или `3` сессионно разблокирует два/три независимых station lane с отдельными A/B escrow, request id, task, progress и refund. Lane 1/2/3 жёстко пинятся к `llm_1`/`llm_2`/`llm_3`; pinned lease не делает profile/model fallback. Обычный однооконный craft сохраняет прежний round-robin/failover contract. MP-клиент передаёт только lane + compact parent refs, а host/server валидирует lane unlock, изымает exact station escrow и один коммитит GeneratedItemData. Profile id добавляется только в world recipe cache identity multi-dev lane и не меняет item wire/schema.

## Explicit primary ownership

Author явно задаёт ровно один существующий `runtimeProgram.primaryEntityId`. В Author `calls` и `bindings` нет поля `role`: compiler детерминированно ставит wire `binding.role=primary` только когда exact `binding.usePolicy.action.targetId == primaryEntityId`, иначе `secondary`. `primaryOwner: "item_body" | "projectile"` выводится только из kind выбранной entity. Ни имя, категория, input, capability, урон, ни факт spawn не выбирают primary вместо модели.

`primaryOwner` — executable contract, а не telemetry: C# использует его для item `noMelee`/contact hitbox и разрешает `heldProj`/item-animation ownership только primary projectile. Secondary projectile может быть явно spawned тем же use как дополнительная атака/VFX body, но не отбирает melee/held ownership.

## C# runtime

- `Common/Models/RuntimeProgramSpec.cs` — строгий v5 DTO и normalize/validation;
- `Common/Runtime/RuntimeProgramExecutor.cs` — binding/event execution;
- `Content/Items/GeneratedItem*.cs` — item-body projection и explicit inputs;
- `Content/Projectiles/GeneratedProjectile*.cs` — один bounded low-level entity executor;
- `Common/Models/VfxManifestSpec.cs` и visual runtime — exact entity/event effects.

C# не читает name/tooltip/tags/category для выбора gameplay. Неизвестные version, fields, kinds, opcodes, action/input pairs и references отклоняются.

## Result identity: категория и имя принадлежат Author

Категория (`category`) и имя результата — authored значения от Gameplay Author, как и вся механика. Deterministic code не сэмплирует, не «давит сигналами» и не подменяет их:

- `normalize_category` только сверяет authored категорию с конечным словарём `ALLOWED_CATEGORIES` (fallback `generic`);
- `bad_result_name` в `final_normalize` — финальный sanity gate: невалидное имя Author'а = отказ крафта с возвратом ингредиентов, а не шаблонная подмена;
- hint-теги (`category_policy.py`) — read-only debug/validator-контекст родителей; при runtime authoring они не впрыскиваются в authored result tags;
- исторический category sampling/coercion (`category_policy()`, `coerce_category_by_policy`, lane-сэмплинг) и детерминированный генератор имён удалены как скрытый семантический маршрутизатор. Не восстанавливать.

## Bounded composition

Текущая программа ограничена: 12 entities, 8 bindings, 48 calls, child depth 3, bounded event spawn/rate/lifetime. На entity допускается один movement slot и один controller slot. Это конечный безопасный component runtime, не ECS/VM общего назначения.

## Assets

Visual Director выбирает `baked_sprite`, `reuse_item_icon`, `runtime_geometry` или `no_asset` только там, где режим разрешён entity-role. Отсутствующий обязательный PNG — validator failure/Visual Repair. Placeholder не считается игровым результатом.

## Доказательства

- 52 capability vertical witnesses;
- восемь non-archetypal acceptance fixtures и frozen v5 seed replay corpus;
- registry/schema/prompt/compiler/C# owner parity;
- range parity Python↔C#;
- technical lowering mutation gates;
- stage accounting tests;
- full Python suite и C# static scanner.

Игровой build/smoke считается доказанным только после фактического запуска в подходящей tModLoader-среде.
