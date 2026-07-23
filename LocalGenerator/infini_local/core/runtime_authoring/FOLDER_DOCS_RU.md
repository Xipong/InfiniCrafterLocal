# infini_local/core/runtime_authoring

Canonical runtime authoring package.

- `__init__.py` narrow public API for runtimePlan validation/compile/report callers; schema constants and private helpers are not exported.
- `vocabulary.py` owns bounded authoring-only aliases for movement/effect/onHit/delivery; `runtimeFamily` remains strict in `core/runtime_family_policy.py`.
- `common.py` shared enum/number normalization helpers and the single `ENGINE_RUNTIME_API_VERSION` owner.
- `schema.py` engine function catalog, Terraria-family groups, runtime affordances and numeric limits; audio controls are accepted on primary attack calls without repeating the catalog in every function card.
- `semantics.py` finite semantic/runtime-family lowering and parent-backed hint handling.
- `normalize.py` engine-call canonicalization, world-entity rejection and runtimePlan shape normalization.
- `structural.py` code-only structural repair and call selection helpers.
- `compiler.py` orchestrates accepted runtimePlan → game-facing patch lowering; final DTO composition is not owned here.
- `equipment.py` is the single accessory/armor stat and set-bonus lowerer with one shared clamp table.
- `secondary.py` is the single child-budget/secondary lifecycle owner for primary on-hit children and explicit `on_hit`/`on_expire` secondary calls.
- `result_identity.py` is the only runtime result-kind/category/ammo identity projection.
- `final_projection.py` owns final `gameplay/attack/accessory/armor/runtimeContract` sections, compile cache and final-wire receipts.
- `reports.py` owns ordered quality/validation/provenance reports and typed compile result wrapping; it does not compose final DTO sections.

This package owns executable runtime intent for Python. C# still executes only explicit bounded fields after validation and compile.

Sound ids are owned by `../sound_catalog.py`: exact acoustic-role vocabulary, compact LLM card, mechanic-only fallbacks and no weapon-name/prose routing.
