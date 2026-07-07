# infini_local/storage

World recipe storage, trace tools, failure state.

- `world_storage.py` stores/generated recipe data by world/context.
- `trace_tools.py` exposes debug trace utilities.
- `failure_state.py` tracks generation failure state.

Storage/debug data is evidence, not a second authoring layer. Keep world scoping explicit.
