from __future__ import annotations

from pathlib import Path
import re

from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch
from infini_local.core.sound_catalog import (
    ALL_SOUND_IDS,
    IMPACT_SOUND_IDS,
    SOUND_CATALOG_SOURCE,
    USE_SOUND_IDS,
)
from infini_local.pipelines.llm_authoring_prompt import engine_runtime_capability_contract_for_llm
from infini_local.pipelines.presentation_sound import attach_presentation_and_sound

ROOT = Path(__file__).resolve().parents[2]


def _contract_check_sound_catalog_is_large_but_canonical_not_alias_driven() -> None:
    assert len(USE_SOUND_IDS) >= 55
    assert len(IMPACT_SOUND_IDS) >= 30
    assert len(ALL_SOUND_IDS) >= 85
    assert SOUND_CATALOG_SOURCE == "terraria_vanilla"
    for forbidden in [
        "terra_blade", "last_prism", "starfury", "stardust_dragon",
        "zenith", "crystal_serpent", "hornet", "imp", "optic", "spider",
    ]:
        assert forbidden not in ALL_SOUND_IDS




def _contract_check_python_and_csharp_exact_catalogs_match_and_have_real_sound_diversity() -> None:
    source = (ROOT / "ModSources/InfiniCrafterLocal/Common/Audio/InfiniSoundLibrary.cs").read_text(encoding="utf-8")
    pairs = re.findall(r'\["([a-z0-9_]+)"\]\s*=\s*SoundID\.(Item\d+)', source)
    assert {catalog_id for catalog_id, _ in pairs} == set(ALL_SOUND_IDS)
    # Guard against a fake-large semantic list that collapses back into a few clips.
    assert len({sound_id for _, sound_id in pairs}) >= 65
    assert "PitchVariance = safeVariance" in source
    assert "style.Volume * authoredVolumeScale * volumeScale" in source
    assert "style.Pitch + authoredPitch + pitchJitter" in source
    assert "Math.Max(style.PitchVariance, authoredPitchVariance)" in source

def _contract_check_llm_card_exposes_exact_sound_ids_and_controls() -> None:
    card = engine_runtime_capability_contract_for_llm({}, {}, {})
    sound = card["soundCatalog"]
    assert sound["catalogSource"] == "terraria_vanilla"
    assert "melee_energy_slash" in sound["useCatalogIds"]["melee_and_thrown"]
    assert "impact_electric" in sound["impactCatalogIds"]["elemental"]
    assert sound["authoringFields"]["soundVolume"].startswith("0.05..1.0")
    assert sound["placement"] == "Put audio fields in params of the primary attack call."
    assert "not a generic default" in sound["selectionRule"]
    assert "no names/prose/taxonomy" in sound["selectionRule"]


def _contract_check_compiler_preserves_exact_authored_audio_and_rejects_unknown_id() -> None:
    authored = {
        "runtimePlan": {
            "engineCalls": [
                {
                    "fn": "cast_magic_weapon",
                    "params": {
                        "family": "staff",
                        "effect": "electric",
                        "soundUseCatalogId": "laser_space",
                        "soundImpactCatalogId": "impact_electric",
                        "soundVolume": 1.0,
                        "soundPitch": 0.2,
                        "soundPitchVariance": 0.24,
                    },
                }
            ]
        }
    }
    patch = compile_runtime_plan_to_genome_patch(authored)
    assert patch["soundUseCatalogId"] == "laser_space"
    assert patch["soundImpactCatalogId"] == "impact_electric"
    assert patch["soundCatalogSource"] == "terraria_vanilla"
    assert patch["soundVolume"] == 1.0
    assert patch["soundPitch"] == 0.2
    assert patch["soundPitchVariance"] == 0.24

    invalid = {
        "runtimePlan": {
            "engineCalls": [
                {
                    "fn": "perform_melee_attack",
                    "params": {
                        "family": "broadsword",
                        "soundUseCatalogId": "terra_blade_super_sound",
                        "soundImpactCatalogId": "boss_explosion_9000",
                    },
                }
            ]
        }
    }
    rejected = compile_runtime_plan_to_genome_patch(invalid)
    assert rejected["soundUseCatalogId"] == "melee_swing"
    assert rejected["soundImpactCatalogId"] == "impact_soft"
    assert {x["field"] for x in rejected["rejectedSoundCatalogIds"]} == {
        "soundUseCatalogId",
        "soundImpactCatalogId",
    }


def _contract_check_sound_fallback_ignores_name_tooltip_and_taxonomy_prose() -> None:
    base = {
        "name": "Completely Different Name",
        "tooltip": "laser shotgun zenith last prism explosion",
        "attack": {
            "enabled": True,
            "runtimeFamily": "thrust",
            "effect": "electric",
            "onHit": "lightning_arc",
            "genome": {
                "runtimeFamily": "thrust",
                "effect": "electric",
                "onHit": "lightning_arc",
            },
        },
    }
    normalized = attach_presentation_and_sound(base)
    attack = normalized["attack"]
    assert attack["soundUseCatalogId"] == "melee_thrust"
    assert attack["soundImpactCatalogId"] == "impact_electric"
    assert attack["soundPitchVariance"] == 0.18
    assert "soundProfile" not in normalized


def _contract_check_csharp_call_sites_do_not_feed_taxonomy_into_sound_resolution() -> None:
    apply = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs").read_text(encoding="utf-8")
    impact = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")
    helper = apply.split("private Terraria.Audio.SoundStyle UseSoundForCatalog", 1)[1]
    play = impact.split("private void PlayImpactSound", 1)[1].split("public override void OnKill", 1)[0]
    for forbidden in ["WeaponSubfamily", "ProjectileFamily", "AttackPatternTags", "taxonomy"]:
        assert forbidden not in helper
        assert forbidden not in play
    assert "Attack.SoundUseCatalogId" in helper
    assert "_spec.SoundImpactCatalogId" in play
    for removed in ["UseSoundProfile", "ImpactSoundProfile", "legacyProfile", "Attack.SoundUse,", "_spec.SoundImpact,"]:
        assert removed not in helper
        assert removed not in play



def _contract_check_sound_contract_has_no_text_query_side_channel() -> None:
    python_sources = [
        ROOT / "LocalGenerator/infini_local/core/runtime_authoring/compiler.py",
        ROOT / "LocalGenerator/infini_local/core/runtime_authoring/semantics.py",
        ROOT / "LocalGenerator/infini_local/pipelines/combine_genome.py",
        ROOT / "LocalGenerator/infini_local/pipelines/combine_gameplay.py",
    ]
    csharp_sources = [
        ROOT / "ModSources/InfiniCrafterLocal/Common/Audio/InfiniSoundLibrary.cs",
        ROOT / "ModSources/InfiniCrafterLocal/Common/Audio/InfiniFutureSoundCatalog.cs",
        ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in [*python_sources, *csharp_sources])
    for forbidden in ["soundUseSearchQuery", "soundImpactSearchQuery", "SoundUseSearchQuery", "SoundImpactSearchQuery", "QueryText", "SoundProfileSpec", "soundProfile.v3"]:
        assert forbidden not in combined


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_exact_sound_catalog_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_sound_catalog_is_large_but_canonical_not_alias_driven',
            '_contract_check_python_and_csharp_exact_catalogs_match_and_have_real_sound_diversity',
            '_contract_check_llm_card_exposes_exact_sound_ids_and_controls',
            '_contract_check_compiler_preserves_exact_authored_audio_and_rejects_unknown_id',
            '_contract_check_sound_fallback_ignores_name_tooltip_and_taxonomy_prose',
            '_contract_check_csharp_call_sites_do_not_feed_taxonomy_into_sound_resolution',
            '_contract_check_sound_contract_has_no_text_query_side_channel',
        ),
    )
