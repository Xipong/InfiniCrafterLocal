# v0.4.237 — RuntimeArchetypeSpec + runtimeContract refactor

v0.4.237 adds a typed data-authored runtime language around the existing `runtimePlan.engineCalls` path:

- `runtimeArchetype` describes the supported behavior family (`custom_executor`, `boomerang`, `yoyo`, `flail`, `whip`, `held_swing`, `held_thrust`, or preserved unsupported intent such as `channel_beam`, `delayed_starfall`, `secondary_attack`).
- `runtimeContract` describes control feel, phase/state/sync intent, and `mechanicClaims` truth backing.
- Python normalizes/clamps known archetype knobs, preserves unknown knobs inertly, compiles only supported families to finite `AttackSpec` fields, and emits `debug.runtimePromiseTruth` / `unsupportedPromises`.
- C# has data-only DTO support for the new fields and still executes only explicit finite runtime fields.
- `apply_on_hit_effect(onHit=starfall)` is a supported finite child-projectile primitive; `runtimeArchetype.family=delayed_starfall` remains preserved/future unless backed by that explicit engineCall.
- Old generated JSON without these fields remains compatible.

Existing v0.4.234 visual/secondary cleanup behavior is intentionally preserved: conflict swing-secondary salvage, held-light anti-fake-alt-use, fit-only sprite refit, trace/warning cleanup, and capability ontology remain in place.

Main invariant: LLM author’ит fantasy/resultKind/runtimePlan/numbers/visual intent + optional runtimeArchetype/runtimeContract; Python validates and soft-balances; C# applies only hard safety/runtime primitives.

See `../docs/runtime_archetype_contract.md` for schema examples and migration notes.

MP asset sync note: Steam не проксирует HTTP; для LAN/Radmin/hosted MP нужен доступный HTTP asset endpoint или корректный base URL. Клиенту не нужно руками открывать `/get_asset`: мод сам тянет assets через настроенный endpoint.
