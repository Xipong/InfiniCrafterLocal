# infini_local/core/runtime_authoring

Canonical runtime authoring package.

- `__init__.py` narrow public API for runtimePlan validation/compile/report callers; schema constants and private helpers are not exported.
- `vocabulary.py` owns bounded authoring-only aliases for movement/effect/onHit/delivery; `runtimeFamily` remains strict in `core/runtime_family_policy.py`.
- `common.py` shared enum/number normalization helpers and the single `ENGINE_RUNTIME_API_VERSION` owner.
- `schema.py` engine function catalog, Terraria-family groups, runtime affordances and numeric limits; audio controls are accepted on primary attack calls without repeating the catalog in every function card.
- `semantics.py` finite semantic/runtime-family lowering and parent-backed hint handling.
- `normalize.py` engine-call canonicalization, world-entity rejection and runtimePlan shape normalization.
- `structural.py` code-only structural repair and call selection helpers.
- `compiler.py` accepted runtimePlan → game-facing attack/gameplay patch compiler; delegates lifecycle-specific work instead of accumulating it inline.
- `secondary.py` sole compile owner for bounded secondary projectile triggers (`on_hit`/`on_expire`).
- `reports.py` quality/validation/provenance reports and typed compile result wrapping.

This package owns executable runtime intent for Python. C# still executes only explicit bounded fields after validation and compile.

Sound ids are owned by `../sound_catalog.py`: exact acoustic-role vocabulary, compact LLM card, mechanic-only fallbacks and no weapon-name/prose routing.
