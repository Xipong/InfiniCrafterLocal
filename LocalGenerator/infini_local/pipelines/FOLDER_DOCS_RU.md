# infini_local/pipelines

Pipeline orchestration around combine/authoring/visual generation.

- `combine_pipeline.py` main /combine orchestration facade and cache/failure shell.
- `combine_balance.py` family locks, recipe power transfer, vanilla-like balance envelope and stat/size profiles.
- `combine_genome_contract.py` lightweight LLM combat-genome requirement predicates.
- `combine_genome.py` authored attack genome validation/repair and weapon number derivation.
- `combine_validation.py` schema/default repair preserving the old combine_pipeline monkeypatch surface.
- `combine_gameplay.py` attach_gameplay_and_attack runtime/gameplay assembly.
- `result_identity_policy.py` result naming, category sampling/coercion, canonical representation, palette/anchor derivation.
- `equipment_stats.py` accessory/armor stat generation and soft total-stat budget clamps.
- `projectile_affordance.py` projectile visual-family inference and raw parent projectile size affordance/provenance.
- `presentation_sound.py` presentationGenome/soundProfile derivation from explicit attack genome fields.
- `result_knowledge_card.py` generated resultCard compact power/category summary after runtime stats.
- `generated_parent_summary.py` generated-parent summary/debug shaping shared by server and pipeline support.
- `item_power_knowledge.py` parent item signal and generated item-knowledge card facade/helpers.
- `item_rarity_baseline.py` vanilla/modded rarity tier baseline used by item knowledge.
- `engine_pressure_metrics.py` technical projectile/dust pressure estimates and engine sanity clamps.
- `pipeline_visual_config.py` image backend/sd.cpp/ComfyUI/A1111/sprite env configuration re-exported by `pipeline_support.py`.
- `pipeline_runtime_constants.py` palette/runtime/prompt enum constants re-exported by `pipeline_support.py`.
- `pipeline_runtime_dumps.py` live tModLoader item/projectile dump indexes and lookup helpers re-exported by `pipeline_support.py`.
- `combine_orchestrator.py` decomposition seam for orchestration.
- `llm_authoring_pipeline.py` LLM authoring/targeted runtime repair facade and entrypoints.
- `llm_transport.py` provider/auth/replay/fallback HTTP transport and common LLM request options.
- `llm_authoring_prompt.py` planner payload, runtime-contract prompt surface, authored-value preservation helpers.
- `repair_orchestrator.py`, `final_normalize.py`, `generation_debug.py` repair/final/debug seams.
- `visual_generation_pipeline.py` visual facade/orchestration for visual asset path.
- `visual_prompt_contracts.py`, `visual_sprite_generation.py`, `visual_asset_plan.py`, `visual_asset_manifest.py`, `visual_delivery_gate.py`, `visual_soul.py` focused visual prompt/assets/manifest/delivery/soul seams.
- `sprite_processing_pipeline.py` public sprite processing API over geometry/keyer/postprocess modules.
- `sprite_contracts.py` cycle-safe sprite role/chroma/contract helpers shared by postprocess.
- `sprite_geometry.py`, `sprite_keyer.py`, `sprite_postprocess.py` focused bbox/keyer/postprocess seams.
- `image_backend_pipeline.py` image backend adapters.
- `parent_context_pipeline.py` parent projectile/profile context public API.
- `parent_context_cards.py` compact raw parent LLM card assembly.
- `stat_profile.py`, `category_policy.py`, `pipeline_support.py` context/stats/helpers.

Rule: pipeline output must be explicit data, not prose-driven runtime behavior.
