# infini_local/storage

World recipe storage, trace tools, failure state.

- `world_storage.py` stores/generated recipe data by world/context.
- `world_recipe_runtime.py` exposes world-scoped recipe storage wrappers used by server/pipeline facades.
- `trace_tools.py` exposes low-level debug trace utilities.
- `trace_runtime.py` wires rolling trace config/files and shared trace/log wrappers.
- `failure_state.py` tracks generation failure state.

Storage/debug data is evidence, not a second authoring layer. Keep world scoping explicit.
