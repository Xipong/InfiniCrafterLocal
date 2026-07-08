# infini_local/core/runtime_authoring

Canonical runtime authoring package.

- `__init__.py` explicit public API for runtimePlan validation/compile/report callers.
- `common.py` shared enum/number normalization helpers and the single `ENGINE_RUNTIME_API_VERSION` owner.
- `schema.py` movement/effect/onHit/delivery/runtime-family vocabulary, aliases, function catalog and numeric limits.
- `semantics.py` finite semantic/runtime-family lowering and parent-backed hint handling.
- `normalize.py` engine-call canonicalization, world-entity rejection and runtimePlan shape normalization.
- `structural.py` code-only structural repair and call selection helpers.
- `compiler.py` accepted runtimePlan → game-facing attack/gameplay patch compiler.
- `reports.py` quality/validation/provenance reports and typed compile result wrapping.

This package owns executable runtime intent for Python. C# still executes only explicit bounded fields after validation and compile.
