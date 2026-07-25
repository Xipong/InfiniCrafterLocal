# LocalGenerator v0.4.241 — low-level runtime authoring

Active Gameplay contract: `runtimeProgram` v5. Author receives the complete compact catalog once and directly composes entities, bindings, calls and event links. Deterministic code validates and compiles explicit choices only.

Current grammar:

- 7 entity kinds;
- 4 inputs;
- 5 binding actions;
- 10 events;
- 52 public capabilities;
- 12 entities / 8 bindings / 48 calls / child depth 3.

Baseline calls: Gameplay Author, Visual Director, VFX Director. Each Repair is conditional on the rejection of its own stage.

Run:

```bash
PYTHONPATH=. python -m pytest -q
PYTHONPATH=. python ../tools/audit_capability_library.py
PYTHONPATH=. python ../tools/check_delivery_contract.py
```

Old family macros, semantic root lowering, runtime archetype profiles and compatibility cache import are not part of the active package.
