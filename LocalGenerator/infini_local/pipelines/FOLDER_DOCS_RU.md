# infini_local/pipelines

Pipeline orchestration around combine/authoring/visual generation.

- `combine_pipeline.py` main large combine flow.
- `combine_orchestrator.py` decomposition seam for orchestration.
- `llm_authoring_pipeline.py` LLM authoring/targeted runtime repair entrypoints.
- `repair_orchestrator.py`, `final_normalize.py`, `generation_debug.py` repair/final/debug seams.
- `visual_generation_pipeline.py`, `sprite_processing_pipeline.py`, `image_backend_pipeline.py` visual asset path.
- `parent_context_pipeline.py`, `stat_profile.py`, `category_policy.py`, `pipeline_support.py` context/stats/helpers.

Rule: pipeline output must be explicit data, not prose-driven runtime behavior.
