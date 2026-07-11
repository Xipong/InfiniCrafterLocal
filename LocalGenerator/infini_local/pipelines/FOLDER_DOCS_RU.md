# infini_local/pipelines

Pipeline orchestration around combine/authoring/visual generation.

- `combine_pipeline.py` main `/combine` orchestration spine and cache shell; it is not a compatibility/re-export facade.
- `combine_balance.py` family locks, recipe power transfer, vanilla-like balance envelope and stat/size profiles.
- `combine_genome_contract.py` lightweight LLM combat-genome requirement predicates.
- `combine_genome.py` authored attack genome validation/repair and weapon number derivation.
- `combine_validation.py` schema/default repair preserving the old combine_pipeline monkeypatch surface.
- `combine_gameplay.py` attach_gameplay_and_attack runtime/gameplay assembly.
- `result_identity_policy.py` result naming, category sampling/coercion, canonical representation, palette/anchor derivation.
- `equipment_stats.py` accessory/armor stat generation and soft total-stat budget clamps.
- `projectile_affordance.py` projectile visual-family inference and raw parent projectile size affordance/provenance.
- `presentation_sound.py` presentationGenome derivation and exact attack.sound* normalization.
- `result_knowledge_card.py` generated resultCard compact power/category summary after runtime stats.
- `generated_parent_summary.py` owns generated-parent summary/debug shaping shared by server and pipeline owners.
- `item_power_knowledge.py` owns parent item mechanical signals and generated item-knowledge cards; rarity conversion stays in `item_rarity_baseline.py`.
- `item_rarity_baseline.py` vanilla/modded rarity tier baseline used by item knowledge.
- `engine_pressure_metrics.py` technical projectile/dust pressure estimates and engine sanity clamps.
- `pipeline_visual_config.py` owns image backend/sd.cpp/ComfyUI/A1111/sprite env configuration and mutable backend lifecycle state.
- `pipeline_runtime_constants.py` owns pipeline-local palette and prompt contract constants; executor opcodes live in `core/runtime_executor_vocabulary.py`.
- `pipeline_runtime_dumps.py` owns live tModLoader item/projectile dump indexes and lookup helpers.
- `llm_authoring_pipeline.py` owns LLM plan authoring, promise gating and targeted runtime-repair entrypoints; prompt and transport APIs are imported from their concrete owners.
- `llm_transport.py` provider/auth/replay/fallback HTTP transport and common LLM request options.
- `llm_authoring_prompt.py` planner payload, runtime-contract prompt surface, authored-value preservation helpers.
- `final_normalize.py` owns final normalization; `generation_debug.py` is the single owner of last-combine diagnostic state and persistence wiring. Runtime/genome/name repair lives in its concrete owner modules rather than a re-export facade.
- `runtime_presentation_policy.py` projects canonical runtime families into default held visibility, release timing, hand pose and use style; it never repairs family aliases.
- `visual_generation_pipeline.py` owns item visual attachment, item prompt assembly and the visual-director orchestration step; focused prompt/assets/delivery modules are imported directly by their consumers.
- `visual_prompt_contracts.py`, `visual_sprite_generation.py`, `visual_asset_plan.py`, `visual_asset_manifest.py`, `visual_delivery_gate.py`, `visual_soul.py` focused visual prompt/assets/manifest/delivery/soul seams.
- `sprite_contracts.py` cycle-safe sprite role/chroma/contract helpers shared by postprocess.
- `sprite_geometry.py`, `sprite_keyer.py`, `sprite_postprocess.py` focused bbox/keyer/postprocess seams.
- `image_backend_pipeline.py` image backend adapters.
- `parent_context_pipeline.py` parent projectile/profile context public API.
- `parent_context_cards.py` compact raw parent LLM card assembly.
- `stat_profile.py`, `category_policy.py` contain pure debug/summary helpers; executable balance/category constants live in `combine_balance.py` and `core/category_policy.py`. `pipeline_support.py` is retired; import owners directly.

Rule: pipeline output must be explicit data, not prose-driven runtime behavior.
