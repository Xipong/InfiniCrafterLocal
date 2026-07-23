#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from pydantic_core import PydanticUndefined

ROOT = Path(__file__).resolve().parents[1]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
if str(LOCAL_GENERATOR) not in sys.path:
    sys.path.insert(0, str(LOCAL_GENERATOR))

from infini_local.core.runtime_authoring.function_contract_registry import (  # noqa: E402
    ENGINE_FUNCTION_CONTRACTS,
    ROOT_EXECUTOR_SHARED_PARAM_NAMES,
    accepted_engine_param_names,
    compiled_fields_for_authored_path,
    lowerer_output_param_names,
    validate_lowerer_output,
)
from infini_local.core.runtime_authoring.function_contract_types import (  # noqa: E402
    WireObligation,
    validate_engine_function_contracts,
)
from infini_local.core.runtime_authoring.semantics import _lower_typed_engine_call  # noqa: E402

from infini_local.core.boundary_models import (  # noqa: E402
    AttackSpecBoundary,
    BuffEntryBoundary,
    GameplaySpecBoundary,
    GeneratedBuffBoundary,
    RejectedEngineCallBoundary,

    VfxBakedCommandBoundary,
    VfxDebugBoundary,
    VfxManifestBoundary,
    VfxMotifBoundary,
    VfxQualityBudgetBoundary,
    VfxSlotBoundary,
)

MODEL_CS = ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs"
NORMALIZE_CS = ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs"
VFX_MODEL_CS = ROOT / "ModSources/InfiniCrafterLocal/Common/Models/VfxManifestSpec.cs"
NET_CS = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.NetSync.cs"
CHILD_POLICY_CS = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedChildSpecPolicy.cs"
LIFECYCLE = ROOT / "contracts/field_lifecycle.json"
SOURCE_OVERRIDES: dict[Path, str] = {}


def _camel(name: str) -> str:
    return name[:1].lower() + name[1:]


def _pascal(name: str) -> str:
    return name[:1].upper() + name[1:]


def _read(path: Path) -> str:
    resolved = path.resolve()
    if resolved in SOURCE_OVERRIDES:
        return SOURCE_OVERRIDES[resolved]
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _class_properties(source: str, class_name: str) -> dict[str, dict[str, str]]:
    declaration = re.search(
        rf"public\s+sealed\s+(?:partial\s+)?class\s+{re.escape(class_name)}\b[^{{]*\{{",
        source,
    )
    if not declaration:
        raise RuntimeError(f"C# class not found: {class_name}")

    open_brace = source.find("{", declaration.start())
    depth = 0
    close_brace = -1
    for index in range(open_brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                close_brace = index
                break
    if close_brace < 0:
        raise RuntimeError(f"Unclosed C# class: {class_name}")

    body = source[open_brace + 1:close_brace]
    out: dict[str, dict[str, str]] = {}
    for csharp_type, name, default in re.findall(
        r"public\s+([\w<>\[\],?]+)\s+(\w+)\s*\{\s*get;\s*set;\s*\}\s*=\s*([^;]+);",
        body,
    ):
        out[_camel(name)] = {"csharpType": csharp_type, "default": default.strip(), "sourceName": name}
    return out


def _python_type_name(annotation: Any) -> str:
    if get_origin(annotation) is Literal:
        values = get_args(annotation)
        if values and all(isinstance(value, str) for value in values): return "string"
        if values and all(isinstance(value, bool) for value in values): return "bool"
        if values and all(isinstance(value, int) and not isinstance(value, bool) for value in values): return "int"
        if values and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values): return "float"
    text = str(annotation)
    if text in {"<class 'str'>", "str"}: return "string"
    if text in {"<class 'int'>", "int"}: return "int"
    if text in {"<class 'float'>", "float"}: return "float"
    if text in {"<class 'bool'>", "bool"}: return "bool"
    if "list" in text.lower(): return "array"
    if "dict" in text.lower(): return "object"
    try:
        from pydantic import BaseModel
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return "object"
    except (ImportError, TypeError):
        pass
    return text


def _csharp_type_name(value: str) -> str:
    if value == "string": return "string"
    if value == "int": return "int"
    if value == "float": return "float"
    if value == "bool": return "bool"
    if value.endswith("[]") or value.startswith("List<"): return "array"
    return "object"


def _python_default(field: Any) -> tuple[bool, Any]:
    if field.is_required(): return False, None
    if field.default_factory is not None: return True, field.default_factory()
    if field.default is PydanticUndefined: return False, None
    return True, field.default


def _model_manifest(model: type) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, field in model.model_fields.items():
        has_default, default = _python_default(field)
        wire_name = str(field.serialization_alias or field.alias or name)
        out[wire_name] = {
            "pythonType": _python_type_name(field.annotation),
            "required": field.is_required(),
            "hasDefault": has_default,
            "default": default,
        }
    return out


def _parse_csharp_default(value: str) -> tuple[bool, Any]:
    token = value.strip()
    if token == "true": return True, True
    if token == "false": return True, False
    if token == "null": return True, None
    if re.fullmatch(r'"(?:[^"\\]|\\.)*"', token):
        try: return True, json.loads(token)
        except json.JSONDecodeError: return False, None
    if re.fullmatch(r"-?\d+", token): return True, int(token)
    if re.fullmatch(r"-?(?:\d+(?:\.\d*)?|\.\d+)[fFdDmM]?", token):
        return True, float(token.rstrip("fFdDmM"))
    if token.startswith("Array.Empty<") and token.endswith(">()"):
        return True, []
    return False, None


def _method_body(source: str, signature_pattern: str) -> str:
    for match in re.finditer(signature_pattern, source):
        # A bare method-name pattern can also match a call site. Require an
        # access modifier on the declaration line so family-policy extraction
        # cannot accidentally inspect an earlier invocation.
        line_start = source.rfind("\n", 0, match.start()) + 1
        declaration_head = source[line_start:match.end()]
        if not re.search(r"\b(?:public|private|internal|protected)\b", declaration_head):
            continue

        brace = source.find("{", match.end())
        arrow = source.find("=>", match.end())
        semicolon = source.find(";", match.end())
        first_terminator = min((index for index in (brace, arrow, semicolon) if index >= 0), default=-1)
        if first_terminator < 0:
            continue
        if first_terminator == arrow:
            end = source.find(";", arrow + 2)
            return source[arrow + 2:end].strip() if end >= 0 else ""
        if first_terminator != brace:
            continue

        depth = 0
        for index in range(brace, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[brace + 1:index]
    return ""




def _owner_paths(patterns: list[str]) -> list[tuple[str, Path]]:
    """Resolve exact owners and optional glob owners without changing policy.

    Exact paths remain preferred evidence. Glob patterns let a safe refactor split
    an owner into partial/module files without weakening stage checks into a
    repository-wide token search.
    """
    rows: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for pattern in patterns:
        has_glob = any(token in pattern for token in ("*", "?", "["))
        candidates = ROOT.glob(pattern) if has_glob else [ROOT / pattern]
        for path in candidates:
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            rows.append((path.relative_to(ROOT).as_posix(), path))
    return rows

def _python_owner_writes(field: str, owners: list[str]) -> tuple[bool, list[str]]:
    evidence: list[str] = []
    # This is deliberately assignment-shaped, not a mere token search. It catches
    # subscript writes, dict/update projection keys and setdefault ownership.
    patterns = [
        rf"\[\s*['\"]{re.escape(field)}['\"]\s*\]\s*=",
        rf"['\"]{re.escape(field)}['\"]\s*:",
        rf"\.setdefault\(\s*['\"]{re.escape(field)}['\"]",
    ]
    for rel, path in _owner_paths(owners):
        text = _read(path)
        if any(re.search(pattern, text) for pattern in patterns):
            evidence.append(rel)
    return bool(evidence), evidence


def _normalize_assignment(
    field: str,
    pattern: str | None,
    owners: list[str] | None = None,
) -> tuple[bool, str, list[str]]:
    pascal = _pascal(field)
    evidence: list[str] = []
    found_expression = ""
    owner_patterns = owners or [
        "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize*.cs"
    ]
    for rel, path in _owner_paths(owner_patterns):
        text = _read(path)
        assignment = re.search(rf"Attack\.{re.escape(pascal)}\s*=\s*(.*?);", text, re.S)
        if not assignment:
            continue
        expression = " ".join(assignment.group(1).split())
        if not found_expression:
            found_expression = expression
        if pattern and re.search(pattern, f"Attack.{pascal} = {expression}") is None:
            continue
        evidence.append(rel)
    return bool(evidence), found_expression, evidence


def _executor_read(field: str, owners: list[str]) -> tuple[bool, list[str]]:
    pascal = _pascal(field)
    evidence: list[str] = []
    for rel, path in _owner_paths(owners):
        text = _read(path)
        # Exclude assignment-only occurrences: executor proof requires the field on
        # the right side or in a call/condition. The negative lookahead is modest but
        # avoids treating DTO/normalizer writes as execution.
        if re.search(rf"(?:_spec|parent|shot|released|child|spec|Data\.Attack)\.{re.escape(pascal)}\b(?!\s*=)", text):
            evidence.append(rel)
    return bool(evidence), evidence


def _child_policy_state(
    policy: dict[str, Any] | None,
    default_owners: list[str] | None = None,
) -> tuple[bool, str, list[str]]:
    if not policy:
        return False, "", []
    method = str(policy.get("method") or "")
    pattern = str(policy.get("pattern") or "")
    owners = list(policy.get("owners") or [])
    if not owners and policy.get("owner"):
        owners = [str(policy["owner"])]
    owners = owners or default_owners or [
        "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedChildSpecPolicy*.cs"
    ]
    evidence: list[str] = []
    for rel, path in _owner_paths(owners):
        body = _method_body(_read(path), rf"\b{re.escape(method)}\s*\(")
        if body and pattern and re.search(pattern, body):
            evidence.append(rel)
    return bool(evidence), method, evidence


def _network_contract(_csharp_fields: dict[str, dict[str, str]], manifest: dict[str, Any]) -> dict[str, Any]:
    stage_owners = manifest.get("stageOwners") or {}
    owner_patterns = list(stage_owners.get("projectileNetwork") or []) or [
        "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.NetSync*.cs"
    ]
    send = ""
    receive = ""
    owner_evidence: list[str] = []
    for rel, path in _owner_paths(owner_patterns):
        source = _read(path)
        candidate_send = _method_body(source, r"public override void SendExtraAI\s*\(")
        candidate_receive = _method_body(source, r"public override void ReceiveExtraAI\s*\(")
        if candidate_send:
            if send:
                raise RuntimeError("SendExtraAI is declared by more than one configured network owner")
            send = candidate_send
            owner_evidence.append(rel)
        if candidate_receive:
            if receive:
                raise RuntimeError("ReceiveExtraAI is declared by more than one configured network owner")
            receive = candidate_receive
            owner_evidence.append(rel)

    compact_policy = manifest.get("projectileCompactSync") or {}
    expected_writes = [" ".join(str(value).split()) for value in compact_policy.get("writeExpressions") or []]
    actual_writes = [" ".join(match.group(1).split()) for match in re.finditer(r"writer\.Write\((.*?)\);", send, re.S)]

    read_pattern = re.compile(
        r"(?:(?:int|bool|float|string)\s+)?"
        r"(?P<target>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[[^\]]+\])*)\s*=\s*"
        r"(?:\([^;\n]+?\))?reader\.Read(?P<method>\w+)\s*\(\s*\)"
    )
    actual_reads = [
        {"target": match.group("target"), "method": match.group("method")}
        for match in read_pattern.finditer(receive)
    ]
    expected_reads = [
        {"target": str(row.get("target") or ""), "method": str(row.get("method") or "")}
        for row in compact_policy.get("readSlots") or []
    ]

    type_errors: list[str] = []
    order_errors: list[str] = []
    if actual_writes != expected_writes:
        order_errors.append(f"compact projectile network write order mismatch expected={expected_writes} actual={actual_writes}")
    if actual_reads != expected_reads:
        order_errors.append(f"compact projectile network read order/type mismatch expected={expected_reads} actual={actual_reads}")

    version = int(compact_policy.get("version") or 0)
    network_source = "\n".join(_read(path) for _, path in _owner_paths(owner_patterns))
    if f"private const int ProjectileSyncVersion = {version}" not in network_source:
        type_errors.append(f"compact projectile sync version must be exactly {version}")
    if "_spec." in send or "_spec." in receive:
        type_errors.append("combat ExtraAI must not write or read AttackSpec fields")
    for forbidden in compact_policy.get("forbiddenPacketTokens") or []:
        if any(str(forbidden) in expression for expression in actual_writes):
            type_errors.append(f"combat ExtraAI contains forbidden packet token {forbidden!r}")

    hydration_policy = compact_policy.get("registryHydration") or {}
    hydrate = _method_body(network_source, r"private bool TryHydrateRuntimeVariantFromRegistry\s*\(")
    apply_resolved = _method_body(network_source, r"private void ApplyResolvedRuntimeVariant\s*\(")
    defer = _method_body(network_source, r"private void DeferUnconfiguredNetworkProjectile\s*\(")
    clear_resolved = _method_body(network_source, r"private void ClearResolvedRuntimeSpec\s*\(")
    runtime_source = "\n".join(
        _read(path) for _, path in _owner_paths(list(stage_owners.get("projectileRuntime") or []))
    )
    ai = _method_body(runtime_source, r"public override void AI\s*\(")
    policy_source = "\n".join(
        _read(path) for _, path in _owner_paths(list(stage_owners.get("childPolicy") or []))
    )
    variant_factory = _method_body(policy_source, r"public static bool TryCreateRuntimeVariant\s*\(")
    known_variant = _method_body(policy_source, r"public static bool IsKnownVariant\s*\(")
    visual_relay_method = str(hydration_policy.get("visualRelayMethod") or "").strip()
    visual_relay = _method_body(
        network_source,
        rf"private void {re.escape(visual_relay_method)}\s*\(",
    ) if visual_relay_method else ""
    registry_source = "\n".join(
        _read(path) for _, path in _owner_paths(list(stage_owners.get("projectileRegistry") or []))
    )
    registry_method = _method_body(registry_source, r"public AttackSpec\? TryGetAttack\s*\(")

    def has_hydration_token(name: str, source: str) -> bool:
        token = str(hydration_policy.get(name) or "").strip()
        return bool(token) and token in source

    hydration_checks = {
        "receiveDelegates": "TryHydrateRuntimeVariantFromRegistry()" in receive,
        "unconfiguredEmptyIdentityAllowed": "packetConfigured && _generatedItemId.Length <= 0" in receive,
        "configuredInvalidPacketRejected": (
            "packetConfigured && _generatedItemId.Length <= 0" in receive
            and "Generated projectile packet contains an invalid registry identity or runtime variant." in receive
        ),
        "unconfiguredDefersHarmlessly": (
            "if (!packetConfigured)" in receive
            and "DeferUnconfiguredNetworkProjectile()" in receive
            and receive.find("if (!packetConfigured)") < receive.find("if (!TryHydrateRuntimeVariantFromRegistry())")
        ),
        "registryLookup": has_hydration_token("registryLookup", hydrate),
        "variantReconstruction": has_hydration_token("variantReconstruction", hydrate),
        "variantAuthorization": (
            has_hydration_token("variantAuthorization", variant_factory)
            and "return false" in variant_factory
        ),
        "finiteVariantCheck": has_hydration_token("finiteVariantCheck", known_variant),
        "genericPresentation": has_hydration_token("genericPresentation", hydrate),
        "missingDataRequest": has_hydration_token("missingDataRequest", hydrate),
        "visualRelayPresentationOnly": (
            bool(visual_relay)
            and "TryHydrateRuntimeVariantFromRegistry()" not in visual_relay
            and "ApplyGeneratedSpec(" not in visual_relay
        ),
        "harmlessDamage": "Projectile.damage = 0" in defer,
        "harmlessFriendly": "Projectile.friendly = false" in defer,
        "harmlessHostile": "Projectile.hostile = false" in defer,
        "deferClearsResolvedSpec": "ClearResolvedRuntimeSpec(Math.Max(_pendingNetworkSpecTicks, 45))" in defer,
        "clearedSpecIsInert": (
            "_configured = false" in clear_resolved
            and "_statsApplied = false" in clear_resolved
            and "_pendingNetworkSpecTicks = pendingSpecTicks" in clear_resolved
            and "new AttackSpec { Enabled = false" in clear_resolved
        ),
        "aiRetry": "TryHydrateRuntimeVariantFromRegistry()" in ai and "_pendingNetworkSpecTicks" in ai,
        "registryDeepClone": "GeneratedItemData.FromJson(data.ToJson())?.Attack" in registry_method,
        "chargeStateBounded": "Math.Clamp(chargeTicks, 0, Math.Clamp(resolved.ChargeTicks, 1, 300))" in apply_resolved,
        "sentryStateBounded": "Math.Clamp(sentryTimer, 0, Math.Clamp(resolved.SentryAttackIntervalTicks, 12, 180))" in apply_resolved,
        "beamStateBounded": "Math.Clamp(beamLength, 0f, ConfiguredRangePixels(560f))" in apply_resolved,
        "childDepthBounded": "Math.Clamp(childDepth, 0f, 3f)" in apply_resolved,
        "rootIdentityBounded": "Math.Clamp(rootIdentity, 0f, 1_000_000f)" in apply_resolved,
        "spawnIgnoreStateBounded": (
            "_spawnIgnoreNpc < -1 || _spawnIgnoreNpc >= Main.maxNPCs" in receive
            and "_spawnIgnoreTicks < 0 || _spawnIgnoreTicks > 10" in receive
        ),
    }
    registry_errors = [f"projectile registry hydration evidence missing: {name}" for name, ok in hydration_checks.items() if not ok]

    return {
        "ok": not type_errors and not order_errors and not registry_errors,
        # AttackSpec is hydrated once from the registry; zero immutable spec
        # fields are transported in normal projectile combat packets.
        "writeFields": [],
        "readFields": [],
        "writeRows": [],
        "readRows": [],
        "compactWriteExpressions": actual_writes,
        "compactReadSlots": actual_reads,
        "compactFieldCount": len(actual_writes),
        "registryHydration": {"ok": not registry_errors, "checks": hydration_checks},
        "typeErrors": type_errors,
        "orderErrors": order_errors,
        "registryErrors": registry_errors,
        "ownerEvidence": sorted(set(owner_evidence)),
    }


def _family_separation(manifest: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    rows: dict[str, Any] = {}
    errors: list[str] = []
    stage_owners = manifest.get("stageOwners") or {}
    default_owners = list(stage_owners.get("childPolicy") or []) or [
        "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedChildSpecPolicy*.cs"
    ]
    for name, policy in (manifest.get("familySeparation") or {}).items():
        owners = list(policy.get("owners") or [])
        if not owners and policy.get("owner"):
            owners = [str(policy["owner"])]
        owners = owners or default_owners
        method = str(policy.get("method") or "")
        patterns = [str(x) for x in policy.get("patterns") or []]
        checks = {pattern: False for pattern in patterns}
        evidence: list[str] = []
        method_found = False
        for rel, path in _owner_paths(owners):
            body = _method_body(_read(path), rf"\b{re.escape(method)}\s*\(")
            if not body:
                continue
            method_found = True
            evidence.append(rel)
            for pattern in patterns:
                checks[pattern] = checks[pattern] or bool(re.search(pattern, body))
        ok = method_found and all(checks.values())
        rows[name] = {
            "ok": ok,
            "owners": owners,
            "ownerEvidence": evidence,
            "method": method,
            "patterns": checks,
        }
        if not ok:
            errors.append(f"child family policy {name} is incomplete in {owners}:{method}")
    return rows, errors


def _compare_model_pair(
    label: str,
    py_model: type,
    cs_source: str,
    cs_class: str,
) -> tuple[dict[str, Any], list[str]]:
    py_fields = _model_manifest(py_model)
    cs_fields = _class_properties(cs_source, cs_class)
    pair_errors: list[str] = []
    missing_cs = sorted(set(py_fields) - set(cs_fields))
    missing_py = sorted(set(cs_fields) - set(py_fields))
    if missing_cs:
        pair_errors.append(f"{label}: Python-only fields: {missing_cs}")
    if missing_py:
        pair_errors.append(f"{label}: C#-only fields: {missing_py}")
    for field in sorted(set(py_fields) & set(cs_fields)):
        py_type = py_fields[field]["pythonType"]
        cs_type = _csharp_type_name(cs_fields[field]["csharpType"])
        if py_type != cs_type:
            pair_errors.append(f"{label}.{field}: type mismatch Python={py_type} C#={cs_type}")
        cs_has_default, cs_default = _parse_csharp_default(cs_fields[field]["default"])
        if py_fields[field]["hasDefault"] and cs_has_default and py_fields[field]["default"] != cs_default:
            pair_errors.append(f"{label}.{field}: default mismatch Python={py_fields[field]['default']!r} C#={cs_default!r}")
    return {
        "ok": not pair_errors,
        "pythonFieldCount": len(py_fields),
        "csharpFieldCount": len(cs_fields),
        "errors": pair_errors,
    }, pair_errors


def _typed_runtime_contract() -> dict[str, Any]:
    """Check executable lowerers and provenance without freezing implementation snapshots."""

    errors = list(validate_engine_function_contracts(ENGINE_FUNCTION_CONTRACTS))
    lowerer_rows: dict[str, Any] = {}
    provenance_rows: dict[str, Any] = {}
    root_rows: dict[str, Any] = {}

    for spec in ENGINE_FUNCTION_CONTRACTS:
        if spec.root_executor:
            accepted = accepted_engine_param_names(spec.name)
            missing = sorted(ROOT_EXECUTOR_SHARED_PARAM_NAMES - accepted)
            root_rows[spec.name] = {"ok": not missing, "missingSharedParams": missing}
            errors.extend(
                f"{spec.name}: root executor misses shared param {name!r}"
                for name in missing
            )

        missing_paths: list[str] = []
        for param in spec.params:
            if param.wire_obligation is not WireObligation.FINAL_WIRE:
                continue
            paths = (
                tuple(f"{param.name}.{nested.path}" for nested in param.nested_wire_paths)
                if param.nested_wire_paths
                else (param.name,)
            )
            for path in paths:
                if not compiled_fields_for_authored_path(spec.name, path):
                    missing_paths.append(path)
        provenance_rows[spec.name] = {"ok": not missing_paths, "missingCompiledPaths": missing_paths}
        errors.extend(
            f"{spec.name}.{path}: final-wire authored path has no compiled destination"
            for path in missing_paths
        )

        if not spec.lowerers:
            continue
        examples = {param.name: param.example_value for param in spec.params}
        actual = _lower_typed_engine_call(spec.name, examples)
        expected_targets = {lowerer.target_function for lowerer in spec.lowerers}
        actual_targets = {target for target, _ in actual}
        edge_errors: list[str] = []
        if actual_targets != expected_targets:
            edge_errors.append(
                f"target mismatch expected={sorted(expected_targets)} actual={sorted(actual_targets)}"
            )
        outputs: dict[str, Any] = {}
        for target, params in actual:
            output_errors = list(validate_lowerer_output(spec.name, target, params))
            declared = sorted(lowerer_output_param_names(spec.name, target))
            emitted = sorted(str(name) for name in params if not str(name).startswith("_"))
            edge_errors.extend(output_errors)
            outputs[target] = {
                "ok": not output_errors,
                "declaredParams": declared,
                "emittedParams": emitted,
                "errors": output_errors,
            }
        errors.extend(f"{spec.name}: {error}" for error in edge_errors)
        lowerer_rows[spec.name] = {
            "ok": not edge_errors,
            "expectedTargets": sorted(expected_targets),
            "actualTargets": sorted(actual_targets),
            "outputs": outputs,
            "errors": edge_errors,
        }

    return {
        "ok": not errors,
        "errors": errors,
        "rootExecutors": root_rows,
        "provenance": provenance_rows,
        "lowerers": lowerer_rows,
    }


def build_report() -> dict[str, Any]:
    source = _read(MODEL_CS)
    csharp_attack = _class_properties(source, "AttackSpec")
    csharp_gameplay = _class_properties(source, "GameplaySpec")
    python_attack = _model_manifest(AttackSpecBoundary)
    python_gameplay = _model_manifest(GameplaySpecBoundary)
    errors: list[str] = []

    for label, py_fields, cs_fields in (
        ("AttackSpec", python_attack, csharp_attack),
        ("GameplaySpec", python_gameplay, csharp_gameplay),
    ):
        missing_cs = sorted(set(py_fields) - set(cs_fields))
        missing_py = sorted(set(cs_fields) - set(py_fields))
        if missing_cs: errors.append(f"{label}: Python-only fields: {missing_cs}")
        if missing_py: errors.append(f"{label}: C#-only fields: {missing_py}")
        for field in sorted(set(py_fields) & set(cs_fields)):
            py_type = py_fields[field]["pythonType"]
            cs_type = _csharp_type_name(cs_fields[field]["csharpType"])
            if py_type != cs_type:
                errors.append(f"{label}.{field}: type mismatch Python={py_type} C#={cs_type}")
            cs_has_default, cs_default = _parse_csharp_default(cs_fields[field]["default"])
            if py_fields[field]["hasDefault"] and cs_has_default and py_fields[field]["default"] != cs_default:
                errors.append(f"{label}.{field}: default mismatch Python={py_fields[field]['default']!r} C#={cs_default!r}")

    nested_sources = {
        "generated": source,
        "vfx": _read(VFX_MODEL_CS),
    }
    nested_pairs = [
        ("BuffEntrySpec", BuffEntryBoundary, "generated", "BuffEntrySpec"),
        ("GeneratedBuffSpec", GeneratedBuffBoundary, "generated", "GeneratedBuffSpec"),

        ("RejectedEngineCallSpec", RejectedEngineCallBoundary, "generated", "RejectedEngineCallSpec"),
        ("VfxManifestSpec", VfxManifestBoundary, "vfx", "VfxManifestSpec"),
        ("VfxMotifSpec", VfxMotifBoundary, "vfx", "VfxMotifSpec"),
        ("VfxQualityBudgetSpec", VfxQualityBudgetBoundary, "vfx", "VfxQualityBudgetSpec"),
        ("VfxSlotSpec", VfxSlotBoundary, "vfx", "VfxSlotSpec"),
        ("VfxBakedCommandSpec", VfxBakedCommandBoundary, "vfx", "VfxBakedCommandSpec"),
        ("VfxDebugSpec", VfxDebugBoundary, "vfx", "VfxDebugSpec"),
    ]
    nested_report: dict[str, Any] = {}
    for label, model, source_key, class_name in nested_pairs:
        row, pair_errors = _compare_model_pair(label, model, nested_sources[source_key], class_name)
        nested_report[label] = row
        errors.extend(pair_errors)

    manifest = json.loads(_read(LIFECYCLE))
    stage_owners = manifest.get("stageOwners") or {}
    normalize_owners = list(stage_owners.get("csharpNormalize") or [])
    child_policy_owners = list(stage_owners.get("childPolicy") or [])
    network = _network_contract(csharp_attack, manifest)
    errors.extend(network["typeErrors"])
    errors.extend(network["orderErrors"])
    errors.extend(network["registryErrors"])
    writes = set(network["writeFields"])
    reads = set(network["readFields"])

    lifecycle_rows: dict[str, Any] = {}
    for field, policy in (manifest.get("attack") or {}).items():
        compiler_ok, compiler_evidence = _python_owner_writes(field, list(policy.get("compilerOwners") or []))
        projection_ok, projection_evidence = _python_owner_writes(field, list(policy.get("projectionOwners") or []))
        normalize_ok, normalize_expression, normalize_evidence = _normalize_assignment(
            field,
            policy.get("normalizePattern"),
            list(policy.get("normalizeOwners") or []) or normalize_owners,
        )
        executor_ok, executor_evidence = _executor_read(field, list(policy.get("executorOwners") or []))
        child_ok, child_method, child_evidence = _child_policy_state(
            policy.get("childPolicy"),
            child_policy_owners,
        )
        stage_state: dict[str, Any] = {
            "pythonBoundary": field in python_attack,
            "pythonCompiler": compiler_ok,
            "pythonProjection": projection_ok,
            "csharpDto": field in csharp_attack,
            "csharpNormalize": normalize_ok,
            "netWrite": field in writes,
            "netRead": field in reads,
            "registryHydration": network["registryHydration"]["ok"],
            "executorRead": executor_ok,
            "childPolicy": child_ok,
        }
        lifecycle_rows[field] = {
            "ok": all(stage_state.get(stage, False) for stage in policy.get("requiredStages") or []),
            "requiredStages": policy.get("requiredStages") or [],
            "stages": stage_state,
            "evidence": {
                "pythonCompiler": compiler_evidence,
                "pythonProjection": projection_evidence,
                "csharpNormalize": normalize_expression,
                "csharpNormalizeOwners": normalize_evidence,
                "executorRead": executor_evidence,
                "childPolicyMethod": child_method,
                "childPolicyOwners": child_evidence,
            },
            "zeroSemantics": policy.get("zeroSemantics"),
        }
        for stage in policy.get("requiredStages") or []:
            if not stage_state.get(stage, False):
                errors.append(f"AttackSpec.{field}: missing or invalid lifecycle stage {stage}")

    family_rows, family_errors = _family_separation(manifest)
    errors.extend(family_errors)
    typed_runtime = _typed_runtime_contract()
    errors.extend(typed_runtime["errors"])
    return {
        "schema": "infini.contract-parity.v2",
        "ok": not errors,
        "errors": errors,
        "attackFieldCount": len(csharp_attack),
        "gameplayFieldCount": len(csharp_gameplay),
        "networkWriteFieldCount": len(network["writeFields"]),
        "networkReadFieldCount": len(network["readFields"]),
        "compactNetworkFieldCount": network["compactFieldCount"],
        "registryHydration": network["registryHydration"],
        "checkedPrimitiveDefaults": sum(
            1 for fields in (csharp_attack, csharp_gameplay) for row in fields.values() if _parse_csharp_default(row["default"])[0]
        ),
        "network": network,
        "nestedContracts": nested_report,
        "lifecycle": lifecycle_rows,
        "familySeparation": family_rows,
        "typedRuntimeContract": typed_runtime,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print JSON only")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--quiet", action="store_true", help="write/report status without printing the full evidence graph")
    args = parser.parse_args()
    report = build_report()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.quiet:
        print(json.dumps({
            "schema": report["schema"],
            "ok": report["ok"],
            "errorCount": len(report.get("errors") or []),
            "attackFieldCount": report.get("attackFieldCount"),
            "gameplayFieldCount": report.get("gameplayFieldCount"),
            "networkWriteFieldCount": report.get("networkWriteFieldCount"),
            "networkReadFieldCount": report.get("networkReadFieldCount"),
            "compactNetworkFieldCount": report.get("compactNetworkFieldCount"),
            "registryHydration": report.get("registryHydration"),
        }, ensure_ascii=False, sort_keys=True))
    else:
        print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
