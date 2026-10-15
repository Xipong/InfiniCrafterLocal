"""Keep specifically retired duplicate owners retired without pinning implementations."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "infini_local"


@pytest.mark.parametrize(("module", "retired"), [
    ("pipelines/image_backend_pipeline.py", {
        "sdcpp_command_mode_is_template", "sdcpp_base_arg_list", "quote_cmd_arg",
        "_extra_has_flag", "sdcpp_effective_extra_arg_list",
    }),
    ("pipelines/pipeline_visual_config.py", {"_sdcpp_config"}),
    ("pipelines/parent_context_pipeline.py", {
        "llm_parent_card", "runtime_facts_for_prompt", "auto_features_for_prompt",
        "parent_weapon_profiles", "behavior_policy_for_prompt", "combined_tags",
        "_fishing_bait_semantics_for_llm", "_placeable_consumption_semantics_for_llm",
        "_projectile_semantics_for_llm",
    }),
    ("storage/world_recipe_runtime.py", {
        "safe_file_part", "atomic_write_json", "read_json_file", "write_world_manifest",
        "strip_runtime_only_fields", "_delivery_safe_debug", "sanitize_recipe_for_delivery",
        "quarantine_world_recipe_cache", "is_deliverable_recipe_payload",
    }),
    ("web/server.py", {
        "_runtime_dump_candidates", "_resolve_runtime_dump_path", "load_jsonl_index",
        "runtime_item_lookup", "runtime_projectile_lookup",
    }),
])
def test_removed_facades_do_not_regain_duplicate_definitions(module, retired):
    tree = ast.parse((PACKAGE / module).read_text(encoding="utf-8"))
    definitions = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not definitions & retired


def test_runtime_dumps_have_one_snapshot_owner():
    assert not (PACKAGE / "pipelines/pipeline_runtime_dumps.py").exists()
    # Runtime behavior and HTTP snapshot reuse are exercised in test_runtime_dump_contracts.
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "infini_local.pipelines.pipeline_runtime_dumps", path
                if node.module == "infini_local.pipelines":
                    assert all(alias.name != "pipeline_runtime_dumps" for alias in node.names), path
            elif isinstance(node, ast.Import):
                assert all(alias.name != "infini_local.pipelines.pipeline_runtime_dumps" for alias in node.names), path
