# Behavioral-test audit — 2026-10-22

Baseline: `57c58d50504a7c69712e5843fa392b9a39800537` (main). Independent
of the unmerged parallel-image PR #137; no production changes from it are included.

## Scope and interpretation

Baseline collection finds **5,879 Python cases in 181 modules**, plus **118 C#
harness source files / 381 registered native check groups** and one Node frontend
suite. Counts are not interchangeable: native groups contain multiple assertions
and Python parametrization expands functions. This is a whole-suite inventory and
risk screen plus focused semantic audits, **not a claim that every assertion was
individually reviewed or every environment was executed**.

Every Python module was AST-screened for file reads, sleeps/browser delays and
index assertions. These are navigation signals, not errors: fixture/data reads,
controlled clocks, pump-loop polling, wire coordinates and meaningful dependency
order must remain. Auditors then followed actual owners in runtime/repair,
provider/asset transfer, UI, and native placed-VFX families.

## Python navigation categories

One category per baseline module, assigned by its primary test family; cross-cutting
coverage is not counted twice. Counts describe collection, not review depth.

| Family | Modules | Cases |
|---|---:|---:|
| Desktop / configuration / browser | 16 | 287 |
| Gameplay / runtime / storage | 71 | 1934 |
| Image / Visual / VFX delivery | 28 | 1070 |
| Provider / auth / trace | 17 | 639 |
| Registry / schema / Author | 23 | 1328 |
| Repair / frozen authority | 9 | 356 |
| Tooling / bootstrap / harness | 17 | 265 |

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

## Native, Node and tooling risk screen

All 118 native harness files were screened: reflection occurs in 101 files,
IL instrumentation in 26, `SequenceEqual` in 17, and file reads in 13 (fixture
and persistence reads, not source scans). No `Thread.Sleep`/`Task.Delay` calls.
The accurate baseline runner count is 381 named entries; 383 after making two
previously nested scenarios directly selectable. A stricter one-line regex misses
14 registrations, so is not used as the total.

The complete Node script has 142 assertion call sites and three named async
workflows plus linear scenarios; these are not 142 independent test cases. Three
real-browser tests contain 54 assertion sites; local execution skips them because
Playwright is absent. The supplementary tooling/bootstrap/logging screen covers
30 modules / 462 collected cases, plus offline bootstrap/shared check helpers.

| Finding | Disposition and reason |
|---|---|
| Native proximity dictionary iteration mistaken for event chronology | Fixed with duplicate-sensitive event roster; actual ordered light-cue output stays exact. |
| Native metadata publication uses 250ms scheduler limit | Fixed to bounded deadlock watchdog while server discovery is explicitly held; independent publication must finish before release. |
| Tooling XML/YAML exact whitespace/attribute order | Fixed by XML structure and narrow existing job/scalar extraction, with formatting-positive and missing-contract negative controls. |
| Trace clear worker release only after assertions | Fixed to guaranteed finally cleanup and bounded rendezvous. |
| Node exact 94px scroll offset | Fixed layout constant to target-directed bounded scroll; retain navigation wait, group expansion and focus contract. |
| Node exact repaint counts + VM source-injection seam | Retained pending real DOM observer: fake render does not simulate DOM replacement, so removing counts would lose protection despite focus assertions. |
| Native RootSpawn `AssertRootHookCallsCapacity` scans a helper metadata token in IL | Follow-up replaced the raw-token scan with observation of the actual allowance delivered by Shoot/HoldItem at `SpawnRuntimeEntity` entry. The real body still reaches the native registration sentinel; counts 1/4 with event budgets 0/7 must deliver the authored allowance. This proves caller delivery, not full in-game spawning. |
| Browser delayed acknowledgement uses timed edit/poll windows | Deferred until browser prerequisites permit validating request/edit/poll/ack barriers; no claim these race prerequisites are fully hardened. |
| Native IL compatibility/security mutation tests | Keep: exact installed dependency shape, fail-closed hooks and rollback are real compatibility contracts, unlike incidental helper call shape. |
| Trace ordered byte ranges, input-ordered batch results, captured fixture hash | Keep: persistence/provenance, explicit executor-map output and captured source identity are meaningful; completion-time callbacks have separate tests. |

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

## Explicit deletion pass (renewed request, 09:35 UTC)

The follow-up screened all Python test-function bodies for exact duplicates and
nearby repeated assertions, then traced the flagged behavior. Identical coarse
`run_contract_checks(globals(), ...)` wrappers are **not** duplicates: their module
namespaces contain different checks. Likewise assertions before/after repair,
serialization or state transitions remain separate guarantees. Frozen fixture
hashes, opcode identity and model-facing safety instructions are not arbitrary
implementation snapshots and remain intact.

| Removed / replaced | Surviving executable protection |
|---|---|
| Two redundant no-Tk fresh-process tests | `test_settings_controller::test_real_controller_import_and_run_without_tk_or_display` now combines `_tkinter`/`tkinter` rejection, no early backend bootstrap, values/snapshot shape, callback delivery and close. |
| Three duplicate sd.cpp backend checks | `test_sdcpp_command_contract` calls the real pipeline-to-backend wrapper and already exercises safe argv, malformed-template repair and LoRA delivery. Unique direct-backend extraction/payload cases remain. |
| sd.cpp module/function identity and private-alias assertions | Real `/shutdown` route terminates the owned fake process, closes its log and clears process state; independent health snapshot checks remain. |
| sd.cpp LoRA test that corrected its own stale input before execution | Fresh-process environment → actual pipeline configuration → argv test now supplies the stale directory unchanged and observes selected-file precedence. |
| Server echo banner constant-name source scan | Existing inert server-startup cases capture actual enabled/off banner output, including operator setting guidance. |
| Silver-presentation wrapper that only calls `_silver_delivery` | The retained native-fixture test calls the same helper, validates both historical and current payloads through runtime/VFX consumers, then compares exact visual/VFX payloads and owner-keyed entity presentations including multiplicity. Unrelated later gameplay fields are not a presentation snapshot contract. |
| C# RGB property/validation source-string scan | Registered native PlayedSilver checks deserialize strict RGB, reject nested token capture/malformed RGB, and observe actual library consumer color delivery. |
| Two locale mana-template tests | Registered native VFUI14 runs real `ModifyTooltips` in EN/RU, checks -5% not +5%, native arithmetic, and now rejects misleading minimum-cost wording in the rendered result. Placement-refusal localization presence remains checked separately. |
| Raw IL helper-call token scanner | Actual spawn-entry allowance observer described above; depth and owner-cap refusal tests remain. |
| Node `window.confirm(` source substring scan | Actual discard click/cancel/confirm flow checks persisted-baseline restoration, no native prompt/network request, and refusal while save/poll work is pending. |
| Adjacent repeated defaults / VFX wire assertions | One identical assertion remains at the same state; VFX cache/delivery refusals and persisted UI state checks unchanged. |

Negative probes are recorded in the PR: broken argv/template/LoRA/cleanup,
unwanted Tk/backend imports, lost scheduled callback, and native prompt/premature
or unguarded discard/wrong baseline must fail. RootSpawn also injects an actual
undersized allowance at the spawn entry: batch admission refuses it and the
retained delivery oracle rejects the observed wrong value. A harmless native-prompt string in
a JavaScript comment is now accepted. These probes modify temporary test processes
or copies only, never committed production files. Native execution is validated by
exact-head Windows CI, not inferred from source inspection.

The previous Node repaint/VM seam and browser timed-ack findings remain open:
there is still no equivalent verified DOM observer or browser rendezvous. Other
native source-policy checks with uncovered motion reach, selector/filter and
notice-throttling guarantees are retained rather than silently discarded.

## Reproduce and read the inventory

`PYTHONPATH=LocalGenerator python -m pytest --collect-only -q` produces the case
counts. Final acceptance uses `python tools/testing/run_pytest_shards.py --shards 4` and
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

## Native harness inventory

Risk tokens guide review; reflection/IL usage is not automatically brittle.

Harness paths in the baseline table below identify the audited snapshot; current
sources live under `tools/native/` with the same filenames. These historical
signal counts are not a current validation result.

| Baseline harness | Screen signals |
|---|---|
| `tools/EngineRuntimeChecks.AccessoryIdentity.cs` | reflection:22, il_instrumentation:2 |
| `tools/EngineRuntimeChecks.Ammo.cs` | — |
| `tools/EngineRuntimeChecks.AssetIdentity.cs` | reflection:51, sequence_equal:4, il_instrumentation:3 |
| `tools/EngineRuntimeChecks.AssetLifecycle.cs` | reflection:16, file_text_read:2, il_instrumentation:6 |
| `tools/EngineRuntimeChecks.Assets.cs` | reflection:12, sequence_equal:1 |
| `tools/EngineRuntimeChecks.AuditGameplay.cs` | reflection:2 |
| `tools/EngineRuntimeChecks.BodyGeometry.cs` | reflection:5 |
| `tools/EngineRuntimeChecks.BudgetPeer.cs` | reflection:3 |
| `tools/EngineRuntimeChecks.BuffPrecision.cs` | — |
| `tools/EngineRuntimeChecks.ChannelBeam.cs` | reflection:10 |
| `tools/EngineRuntimeChecks.ChargePresentation.cs` | — |
| `tools/EngineRuntimeChecks.ChildCombat.cs` | reflection:10 |
| `tools/EngineRuntimeChecks.Client.cs` | reflection:122, il_instrumentation:5 |
| `tools/EngineRuntimeChecks.CompactTooltips.cs` | reflection:1, sequence_equal:1 |
| `tools/EngineRuntimeChecks.Concurrency.cs` | reflection:1 |
| `tools/EngineRuntimeChecks.Contract.cs` | reflection:12 |
| `tools/EngineRuntimeChecks.CraftCancellation.cs` | reflection:7 |
| `tools/EngineRuntimeChecks.CraftQol.cs` | reflection:27, il_instrumentation:4 |
| `tools/EngineRuntimeChecks.CraftWorldExit.cs` | reflection:7 |
| `tools/EngineRuntimeChecks.CursorDeath.cs` | reflection:8 |
| `tools/EngineRuntimeChecks.DelayedNpcIncarnation.cs` | reflection:3 |
| `tools/EngineRuntimeChecks.DetachedVfxRetirement.cs` | reflection:12, il_instrumentation:4 |
| `tools/EngineRuntimeChecks.DocxImageReadiness.cs` | reflection:1, file_text_read:4, sequence_equal:1 |
| `tools/EngineRuntimeChecks.Equipment.cs` | reflection:11, file_text_read:1 |
| `tools/EngineRuntimeChecks.EquipmentPresentation.cs` | reflection:30 |
| `tools/EngineRuntimeChecks.EquipmentUtilities.cs` | reflection:14 |
| `tools/EngineRuntimeChecks.EscrowSession.cs` | reflection:8, il_instrumentation:3 |
| `tools/EngineRuntimeChecks.EventDomains.cs` | reflection:3 |
| `tools/EngineRuntimeChecks.Events.cs` | reflection:35 |
| `tools/EngineRuntimeChecks.Exhaustion.cs` | reflection:17 |
| `tools/EngineRuntimeChecks.ExhaustionPresentation.cs` | reflection:17, sequence_equal:4, il_instrumentation:11 |
| `tools/EngineRuntimeChecks.Float32BuffIdentity.cs` | reflection:3 |
| `tools/EngineRuntimeChecks.ForgePresentation.cs` | reflection:24 |
| `tools/EngineRuntimeChecks.FrontHand.cs` | reflection:5, file_text_read:1 |
| `tools/EngineRuntimeChecks.FrontHandRepairs.cs` | reflection:28, sequence_equal:1 |
| `tools/EngineRuntimeChecks.GeneratedItemPrefix.cs` | reflection:18 |
| `tools/EngineRuntimeChecks.GeneratedStacking.cs` | reflection:3 |
| `tools/EngineRuntimeChecks.Grounded.cs` | reflection:3 |
| `tools/EngineRuntimeChecks.HeldProxy.cs` | reflection:23 |
| `tools/EngineRuntimeChecks.HitboxCurve.cs` | reflection:9 |
| `tools/EngineRuntimeChecks.InitialNpcExclusion.cs` | reflection:10 |
| `tools/EngineRuntimeChecks.IntegratedQol.cs` | reflection:34, il_instrumentation:5 |
| `tools/EngineRuntimeChecks.InventorySeeds.cs` | reflection:6, file_text_read:4, sequence_equal:1 |
| `tools/EngineRuntimeChecks.ItemVfxEvents.cs` | reflection:23 |
| `tools/EngineRuntimeChecks.JournalReactions.cs` | — |
| `tools/EngineRuntimeChecks.LegacyRetirement.cs` | — |
| `tools/EngineRuntimeChecks.LibraryInterop.cs` | reflection:9, il_instrumentation:6 |
| `tools/EngineRuntimeChecks.LibraryVfx.cs` | reflection:3 |
| `tools/EngineRuntimeChecks.LiteralStackCost.cs` | reflection:1, il_instrumentation:1 |
| `tools/EngineRuntimeChecks.LocalRgb.cs` | reflection:6, sort:1 |
| `tools/EngineRuntimeChecks.MaterialElements.cs` | reflection:68 |
| `tools/EngineRuntimeChecks.MaterialReview.cs` | reflection:44 |
| `tools/EngineRuntimeChecks.Mobility.cs` | reflection:3 |
| `tools/EngineRuntimeChecks.MobilityConsumption.cs` | reflection:11, il_instrumentation:4 |
| `tools/EngineRuntimeChecks.Modifiers.cs` | reflection:9 |
| `tools/EngineRuntimeChecks.NamedItemEffects.cs` | reflection:4, il_instrumentation:3 |
| `tools/EngineRuntimeChecks.NativeChest.cs` | reflection:24, il_instrumentation:16 |
| `tools/EngineRuntimeChecks.NativeChestNetwork.cs` | reflection:7 |
| `tools/EngineRuntimeChecks.NativeChestPersistence.cs` | reflection:25 |
| `tools/EngineRuntimeChecks.NativeChestVfx.cs` | reflection:1 |
| `tools/EngineRuntimeChecks.NativeDtoRetirement.cs` | reflection:14 |
| `tools/EngineRuntimeChecks.NetworkHit.cs` | reflection:6 |
| `tools/EngineRuntimeChecks.OwnerLink.cs` | reflection:12 |
| `tools/EngineRuntimeChecks.ParentFacts.cs` | reflection:35, sort:4 |
| `tools/EngineRuntimeChecks.ParentPlacement.cs` | reflection:16 |
| `tools/EngineRuntimeChecks.ParentTileState.cs` | reflection:15 |
| `tools/EngineRuntimeChecks.PersistedDefinitions.cs` | reflection:3, file_text_read:1, sequence_equal:2 |
| `tools/EngineRuntimeChecks.PlacedAlphaPivot.cs` | reflection:12, file_text_read:1, sequence_equal:1, il_instrumentation:1 |
| `tools/EngineRuntimeChecks.PlacedBody.cs` | reflection:8 |
| `tools/EngineRuntimeChecks.PlacedBodyLedger.cs` | reflection:6, sequence_equal:1, il_instrumentation:3 |
| `tools/EngineRuntimeChecks.PlacedBodyNative.cs` | reflection:7, il_instrumentation:2 |
| `tools/EngineRuntimeChecks.PlacedBodyPeerIdentity.cs` | reflection:6, il_instrumentation:5 |
| `tools/EngineRuntimeChecks.PlacedLight.cs` | reflection:2 |
| `tools/EngineRuntimeChecks.PlacedVfx.cs` | reflection:25, file_text_read:1 |
| `tools/EngineRuntimeChecks.PlacementPool.cs` | reflection:2, il_instrumentation:4 |
| `tools/EngineRuntimeChecks.PlacementPrefix.cs` | — |
| `tools/EngineRuntimeChecks.PlayedMechanics.cs` | reflection:44, file_text_read:1, il_instrumentation:1 |
| `tools/EngineRuntimeChecks.PlayedPresentation.cs` | reflection:8, sequence_equal:1 |
| `tools/EngineRuntimeChecks.PlayedSilver.cs` | file_text_read:1 |
| `tools/EngineRuntimeChecks.PlayedUmbrella.cs` | file_text_read:1 |
| `tools/EngineRuntimeChecks.Player.cs` | reflection:36 |
| `tools/EngineRuntimeChecks.ProjectileControls.cs` | — |
| `tools/EngineRuntimeChecks.ProjectileHydration.cs` | reflection:9 |
| `tools/EngineRuntimeChecks.Proximity.cs` | reflection:7 |
| `tools/EngineRuntimeChecks.QuickUse.cs` | reflection:6 |
| `tools/EngineRuntimeChecks.QuickUtilityActivation.cs` | reflection:21, il_instrumentation:1 |
| `tools/EngineRuntimeChecks.RawJsonNumeric.cs` | — |
| `tools/EngineRuntimeChecks.ReactionPresentation.cs` | reflection:14, sequence_equal:2, il_instrumentation:6 |
| `tools/EngineRuntimeChecks.ReactiveBuffNetwork.cs` | reflection:3 |
| `tools/EngineRuntimeChecks.ReactiveBuffTooltips.cs` | reflection:1 |
| `tools/EngineRuntimeChecks.ReactiveBuffs.cs` | — |
| `tools/EngineRuntimeChecks.RootCombat.cs` | reflection:29, il_instrumentation:8 |
| `tools/EngineRuntimeChecks.RootSpawn.cs` | reflection:8, sequence_equal:1, raw_il_body:2 |
| `tools/EngineRuntimeChecks.SentryLifecycle.cs` | reflection:6 |
| `tools/EngineRuntimeChecks.SentryTargeting.cs` | reflection:8 |
| `tools/EngineRuntimeChecks.SoundSelection.cs` | reflection:5, sequence_equal:6 |
| `tools/EngineRuntimeChecks.SpawnDistributions.cs` | reflection:9 |
| `tools/EngineRuntimeChecks.StackChance.cs` | — |
| `tools/EngineRuntimeChecks.SwarmPersistence.cs` | reflection:19 |
| `tools/EngineRuntimeChecks.SwarmRuntime.cs` | reflection:21, sort:1, il_instrumentation:4 |
| `tools/EngineRuntimeChecks.TargetEmission.cs` | reflection:4 |
| `tools/EngineRuntimeChecks.TestSupport.cs` | reflection:28, il_instrumentation:2 |
| `tools/EngineRuntimeChecks.TooltipSecondaries.cs` | reflection:1, file_text_read:1, sequence_equal:1 |
| `tools/EngineRuntimeChecks.Tooltips.cs` | reflection:13, sequence_equal:2 |
| `tools/EngineRuntimeChecks.TransportIdentity.cs` | reflection:5 |
| `tools/EngineRuntimeChecks.UiQol.cs` | — |
| `tools/EngineRuntimeChecks.UnitBoundaries.cs` | — |
| `tools/EngineRuntimeChecks.UseFeedback.cs` | — |
| `tools/EngineRuntimeChecks.VerticalAcceleration.cs` | — |
| `tools/EngineRuntimeChecks.Vfx.cs` | reflection:75 |
| `tools/EngineRuntimeChecks.VfxEventConsistency.cs` | reflection:15 |
| `tools/EngineRuntimeChecks.VfxGeometry.cs` | reflection:7 |
| `tools/EngineRuntimeChecks.VfxPreview.cs` | reflection:3 |
| `tools/EngineRuntimeChecks.VideoUiBuffs.cs` | reflection:20, file_text_read:1, sequence_equal:2, il_instrumentation:9 |
| `tools/EngineRuntimeChecks.WeaponAmmo.cs` | reflection:11 |
| `tools/EngineRuntimeChecks.Whip.cs` | reflection:8 |
| `tools/EngineRuntimeChecks.World.cs` | — |
| `tools/EngineRuntimeChecks.cs` | reflection:13 |
