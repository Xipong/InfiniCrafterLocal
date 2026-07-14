from __future__ import annotations

import json
import re
from pathlib import Path

from infini_local.qa.golden_runtime_cases import GOLDEN_RUNTIME_CASES
from infini_local.qa.runtime_proof import build_gameplay_seam_report
from infini_local.storage import world_storage


ROOT = Path(__file__).resolve().parents[2]


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
    assert stored["debug"]["nested"] == '{"ok":true}'
    assert stored["debug"]["num"] == "7"
    assert stored["debug"]["recipeHealthStatus"] == "healthy"
    assert stored["recipeMeta"]["parentA"] == "A"
    assert stored["recipeMeta"]["worldScoped"] is True

    loaded = world_storage.read_world_recipe_cache(tmp_path, "9.9.9", "recipe_v_test", "parentA+parentB", "world:alpha")
    assert loaded is not None
    assert loaded["debug"]["cacheHit"] == "world_file"
    assert loaded["debug"]["recipeIdentityVersion"] == "recipe_v_test"


def _check_deliverable_recipe_payload_rejects_placeholders_and_fallbacks() -> None:
    assert world_storage.is_deliverable_recipe_payload({"id": "x", "name": "Real", "sourceMode": "llm"}) is True
    assert world_storage.is_deliverable_recipe_payload({"id": "placeholder", "name": "Real"}) is False
    assert world_storage.is_deliverable_recipe_payload({"id": "x", "name": "Real", "sourceMode": "fallback_dev"}) is False


def _csharp_auto_property_fields(class_name: str) -> frozenset[str]:
    sources = "\n".join(
        path.read_text(encoding="utf-8-sig")
        for path in (ROOT / "ModSources/InfiniCrafterLocal").rglob("*.cs")
    )
    marker = re.search(rf"public\s+(?:sealed\s+)?(?:partial\s+)?class\s+{re.escape(class_name)}\b", sources)
    assert marker is not None, class_name
    start = sources.index("{", marker.end())
    depth = 0
    end = start
    for end in range(start, len(sources)):
        depth += int(sources[end] == "{") - int(sources[end] == "}")
        if depth == 0:
            break
    body = sources[start : end + 1]
    return frozenset(
        name[:1].lower() + name[1:]
        for name in re.findall(
            r"public\s+(?!static\b|void\b)[A-Za-z_]\w*(?:<[A-Za-z0-9_.,?\[\] \t]+>)?[\[\]?]*[ \t]+(\w+)\s*\{\s*get;\s*set;\s*\}",
            body,
        )
    )


def _strict_csharp_unmapped_paths(payload: dict) -> list[str]:
    classes: dict[str, dict] = {}
    for path in (ROOT / "ModSources/InfiniCrafterLocal").rglob("*.cs"):
        source = path.read_text(encoding="utf-8-sig")
        for marker in re.finditer(r"public\s+(?:(?:sealed|partial)\s+)*class\s+(\w+)", source):
            class_name = marker.group(1)
            start = source.index("{", marker.end())
            depth = 0
            end = start
            for end in range(start, len(source)):
                depth += int(source[end] == "{") - int(source[end] == "}")
                if depth == 0:
                    break
            body = source[start : end + 1]
            contract = classes.setdefault(class_name, {"properties": {}, "extension": False})
            contract["extension"] = contract["extension"] or "[JsonExtensionData]" in body
            for property_match in re.finditer(
                r"public\s+(?!sealed\b|static\b|void\b)([A-Za-z_]\w*(?:<[A-Za-z0-9_.,?\[\] \t]+>)?[\[\]?]*)[ \t]+(\w+)\s*\{\s*get;\s*set;\s*\}",
                body,
            ):
                property_type, property_name = property_match.groups()
                contract["properties"][property_name.lower()] = re.sub(r"\s+", "", property_type)

    primitives = {
        "string", "int", "long", "float", "double", "decimal", "bool",
        "byte", "short", "uint", "ulong", "ushort", "JsonElement", "object",
    }
    unmapped: list[str] = []

    def visit(value, type_name: str, json_path: str) -> None:
        type_name = type_name.rstrip("?")
        if type_name.endswith("[]"):
            if isinstance(value, list):
                for index, item in enumerate(value):
                    visit(item, type_name[:-2], f"{json_path}[{index}]")
            return
        for prefix in ("List<", "IReadOnlyList<", "IEnumerable<"):
            if type_name.startswith(prefix) and type_name.endswith(">"):
                if isinstance(value, list):
                    for index, item in enumerate(value):
                        visit(item, type_name[len(prefix) : -1], f"{json_path}[{index}]")
                return
        if type_name.startswith(("Dictionary<", "IDictionary<")) or type_name in primitives or value is None:
            return
        contract = classes.get(type_name)
        if contract is not None and not isinstance(value, dict):
            unmapped.append(f"{json_path} -> expected {type_name} object")
            return
        if contract is None:
            return
        for key, item in value.items():
            child_type = contract["properties"].get(key.lower())
            if child_type is None:
                if not contract["extension"]:
                    unmapped.append(f"{json_path}.{key} -> {type_name}")
                continue
            visit(item, child_type, f"{json_path}.{key}")

    visit(payload, "GeneratedItemData", "$")
    return unmapped


def _check_golden_delivery_has_no_unmapped_nested_csharp_fields() -> None:
    for case in GOLDEN_RUNTIME_CASES:
        item = build_gameplay_seam_report(case).get("item") or {}
        delivered = world_storage.sanitize_recipe_for_delivery(item)
        assert not _strict_csharp_unmapped_paths(delivered), case["caseId"]


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
            **{field: f"wire:{field}" for field in visual_fields},
            "itemPrompt": "one authored item prompt",
            "itemSilhouetteContract": "one connected body",
            "styleGuide": "pixel art",
            "vfxIntent": "sawdust",
        },
        "generatedParentSummary": {
            **{field: f"wire:{field}" for field in summary_fields},
            "customAttackEnabled": True,
            "vanillaItemHitboxDamage": False,
        },
        "itemKnowledge": {
            "enabled": True,
            "parents": [{**{field: f"wire:{field}" for field in parent_fields}, "recipeFrame": {}, "signals": {}}],
            "resultCard": {**{field: f"wire:{field}" for field in parent_fields}, "signals": {}},
        },
        "recipeMeta": {
            **{field: f"wire:{field}" for field in recipe_meta_fields},
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
                **{field: f"wire:{field}" for field in vfx_budget_fields},
                "quality": "high",
                "renderQuality": "high",
            },
            "debug": {
                **{field: f"wire:{field}" for field in vfx_debug_fields},
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


def _check_delivery_rejects_scalar_for_csharp_object_contract() -> None:
    payload = {
        "id": "g_scalar_archetype",
        "name": "Scalar Archetype",
        "runtimeArchetype": "consumable_melee_projectile",
    }

    assert _strict_csharp_unmapped_paths(payload) == [
        "$.runtimeArchetype -> expected RuntimeArchetypeSpec object"
    ]
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
    assert _strict_csharp_unmapped_paths(object_payload) == [
        "$.runtimeArchetype.futureNestedKey -> RuntimeArchetypeSpec"
    ]
    projected = world_storage.sanitize_recipe_for_delivery(object_payload)
    assert projected["runtimeArchetype"] == {
        "schema": "infini.runtime-archetype.v1",
        "source": "generated",
        "family": "custom_executor",
        "channelled": True,
        "overrideKnobs": {"orbitRadius": 4.5},
    }
    assert _strict_csharp_unmapped_paths(projected) == []
    assert "futureNestedKey" in object_payload["runtimeArchetype"]


def _check_world_recipe_health_index_tracks_runtime_assets_and_contracts(tmp_path: Path) -> None:
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
    health_index = json.loads((root / "health.json").read_text(encoding="utf-8"))
    world_index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert stored["recipeHealth"]["status"] == "healthy"
    assert health_index["counts"]["healthy"] == 1
    assert health_index["recipes"]["r_health"]["runtime"]["delivery"] == "thrust"
    assert world_index["recipes"]["r_health"]["health"]["ok"] is True

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
    '_check_delivery_matches_strict_nested_csharp_specs',
    '_check_delivery_rejects_scalar_for_csharp_object_contract',
    '_check_world_recipe_health_index_tracks_runtime_assets_and_contracts'
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
