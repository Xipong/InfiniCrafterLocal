# LocalGenerator 0.4.241 — project map

```text
infini_local/core/runtime_authoring/
  capability_registry.py  immutable grammar and capabilities
  program_schema.py       strict Author + Repair patch schema
  repair_scope.py         exact frozen field scope + blocker/dependency closure
  validator.py            references/conflicts/events/budgets
  compiler.py             exact wire projection + receipts
  technical_lowering.py   lossless adapters only
  wire_validator.py       strict final DTO

infini_local/pipelines/
  llm_authoring_prompt.py  one complete Gameplay prompt
  llm_authoring_pipeline.py Gameplay Author + conditional Repair
  combine_pipeline.py      three-stage orchestration
  visual_*                 entity-role Visual contract and assets

infini_local/core/vfx_manifest.py exact entity/event VFX Director
infini_local/qa/                   fixtures/witnesses/machine audit
infini_local/storage/              v5 world recipes and traces
tests/                             contracts and infrastructure tests
```

Public source imports should use `infini_local.core.runtime_authoring`, not deleted legacy compiler/root-lowering modules.
