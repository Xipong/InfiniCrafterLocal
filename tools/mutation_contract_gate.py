#!/usr/bin/env python3
"""Prove the contract checker fails on representative agent mistakes.

This gate never edits the checkout. It supplies in-memory source mutations to the
same extractor used by release validation and expects each mutation to turn the
report red. A mutation that remains green is itself a failed safety gate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import contract_parity

ROOT = Path(__file__).resolve().parents[1]


def _replace_once(path: Path, old: str, new: str) -> str:
    source = path.read_text(encoding="utf-8-sig")
    if source.count(old) < 1:
        raise RuntimeError(f"mutation anchor missing in {path}: {old!r}")
    return source.replace(old, new, 1)


def _run_mutation(name: str, overrides: dict[Path, str], expected: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    contract_parity.SOURCE_OVERRIDES.clear()
    contract_parity.SOURCE_OVERRIDES.update({path.resolve(): text for path, text in overrides.items()})
    try:
        report = contract_parity.build_report()
    finally:
        contract_parity.SOURCE_OVERRIDES.clear()
    caught = (not report["ok"]) and expected(report)
    return {
        "name": name,
        "caught": caught,
        "errors": report.get("errors", [])[:12],
    }


def build_report() -> dict[str, Any]:
    projection = ROOT / "LocalGenerator/infini_local/pipelines/combine_gameplay.py"
    normalize = ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs"
    net = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.NetSync.cs"
    child = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedChildSpecPolicy.cs"
    dto = ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs"
    executor = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.ChargeRelease.cs"

    net_source = net.read_text(encoding="utf-8-sig")
    old_pair = "_spec.ChargeTicks = reader.ReadInt32();\n            _spec.ChargePowerMultiplier = reader.ReadSingle();"
    new_pair = "_spec.ChargePowerMultiplier = reader.ReadSingle();\n            _spec.ChargeTicks = reader.ReadInt32();"
    if old_pair not in net_source:
        raise RuntimeError("network mutation anchor missing")

    rows = [
        _run_mutation(
            "python_projection_loses_charge_ticks",
            {projection: _replace_once(projection, '"chargeTicks": max(', '"chargeTicksBROKEN": max(')},
            lambda r: any("chargeTicks" in e and "pythonProjection" in e for e in r["errors"]),
        ),
        _run_mutation(
            "csharp_dto_loses_charge_ticks",
            {dto: _replace_once(
                dto,
                "public int ChargeTicks { get; set; } = 45;",
                "public int ChargeTicksBROKEN { get; set; } = 45;",
            )},
            lambda r: any("chargeTicks" in e and "csharpDto" in e for e in r["errors"]),
        ),
        _run_mutation(
            "csharp_default_drifts_from_python",
            {dto: _replace_once(
                dto,
                "public int ChargeTicks { get; set; } = 45;",
                "public int ChargeTicks { get; set; } = 46;",
            )},
            lambda r: any("chargeTicks" in e and "default mismatch" in e for e in r["errors"]),
        ),
        _run_mutation(
            "csharp_normalize_replaces_charge_ticks_with_constant",
            {normalize: _replace_once(
                normalize,
                "Attack.ChargeTicks = ClampInt(Attack.ChargeTicks, 1, 300);",
                "Attack.ChargeTicks = 1;",
            )},
            lambda r: any("chargeTicks" in e and "csharpNormalize" in e for e in r["errors"]),
        ),
        _run_mutation(
            "csharp_executor_stops_reading_charge_ticks",
            {executor: executor.read_text(encoding="utf-8-sig").replace(
                "_spec.ChargeTicks",
                "_spec.ChargeTicksBROKEN",
            )},
            lambda r: any("chargeTicks" in e and "executorRead" in e for e in r["errors"]),
        ),
        _run_mutation(
            "projectile_network_read_order_swapped",
            {net: net_source.replace(old_pair, new_pair, 1)},
            lambda r: any("network order mismatch" in e for e in r["errors"]),
        ),
        _run_mutation(
            "projectile_network_extra_read_added",
            {net: net_source.replace(
                "_spec.ChargePowerMultiplier = reader.ReadSingle();",
                "_spec.ChargePowerMultiplier = reader.ReadSingle();\n            _spec.ChargeTicks = reader.ReadInt32();",
                1,
            )},
            lambda r: any("network order mismatch" in e or "network field count mismatch" in e for e in r["errors"]),
        ),
        _run_mutation(
            "dust_explicit_zero_destroyed",
            {normalize: _replace_once(
                normalize,
                "Attack.DustSpawnDenom = Attack.DustSpawnDenom <= 0 ? 0 : ClampInt(Attack.DustSpawnDenom, 2, 240);",
                "Attack.DustSpawnDenom = ClampInt(Attack.DustSpawnDenom, 1, 240);",
            )},
            lambda r: any("dustSpawnDenom" in e and "csharpNormalize" in e for e in r["errors"]),
        ),
        _run_mutation(
            "sentry_shot_keeps_sentry_family",
            {child: _replace_once(
                child,
                "shot.RuntimeFamily = GeneratedRuntimeFamilyPolicy.Shoot;",
                "shot.RuntimeFamily = GeneratedRuntimeFamilyPolicy.Sentry;",
            )},
            lambda r: any("sentryShot" in e or ("runtimeFamily" in e and "childPolicy" in e) for e in r["errors"]),
        ),
    ]
    return {
        "schema": "infini.contract-mutation-gate.v1",
        "ok": all(row["caught"] for row in rows),
        "mutations": rows,
    }


def main() -> int:
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
