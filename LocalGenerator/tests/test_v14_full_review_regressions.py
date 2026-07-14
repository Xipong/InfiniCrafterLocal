from __future__ import annotations

from pathlib import Path

from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch

ROOT = Path(__file__).resolve().parents[2]


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _contract_check_overhead_executor_imports_runtime_authority_namespace() -> None:
    source = _source("ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.OverheadBarrage.cs")
    assert "using InfiniCrafterLocal.Common.Services;" in source
    assert "InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)" in source


def _contract_check_on_expire_has_real_onkill_callsite_and_shared_lifetime_budget() -> None:
    source = _source("ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs")
    state = _source("ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.cs")
    onkill = source[source.index("public override void OnKill"):]
    assert "SpawnExpireSecondaries();" in onkill.split("}", 1)[0] or "SpawnExpireSecondaries();" in onkill[:900]
    assert "RemainingGameplayChildBudget" in source
    assert "_spawnedGameplayChildCount++" in source
    assert "private int _spawnedGameplayChildCount;" in state


def _contract_check_unknown_csharp_secondary_trigger_is_inert_not_on_hit() -> None:
    source = _source("ModSources/InfiniCrafterLocal/Common/Models/GeneratedSecondaryTriggerPolicy.cs")
    assert "_ => """ in source
    assert "NormalizeForRuntimeFamily" in source
    assert "? OnExpire : OnHit" not in source
    assert "Token(value) == OnExpire ? OnExpire : OnHit" not in source


def _contract_check_projectile_visuals_do_not_route_from_taxonomy_or_prose() -> None:
    source = _source("ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Visuals.cs")
    for forbidden in [
        "PresentationIdentityText", "WeaponSubfamily", "AttackPatternTags",
        'Contains("star")', 'Contains("fire")', 'Contains("ice")', 'Contains("magic")',
    ]:
        assert forbidden not in source
    assert "DustForEffect(_spec.EffectCode)" in source
    assert "GeneratedRuntimeFamilyPolicy.Is" in source


def _contract_check_retired_overhead_family_migration_is_absent_from_active_runtime() -> None:
    active = "\n".join([
        _source("LocalGenerator/infini_local/core/runtime_archetypes.py"),
        _source("LocalGenerator/infini_local/core/runtime_contracts.py"),
        _source("LocalGenerator/infini_local/core/runtime_overhead_barrage_policy.py"),
        _source("ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs"),
        _source("ModSources/InfiniCrafterLocal/Common/Models/GeneratedRuntimeFamilyPolicy.cs"),
    ])
    retired = "delayed_" + "starfall"
    assert retired not in active



def _contract_check_python_presentation_and_sound_use_exact_compiled_fields_only() -> None:
    source = _source("LocalGenerator/infini_local/pipelines/presentation_sound.py")
    assert "visual_text" not in source
    assert " in visual_text" not in source
    assert 'attack_mode_by_family' in source
    assert 'data["soundProfile"]' not in source
    assert "sound_profile_from_genome" not in source
    assert 'attack["soundUseCatalogId"]' in source
    assert 'attack["soundImpactCatalogId"]' in source
    assert 'sp.get("useCatalogId")' not in source
    assert 'sp.get("impactCatalogId")' not in source

def _contract_check_numeric_token_examples_are_not_secret_placeholders() -> None:
    source = _source("LocalGenerator/config.example.env")
    assert "INFINI_VISUAL_DIRECTOR_MAX_TOKENS=" in source
    assert "INFINI_VISUAL_DIRECTOR_MAX_TOKENS=PASTE_KEY_HERE" not in source
    assert "INFINI_LLM_MAX_TOKENS=PASTE_KEY_HERE" not in source
    assert "INFINI_LLM_REASONING_MAX_TOKENS=PASTE_KEY_HERE" not in source


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_v14_full_review_regressions_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_overhead_executor_imports_runtime_authority_namespace',
            '_contract_check_on_expire_has_real_onkill_callsite_and_shared_lifetime_budget',
            '_contract_check_unknown_csharp_secondary_trigger_is_inert_not_on_hit',
            '_contract_check_projectile_visuals_do_not_route_from_taxonomy_or_prose',
            '_contract_check_retired_overhead_family_migration_is_absent_from_active_runtime',
            '_contract_check_python_presentation_and_sound_use_exact_compiled_fields_only',
            '_contract_check_numeric_token_examples_are_not_secret_placeholders',
        ),
    )
