# tools

Development/agent utilities. None of these files are imported by the game runtime.

- `agentctl.py` — doctor/context/diff-aware verify/task boundary/handoff/snapshot baseline.
- `contract_parity.py`, `mutation_contract_gate.py` — cross-language lifecycle and mutation proof.
- `export_contract_schemas.py`, `config_registry.py` — generated evidence drift checks.
- `semantic_runtime_diff.py`, `runtime_impact_report.py` — gameplay baseline and tooling-isolation proof.
- `replay_generation_case.py` — saved-case audit and strict deterministic replay gate.
- `validate_sandbox.py` — stdlib-only bounded structural gate for ChatGPT/restricted sandboxes; reports degraded coverage honestly and never substitutes for release validation.
- `validate_release.*`, `render_validation_report.py` — unified machine-readable release validation.
