# infini_local/core

Core contracts and policies.

- `runtime_executor_vocabulary.py` owns canonical movement/effect/onHit names and numeric executor opcodes.
- `runtime_family_policy.py` owns strict canonical runtime families and a single capability/presentation profile table; no aliases.
- `runtime_authoring/` package owns `runtimePlan.engineCalls` validation, repair, semantic lowering, compilation and reports.
- `runtime_authoring/vocabulary.py` owns the exact current movement/effect/onHit/delivery vocabulary; removed spellings are rejected instead of being repaired downstream.
- `runtime_authoring/__init__.py` is the narrow public compile/validate/report API; production imports concrete owners directly.
- `runtime_authoring/common.py` owns shared enum/number normalization and the single `ENGINE_RUNTIME_API_VERSION` source.
- `runtime_authoring/schema.py` owns the engine-call catalog, Terraria family grouping, affordances and numeric ranges; canonical executor vocabulary is imported from its owner.
- `runtime_authoring/normalize.py` owns engine-call canonicalization and hard world-entity rejection.
- `runtime_authoring/structural.py` owns code-only repair for malformed runtimePlan shapes and call selection helpers.
- `runtime_authoring/semantics.py` owns finite Terraria-family lowering, parent-backed onHit preservation, semantic tags/audio helpers.
- `runtime_authoring/compiler.py` owns explicit runtimePlan → game-facing field compilation.
- `runtime_authoring/reports.py` owns validation, provenance, compiled contract and result wrapper.
- `strict_json.py` owns finite, duplicate-free machine JSON parsing/serialization for HTTP, durable caches, and gates.
- `json_debug.py` owns bounded, always-parseable diagnostic JSON and circular/non-finite value sanitization.
- `result_models.py` typed helper results: `RuntimeCompileResult`, `ClampRecord`, `RepairResult`, `BalanceReportModel`.
- `contract_versions.py` provenance/version stamps, not automatic feature implementation.
- `balance_mode.py` owns exact `report/safety/normalize` policy; `balance_policy.py` owns reference/envelope numbers; `balance_report.py` only reports authored/final/advice/clamps.
- `llm_stage_messages.py` owns Attributed Chat History: finite ChatCompletion speaker names, canonical Planner `messages[]`, and Agent Handoff provenance (`source/cause/next speaker`).
- `vfx_manifest.py` public VFX manifest assembly API.
- `vfx_manifest_config.py` VFX env knobs, JSON library paths and raw recipe/name-bank data.
- `vfx_director_context.py` optional LLM VFX Director context/tag/weak-hint packet helpers.
- `vfx_director_prompt.py` optional LLM VFX Director compact prompt payloads and debug-only name bank.
- `vfx_director_contract.py` optional LLM VFX Director enum/range surface and validation-report primitives.
- `vfx_projectile_profile.py` projectile/source weapon fact extraction for VFX authoring.
- `vfx_recipe_library.py` VFX recipe macro expansion and compact macro cards.
- `vfx_composition_primitives.py` deterministic VFX primitives: renderer/channel normalization, slot scoring/arbitration, magnitude/budget and particle address resolution.
- `vfx_composition_parent.py` parent VFX inheritance and generated-parent effect profiling.
- `vfx_runtime_slots.py` slot compilation, baked command tapes, procedural support layers, runtimePlan direct manifest and authored-cue conversion.
- `vfx_lint_timeline.py` debug-only VFX effect-stack summaries, linter helpers and timeline previews.
- `effect_catalog.py` owns the finite VFX/effect/audio vocabulary; executable gameplay remains in runtime authoring contracts.
- `env_utils.py`, `config_bootstrap.py`, `paths.py` env/config/path support.

Risk: many callers still use dictionaries; verify field names and provenance before changing contracts.

- `runtime_secondary_policy.py` owns exact secondary lifecycle vocabulary (`on_hit`, `on_expire`).
- `runtime_overhead_barrage_policy.py` owns bounded overhead-barrage defaults/limits; only exact `overhead_barrage` is accepted.
- Do not merge these into a generic trigger/action/state engine; see `../../../docs/RUNTIME_VERTICAL_SLICES_RU.md`.
