from __future__ import annotations

import json
from pathlib import Path
import threading

import pytest

from infini_local.qa.csharp_delivery_contract import load_csharp_contract_graph
from infini_local.qa.golden_runtime_cases import GOLDEN_RUNTIME_CASES
from infini_local.qa.runtime_proof import build_gameplay_seam_report
from infini_local.storage import world_storage


ROOT = Path(__file__).resolve().parents[2]
CSHARP_DELIVERY_CONTRACT = load_csharp_contract_graph()


def _check_safe_file_part_is_stable_and_boring() -> None:
    assert world_storage.safe_file_part(" My World: #1! ") == "My_World_1"
    assert world_storage.safe_file_part("***", "fallback") == "fallback"
    assert len(world_storage.safe_file_part("x" * 200, max_len=12)) == 12


def _check_world_cache_delivery_sanitizes_debug_and_runtime_only_fields(tmp_path: Path) -> None:
    data = {
        "id": "generated_test",
        "name": "Generated Test",
        "debug": {"nested": {"ok": True}, "num": 7},
        "_llmHistory": {"messages": ["must not leak"]},
        "_runtimePlanCompileCache": {"must": "not leak"},
    }

    world_storage.write_world_recipe_cache(
        tmp_path,
        "9.9.9",
        "parentA+parentB",
        "world:alpha",
        data,
        parent_a_name="A",
        parent_b_name="B",
        world_name="Alpha",
    )

    stored_path = world_storage.world_recipe_file(tmp_path, "world:alpha", "parentA+parentB")
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    assert "_llmHistory" not in stored
    assert "_runtimePlanCompileCache" not in stored
    assert "debug" not in stored

    assert stored["recipeMeta"]["parentA"] == "A"
    assert stored["recipeMeta"]["worldScoped"] is True

    loaded = world_storage.read_world_recipe_cache(tmp_path, "9.9.9", "recipe_v_test", "parentA+parentB", "world:alpha")
    assert loaded is not None
    assert "runtimePlan" not in loaded
    assert "runtimeContract" not in loaded


def _check_deliverable_recipe_payload_rejects_placeholders_and_fallbacks() -> None:
    assert world_storage.is_deliverable_recipe_payload({"id": "x", "name": "Real", "sourceMode": "llm"}) is True
    assert world_storage.is_deliverable_recipe_payload({"id": "placeholder", "name": "Real"}) is False
    assert world_storage.is_deliverable_recipe_payload({"id": "x", "name": "Real", "sourceMode": "fallback_dev"}) is False


def _csharp_auto_property_fields(class_name: str) -> frozenset[str]:
    return CSHARP_DELIVERY_CONTRACT.json_fields(class_name)


def _strict_csharp_unmapped_paths(payload: dict) -> list[str]:
    return CSHARP_DELIVERY_CONTRACT.validate(payload)


def _wire_probe_value(class_name: str, field_name: str):
    contract = CSHARP_DELIVERY_CONTRACT.class_contract(class_name)
    assert contract is not None
    prop = contract.property_for_json_name(field_name)
    assert prop is not None
    type_name = prop.type_name
    if type_name.endswith("[]") or type_name.startswith(("List<", "IReadOnlyList<", "IEnumerable<")):
        return []
    if type_name.startswith(("Dictionary<", "IDictionary<", "IReadOnlyDictionary<")):
        return {}
    if type_name in {"bool", "Boolean"}:
        return True
    if type_name in {"byte", "sbyte", "short", "ushort", "int", "uint", "long", "ulong"}:
        return 1
    if type_name in {"float", "double", "decimal", "Half", "Single", "Double", "Decimal"}:
        return 1.0
    return f"wire:{field_name}"


def _check_golden_delivery_has_no_unmapped_nested_csharp_fields() -> None:
    for case in GOLDEN_RUNTIME_CASES:
        item = build_gameplay_seam_report(case).get("item") or {}
        delivered = world_storage.sanitize_recipe_for_delivery(item)
        assert not _strict_csharp_unmapped_paths(delivered), case["caseId"]


def _check_delivery_strips_python_author_proof() -> None:
    delivered = world_storage.sanitize_recipe_for_delivery({
        "id": "g_author_proof",
        "name": "Author Proof",
        "runtimePlan": {"engineCalls": [{"callId": "primary", "fn": "shoot_projectile", "params": {"runtimeFamily": "shoot"}}]},
        "runtimeContract": {"schema": "infini.runtime-contract.v3", "mechanicClaims": []},
        "debug": {"planner": "llm_author_first", "authorProof": "python-only"},
        "gameplay": {"kind": "weapon", "damage": 12},
        "attack": {"enabled": True, "runtimeFamily": "shoot"},
    })
    assert "runtimePlan" not in delivered
    assert "runtimeContract" not in delivered
    assert "debug" not in delivered


def _check_delivery_matches_strict_nested_csharp_specs() -> None:
    contracts = {
        "VisualSpec": world_storage.VISUAL_DELIVERY_FIELDS,
        "GeneratedParentSummarySpec": world_storage.GENERATED_PARENT_SUMMARY_DELIVERY_FIELDS,
        "ParentItemCardSpec": world_storage.PARENT_ITEM_CARD_DELIVERY_FIELDS,
        "RecipeMetaSpec": world_storage.RECIPE_META_DELIVERY_FIELDS,
        "VfxQualityBudgetSpec": world_storage.VFX_QUALITY_BUDGET_DELIVERY_FIELDS,
        "VfxDebugSpec": world_storage.VFX_DEBUG_DELIVERY_FIELDS,
    }
    for class_name, delivery_fields in contracts.items():
        assert delivery_fields == _csharp_auto_property_fields(class_name)

    visual_fields = contracts["VisualSpec"]
    summary_fields = contracts["GeneratedParentSummarySpec"]
    parent_fields = contracts["ParentItemCardSpec"]
    recipe_meta_fields = contracts["RecipeMetaSpec"]
    vfx_budget_fields = contracts["VfxQualityBudgetSpec"]
    vfx_debug_fields = contracts["VfxDebugSpec"]
    payload = {
        "visual": {
            **{field: _wire_probe_value("VisualSpec", field) for field in visual_fields},
            "itemPrompt": "one authored item prompt",
            "itemSilhouetteContract": "one connected body",
            "styleGuide": "pixel art",
            "vfxIntent": "sawdust",
        },
        "generatedParentSummary": {
            **{field: _wire_probe_value("GeneratedParentSummarySpec", field) for field in summary_fields},
            "customAttackEnabled": True,
            "vanillaItemHitboxDamage": False,
        },
        "itemKnowledge": {
            "enabled": True,
            "parents": [{**{field: _wire_probe_value("ParentItemCardSpec", field) for field in parent_fields}, "recipeFrame": {}, "signals": {}}],
            "resultCard": {**{field: _wire_probe_value("ParentItemCardSpec", field) for field in parent_fields}, "signals": {}},
        },
        "recipeMeta": {
            **{field: _wire_probe_value("RecipeMetaSpec", field) for field in recipe_meta_fields},
            "assetSync": {},
            "contractVersions": {},
            "parentA": "A",
            "parentB": "B",
            "recipeKey": "r_test",
            "storage": "world_recipes_file",
            "worldName": "World",
        },
        "vfxManifest": {
            "budget": {
                **{field: _wire_probe_value("VfxQualityBudgetSpec", field) for field in vfx_budget_fields},
                "quality": "high",
                "renderQuality": "high",
            },
            "debug": {
                **{field: _wire_probe_value("VfxDebugSpec", field) for field in vfx_debug_fields},
                "composition": {},
                "effectLineage": [],
                "rerollSalt": "salt",
            },
        },
    }
    delivered = world_storage.sanitize_recipe_for_delivery(payload)

    assert not _strict_csharp_unmapped_paths(delivered)
    assert set(delivered["visual"]) == visual_fields
    assert set(delivered["generatedParentSummary"]) == summary_fields
    assert set(delivered["itemKnowledge"]["parents"][0]) == parent_fields
    assert set(delivered["itemKnowledge"]["resultCard"]) == parent_fields
    assert set(delivered["recipeMeta"]) == recipe_meta_fields
    assert set(delivered["vfxManifest"]["budget"]) == vfx_budget_fields
    assert set(delivered["vfxManifest"]["debug"]) == vfx_debug_fields
    assert delivered["visual"]["imagePrompt"] == "wire:imagePrompt"
    assert delivered["visual"]["spritePath"] == "wire:spritePath"
    assert "itemPrompt" in payload["visual"]
    assert "recipeFrame" in payload["itemKnowledge"]["parents"][0]


def _check_delivery_strips_removed_runtime_archetype_surface() -> None:
    payload = {
        "id": "g_scalar_archetype",
        "name": "Scalar Archetype",
        "runtimeArchetype": "consumable_melee_projectile",
    }

    assert _strict_csharp_unmapped_paths(payload) == []
    delivered = world_storage.sanitize_recipe_for_delivery(payload)
    assert "runtimeArchetype" not in delivered
    assert payload["runtimeArchetype"] == "consumable_melee_projectile"

    object_payload = {
        "id": "g_future_archetype",
        "name": "Future Archetype",
        "runtimeArchetype": {
            "schema": "infini.runtime-archetype.v1",
            "source": "generated",
            "family": "custom_executor",
            "channelled": True,
            "overrideKnobs": {"orbitRadius": 4.5},
            "aiType": 17,
            "supportNotes": "must be a string list",
            "futureNestedKey": "strict C# must never receive this",
        },
    }
    assert _strict_csharp_unmapped_paths(object_payload) == []
    projected = world_storage.sanitize_recipe_for_delivery(object_payload)
    assert "runtimeArchetype" not in projected
    assert _strict_csharp_unmapped_paths(projected) == []
    assert "futureNestedKey" in object_payload["runtimeArchetype"]


def _check_concurrent_world_cache_writes_preserve_every_recipe_without_aggregate_rewrites(tmp_path: Path) -> None:
    count = 8
    barrier = threading.Barrier(count)
    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def writer(index: int) -> None:
        try:
            barrier.wait(timeout=3)
            world_storage.write_world_recipe_cache(
                tmp_path,
                "9.9.9",
                f"recipe-{index}",
                "shared-world",
                {
                    "id": f"generated-{index}",
                    "name": f"Generated {index}",
                    "sourceMode": "generated",
                    "gameplay": {"kind": "utility", "runtimeOutputKind": "utility"},
                    "visual": {"spriteStatus": "generated"},
                },
                parent_a_name="A",
                parent_b_name="B",
                world_name="Shared World",
            )
        except BaseException as error:
            with errors_lock:
                errors.append(error)

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=8)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    root = world_storage.world_recipe_dir(tmp_path, "shared-world")
    recipe_files = sorted((root / "recipes").glob("*.json"))
    manifest = world_storage.read_json_file(root / "manifest.json")
    assert len(recipe_files) == count
    assert isinstance(manifest, dict)
    assert manifest["schema"] == "infini-world-recipes-v2"
    assert not (root / "index.json").exists()
    assert not (root / "health.json").exists()
    assert list(root.rglob("*.tmp")) == []




def _check_distinct_recipes_in_one_world_write_in_parallel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world_storage.write_world_manifest(tmp_path, "9.9.9", "parallel-world", "Parallel World")
    original_atomic_write_json = world_storage.atomic_write_json
    recipe_barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def synchronized_atomic_write_json(path: Path, payload: dict) -> None:
        if path.parent.name == "recipes":
            recipe_barrier.wait(timeout=3)
        original_atomic_write_json(path, payload)

    monkeypatch.setattr(world_storage, "atomic_write_json", synchronized_atomic_write_json)

    def writer(key: str) -> None:
        try:
            world_storage.write_world_recipe_cache(
                tmp_path,
                "9.9.9",
                key,
                "parallel-world",
                {"id": key, "name": key, "sourceMode": "generated"},
                world_name="Parallel World",
            )
        except BaseException as error:
            with errors_lock:
                errors.append(error)

    threads = [threading.Thread(target=writer, args=(key,)) for key in ("recipe-a", "recipe-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=6)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert world_storage.world_recipe_file(tmp_path, "parallel-world", "recipe-a").exists()
    assert world_storage.world_recipe_file(tmp_path, "parallel-world", "recipe-b").exists()


def _check_recipe_write_path_only_replaces_the_changed_recipe_after_manifest_creation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[str] = []
    original_atomic_write_json = world_storage.atomic_write_json

    def tracked_atomic_write_json(path: Path, payload: dict) -> None:
        writes.append(path.relative_to(tmp_path).as_posix())
        original_atomic_write_json(path, payload)

    monkeypatch.setattr(world_storage, "atomic_write_json", tracked_atomic_write_json)

    for key in ("recipe-a", "recipe-b"):
        world_storage.write_world_recipe_cache(
            tmp_path,
            "9.9.9",
            key,
            "single-authority-world",
            {"id": key, "name": key, "sourceMode": "generated"},
            parent_a_name="A",
            parent_b_name="B",
            world_name="Single Authority",
        )

    before_read = list(writes)
    loaded = world_storage.read_world_recipe_cache(
        tmp_path,
        "9.9.9",
        "recipe-v-test",
        "recipe-a",
        "single-authority-world",
        "Single Authority",
    )

    assert loaded is not None
    assert writes == before_read
    assert writes == [
        "world_single-authority-world/manifest.json",
        "world_single-authority-world/recipes/recipe-a.json",
        "world_single-authority-world/recipes/recipe-b.json",
    ]


def _check_world_storage_rejects_nonfinite_and_duplicate_json(tmp_path: Path) -> None:
    target = tmp_path / "strict.json"
    with pytest.raises(ValueError):
        world_storage.atomic_write_json(target, {"value": float("nan")})
    assert target.exists() is False
    assert list(tmp_path.glob("*.tmp")) == []

    target.write_text('{"value":1,"value":2}', encoding="utf-8")
    assert world_storage.read_json_file(target) is None


def _check_world_recipe_file_embeds_runtime_assets_health_and_contracts(tmp_path: Path) -> None:
    data = {
        "id": "g_health",
        "name": "Health Blade",
        "sourceMode": "generated",
        "recipeKey": "r_health",
        "runtimePlan": {"resultKind": "weapon"},
        "gameplay": {"kind": "weapon", "runtimeOutputKind": "weapon"},
        "attack": {"enabled": True, "delivery": "thrust", "runtimeFamily": "thrust", "damagePath": "generated_executor"},
        "visual": {"spriteStatus": "generated"},
        "debug": {"runtimePlanValidation": '{"ok":true}', "runtimePlanProvenance": '{"gameplayChildren":{"enabled":false},"pureVfx":{"enabled":true}}'},
        "recipeMeta": {"assetFiles": ["g_health.png"]},
    }
    contract_versions = {"schema": "infini.contract-stamp.v1", "appVersion": "9.9.9", "runtimeApiVersion": "v_test"}
    visual_report = {
        "ok": True,
        "slots": [
            {"role": "item", "required": True, "status": "generated", "exists": True, "usable": True},
            {"role": "projectile", "required": False, "status": "", "exists": False, "usable": False},
        ],
    }
    world_storage.attach_recipe_health(data, app_version="9.9.9", contract_versions=contract_versions, visual_report=visual_report)
    assert data["recipeHealth"]["ok"] is True
    assert data["recipeHealth"]["runtime"]["pureVfx"] is True
    assert data["contractVersions"]["runtimeApiVersion"] == "v_test"

    world_storage.write_world_recipe_cache(
        tmp_path,
        "9.9.9",
        "r_health",
        "world-health",
        data,
        parent_a_name="A",
        parent_b_name="B",
        world_name="Health World",
    )
    root = world_storage.world_recipe_dir(tmp_path, "world-health")
    stored = json.loads(world_storage.world_recipe_file(tmp_path, "world-health", "r_health").read_text(encoding="utf-8"))
    assert stored["recipeHealth"]["status"] == "healthy"
    assert stored["recipeHealth"]["runtime"]["delivery"] == "thrust"
    assert stored["recipeHealth"]["ok"] is True
    assert stored["recipeMeta"]["storage"] == "world_recipe_file_authority"
    assert not (root / "index.json").exists()
    assert not (root / "health.json").exists()

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_safe_file_part_is_stable_and_boring',
    '_check_world_cache_delivery_sanitizes_debug_and_runtime_only_fields',
    '_check_deliverable_recipe_payload_rejects_placeholders_and_fallbacks',
    '_check_golden_delivery_has_no_unmapped_nested_csharp_fields',
    '_check_delivery_strips_python_author_proof',
    '_check_delivery_matches_strict_nested_csharp_specs',
    '_check_delivery_strips_removed_runtime_archetype_surface',
    '_check_concurrent_world_cache_writes_preserve_every_recipe_without_aggregate_rewrites',
    '_check_distinct_recipes_in_one_world_write_in_parallel',
    '_check_recipe_write_path_only_replaces_the_changed_recipe_after_manifest_creation',
    '_check_world_storage_rejects_nonfinite_and_duplicate_json',
    '_check_world_recipe_file_embeds_runtime_assets_health_and_contracts'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_world_storage_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
