from __future__ import annotations

from copy import deepcopy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from infini_local.core.boundary_models import (
    VfxManifestBoundary,
    executable_wire_view,
    runtime_plan_boundary_report,
    validate_executable_item_boundary,
    validate_vfx_manifest_boundary,
)
from infini_local.core.runtime_authoring.engine_call_contracts import (
    engine_contract_inventory,
    engine_params_model,
)
from infini_local.core.runtime_authoring.schema import ENGINE_FN_CATALOG_V2
from infini_local.qa.golden_runtime_cases import GOLDEN_RUNTIME_CASES
from infini_local.qa.runtime_proof import build_gameplay_seam_report

ROOT = Path(__file__).resolve().parents[2]


def _run_tool(relative: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / relative)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "LocalGenerator")},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, proc.stdout


def _load_tool_module(module_name: str, relative: str):
    import importlib.util

    module_path = ROOT / relative
    tools_path = str(module_path.parent)
    inserted = tools_path not in sys.path
    if inserted:
        sys.path.insert(0, tools_path)
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        previous = sys.modules.get(module_name)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous
        return module
    finally:
        if inserted:
            sys.path.remove(tools_path)


def _contract_check_dynamic_engine_models_follow_the_canonical_catalog() -> None:
    inventory = engine_contract_inventory()
    assert set(inventory) == set(ENGINE_FN_CATALOG_V2)
    for fn in ENGINE_FN_CATALOG_V2:
        # Parameters are optional at the raw boundary: the compiler/semantic
        # validator, not Pydantic defaults, decides whether a call is executable.
        assert engine_params_model(fn).model_validate({}).model_dump(exclude_none=True) == {}

    # A new function card is picked up without editing a parallel Pydantic union.
    probe = "agent_extension_probe"
    ENGINE_FN_CATALOG_V2[probe] = {
        "params": {"material": "open runtime identity", "count": "integer"},
        "description": "test-only dynamic catalog extension",
    }
    engine_params_model.cache_clear()
    try:
        parsed = engine_params_model(probe).model_validate({"material": "voidglass", "count": 2})
        assert parsed.model_dump(exclude_none=True) == {"count": 2, "material": "voidglass"}
        with pytest.raises(ValidationError):
            engine_params_model(probe).model_validate({"material": "voidglass", "count": 2.5})
    finally:
        ENGINE_FN_CATALOG_V2.pop(probe, None)
        engine_params_model.cache_clear()


def _contract_check_engine_call_boundary_rejects_wrong_types_and_unambiguous_unknown_enums() -> None:
    wrong_type = runtime_plan_boundary_report({
        "runtimePlan": {"engineCalls": [{
            "fn": "fire_ranged_weapon",
            "params": {"family": "charge_release", "chargeTicks": "много"},
        }]}
    })
    assert wrong_type["ok"] is False
    assert any("chargeTicks" in error for error in wrong_type["errors"])

    unknown_family = runtime_plan_boundary_report({
        "runtimePlan": {"engineCalls": [{
            "fn": "fire_ranged_weapon",
            "params": {"family": "future_family"},
        }]}
    })
    assert unknown_family["ok"] is False
    assert any("family" in error for error in unknown_family["errors"])

    # Runtime range is represented as float in both Python and C# and must not
    # regress to an int-only authoring boundary.
    sentry = runtime_plan_boundary_report({
        "runtimePlan": {"engineCalls": [{
            "fn": "deploy_sentry",
            "params": {
                "placement": "grounded",
                "attackIntervalTicks": 30,
                "targetRangeTiles": 25.5,
                "helperLifetimeTicks": 600,
            },
        }]}
    })
    assert sentry["ok"] is True, sentry

    # Integral gameplay fields remain integral even though their clamp bounds
    # live in a numeric map shared with floats.
    fractional_ticks = runtime_plan_boundary_report({
        "runtimePlan": {"engineCalls": [{
            "fn": "fire_ranged_weapon",
            "params": {"family": "charge_release", "chargeTicks": 1.5},
        }]}
    })
    assert fractional_ticks["ok"] is False
    assert any("chargeTicks" in error for error in fractional_ticks["errors"])

    fractional_buff = runtime_plan_boundary_report({
        "runtimePlan": {"engineCalls": [{
            "fn": "apply_player_effect_on_use",
            "params": {"buffs": [{"buffType": 1.5, "buffTime": 60}]},
        }]}
    })
    assert fractional_buff["ok"] is False
    assert any("buffType" in error for error in fractional_buff["errors"])

    # Catalog descriptors ending in `etc` are extension points, not closed
    # enums. A new identity can reach the semantic compiler without editing the
    # validation library first.
    open_projectile_identity = runtime_plan_boundary_report({
        "runtimePlan": {"engineCalls": [{
            "fn": "cast_magic_weapon",
            "params": {"family": "staff", "projectileFamily": "crystal_lance_v2"},
        }]}
    })
    assert open_projectile_identity["ok"] is True, open_projectile_identity

    open_material_identity = runtime_plan_boundary_report({
        "runtimePlan": {"engineCalls": [{
            "fn": "spawn_contact_particles",
            "params": {"effect": "dust", "material": "voidglass"},
        }]}
    })
    assert open_material_identity["ok"] is True, open_material_identity

    narrow_trigger = runtime_plan_boundary_report({
        "runtimePlan": {"engineCalls": [{
            "fn": "spawn_secondary_projectiles",
            "params": {"trigger": "while_held"},
        }]}
    })
    assert narrow_trigger["ok"] is False
    assert any("trigger" in error for error in narrow_trigger["errors"])


def _contract_check_final_boundary_requires_compiler_owned_fields_instead_of_defaulting_them() -> None:
    case = next(case for case in GOLDEN_RUNTIME_CASES if case["caseId"] == "ranged_straight_shot")
    report = build_gameplay_seam_report(case)
    assert report["error"] is None
    item = deepcopy(report["item"])
    item["attack"].pop("lifetime")
    with pytest.raises(ValueError, match="compiler-owned fields missing"):
        validate_executable_item_boundary(item)


def _contract_check_boundary_validation_and_wire_projection_do_not_mutate_inputs() -> None:
    case = next(case for case in GOLDEN_RUNTIME_CASES if case["caseId"] == "forbidden_world_entity")
    report = build_gameplay_seam_report(case)
    assert report["error"] is None
    payload = deepcopy(report["item"])
    before = deepcopy(payload)
    wire = executable_wire_view(payload)
    validate_executable_item_boundary(payload)
    assert payload == before
    assert wire is not payload
    assert "index" not in (wire["gameplay"].get("rejectedEngineCalls") or [{}])[0]


def _contract_check_nested_vfx_contract_is_strict_and_defaults_match_csharp() -> None:
    with pytest.raises(ValidationError):
        validate_vfx_manifest_boundary({
            "schema": "infini.vfx.hybrid.v14",
            "motif": {"element": "fire", "futureField": True},
        })
    with pytest.raises(ValidationError):
        validate_vfx_manifest_boundary({
            "schema": "infini.vfx.hybrid.v14",
            "slots": [{"bakedCommands": [{"tick": 1, "futureField": True}]}],
        })
    assert VfxManifestBoundary().slots == []
    parsed = validate_vfx_manifest_boundary({
        "schema": "infini.vfx.hybrid.v14",
        "slots": [{"event": "tick"}],
    })
    assert parsed["slots"][0]["budgetWeight"] == 1.0


def _contract_check_nested_vfx_contract_projects_known_diagnostics_and_stays_strict() -> None:
    parsed = validate_vfx_manifest_boundary({
        "schema": "infini.vfx.hybrid.v14",
        "parentEffectProfile": {"effectTags": ["fire"]},
        "budget": {
            "renderQuality": "Full",
            "quality": "Full",
            "effectMagnitude": 0.25,
        },
        "debug": {
            "pattern": "thrown_simple",
            "composition": {"mode": "runtime_plan_direct"},
            "effectLineage": {"mode": "runtime_plan_direct"},
            "rerollSalt": "test-salt",
        },
    })
    assert "parentEffectProfile" not in parsed
    assert "renderQuality" not in parsed["budget"]
    assert "quality" not in parsed["budget"]
    assert parsed["budget"]["effectMagnitude"] == 0.25
    assert parsed["debug"]["pattern"] == "thrown_simple"
    assert "composition" not in parsed["debug"]
    assert "effectLineage" not in parsed["debug"]
    assert "rerollSalt" not in parsed["debug"]

    with pytest.raises(ValidationError):
        validate_vfx_manifest_boundary({
            "schema": "infini.vfx.hybrid.v14",
            "debug": {"futureField": True},
        })


def _contract_check_compiler_only_gameplay_markers_do_not_cross_executable_wire_boundary() -> None:
    wire = executable_wire_view({
        "gameplay": {
            "kind": "weapon",
            "consumable": True,
            "maxStack": 50,
            "craftYield": 25,
            "runtimeOutputKind": "consumable_weapon",
            "actualAmmoMode": "diagnostic only",
            "unsupportedAmmoFor": "empty",
        },
        "attack": {},
    })
    assert wire["gameplay"]["kind"] == "weapon"
    assert wire["gameplay"]["consumable"] is True
    assert wire["gameplay"]["maxStack"] == 50
    assert wire["gameplay"]["craftYield"] == 25
    assert "runtimeOutputKind" not in wire["gameplay"]
    assert "actualAmmoMode" not in wire["gameplay"]
    assert "unsupportedAmmoFor" not in wire["gameplay"]


def _contract_check_direct_runtime_vfx_is_projected_before_frozen_csharp_json(monkeypatch) -> None:
    from infini_local.core import vfx_manifest as vfx

    monkeypatch.setattr(vfx, "VFX_SELECTOR_ENABLED", True)
    monkeypatch.setattr(vfx, "_vfx_runtime_plan_direct_manifest", lambda *_args, **_kwargs: {
        "schema": "infini.vfx.hybrid.v14",
        "budget": {"renderQuality": "Full", "quality": "Full", "effectMagnitude": 0.2},
        "slots": [],
        "debug": {
            "pattern": "thrown_simple",
            "composition": {"mode": "runtime_plan_direct"},
            "effectLineage": {"mode": "runtime_plan_direct"},
            "rerollSalt": "",
        },
    })
    data = {"id": "g_direct", "attack": {"enabled": True}, "debug": {}}
    result = vfx.attach_hybrid_vfx_manifest(data, "direct-test")
    frozen = json.loads(result["attack"]["vfxManifestJson"])
    assert result["vfxManifest"] != frozen
    assert result["vfxManifest"]["debug"]["composition"]["mode"] == "runtime_plan_direct"
    assert result["vfxManifest"]["debug"]["effectLineage"]["mode"] == "runtime_plan_direct"
    assert "renderQuality" not in frozen["budget"]
    assert "quality" not in frozen["budget"]
    assert "composition" not in frozen["debug"]
    assert "effectLineage" not in frozen["debug"]
    assert "rerollSalt" not in frozen["debug"]


def _contract_check_runtime_vfx_baked_commands_use_the_authored_item_palette(monkeypatch) -> None:
    from infini_local.core import vfx_runtime_slots as slots

    monkeypatch.setattr(slots, "VFX_RUNTIME_INTENT_FIRST", True)
    authored = {"#123456", "#ABCDEF"}
    manifest = slots._vfx_runtime_plan_direct_manifest({
        "id": "palette_probe",
        "name": "Palette Probe",
        "runtimePlan": {"engineCalls": [{"fn": "apply_on_hit_effect", "params": {"effect": "burn"}}]},
        "attack": {
            "enabled": True,
            "effect": "flame",
            "onHit": "burn",
            "powerBudget": 1.0,
            "burstDustCap": 8,
        },
        "gameplay": {"powerBudget": 1.0},
        "visual": {"palette": sorted(authored), "impactVfx": "compact palette-matched flash"},
    }, "palette-probe")

    assert manifest is not None
    colors = {
        str(command.get("startColor") or "").upper()
        for slot in manifest["slots"]
        for command in slot.get("bakedCommands", [])
        if command.get("startColor")
    }
    assert colors
    assert colors <= authored


def _contract_check_all_golden_gameplay_cases_cross_the_final_strict_boundary() -> None:
    for case in GOLDEN_RUNTIME_CASES:
        report = build_gameplay_seam_report(case)
        assert report["error"] is None, f"{case['caseId']}: {report['error']}"
        assert report["strictExecutableBoundary"]["ok"] is True


def _contract_check_parity_checker_and_mutation_gate_are_release_gates() -> None:
    parity = _load_tool_module("infini_contract_parity_gate_test", "tools/contract_parity.py").build_report()
    assert parity["ok"] is True
    assert parity["networkWriteFieldCount"] == parity["networkReadFieldCount"] >= 80
    assert parity["nestedContracts"]

    delivery = _load_tool_module("infini_delivery_gate_test", "tools/check_delivery_contract.py").build_report()
    assert delivery["ok"] is True
    assert delivery["reachable"]["classCount"] >= 30
    assert delivery["reachable"]["propertyCount"] >= 500
    assert delivery["payloadCount"] >= 10

    mutations = _load_tool_module("infini_mutation_gate_test", "tools/mutation_contract_gate.py").build_report()
    assert mutations["ok"] is True
    assert len(mutations["mutations"]) >= 15
    assert all(row["caught"] for row in mutations["mutations"])

def _contract_check_csharp_strict_json_failures_are_structurally_observable() -> None:
    diagnostics = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/ContractJsonDiagnostics.cs").read_text(encoding="utf-8-sig")
    generated = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.cs").read_text(encoding="utf-8-sig")
    vfx = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/VfxManifestSpec.cs").read_text(encoding="utf-8-sig")
    assert "public sealed record ContractJsonError" in diagnostics
    assert "exception as JsonException" in diagnostics
    assert 'const string boundary = "GeneratedItemData.FromJson"' in generated
    assert "ContractJsonDiagnostics.Clear(boundary);" in generated
    assert "ContractJsonDiagnostics.Record(boundary, finalException);" in generated
    assert 'const string boundary = "VfxManifestSpec.FromJson"' in vfx
    assert "ContractJsonDiagnostics.Clear(boundary);" in vfx
    assert "ContractJsonDiagnostics.Record(boundary, exception);" in vfx
    assert "IReadOnlyDictionary<string, ContractJsonError> Snapshot()" in diagnostics
    assert "Errors[safeBoundary] = error" in diagnostics


def _contract_check_contract_evidence_owners_allow_safe_file_splitting_without_global_token_search() -> None:
    import importlib.util

    module_path = ROOT / "tools/contract_parity.py"
    spec = importlib.util.spec_from_file_location("infini_contract_parity_test", module_path)
    assert spec is not None and spec.loader is not None
    contract_parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract_parity)

    manifest = json.loads((ROOT / "contracts/field_lifecycle.json").read_text(encoding="utf-8"))
    owners = manifest["stageOwners"]

    normalize_ok, expression, normalize_files = contract_parity._normalize_assignment(
        "chargeTicks",
        manifest["attack"]["chargeTicks"]["normalizePattern"],
        owners["csharpNormalize"],
    )
    assert normalize_ok is True
    assert "ClampInt(Attack.ChargeTicks" in expression
    assert normalize_files == [
        "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs"
    ]

    child_ok, method, child_files = contract_parity._child_policy_state(
        manifest["attack"]["chargeTicks"]["childPolicy"],
        owners["childPolicy"],
    )
    assert child_ok is True
    assert method == "ConfigureChargeReleasedShot"
    assert child_files == [
        "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedChildSpecPolicy.cs"
    ]

    family, errors = contract_parity._family_separation(manifest)
    assert errors == []
    assert family["sentryShot"]["ok"] is True
    assert family["chargeReleasedShot"]["ok"] is True
    assert family["sentryShot"]["ownerEvidence"]


def _contract_check_runtime_refactor_preserves_family_separation_in_one_pure_policy_owner() -> None:
    policy = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedChildSpecPolicy.cs").read_text(encoding="utf-8-sig")
    sentry = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Sentry.cs").read_text(encoding="utf-8-sig")
    charge = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.ChargeRelease.cs").read_text(encoding="utf-8-sig")
    assert "ConfigureSentryShot" in policy and "GeneratedRuntimeFamilyPolicy.Shoot" in policy
    assert "ConfigureChargeReleasedShot" in policy and "released.ChannelUse = false" in policy
    assert "GeneratedChildSpecPolicy.ConfigureSentryShot" in sentry
    assert "GeneratedChildSpecPolicy.ConfigureChargeReleasedShot" in charge


def _contract_check_agent_control_plane_is_machine_readable_and_diff_aware() -> None:
    agentctl = _load_tool_module("infini_agent_control_plane_test", "tools/agentctl.py")
    files = agentctl.changed_files()
    # The canonical shard runner intentionally copies source without `.git`.
    # In that source-only snapshot there may be no diff index, so exercise the
    # impact engine with representative changed paths instead of asserting on
    # incidental repository metadata.
    probe_files = files or [
        "LocalGenerator/infini_local/core/runtime_authoring/compiler.py",
        "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs",
    ]
    rules_hit, checks, requires_build = agentctl.impacted(probe_files)
    assert agentctl._base_revision()
    assert rules_hit
    assert "semantic_runtime_diff" in checks
    assert requires_build is True

    rules = json.loads((ROOT / ".agent/impact_rules.json").read_text(encoding="utf-8"))
    csharp = next(row for row in rules["rules"] if row["id"] == "csharp-runtime-contract")
    assert csharp["requiresBuild"] is True
    assert "contract_parity" in csharp["checks"]
    assert "delivery_contract" in csharp["checks"]
    assert "mutation_gate" in csharp["checks"]

    manifest = json.loads((ROOT / ".agent/manifest.json").read_text(encoding="utf-8"))
    assert "delivery_contract" in manifest["alwaysChecks"]
    assert "delivery_contract" in manifest["fullChecks"]
    assert manifest["checks"]["delivery_contract"] == ["python", "tools/check_delivery_contract.py"]

def _contract_check_generated_config_registry_is_current_and_redacts_secrets() -> None:
    report = _load_tool_module("infini_config_registry_test", "tools/config_registry.py").build_registry()
    committed = json.loads((ROOT / "contracts" / "config_registry.json").read_text(encoding="utf-8"))
    assert report == committed
    assert report["ok"] is True
    assert report["fieldCount"] >= 200
    assert report["guiFieldCount"] >= 90
    secrets = [row for row in report["entries"] if row["secret"]]
    assert secrets
    assert all("PASTE_KEY" not in json.dumps(row) for row in secrets)

def _contract_check_agent_task_contract_enforces_revision_boundaries_and_build_flag(tmp_path: Path) -> None:
    agentctl = _load_tool_module("infini_agent_task_contract_test", "tools/agentctl.py")
    revision = agentctl._base_revision()
    task = {
        "taskId": "v18-contract-safety",
        "goal": "verify agent-safe contract stack",
        "baseRevision": revision,
        "allowedBoundaries": ["**"],
        "forbiddenChanges": ["definitely-not-present/**"],
        "acceptance": ["all generated gates pass"],
        "requiresBuild": True,
    }
    assert agentctl._validate_task_payload(task) == []
    files = agentctl.changed_files()
    probe_files = files or [
        "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs",
    ]
    assert not [path for path in probe_files if not any(agentctl._matches(path, pattern) for pattern in task["allowedBoundaries"])]
    assert not [path for path in probe_files if any(agentctl._matches(path, pattern) for pattern in task["forbiddenChanges"])]
    assert agentctl.impacted(probe_files)[2] is True

    wrong = dict(task, baseRevision="wrong")
    assert agentctl._validate_task_payload(wrong) == []
    assert wrong["baseRevision"] != revision

def _contract_check_optional_tml_runtime_selftest_is_inert_by_default_and_machine_checkable(tmp_path: Path) -> None:
    source = (ROOT / "ModSources/InfiniCrafterLocal/Common/Systems/InfiniAgentContractSelfTestSystem.cs").read_text(encoding="utf-8-sig")
    assert 'Environment.GetEnvironmentVariable(EnabledEnv), "1"' in source
    assert "PostSetupContent" in source
    assert "Projectile.NewProjectile" not in source
    assert "Main.LocalPlayer" not in source
    for check_id in (
        "dust-zero-remains-disabled",
        "sentry-shot-not-root",
        "charge-shot-not-holdout",
        "strict-generated-item-json",
        "strict-vfx-json",
    ):
        assert check_id in source

    report_path = tmp_path / "selftest.json"
    report_path.write_text(json.dumps({
        "schema": "infini.tml-runtime-selftest.v1",
        "ok": True,
        "checks": [
            {"id": check_id, "ok": True, "detail": "ok"}
            for check_id in (
                "dust-zero-remains-disabled",
                "sentry-shot-not-root",
                "charge-shot-not-holdout",
                "strict-generated-item-json",
                "strict-vfx-json",
            )
        ],
        "failures": [],
    }), encoding="utf-8")
    module = _load_tool_module("infini_tml_selftest_report_test", "tools/check_tml_selftest_report.py")
    assert module.validate(report_path)["ok"] is True


def _contract_check_runtime_impact_gate_proves_tooling_is_not_loaded_by_game() -> None:
    report = _load_tool_module("infini_runtime_impact_test", "tools/runtime_impact_report.py").build_report()
    assert report["gameplaySemanticBaseline"]["differences"] == []
    assert report["infrastructureImportedByRuntime"] == []
    assert all(row["ok"] for row in report["intentionalRuntimeCorrections"])


def _contract_check_semantic_tools_run_without_preconfigured_pythonpath() -> None:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    script = r"""
import json
from pathlib import Path
import sys
root = Path.cwd()
sys.path.insert(0, str(root / "tools"))
import semantic_runtime_diff
import runtime_impact_report
reports = [semantic_runtime_diff.build_report(), runtime_impact_report.build_report()]
print(json.dumps({"ok": all(row.get("ok") is True for row in reports), "reports": reports}))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["ok"] is True

def _contract_check_raw_strict_boundary_cannot_be_bypassed_by_spoofed_normalization_marker() -> None:
    from infini_local.pipelines.llm_authoring_pipeline import _merge_raw_boundary_errors

    raw = {
        "runtimePlan": {
            "_normalization": {"api": "spoofed"},
            "engineCalls": [{
                "fn": "fire_ranged_weapon",
                "params": {"family": "charge_release", "chargeTicks": "много"},
            }],
        }
    }
    raw_boundary = runtime_plan_boundary_report(raw)
    assert raw_boundary["ok"] is False
    merged = _merge_raw_boundary_errors({"ok": True, "errors": []}, raw_boundary, [])
    assert merged["ok"] is False
    assert any("chargeTicks" in row for row in merged["errors"])

    repairable = {
        "runtimePlan": {
            "engineCalls": [{
                "fn": "fire_ranged_weapon",
                "params": {"family": "charge_release", "chargeTicks": "24 ticks"},
            }],
        }
    }
    repairable_boundary = runtime_plan_boundary_report(repairable)
    repaired = _merge_raw_boundary_errors(
        {"ok": True, "errors": []},
        repairable_boundary,
        [{"index": 0, "kind": "scalar_parse", "field": "chargeTicks", "to": 24}],
    )
    assert repaired["ok"] is True
    assert repaired["rawStrictBoundary"]["ok"] is False


def _contract_check_source_only_agent_diff_uses_file_index_before_git_bootstrap(tmp_path: Path) -> None:
    import hashlib
    import importlib.util

    module_path = ROOT / "tools/agentctl.py"
    spec = importlib.util.spec_from_file_location("agentctl_source_index_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    tracked = tmp_path / "tracked.txt"
    tracked.write_text("baseline\n", encoding="utf-8")
    digest = hashlib.sha256(tracked.read_bytes()).hexdigest()
    (tmp_path / "SOURCE_FILE_INDEX.txt").write_text(
        f"{digest} {tracked.stat().st_size:10d}  tracked.txt\n",
        encoding="utf-8",
    )

    assert module._source_index_changes(tmp_path) == []
    tracked.write_text("changed\n", encoding="utf-8")
    assert module._source_index_changes(tmp_path) == ["tracked.txt"]

    tracked.write_text("baseline\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")
    assert module._source_index_changes(tmp_path) == ["new.txt"]

    tracked.unlink()
    assert module._source_index_changes(tmp_path) == ["new.txt", "tracked.txt"]


def _contract_check_source_snapshot_index_excludes_hidden_tool_state(tmp_path: Path) -> None:
    import importlib.util

    module_path = ROOT / "tools/agentctl.py"
    spec = importlib.util.spec_from_file_location("agentctl_hidden_state_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._ignored_repository_path(".git/config") is True
    assert module._ignored_repository_path("./.hypothesis/examples/abc") is True
    assert module._ignored_repository_path(".pytest_cache/v/cache/nodeids") is True
    assert module._ignored_repository_path(".agent/manifest.json") is False
    assert module._ignored_repository_path(".gitignore") is False


def _contract_check_agentctl_resolves_pyright_from_current_python_environment(monkeypatch, tmp_path: Path) -> None:
    import importlib.util

    module_path = ROOT / "tools/agentctl.py"
    spec = importlib.util.spec_from_file_location("agentctl_venv_tool_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text("", encoding="utf-8")
    pyright = bin_dir / "pyright"
    pyright.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
    pyright.chmod(0o755)

    monkeypatch.setattr(module.sys, "executable", str(python))
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, stdout="ok", stderr=""),
    )

    row = module._run_check("pyright", ["pyright"])

    assert row["status"] == "passed"
    assert row["command"] == [str(pyright), "--pythonpath", str(python)]


def _contract_check_agentctl_resolves_windows_pyright_entrypoint_next_to_python(monkeypatch, tmp_path: Path) -> None:
    import importlib.util

    module_path = ROOT / "tools/agentctl.py"
    spec = importlib.util.spec_from_file_location("agentctl_windows_venv_tool_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    scripts_dir = tmp_path / "venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    python = scripts_dir / "python.exe"
    python.write_text("", encoding="utf-8")
    pyright = scripts_dir / "pyright.exe"
    pyright.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
    pyright.chmod(0o755)

    monkeypatch.setattr(module.sys, "executable", str(python))
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, stdout="ok", stderr=""),
    )

    row = module._run_check("pyright", ["pyright"])

    assert row["status"] == "passed"
    assert row["command"] == [str(pyright), "--pythonpath", str(python)]


# Keep process-spawning tooling checks ahead of runtime-import checks. Some runtime
# modules install long-lived signal/thread state by design; spawning tool subprocesses
# after those imports made the former all-in-one contract order-dependent.
def test_v18_agent_tooling_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_semantic_tools_run_without_preconfigured_pythonpath',
            '_contract_check_parity_checker_and_mutation_gate_are_release_gates',
            '_contract_check_agent_control_plane_is_machine_readable_and_diff_aware',
            '_contract_check_generated_config_registry_is_current_and_redacts_secrets',
            '_contract_check_agent_task_contract_enforces_revision_boundaries_and_build_flag',
            '_contract_check_optional_tml_runtime_selftest_is_inert_by_default_and_machine_checkable',
            '_contract_check_runtime_impact_gate_proves_tooling_is_not_loaded_by_game',
            '_contract_check_source_only_agent_diff_uses_file_index_before_git_bootstrap',
            '_contract_check_source_snapshot_index_excludes_hidden_tool_state',
            '_contract_check_agentctl_resolves_pyright_from_current_python_environment',
            '_contract_check_agentctl_resolves_windows_pyright_entrypoint_next_to_python',
        ),
    )


def test_v18_runtime_boundary_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_dynamic_engine_models_follow_the_canonical_catalog',
            '_contract_check_engine_call_boundary_rejects_wrong_types_and_unambiguous_unknown_enums',
            '_contract_check_final_boundary_requires_compiler_owned_fields_instead_of_defaulting_them',
            '_contract_check_boundary_validation_and_wire_projection_do_not_mutate_inputs',
            '_contract_check_nested_vfx_contract_is_strict_and_defaults_match_csharp',
            '_contract_check_nested_vfx_contract_projects_known_diagnostics_and_stays_strict',
            '_contract_check_compiler_only_gameplay_markers_do_not_cross_executable_wire_boundary',
            '_contract_check_direct_runtime_vfx_is_projected_before_frozen_csharp_json',
            '_contract_check_runtime_vfx_baked_commands_use_the_authored_item_palette',
            '_contract_check_all_golden_gameplay_cases_cross_the_final_strict_boundary',
            '_contract_check_csharp_strict_json_failures_are_structurally_observable',
            '_contract_check_contract_evidence_owners_allow_safe_file_splitting_without_global_token_search',
            '_contract_check_runtime_refactor_preserves_family_separation_in_one_pure_policy_owner',
            '_contract_check_raw_strict_boundary_cannot_be_bypassed_by_spoofed_normalization_marker',
        ),
    )
