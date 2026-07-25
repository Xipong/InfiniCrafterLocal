from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CS = ROOT / "ModSources" / "InfiniCrafterLocal"


def _read(path: str) -> str:
    return (CS / path).read_text("utf-8", errors="ignore")


def test_csharp_uses_v5_dto_and_explicit_entity_dispatch() -> None:
    dto = _read("Common/Models/RuntimeProgramSpec.cs")
    item = _read("Content/Items/GeneratedItem.cs") + _read("Content/Items/GeneratedItem.UseStyle.cs")
    projectile = _read("Content/Projectiles/GeneratedProjectile.cs") + _read("Content/Projectiles/GeneratedProjectile.Executors.cs")
    executor = _read("Common/Runtime/RuntimeProgramExecutor.cs")
    assert "infini.runtime-program.v5" in dto
    assert "infini.runtime-program.wire.v1" in dto
    assert "RuntimeProgram.Entities" in item or "RuntimeProgram" in item
    assert "binding.Input" in item or "Binding" in item
    assert "Movement.Code" in projectile
    assert "ActionCode" in executor or "actionCode" in executor
    for token in ("GeneratedRuntimeFamilyPolicy", "AttackSpec", "RuntimeFamily"):
        assert token not in item + projectile + executor


def test_old_monolithic_projectile_partials_and_policies_are_deleted() -> None:
    deleted = [
        "Content/Projectiles/GeneratedProjectile.Runtime.cs",
        "Content/Projectiles/GeneratedProjectile.Impact.cs",
        "Content/Projectiles/GeneratedProjectile.ChargeRelease.cs",
        "Content/Projectiles/GeneratedProjectile.Sentry.cs",
        "Content/Projectiles/GeneratedProjectile.OverheadBarrage.cs",
        "Common/Models/GeneratedRuntimeFamilyPolicy.cs",
        "Common/Models/GeneratedChildSpecPolicy.cs",
        "Common/Models/GeneratedSecondaryTriggerPolicy.cs",
    ]
    assert all(not (CS / path).exists() for path in deleted)


def test_unknown_opcodes_fail_closed_in_csharp() -> None:
    executor = _read("Content/Projectiles/GeneratedProjectile.Executors.cs") + _read("Common/Runtime/RuntimeProgramExecutor.cs")
    assert "default:" in executor
    assert "Kill" in executor or "return false" in executor or "InvalidOperationException" in executor
