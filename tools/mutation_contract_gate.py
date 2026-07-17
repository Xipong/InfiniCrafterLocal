#!/usr/bin/env python3
"""Prove the contract checker fails on representative agent mistakes.

This gate never edits the checkout. It supplies in-memory source mutations to the
same extractor used by release validation and expects each mutation to turn the
report red. A mutation that remains green is itself a failed safety gate.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

import contract_parity  # noqa: E402
from infini_local.qa.csharp_delivery_contract import (  # noqa: E402
    CSharpContractGraph,
    load_csharp_contract_graph,
)


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
        "kind": "source",
        "caught": caught,
        "errors": report.get("errors", [])[:12],
    }


def _run_delivery_mutation(
    graph: CSharpContractGraph,
    name: str,
    payload: dict[str, Any],
    expected_error: str,
) -> dict[str, Any]:
    errors = graph.validate(payload)
    return {
        "name": name,
        "kind": "delivered_json",
        "caught": expected_error in errors,
        "expectedError": expected_error,
        "errors": errors[:12],
    }


def _run_parser_mask_probe() -> dict[str, Any]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "GeneratedItemData.cs").write_text(
            'public sealed class GeneratedItemData { public int Damage { get; set; } = 0; '
            '/* public int Phantom { get; set; } = 1; */ '
            'public string Note => "public int StringPhantom { get; set; }"; }',
            encoding="utf-8",
        )
        graph = load_csharp_contract_graph(root)
    actual = sorted(graph.classes["GeneratedItemData"].properties)
    return {
        "name": "delivery_parser_ignores_comment_and_string_tokens",
        "kind": "parser_integrity",
        "caught": actual == ["damage"],
        "expectedProperties": ["damage"],
        "actualProperties": actual,
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
        _run_parser_mask_probe(),
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
    graph = load_csharp_contract_graph()
    rows.extend([
        _run_delivery_mutation(
            graph,
            "delivery_object_expected_scalar_supplied",
            {"visual": "not-an-object"},
            "$.visual: expected object, got string",
        ),
        _run_delivery_mutation(
            graph,
            "delivery_unknown_nested_field",
            {"visual": {"futureNestedKey": True}},
            "$.visual.futureNestedKey: unknown field for VisualSpec",
        ),
        _run_delivery_mutation(
            graph,
            "delivery_string_expected_number_supplied",
            {"visual": {"inventoryScale": "large"}},
            "$.visual.inventoryScale: expected number, got string",
        ),
        _run_delivery_mutation(
            graph,
            "delivery_list_expected_string_supplied",
            {"visual": {"palette": "not-a-list"}},
            "$.visual.palette: expected array, got string",
        ),
        _run_delivery_mutation(
            graph,
            "delivery_dictionary_expected_list_supplied",
            {"visual": {"palette": {}}},
            "$.visual.palette: expected array, got object",
        ),
        _run_delivery_mutation(
            graph,
            "delivery_nested_list_element_wrong_type",
            {"visual": {"palette": [1]}},
            "$.visual.palette[0]: expected string, got integer",
        ),
        _run_delivery_mutation(
            graph,
            "delivery_int32_overflow",
            {"schemaVersion": 2**40},
            "$.schemaVersion: integer 1099511627776 out of range for int [-2147483648, 2147483647]",
        ),
        _run_delivery_mutation(
            graph,
            "delivery_single_overflow",
            {"visual": {"inventoryScale": 1e100}},
            "$.visual.inventoryScale: number 1e+100 out of range for float [-3.4028234663852886e+38, 3.4028234663852886e+38]",
        ),
        _run_delivery_mutation(
            graph,
            "delivery_nonfinite_number",
            {"visual": {"inventoryScale": float("nan")}},
            "$.visual.inventoryScale: non-finite number nan is invalid for float",
        ),
        _run_delivery_mutation(
            graph,
            "delivery_case_insensitive_alias_duplicate",
            {"name": "one", "Name": "two"},
            "$.Name: duplicate field for GeneratedItemData.name (already supplied as $.name)",
        ),
    ])
    return {
        "schema": "infini.contract-mutation-gate.v3",
        "ok": all(row["caught"] for row in rows),
        "mutations": rows,
    }


def main() -> int:
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
