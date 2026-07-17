from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECTILE_PATH = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs"
PROJECTILE_STATE_PATH = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.cs"
ITEM_PATH = ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _method_body(source: str, marker: str) -> str:
    """Return one C# method body without depending on whitespace or nearby methods."""
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    raise AssertionError(f"unterminated C# method after {marker!r}")


def _contract_check_projectile_aoe_executes_on_hit_not_expiry() -> None:
    source = _source(PROJECTILE_PATH)
    on_hit = _method_body(source, "public override void OnHitNPC")
    on_kill = _method_body(source, "public override void OnKill")
    aoe = _method_body(source, "private void ApplyAuthoredOnHitAoeDamage")

    assert "ApplyAuthoredOnHitAoeDamage" in on_hit
    assert "target.Center" in on_hit and "target.whoAmI" in on_hit
    assert "AoeDamageRadiusPx" in aoe
    assert "radius * 2" in aoe
    assert aoe.count("Projectile.Damage()") == 1
    assert "AoeDamageRadiusPx" not in on_kill
    assert "Projectile.Damage()" not in on_kill


def _contract_check_projectile_aoe_is_authoritative_non_recursive_and_restores_hitbox() -> None:
    source = _source(PROJECTILE_PATH)
    state = _source(PROJECTILE_STATE_PATH)
    colliding = _method_body(source, "public override bool? Colliding")
    modify_hitbox = _method_body(source, "public override void ModifyDamageHitbox")
    can_hit = _method_body(source, "public override bool? CanHitNPC")
    on_hit = _method_body(source, "public override void OnHitNPC")
    aoe = _method_body(source, "private void ApplyAuthoredOnHitAoeDamage")

    assert "_applyingAuthoredAoeDamage" in state
    assert "_applyingAuthoredAoeDamage" in colliding and "projHitbox.Intersects(targetHitbox)" in colliding
    assert "_applyingAuthoredAoeDamage" in modify_hitbox
    assert "_applyingAuthoredAoeDamage" in can_hit
    assert "if (_applyingAuthoredAoeDamage)" in on_hit
    assert "InfiniRuntimeAuthority.ShouldRunNpcGameplay()" in aoe
    assert "Math.Clamp" in aoe and ", 0, 160" in aoe
    assert "_applyingAuthoredAoeDamage" in aoe
    assert "Projectile.localNPCImmunity" in aoe
    assert "directTargetWhoAmI" in aoe
    assert "try" in aoe and "finally" in aoe
    assert "originalCenter" in aoe
    assert "originalWidth" in aoe and "originalHeight" in aoe


def _contract_check_aura_uses_the_shared_authored_radius_without_second_damage() -> None:
    source = _source(PROJECTILE_PATH)
    on_hit = _method_body(source, "public override void OnHitNPC")
    aura = _method_body(source, "private void AuraPulse")
    aoe = _method_body(source, "private void ApplyAuthoredOnHitAoeDamage")

    assert on_hit.count("ApplyAuthoredOnHitAoeDamage") == 1
    assert "AoeDamageRadiusPx" in aura
    assert "Projectile.Damage()" not in aura
    assert "ResizeProjectilePreserveCenter" not in aura
    assert aoe.count("Projectile.Damage()") == 1


def _contract_check_swing_aoe_consumes_radius_with_owner_authority_and_target_cap() -> None:
    source = _source(ITEM_PATH)
    on_hit = _method_body(source, "public override void OnHitNPC")
    aoe = _method_body(source, "private void ApplyGeneratedSwingAoeDamage")

    assert "ApplyGeneratedSwingAoeDamage" in on_hit
    assert "attack.AoeDamageRadiusPx" in aoe
    assert "radius * 2" in aoe
    assert "InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(player)" in aoe
    assert "_applyingGeneratedSwingAoeDamage" in aoe
    assert "npc.whoAmI == directTarget.whoAmI" in aoe
    assert "MaxGeneratedAoeTargetsPerHit" in aoe
    assert aoe.count("player.ApplyDamageToNPC") == 1
    assert "try" in aoe and "finally" in aoe


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_248_aoe_execution_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            "_contract_check_projectile_aoe_executes_on_hit_not_expiry",
            "_contract_check_projectile_aoe_is_authoritative_non_recursive_and_restores_hitbox",
            "_contract_check_aura_uses_the_shared_authored_radius_without_second_damage",
            "_contract_check_swing_aoe_consumes_radius_with_owner_authority_and_target_cap",
        ),
        require_all=True,
    )
