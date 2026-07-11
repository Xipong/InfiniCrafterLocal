from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "LocalGenerator"
CS = ROOT / "ModSources" / "InfiniCrafterLocal"


def test_selected_runtime_policy_owners_exist() -> None:
    required = [
        LOCAL / "infini_local/core/sound_catalog.py",
        LOCAL / "infini_local/core/balance_mode.py",
        LOCAL / "infini_local/core/runtime_secondary_policy.py",
        LOCAL / "infini_local/core/runtime_charge_release_policy.py",
        LOCAL / "infini_local/core/runtime_overhead_barrage_policy.py",
        LOCAL / "infini_local/core/runtime_sentry_policy.py",
        LOCAL / "infini_local/core/runtime_authoring/engine_call_contracts.py",
        CS / "Common/Models/GeneratedSecondaryTriggerPolicy.cs",
        CS / "Content/Projectiles/GeneratedChildSpecPolicy.cs",
        CS / "Content/Projectiles/GeneratedProjectile.ChargeRelease.cs",
        CS / "Content/Projectiles/GeneratedProjectile.OverheadBarrage.cs",
        CS / "Content/Projectiles/GeneratedProjectile.Sentry.cs",
    ]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    assert missing == []


def test_runtime_family_vocabularies_include_selected_finite_families() -> None:
    python_policy = (LOCAL / "infini_local/core/runtime_family_policy.py").read_text(encoding="utf-8")
    csharp_policy = (CS / "Common/Models/GeneratedRuntimeFamilyPolicy.cs").read_text(encoding="utf-8")
    for family in ("beam", "charge_release", "overhead_barrage", "sentry"):
        assert f'"{family}"' in python_policy
        assert f'"{family}"' in csharp_policy


def test_active_runtime_does_not_keep_prose_sound_router_fields() -> None:
    roots = [LOCAL / "infini_local", CS]
    forbidden = ("soundUseSearchQuery", "soundImpactSearchQuery", "attackPatternTags", "weaponSubfamily")
    hits: list[str] = []
    for root in roots:
        for path in root.rglob("*.py" if root == LOCAL / "infini_local" else "*.cs"):
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(ROOT).as_posix()}:{token}")
    assert hits == []


def test_flux2_klein_hybrid_profile_is_exact() -> None:
    from infini_local.desktop.settings_schema import DEFAULTS, SDCPP_EXTRA_PROFILES

    profile = SDCPP_EXTRA_PROFILES["flux2_klein4b_rx6800xt_hybrid"]
    assert "diffusion=rocm0,vae=vulkan0,te=rocm0" in profile
    assert "--params-backend te=cpu" in profile
    assert DEFAULTS["INFINI_SDCPP_STEPS"] == "4"
    assert "--diffusion-fa" not in profile


def test_agent_control_plane_treats_compile_as_completion_and_selftest_as_optional() -> None:
    agentctl = (ROOT / "tools/agentctl.py").read_text(encoding="utf-8")
    manifest = (ROOT / ".agent/manifest.json").read_text(encoding="utf-8")
    assert "dotnet.exe" in agentctl or "build_tml_windows" in agentctl
    assert "runtime self-test report is required" not in agentctl
    assert "tml_runtime_selftest" not in manifest
