# infini_local/qa

Gameplay/runtime proof helpers for PATCH 0.4.239.

- `golden_runtime_cases.py` owns deterministic authored `runtimePlan` golden cases and expected compiler/gameplay envelopes.
- `runtime_proof.py` builds:
  - compiler/provenance reports via `compile_runtime_plan_to_genome_patch`;
  - gameplay-seam reports via `validate_and_repair` + `apply_item_knowledge` + `attach_gameplay_and_attack`.
- `csharp_delivery_contract.py` derives the strict recursive `GeneratedItemData` JSON graph from current C# DTO source and validates already-sanitized delivery payloads, including nested unknown fields and JSON kinds.
- `__init__.py` exposes the small public proof API for tests and tools.

This package does not call LLMs, HTTP, image backends, or Terraria. It proves the Python runtime authoring → compiled fields → GeneratedItemData gameplay/attack seam. Full visual generation and in-game smoke checks remain separate layers.
