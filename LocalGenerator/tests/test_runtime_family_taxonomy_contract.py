from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PY_ROOT = ROOT / "LocalGenerator" / "infini_local"
CS_ROOT = ROOT / "ModSources" / "InfiniCrafterLocal"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _assigned_names(path: Path) -> set[str]:
    tree = ast.parse(_read(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _contract_check_runtime_authoring_package_exposes_only_public_api() -> None:
    package_path = PY_ROOT / "core" / "runtime_authoring" / "__init__.py"
    tree = ast.parse(_read(package_path))
    exported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            assert isinstance(node.value, (ast.List, ast.Tuple))
            exported = {item.value for item in node.value.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)}

    assert exported == {
        "ENGINE_FN_CATALOG_V2",
        "ENGINE_RUNTIME_API_VERSION",
        "all_calls",
        "compile_runtime_plan_to_genome_patch",
        "compile_runtime_plan_to_genome_result",
        "compiled_runtime_contract",
        "find_call",
        "infer_attack_pattern_from_runtime",
        "normalize_runtime_plan_inplace",
        "runtime_plan",
        "runtime_plan_provenance_report",
        "runtime_plan_quality_report",
        "runtime_plan_validation_report",
        "structural_repair_runtime_plan_inplace",
    }
    assert not any(name.startswith("_") for name in exported)

    package_dir = PY_ROOT / "core" / "runtime_authoring"
    for path in PY_ROOT.rglob("*.py"):
        if path == package_path or package_dir in path.parents:
            continue
        source_tree = ast.parse(_read(path))
        for node in ast.walk(source_tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "infini_local.core.runtime_authoring", path


def _contract_check_runtime_family_policy_is_strict_and_capability_based() -> None:
    from infini_local.core.runtime_family_policy import (
        CANONICAL_RUNTIME_FAMILIES,
        canonical_runtime_family,
        is_canonical_runtime_family,
        is_item_bodied_projectile_family,
        is_projectile_owned_family,
        uses_held_projectile_family,
    )

    assert CANONICAL_RUNTIME_FAMILIES == frozenset(
        {"none", "swing", "thrust", "returning", "flail", "yoyo", "whip", "shoot", "cast", "beam", "charge_release", "overhead_barrage", "throw", "summon", "sentry"}
    )
    assert canonical_runtime_family(" RETURNING ") == "returning"
    assert canonical_runtime_family("boomerang") == "none"
    assert canonical_runtime_family("spear") == "none"
    assert not is_canonical_runtime_family("boomerang")
    assert is_projectile_owned_family("thrust")
    assert not is_projectile_owned_family("swing")
    assert uses_held_projectile_family("thrust")
    assert uses_held_projectile_family("whip")
    assert is_projectile_owned_family("beam")
    assert uses_held_projectile_family("beam")
    assert is_projectile_owned_family("charge_release")
    assert uses_held_projectile_family("charge_release")
    assert not is_item_bodied_projectile_family("charge_release")
    assert is_projectile_owned_family("sentry")
    assert not uses_held_projectile_family("sentry")
    assert not is_item_bodied_projectile_family("sentry")
    assert is_projectile_owned_family("overhead_barrage")
    assert canonical_runtime_family("unknown_runtime_family") == "none"
    assert not uses_held_projectile_family("overhead_barrage")
    assert not is_item_bodied_projectile_family("beam")
    assert is_item_bodied_projectile_family("returning")
    assert is_item_bodied_projectile_family("throw")
    assert not is_item_bodied_projectile_family("flail")


def _contract_check_onhit_codes_are_unique_and_heal_normalizes_to_lifesteal() -> None:
    from infini_local.core.runtime_authoring.vocabulary import normalize_authoring_enum
    from infini_local.core.runtime_executor_vocabulary import ONHITS, ONHIT_CODE

    assert "heal" not in ONHITS
    assert normalize_authoring_enum("heal", "onHit") == "lifesteal"
    assert len(set(ONHIT_CODE.values())) == len(ONHIT_CODE)


def _contract_check_executor_vocabulary_has_one_injective_owner() -> None:
    from infini_local.core.runtime_authoring.vocabulary import normalize_authoring_enum
    from infini_local.core.runtime_executor_vocabulary import (
        EFFECTS,
        EFFECT_CODE,
        MOVEMENTS,
        MOVEMENT_CODE,
        ONHITS,
        ONHIT_CODE,
    )

    assert MOVEMENTS == frozenset(MOVEMENT_CODE)
    assert EFFECTS == frozenset(EFFECT_CODE)
    assert ONHITS == frozenset(ONHIT_CODE)
    for codes in (MOVEMENT_CODE, EFFECT_CODE, ONHIT_CODE):
        assert len(set(codes.values())) == len(codes)

    assert "dust" not in EFFECTS
    assert normalize_authoring_enum("dust", "effect") == "smoke"

    from infini_local.pipelines.presentation_sound import _EFFECT_PRESENTATION

    assert set(_EFFECT_PRESENTATION) == EFFECTS

    owner = PY_ROOT / "core" / "runtime_executor_vocabulary.py"
    old_owners = [
        PY_ROOT / "core" / "runtime_authoring" / "vocabulary.py",
        PY_ROOT / "pipelines" / "pipeline_runtime_constants.py",
    ]
    required = {"MOVEMENTS", "EFFECTS", "ONHITS", "MOVEMENT_CODE", "EFFECT_CODE", "ONHIT_CODE"}
    assert required <= _assigned_names(owner)
    for old_owner in old_owners:
        assert not (required & _assigned_names(old_owner))

    canonical_names = {"MOVEMENTS", "EFFECTS", "ONHITS", "RUNTIME_FAMILIES"}
    forbidden_modules = {
        "infini_local.core.runtime_authoring.vocabulary",
        "infini_local.core.runtime_authoring.schema",
    }
    for path in (PY_ROOT / "core" / "runtime_authoring").glob("*.py"):
        tree = ast.parse(_read(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in forbidden_modules:
                assert not (canonical_names & {alias.name for alias in node.names}), path


def _contract_check_authored_zero_is_not_replaced_by_attack_payload_defaults() -> None:
    from infini_local.pipelines.combine_gameplay import _authored_float_or_default

    assert _authored_float_or_default({"radius": 0}, "radius", 24) == 0.0
    assert _authored_float_or_default({"radius": "0"}, "radius", 24) == 0.0
    assert _authored_float_or_default({}, "radius", 24) == 24.0


def _contract_check_runtime_presentation_policy_projects_canonical_families() -> None:
    from infini_local.core.runtime_family_policy import CANONICAL_RUNTIME_FAMILIES, runtime_family_profile
    from infini_local.pipelines.runtime_presentation_policy import runtime_presentation_defaults

    assert all(runtime_family_profile(family).name == family for family in CANONICAL_RUNTIME_FAMILIES)
    assert runtime_family_profile("thrust").held_projectile
    assert runtime_family_profile("returning").item_bodied_projectile
    assert runtime_family_profile("boomerang").name == "none"

    assert runtime_presentation_defaults("thrust", "melee") == {
        "useStyle": 5,
        "heldVisibility": "show_projectile",
        "releaseTiming": "instant",
        "handPose": "two_hand",
    }
    assert runtime_presentation_defaults("returning", "melee")["handPose"] == "throwing"
    assert runtime_presentation_defaults("returning", "melee")["releaseTiming"] == "early"
    assert runtime_presentation_defaults("cast", "magic")["handPose"] == "staff"
    assert runtime_presentation_defaults("shoot", "ranged")["handPose"] == "held_out"
    assert runtime_presentation_defaults("overhead_barrage", "ranged", "shoot")["handPose"] == "held_out"
    assert runtime_presentation_defaults("overhead_barrage", "magic", "cast")["handPose"] == "staff"
    assert runtime_presentation_defaults("overhead_barrage", "melee", "swing")["handPose"] == "short_weapon"
    assert runtime_presentation_defaults("overhead_barrage", "melee", "swing")["useStyle"] == 1
    assert runtime_presentation_defaults("swing", "melee")["useStyle"] == 1
    assert runtime_presentation_defaults("boomerang", "melee")["handPose"] == "short_weapon"

    presentation_owner = PY_ROOT / "pipelines" / "runtime_presentation_policy.py"
    assert not {name for name in _assigned_names(presentation_owner) if name.endswith("_FAMILIES")}


def _contract_check_alias_vocabularies_have_one_authoring_boundary_owner() -> None:
    vocabulary = PY_ROOT / "core" / "runtime_authoring" / "vocabulary.py"
    schema = PY_ROOT / "core" / "runtime_authoring" / "schema.py"
    pipeline_constants = PY_ROOT / "pipelines" / "pipeline_runtime_constants.py"
    alias_names = {"MOVEMENT_ALIASES", "DELIVERY_ALIASES", "EFFECT_ALIASES", "ONHIT_ALIASES"}

    assert alias_names <= _assigned_names(vocabulary)
    assert not (alias_names & _assigned_names(schema))
    assert not (alias_names & _assigned_names(pipeline_constants))

    consumers = [
        PY_ROOT / "core" / "runtime_authoring" / "schema.py",
        PY_ROOT / "core" / "runtime_authoring" / "common.py",
        PY_ROOT / "pipelines" / "combine_genome.py",
    ]
    for consumer in consumers:
        assert not any(name in _read(consumer) for name in alias_names), consumer
    for consumer in consumers[1:]:
        assert "normalize_authoring_enum" in _read(consumer), consumer


def _contract_check_visual_asset_plan_consumes_only_canonical_runtime_families() -> None:
    source = _read(PY_ROOT / "pipelines" / "visual_asset_plan.py")
    forbidden_alias_table = "PROJECTILE_FAMILY_" + "ALIASES"
    assert forbidden_alias_table not in source
    assert "canonical_projectile_runtime_family" not in source
    assert "is_item_bodied_projectile_family" in source
    assert "noncanonical_runtime_family" in source


def _contract_check_genome_validation_rejects_noncanonical_runtime_family() -> None:
    from infini_local.pipelines.combine_genome import genome_defects

    data = {
        "attack": {
            "genome": {
                "delivery": "throw",
                "runtimeFamily": "boomerang",
                "movement": "boomerang",
                "effect": "dust",
                "onHit": "none",
                "useTimeTicks": 24,
                "shotCount": 1,
                "pierce": 1,
                "aoeRadiusTiles": 0,
                "lifetimeTicks": 90,
                "rangeTiles": 30,
                "reliability": 1,
                "selfLockTicks": 0,
                "missPunish": 0,
            }
        }
    }
    defects = genome_defects(data)
    assert "unsupported attack.genome.runtimeFamily='boomerang'" in defects

    data["attack"]["genome"]["runtimeFamily"] = "none"
    defects = genome_defects(data)
    assert "unsupported attack.genome.runtimeFamily='none'" in defects

    source = _read(PY_ROOT / "pipelines" / "combine_genome.py")
    assert "Legacy combat-genome compatibility" not in source


def _contract_check_csharp_runtime_family_policy_is_the_only_family_vocab_owner() -> None:
    policy_path = CS_ROOT / "Common" / "Models" / "GeneratedRuntimeFamilyPolicy.cs"
    policy = _read(policy_path)
    assert "internal static class GeneratedRuntimeFamilyPolicy" in policy
    assert "IsProjectileOwned" in policy
    assert "UsesHeldProjectile" in policy
    assert "UsesItemSpriteAsProjectile" in policy

    from infini_local.core.runtime_family_policy import (
        CANONICAL_RUNTIME_FAMILIES,
        HELD_PROJECTILE_RUNTIME_FAMILIES,
        ITEM_BODIED_PROJECTILE_RUNTIME_FAMILIES,
        PROJECTILE_OWNED_RUNTIME_FAMILIES,
    )

    constants = dict(re.findall(r'public const string (\w+) = "([^"]+)";', policy))
    assert set(constants.values()) == set(CANONICAL_RUNTIME_FAMILIES)

    profile_rows = re.findall(
        r"\[(\w+)\]\s*=\s*new\(\1,\s*(true|false),\s*(true|false),\s*(true|false),\s*GeneratedHeldRenderRole\.(\w+)\)",
        policy,
    )
    assert len(profile_rows) == len(CANONICAL_RUNTIME_FAMILIES)
    profiles = {
        constants[name]: (projectile == "true", held == "true", item_bodied == "true", role)
        for name, projectile, held, item_bodied, role in profile_rows
    }
    assert {name for name, values in profiles.items() if values[0]} == set(PROJECTILE_OWNED_RUNTIME_FAMILIES)
    assert {name for name, values in profiles.items() if values[1]} == set(HELD_PROJECTILE_RUNTIME_FAMILIES)
    assert {name for name, values in profiles.items() if values[2]} == set(ITEM_BODIED_PROJECTILE_RUNTIME_FAMILIES)

    consumers = [
        CS_ROOT / "Common" / "Models" / "GeneratedItemData.Normalize.cs",
        CS_ROOT / "Common" / "Models" / "GeneratedItemData.Apply.cs",
        CS_ROOT / "Content" / "Items" / "GeneratedItem.cs",
        CS_ROOT / "Content" / "Projectiles" / "GeneratedProjectile.Runtime.cs",
        CS_ROOT / "Content" / "Projectiles" / "GeneratedProjectile.Visuals.cs",
    ]
    canonical_soup = 'r is "swing" or "thrust" or "returning"'
    item_body_soup = 'family is "returning" or "thrust" or "yoyo" or "throw"'
    for path in consumers:
        source = _read(path)
        assert canonical_soup not in source, path
        assert item_body_soup not in source, path

    assert "GeneratedRuntimeFamilyPolicy.Normalize" in _read(consumers[0])
    assert "GeneratedRuntimeFamilyPolicy.UsesProjectileOnlyItemAffordance" in _read(consumers[1])
    assert "GeneratedRuntimeFamilyPolicy.Normalize" in _read(consumers[3])
    assert "GeneratedRuntimeFamilyPolicy.UsesItemSpriteAsProjectile" in _read(consumers[4])

    literal_pattern = re.compile(
        r'\b(?:RuntimeFamily|runtimeFamily)\b[^;\n]*(?:==|!=|=|\bis\b)\s*"(?:none|swing|thrust|returning|flail|yoyo|whip|shoot|cast|throw|summon)"'
    )
    for path in CS_ROOT.rglob("*.cs"):
        if path == policy_path:
            continue
        assert literal_pattern.search(_read(path)) is None, path


def _contract_check_csharp_held_render_role_has_no_keyword_router() -> None:
    policy = _read(CS_ROOT / "Common" / "Models" / "GeneratedRuntimeFamilyPolicy.cs")
    source = _read(CS_ROOT / "Common" / "Players" / "GeneratedHeldItemDrawLayer.cs")

    assert "enum GeneratedHeldRenderRole" in policy
    assert "HeldRenderRole(string? value)" in policy
    assert "enum HeldRenderRole" not in source
    assert "ResolveHeldRenderRole" in source
    assert "GeneratedRuntimeFamilyPolicy.HeldRenderRole" in source
    assert "ContainsPresentationTerm" not in source
    assert "BuildHeldRoleText" not in source
    assert "ItemUseStyleID.Shoot" in source
    assert "Gameplay?.HandPose" in source


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_runtime_family_taxonomy_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_runtime_authoring_package_exposes_only_public_api',
            '_contract_check_runtime_family_policy_is_strict_and_capability_based',
            '_contract_check_onhit_codes_are_unique_and_heal_normalizes_to_lifesteal',
            '_contract_check_executor_vocabulary_has_one_injective_owner',
            '_contract_check_authored_zero_is_not_replaced_by_attack_payload_defaults',
            '_contract_check_runtime_presentation_policy_projects_canonical_families',
            '_contract_check_alias_vocabularies_have_one_authoring_boundary_owner',
            '_contract_check_visual_asset_plan_consumes_only_canonical_runtime_families',
            '_contract_check_genome_validation_rejects_noncanonical_runtime_family',
            '_contract_check_csharp_runtime_family_policy_is_the_only_family_vocab_owner',
            '_contract_check_csharp_held_render_role_has_no_keyword_router',
        ),
    )
