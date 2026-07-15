# infini_local/storage

World recipe storage, trace tools, failure state.

- `world_storage.py` stores each generated recipe as the sole authoritative world-scoped JSON file. Writes use per-file locks, unique atomic sibling temps, and no aggregate `index.json`/`health.json` rewrite.
- `world_recipe_runtime.py` owns the world-scoped recipe serialization/storage API used by HTTP and pipeline boundaries.
- `trace_tools.py` exposes low-level debug trace utilities.
- `trace_runtime.py` wires rolling trace config/files and shared trace/log wrappers.
- `failure_state.py` tracks generation failure state.

Storage/debug data is evidence, not a second authoring layer. Keep world scoping explicit.
