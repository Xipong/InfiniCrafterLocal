#!/usr/bin/env python3
"""Prove v18 safety tooling stays outside gameplay authorship/runtime semantics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

import semantic_runtime_diff

ROOT = Path(__file__).resolve().parents[1]
PY_RUNTIME = ROOT / "LocalGenerator" / "infini_local"
CS_RUNTIME = ROOT / "ModSources" / "InfiniCrafterLocal"


def _infrastructure_leaks() -> list[dict[str, Any]]:
    leaks: list[dict[str, Any]] = []
    forbidden_py = re.compile(r"(?:from|import)\s+(?:tools|config_registry|agentctl)\b|\.agent")
    for path in PY_RUNTIME.rglob("*.py"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            if forbidden_py.search(line):
                leaks.append({"file": path.relative_to(ROOT).as_posix(), "line": line_no, "text": line.strip()})
    forbidden_cs = ("ContractParity", "AgentCtl", ".agent/", "config_registry.json")
    for path in CS_RUNTIME.rglob("*.cs"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for token in forbidden_cs:
            if token in text:
                leaks.append({"file": path.relative_to(ROOT).as_posix(), "token": token})
    return leaks


def _intentional_runtime_fixes() -> list[dict[str, Any]]:
    normalize = (CS_RUNTIME / "Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8-sig")
    gameplay = (PY_RUNTIME / "pipelines/combine_gameplay.py").read_text(encoding="utf-8-sig")
    child_policy = (CS_RUNTIME / "Content/Projectiles/GeneratedChildSpecPolicy.cs").read_text(encoding="utf-8-sig")
    return [
        {
            "id": "dust-zero-remains-disabled",
            "ok": "Attack.DustSpawnDenom <= 0 ? 0 : ClampInt(Attack.DustSpawnDenom, 2, 240)" in normalize,
            "effect": "fixes v17 zero-to-one drift; does not add a new mechanic",
        },
        {
            "id": "tool-light-uses-existing-csharp-contract",
            "ok": '"holdLightStrength"' in gameplay and '"holdLightColorName"' in gameplay,
            "effect": "routes the same authored tool light into already executable GameplaySpec fields",
        },
        {
            "id": "child-transform-is-pure-policy",
            "ok": all(name in child_policy for name in ("SanitizeGenericGameplayChild", "ConfigureSentryShot", "ConfigureChargeReleasedShot")),
            "effect": "moves existing child reset semantics to a single pure owner",
        },
    ]




def _opt_in_runtime_selftest() -> dict[str, Any]:
    path = CS_RUNTIME / "Common/Systems/InfiniAgentContractSelfTestSystem.cs"
    source = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
    checks = {
        "environmentGuard": 'Environment.GetEnvironmentVariable(EnabledEnv), "1"' in source,
        "noProjectileSpawn": "Projectile.NewProjectile" not in source,
        "noPlayerMutation": "Main.LocalPlayer" not in source and "GetModPlayer" not in source,
        "writesMachineReport": "infini.tml-runtime-selftest.v1" in source and "INFINI_AGENT_SELFTEST_REPORT" in source,
        "testsCompiledContracts": all(token in source for token in (
            "GeneratedItemData.FromJson", "VfxManifestSpec.FromJson",
            "ConfigureSentryShot", "ConfigureChargeReleasedShot", "DustSpawnDenom",
        )),
    }
    return {
        "ok": all(checks.values()),
        "file": path.relative_to(ROOT).as_posix(),
        "checks": checks,
        "defaultRuntimeEffect": "none; PostSetupContent returns unless INFINI_AGENT_SELFTEST=1",
    }

def build_report() -> dict[str, Any]:
    semantic = semantic_runtime_diff.build_report()
    leaks = _infrastructure_leaks()
    fixes = _intentional_runtime_fixes()
    runtime_selftest = _opt_in_runtime_selftest()
    return {
        "schema": "infini.runtime-impact.v1",
        "ok": bool(semantic.get("ok")) and not leaks and all(row["ok"] for row in fixes) and runtime_selftest["ok"],
        "gameplaySemanticBaseline": semantic,
        "infrastructureImportedByRuntime": leaks,
        "intentionalRuntimeCorrections": fixes,
        "optInTmlRuntimeSelfTest": runtime_selftest,
        "runtimePolicy": {
            "toolsAndAgentControlPlaneLoadedByGame": False,
            "schemasGenerateCsharp": False,
            "validatorsAuthorGameplay": False,
            "newCapabilityPath": "catalog -> typed raw boundary -> compiler/projection -> C# DTO/normalize/network/executor -> lifecycle/property proof",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
