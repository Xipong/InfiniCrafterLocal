# infini_local/core

Core contracts and policies.

- `runtime_authoring.py` validates/compiles `runtimePlan.engineCalls` into explicit game-facing fields.
- `result_models.py` typed helper results: `RuntimeCompileResult`, `ClampRecord`, `RepairResult`, `BalanceReportModel`.
- `contract_versions.py` provenance/version stamps, not automatic feature implementation.
- `balance_policy.py` / `balance_report.py` code-owned soft balance.
- `vfx_manifest.py`, `effect_catalog.py`, `runtime_effect_policy.py` VFX/effect/audio contracts.
- `env_utils.py`, `config_bootstrap.py`, `paths.py` env/config/path support.

Risk: many callers still use dictionaries; verify field names and provenance before changing contracts.
