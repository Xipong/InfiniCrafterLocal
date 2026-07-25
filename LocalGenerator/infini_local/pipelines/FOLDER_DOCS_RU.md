# pipelines

Active baseline:

1. `llm_authoring_pipeline.try_llm_plan` — one Gameplay Author call.
2. entity-based Visual Director/generation.
3. `core.vfx_manifest` — one VFX Director call.

Conditional repairs belong only to the stage whose deterministic validator rejected output. A repair must not restart already accepted previous stages without necessity.

`category` is UI/result metadata only. Parent prose and visual concepts never route C# gameplay.
