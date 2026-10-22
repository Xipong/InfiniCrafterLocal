# Behavioral-test audit — 2026-10-22

Baseline: `57c58d50504a7c69712e5843fa392b9a39800537` (main). Independent
of the unmerged parallel-image PR #137; no production changes from it are included.

## Scope and interpretation

Baseline collection finds **5,879 Python cases in 181 modules**, plus **118 C#
harness source files / 367 registered native check groups** and one Node frontend
suite. Counts are not interchangeable: native groups contain multiple assertions
and Python parametrization expands functions. This is a whole-suite inventory and
risk screen plus focused semantic audits, **not a claim that every assertion was
individually reviewed or every environment was executed**.

Every Python module was AST-screened for file reads, sleeps/browser delays and
index assertions. These are navigation signals, not errors: fixture/data reads,
controlled clocks, pump-loop polling, wire coordinates and meaningful dependency
order must remain. Auditors then followed actual owners in runtime/repair,
provider/asset transfer, UI, and native placed-VFX families.

## Decisions and evidence

| Area | Change / invariant kept |
|---|---|
| Structured parameter projection | Exact duplicate-sensitive source/destination/value records, in both registry declaration orders. Missing, duplicate and wrong values/provenance still fail. |
| Repair scope | Complete permission rows and paths compared independently of traversal order, with reordered execution. Duplicate or wider permissions still fail; exact frozen output and wire validation remain. |
| Rate deadline | Existing controlled clock replaces a 330ms scheduler-sensitive bound; both pacing and 429 blocking still forbid physical attempts after expiry and drain waiters. Real HTTP deadline integration remains. |
| Asset transfer | Require all workers finish and join, zero active work and exact delivery multiplicity, in addition to maximum concurrency. Previously a stuck worker could escape the assertion. |
| UI callbacks | Held-I/O events prove callback returns before background work completes; no 200ms machine-speed requirement. Release/teardown remains bounded. |
| Placed VFX | Remove duplicated private C# text/order/count snapshots for deduplication, admission capacity, once-per-tick work and retirement. Existing native consumers verify these outputs, liveness/linear work and unchanged identity. Two nested native scenarios are now directly registered/check-filterable, not located by Python string splitting. |
| Mana tooltip | Preserve both locale formats; actual rendered sign remains the existing native VFUI14 test rather than an exact implementation-line assertion. |

Native correspondence: `PlacedVfxRegistrationAndViewportRegressions` covers 600
distant sources followed by a nearby delivery, repeated-source deduplication,
linear liveness visits, stale binding replacement, reentry, opt-out and unchanged
wire. `PlacedVfxTwoInstancesGateAndGenerationDraw` covers same-tick duplicate
prevention. `PlacedVfxInactiveLedgerBroadPhaseRetainsRetirement` covers offscreen
retirement/no resurrection/material ownership. Registration checks and their
existing missing/duplicate/commented/renamed controls remain unchanged.

## Deliberately retained / next targeted investigations

- Frozen documents, original malformed-row indices, retry chains, semaphore
  enter/exit order, image retry budgets and literal wire/provenance remain strict.
- PR #137 owns parallel image delivery assertions and settings count changes;
  touching those here would mix an unmerged production contract into this PR.
- Real HTTP trickle deadline wall-clock integration remains intentionally strict;
  controlled policy-clock checks complement but do not replace real socket bounds.
- Some native source assertions (authored motion/size terms, exact selector/light
  filters and local placement feedback guards) remain: deleting them before
  equivalent focused native negative controls exist would silently lose checks.
- Browser delayed-response tests retain explicit orchestration delays; replace
  those only with a verified request/ack rendezvous in a browser-capable run.
- Provider startup contention has a sleep inside a lock-protected health probe;
  a naive barrier replacement would deadlock. Keep it until an external boundary
  can establish contention without demanding multiple lock holders.

No blanket list-to-set rewrite, production change, retry masking, skip/xfail,
new global test framework or copied Hermes runner is introduced. The companion
`LocalGenerator/tests/AGENTS.md` records the transferable test-writing policy.

## Reproduce and read the inventory

`PYTHONPATH=LocalGenerator python -m pytest --collect-only -q` produces the case
counts. Final acceptance uses `python tools/run_pytest_shards.py --shards 4` and
existing CI native/static gates. Check execution results are recorded in the PR,
not inferred from inventory. `read`, `wait`, `index` below are AST signal counts
in the baseline (including legitimate data reads and fake sleeps).

| Baseline module | Collected cases | Screen signals |
|---|---:|---|
| `LocalGenerator/tests/test_alpha_launchers.py` | 2 | read:2 |
| `LocalGenerator/tests/test_asset_transfer_cache_contracts.py` | 81 | read:16, wait:1 |
| `LocalGenerator/tests/test_asset_transport_linked_source.py` | 1 | — |
| `LocalGenerator/tests/test_author_advisory_contract.py` | 10 | — |
| `LocalGenerator/tests/test_author_concept_bounds.py` | 7 | — |
| `LocalGenerator/tests/test_author_event_domains.py` | 68 | read:2 |
| `LocalGenerator/tests/test_author_item_aliases.py` | 64 | — |
| `LocalGenerator/tests/test_author_payload_headroom.py` | 4 | — |
| `LocalGenerator/tests/test_author_projectile_aliases.py` | 129 | read:3 |
| `LocalGenerator/tests/test_author_prompt_cache.py` | 14 | — |
| `LocalGenerator/tests/test_author_prompt_clarity.py` | 32 | — |
| `LocalGenerator/tests/test_author_prompt_consistency.py` | 7 | — |
| `LocalGenerator/tests/test_author_prose_owners.py` | 9 | — |
| `LocalGenerator/tests/test_author_request_compaction.py` | 19 | — |
| `LocalGenerator/tests/test_author_world_unit_projection.py` | 40 | read:3 |
| `LocalGenerator/tests/test_binding_fixed_literals.py` | 120 | — |
| `LocalGenerator/tests/test_binding_stack_chance.py` | 38 | — |
| `LocalGenerator/tests/test_canonical_author_notation.py` | 115 | — |
| `LocalGenerator/tests/test_capability_declaration_ownership.py` | 77 | — |
| `LocalGenerator/tests/test_channel_beam_sustain_contract.py` | 46 | — |
| `LocalGenerator/tests/test_ci_tml_build_hardening_contract.py` | 1 | read:1 |
| `LocalGenerator/tests/test_code_health.py` | 12 | read:1 |
| `LocalGenerator/tests/test_codex_gui_catalog.py` | 5 | — |
| `LocalGenerator/tests/test_codex_settings.py` | 4 | — |
| `LocalGenerator/tests/test_codex_static_instruction_prefix.py` | 86 | — |
| `LocalGenerator/tests/test_codex_subscription_contract.py` | 65 | read:1, wait:1 |
| `LocalGenerator/tests/test_codex_trace_a6.py` | 8 | read:4 |
| `LocalGenerator/tests/test_codex_trace_boundaries.py` | 16 | read:13 |
| `LocalGenerator/tests/test_codex_transport_trace.py` | 57 | read:9 |
| `LocalGenerator/tests/test_config_registry_diagnostics_contract.py` | 1 | — |
| `LocalGenerator/tests/test_console_event_echo_contract.py` | 1 | read:3 |
| `LocalGenerator/tests/test_contract_checks_infrastructure.py` | 4 | read:1 |
| `LocalGenerator/tests/test_craft_instruction_segments.py` | 20 | — |
| `LocalGenerator/tests/test_csharp_compile_surface_contract.py` | 23 | read:2 |
| `LocalGenerator/tests/test_current_stage_packets.py` | 29 | — |
| `LocalGenerator/tests/test_deliberate_projectile_motion.py` | 4 | — |
| `LocalGenerator/tests/test_dependency_runtime_floor.py` | 1 | read:1 |
| `LocalGenerator/tests/test_director_example_neutrality.py` | 6 | — |
| `LocalGenerator/tests/test_director_schema_cache_extraction.py` | 49 | — |
| `LocalGenerator/tests/test_documentation_layout.py` | 3 | — |
| `LocalGenerator/tests/test_documentation_site.py` | 18 | read:4 |
| `LocalGenerator/tests/test_docx_image_readiness.py` | 32 | read:5 |
| `LocalGenerator/tests/test_dual_use_placeable_contract.py` | 8 | — |
| `LocalGenerator/tests/test_early_result_name_contract.py` | 10 | — |
| `LocalGenerator/tests/test_env_file_codec.py` | 46 | read:8 |
| `LocalGenerator/tests/test_environment_access_contract.py` | 1 | — |
| `LocalGenerator/tests/test_equipment_image_prompt_facts.py` | 19 | — |
| `LocalGenerator/tests/test_equipment_native_utilities.py` | 11 | read:1 |
| `LocalGenerator/tests/test_equipment_presentation_assets.py` | 1 | — |
| `LocalGenerator/tests/test_flux_hybrid_profile_contract.py` | 1 | — |
| `LocalGenerator/tests/test_format_repair_packet_scope.py` | 8 | — |
| `LocalGenerator/tests/test_front_hand_movement.py` | 113 | — |
| `LocalGenerator/tests/test_front_hand_repair_integration.py` | 45 | index:1 |
| `LocalGenerator/tests/test_front_hand_visual_contract.py` | 31 | — |
| `LocalGenerator/tests/test_front_hand_wire_integration.py` | 16 | — |
| `LocalGenerator/tests/test_full_logging_contract.py` | 43 | read:9 |
| `LocalGenerator/tests/test_fusion_prompt_freedom.py` | 12 | — |
| `LocalGenerator/tests/test_gameplay_repair_readonly_context.py` | 31 | — |
| `LocalGenerator/tests/test_generated_buff_exhaustion.py` | 76 | — |
| `LocalGenerator/tests/test_generated_parent_exact_context.py` | 22 | — |
| `LocalGenerator/tests/test_generation_budgets.py` | 25 | — |
| `LocalGenerator/tests/test_generator_bootstrap.py` | 6 | read:3 |
| `LocalGenerator/tests/test_hit_target_spawn.py` | 61 | — |
| `LocalGenerator/tests/test_hitbox_curve_contract.py` | 47 | — |
| `LocalGenerator/tests/test_image_adapter_contracts.py` | 33 | read:3 |
| `LocalGenerator/tests/test_image_attempt_contracts.py` | 77 | read:20 |
| `LocalGenerator/tests/test_image_display_budget.py` | 16 | read:4 |
| `LocalGenerator/tests/test_image_transport_join.py` | 13 | read:8 |
| `LocalGenerator/tests/test_input_conditions_and_equipment_reactions.py` | 8 | — |
| `LocalGenerator/tests/test_inventory_seed_collection.py` | 36 | read:2 |
| `LocalGenerator/tests/test_item_effect_groups.py` | 77 | — |
| `LocalGenerator/tests/test_item_event_and_equipped_topology.py` | 16 | — |
| `LocalGenerator/tests/test_item_placement_contracts.py` | 14 | — |
| `LocalGenerator/tests/test_item_use_style_prompt.py` | 7 | — |
| `LocalGenerator/tests/test_json_input_marker_contract.py` | 74 | — |
| `LocalGenerator/tests/test_live20_no_image_harness.py` | 46 | read:17 |
| `LocalGenerator/tests/test_llm_auth_diagnostics_contract.py` | 2 | — |
| `LocalGenerator/tests/test_low_level_three_stage_pipeline.py` | 45 | — |
| `LocalGenerator/tests/test_luna_prompt_clarity.py` | 7 | — |
| `LocalGenerator/tests/test_model_facing_topology_prompt.py` | 3 | — |
| `LocalGenerator/tests/test_mp_craft_state_simulator.py` | 1 | — |
| `LocalGenerator/tests/test_multidev_craft_contract.py` | 3 | — |
| `LocalGenerator/tests/test_openrouter_provider_settings.py` | 8 | index:1, read:2 |
| `LocalGenerator/tests/test_parent_ammo_information.py` | 12 | — |
| `LocalGenerator/tests/test_parent_crit_source.py` | 21 | — |
| `LocalGenerator/tests/test_parent_semantics_audit.py` | 1 | — |
| `LocalGenerator/tests/test_parent_tile_state_facts.py` | 5 | — |
| `LocalGenerator/tests/test_pipeline_repair_contract.py` | 50 | — |
| `LocalGenerator/tests/test_placed_alpha_pivot.py` | 27 | read:2 |
| `LocalGenerator/tests/test_placed_body_capability.py` | 60 | read:5 |
| `LocalGenerator/tests/test_placed_light_capability.py` | 28 | — |
| `LocalGenerator/tests/test_placed_vfx_capability.py` | 21 | — |
| `LocalGenerator/tests/test_placed_vfx_review_regressions.py` | 9 | index:5, read:13 |
| `LocalGenerator/tests/test_plan_report_diagnostics.py` | 9 | — |
| `LocalGenerator/tests/test_played_mechanical_contracts.py` | 29 | read:1 |
| `LocalGenerator/tests/test_played_presentation_contracts.py` | 20 | read:3 |
| `LocalGenerator/tests/test_played_secondary_fixtures.py` | 1 | read:1 |
| `LocalGenerator/tests/test_project_hygiene_metadata.py` | 2 | — |
| `LocalGenerator/tests/test_projectile_charge_orbit_bounce.py` | 33 | — |
| `LocalGenerator/tests/test_projectile_concurrency_contract.py` | 44 | — |
| `LocalGenerator/tests/test_projectile_modifiers_contract.py` | 41 | — |
| `LocalGenerator/tests/test_projectile_target_emission_contract.py` | 77 | — |
| `LocalGenerator/tests/test_provider_activity_contract.py` | 34 | read:4 |
| `LocalGenerator/tests/test_provider_http_contract.py` | 89 | read:4 |
| `LocalGenerator/tests/test_provider_request_contract.py` | 70 | — |
| `LocalGenerator/tests/test_provider_runtime_contract.py` | 18 | wait:1 |
| `LocalGenerator/tests/test_provider_transport_contract.py` | 56 | wait:1 |
| `LocalGenerator/tests/test_provider_union_proof.py` | 33 | — |
| `LocalGenerator/tests/test_pytest_runner_selection.py` | 82 | index:1, read:9 |
| `LocalGenerator/tests/test_python_package_integrity.py` | 1 | — |
| `LocalGenerator/tests/test_reactive_generated_buffs.py` | 16 | — |
| `LocalGenerator/tests/test_realization_report_bounds.py` | 14 | read:1 |
| `LocalGenerator/tests/test_recipe_singleflight.py` | 4 | — |
| `LocalGenerator/tests/test_recommended_defaults.py` | 17 | read:20 |
| `LocalGenerator/tests/test_referenced_entity_requirements.py` | 19 | — |
| `LocalGenerator/tests/test_registry_author_packet.py` | 31 | — |
| `LocalGenerator/tests/test_registry_author_units.py` | 181 | read:3 |
| `LocalGenerator/tests/test_registry_composition_contract.py` | 19 | — |
| `LocalGenerator/tests/test_registry_neutral_provenance.py` | 94 | — |
| `LocalGenerator/tests/test_registry_receipt_identity.py` | 121 | — |
| `LocalGenerator/tests/test_registry_structured_params.py` | 32 | read:1 |
| `LocalGenerator/tests/test_registry_vertical_contract.py` | 81 | — |
| `LocalGenerator/tests/test_registry_wire_boundary.py` | 130 | read:2 |
| `LocalGenerator/tests/test_release_hygiene_tool_contract.py` | 1 | read:4 |
| `LocalGenerator/tests/test_repair_diagnostic_composition.py` | 4 | — |
| `LocalGenerator/tests/test_repair_frozen_contract.py` | 14 | read:2 |
| `LocalGenerator/tests/test_repair_gameplay_contract.py` | 161 | index:1 |
| `LocalGenerator/tests/test_repair_request_compaction.py` | 17 | — |
| `LocalGenerator/tests/test_repair_structure_unions.py` | 26 | — |
| `LocalGenerator/tests/test_repair_vfx_contract.py` | 22 | — |
| `LocalGenerator/tests/test_runtime_dump_contracts.py` | 3 | — |
| `LocalGenerator/tests/test_runtime_import_boundaries.py` | 8 | — |
| `LocalGenerator/tests/test_runtime_parent_combat.py` | 57 | read:2 |
| `LocalGenerator/tests/test_runtime_program_v5_seed_replay.py` | 1 | read:1 |
| `LocalGenerator/tests/test_runtime_spawn_distributions.py` | 89 | — |
| `LocalGenerator/tests/test_sdcpp_backend_contract.py` | 1 | read:1 |
| `LocalGenerator/tests/test_sdcpp_command_contract.py` | 3 | — |
| `LocalGenerator/tests/test_sentry_lifecycle_contract.py` | 42 | — |
| `LocalGenerator/tests/test_sentry_targeting_contract.py` | 59 | — |
| `LocalGenerator/tests/test_settings_controller.py` | 28 | read:4 |
| `LocalGenerator/tests/test_settings_fields.py` | 5 | — |
| `LocalGenerator/tests/test_settings_gui_contract.py` | 42 | read:14, wait:1 |
| `LocalGenerator/tests/test_settings_user_presets.py` | 33 | read:9 |
| `LocalGenerator/tests/test_signed_vertical_acceleration.py` | 41 | — |
| `LocalGenerator/tests/test_source_audit_gates.py` | 42 | read:3 |
| `LocalGenerator/tests/test_source_unit_guidance.py` | 39 | — |
| `LocalGenerator/tests/test_sprite_render_contracts.py` | 80 | read:2 |
| `LocalGenerator/tests/test_stable_schema_data.py` | 14 | — |
| `LocalGenerator/tests/test_stage_request_artifacts.py` | 14 | read:6 |
| `LocalGenerator/tests/test_studio_form.py` | 3 | — |
| `LocalGenerator/tests/test_studio_headless_security.py` | 4 | wait:1 |
| `LocalGenerator/tests/test_studio_operations.py` | 16 | read:1, wait:1 |
| `LocalGenerator/tests/test_targeting_spawn_prompt.py` | 3 | — |
| `LocalGenerator/tests/test_terraria_standardization.py` | 9 | — |
| `LocalGenerator/tests/test_trace_failure_state_contract.py` | 1 | — |
| `LocalGenerator/tests/test_trace_tools_contract.py` | 1 | read:7 |
| `LocalGenerator/tests/test_transport_retry_redaction.py` | 42 | read:5 |
| `LocalGenerator/tests/test_units_packet_preservation.py` | 33 | — |
| `LocalGenerator/tests/test_v5_replay_harness.py` | 2 | — |
| `LocalGenerator/tests/test_vfx_current_contract.py` | 62 | — |
| `LocalGenerator/tests/test_vfx_dependency_delivery_contracts.py` | 36 | read:3 |
| `LocalGenerator/tests/test_vfx_frozen_boundary_contracts.py` | 53 | read:1 |
| `LocalGenerator/tests/test_vfx_ingredient_generation_contracts.py` | 82 | read:13 |
| `LocalGenerator/tests/test_vfx_material_admission_contracts.py` | 135 | read:2 |
| `LocalGenerator/tests/test_vfx_native_float_roundtrip.py` | 24 | — |
| `LocalGenerator/tests/test_vfx_owner_link.py` | 48 | — |
| `LocalGenerator/tests/test_vfx_packet_contracts.py` | 3 | — |
| `LocalGenerator/tests/test_vfx_repair_packet_scope.py` | 27 | — |
| `LocalGenerator/tests/test_vfx_sound_controls.py` | 59 | — |
| `LocalGenerator/tests/test_vfx_sound_selection.py` | 31 | read:4 |
| `LocalGenerator/tests/test_visual_presentation_metadata.py` | 37 | — |
| `LocalGenerator/tests/test_visual_repair_packet_scope.py` | 20 | — |
| `LocalGenerator/tests/test_visual_vfx_prompt_prefix.py` | 15 | — |
| `LocalGenerator/tests/test_weapon_ammo.py` | 70 | read:1 |
| `LocalGenerator/tests/test_web_studio.py` | 13 | read:2 |
| `LocalGenerator/tests/test_web_studio_browser.py` | 3 | read:4, wait:8 |
| `LocalGenerator/tests/test_web_studio_interactions.py` | 48 | read:10 |
| `LocalGenerator/tests/test_web_studio_state.py` | 2 | — |
| `LocalGenerator/tests/test_web_studio_workflows_browser.py` | 15 | wait:2 |
| `LocalGenerator/tests/test_world_recipe_cache_admission.py` | 37 | read:19 |
| `toolbox/tests/test_live20_support_v5.py` | 20 | read:3 |
