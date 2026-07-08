# infini_local/core

Core contracts and policies.

- `runtime_authoring/` package owns `runtimePlan.engineCalls` validation, repair, semantic lowering, compilation and reports.
- `runtime_authoring/__init__.py` is the explicit public API for runtime authoring.
- `runtime_authoring/common.py` owns shared enum/number normalization and the single `ENGINE_RUNTIME_API_VERSION` source.
- `runtime_authoring/schema.py` owns static runtime authoring vocabulary/catalog/range schema.
- `runtime_authoring/normalize.py` owns engine-call canonicalization and hard world-entity rejection.
- `runtime_authoring/structural.py` owns code-only repair for malformed runtimePlan shapes and call selection helpers.
- `runtime_authoring/semantics.py` owns finite Terraria-family lowering, parent-backed onHit preservation, semantic tags/audio helpers.
- `runtime_authoring/compiler.py` owns explicit runtimePlan → game-facing field compilation.
- `runtime_authoring/reports.py` owns validation, provenance, compiled contract and result wrapper.
- `result_models.py` typed helper results: `RuntimeCompileResult`, `ClampRecord`, `RepairResult`, `BalanceReportModel`.
- `contract_versions.py` provenance/version stamps, not automatic feature implementation.
- `balance_policy.py` / `balance_report.py` code-owned soft balance.
- `vfx_manifest.py` public VFX manifest assembly API.
- `vfx_manifest_config.py` VFX env knobs, JSON library paths and raw recipe/name-bank data.
- `vfx_director_context.py` optional LLM VFX Director context/tag/weak-hint packet helpers.
- `vfx_director_prompt.py` optional LLM VFX Director compact prompt payloads and debug-only name bank.
- `vfx_director_contract.py` optional LLM VFX Director enum/range surface and validation-report primitives.
- `vfx_projectile_profile.py` projectile/source weapon fact extraction for VFX authoring.
- `vfx_recipe_library.py` VFX recipe macro expansion and compact macro cards.
- `vfx_composition.py` public VFX composition API.
- `vfx_composition_primitives.py` deterministic VFX primitives: renderer/channel normalization, slot scoring/arbitration, magnitude/budget and particle address resolution.
- `vfx_composition_parent.py` parent VFX inheritance and generated-parent effect profiling.
- `vfx_runtime_slots.py` slot compilation, baked command tapes, procedural support layers, runtimePlan direct manifest and authored-cue conversion.
- `vfx_lint_timeline.py` debug-only VFX effect-stack summaries, linter helpers and timeline previews.
- `effect_catalog.py`, `runtime_effect_policy.py` VFX/effect/audio contracts.
- `env_utils.py`, `config_bootstrap.py`, `paths.py` env/config/path support.

Risk: many callers still use dictionaries; verify field names and provenance before changing contracts.
