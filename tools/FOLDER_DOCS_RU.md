# tools

Development/agent utilities. None of these files are imported by the game runtime.

- `EngineRuntimeChecks.GeneratedItemPrefix.cs` — native instance-prefix lifecycle checks: real `Item.Prefix`/`CanUseItem`, repeated projection and clone, placement/ammo independence, actual SaveData + native ItemIO prefix importer, compact forwarding and later full-definition hydration. Shared-proxy content registration, complete ItemIO.Load/Receive routing, sockets and gameplay loop are separate acceptance boundaries.
- `EngineRuntimeChecks.RootCombat.cs` — native ItemCheck/shoot query contexts and counts, active primary/alternate roots, applied prefixes, actual hook order, terminal hold and restoration of the original source Item/crit/armor. Uses scoped native hooks and intercepted spawn boundaries; not a gameplay/MP smoke.
- `EngineRuntimeChecks.Tooltips.cs` — real `ModifyTooltips`/`TooltipLine`/Language consumers with typed CPU fixtures and existing EN/RU HJSON: exact executable bindings, separate stack costs, base mana, bounded effects, UI number culture and non-mutation. Does not prove native inventory/GPU UI or player-dependent mana discounts.

All three partial check files are registered in `EngineRuntimeChecks.cs` and `EngineRuntimeChecks.csproj`. Registration is not an execution result; compilation and native acceptance remain separate integration gates.

- `agentctl.py` — doctor/context/diff-aware verify/task boundary/handoff/snapshot baseline.
- `contract_parity.py`, `check_delivery_contract.py`, `mutation_contract_gate.py` — cross-language lifecycle, strict delivered-JSON DTO parity, and mutation proof.
- `export_contract_schemas.py`, `config_registry.py` — generated evidence drift checks.
- `audit_targeted_repair.py` — измеряет размер Repair dossier, blocker subsets и совпадение model-facing cards с deterministic scope.
- `audit_terraria_standardization.py`, `generate_lowery.py` — проверяют canonical tModLoader mappings, отсутствие gameplay aliases и актуальность корневого `lowery.md`.
- `semantic_runtime_diff.py`, `runtime_impact_report.py` — gameplay baseline and tooling-isolation proof.
- `replay_generation_case.py` — saved-case audit and strict deterministic replay gate.
- `validate_sandbox.py` — stdlib-only bounded structural gate for ChatGPT/restricted sandboxes; reports degraded coverage honestly and never substitutes for release validation.
- `validate_release.*`, `render_validation_report.py` — unified machine-readable release validation.
