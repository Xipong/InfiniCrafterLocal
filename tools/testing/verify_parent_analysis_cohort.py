#!/usr/bin/env python3
"""Validate the exact four-scenario/16-phase native parent-analysis cohort.

Report hashes alone are explicitly labelled, never confused with locally verified
payloads. Cold latency and parity have independent acceptance results. The tool
has no network, provider calls, game execution, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
import zipfile

SCENARIOS = ("plain", "mixed", "nebula-prism", "eventide")
PHASES = ("cold-first-request", "warm-1", "warm-2", "source-cache-reset")
ENVIRONMENT_FIELDS = (
    "runtimeVersion", "nativeMvid", "itemCount", "projectileCount",
    "itemSampleCount", "projectileSampleCount", "tooltipContext", "parentTypes",
    "coldScope", "resetScope", "allocationScope", "gcScope",
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=_reject_constant)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def exact_bytes(left: Path, right: Path) -> bool:
    with left.open("rb") as a, right.open("rb") as b:
        while True:
            x, y = a.read(1024 * 1024), b.read(1024 * 1024)
            if x != y:
                return False
            if not x:
                return True



# This is an explicit migration audit against the pre-source-pack revision, not
# byte parity and not a generic graph normalizer. Exact byte mode stays default.
GRAPH_CONTRACT_MODE = "parent-graph-contract-v1"
GRAPH_CONTRACT_BASELINE = "d5dd52da8eb9f5910eef4962254a86d6d2d87323"
GRAPH_BASELINE_SCOPE = 'Read-only source, never inherited execution or final stats/DPS. values: [IL opcode, operand, input IDs, block]. {member:N}/node.method reference members[N]; module references modules[N]. blocks: [offset, successors, branch-value ID, required enclosing branch IDs]; targets outside this slice stay unresolved. ldloc/predecessor definitions are alternatives, not independent rolls. Helpers bind caller inputs to argument slots (instance this=0). All statements require control to reach their offsets. Roots, virtual bodies and registered globals/players are dispatch candidates; current immunity registrations are not target admission. Native units/operators are not final stat multipliers. No hooks/helpers/getters/constructors ran. Runtime detours, missing edges and omitted source remain unknown.'
GRAPH_CANDIDATE_SCOPE = 'Read-only source, never inherited execution or final stats/DPS. values: [IL opcode, operand, input IDs, block]. {member:N}/node.method/receiverType/originReceiverType reference members[N]; module references modules[N]. blocks: [offset, successors, branch-value ID, required enclosing branch IDs]; targets outside this slice stay unresolved. ldloc/predecessor definitions are alternatives, not independent rolls. Helpers bind caller inputs to argument slots (instance this=0). All statements require control to reach their offsets. Roots, virtual bodies and registered globals/players are dispatch candidates; current immunity registrations are not target admission. nativeIdentity distinguishes certified identity CFG from conditional source windows; live predicates are never evaluated. Native units/operators are not final stat multipliers. No hooks/helpers/getters/constructors ran. Runtime detours, missing edges and omitted source remain unknown. Discovery is independent of export; sourceCoverage marks edges whose callsite is not in the exported slice.'
GRAPH_BASELINE_LIMITS = {'nodes': 48, 'edges': 192, 'helperDepth': 6, 'characters': 16000}
GRAPH_CANDIDATE_LIMITS = {'nodes': 48, 'edges': 192, 'helperDepth': 6, 'characters': 40000, 'allocatedCharacters': 30000, 'reservedCatalogCoverageCharacters': 320, 'discoveryNodes': 256, 'discoveryEdges': 1024}
GRAPH_ZERO_COUNTS = ("omittedNodeCount", "omittedRootCount", "omittedBodyCount", "omittedEdgeCount")
GRAPH_PATHS = tuple((item, *container, "parentSourceGraph")
                    for item in ("itemA", "itemB")
                    for container in ((), ("runtimeFacts",), ("fingerprint",), ("fingerprint", "runtimeFacts")))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical(value: Any) -> str:
    # Preserve scalar types, array order and edge multiplicity. Python equality
    # alone would incorrectly accept True == 1 and 1 == 1.0.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _graph_spans(text: str) -> dict[tuple[str, ...], tuple[int, int, dict[str, Any]]]:
    decoder = json.JSONDecoder(object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    root = decoder.decode(text)  # Validate all input, including skipped values.
    if not isinstance(root, dict):
        raise ValueError("Parent payload must be an object")
    result: dict[tuple[str, ...], tuple[int, int, dict[str, Any]]] = {}

    def whitespace(index: int) -> int:
        while index < len(text) and text[index] in " \r\n\t":
            index += 1
        return index

    def visit(start: int, path: tuple[str, ...]) -> None:
        index = whitespace(start)
        if text[index] != "{":
            raise ValueError("Missing graph container: " + "/".join(path))
        index = whitespace(index + 1)
        while text[index] != "}":
            key, index = decoder.raw_decode(text, index)
            index = whitespace(index)
            if text[index] != ":":
                raise ValueError("Invalid JSON object separator")
            value_start = whitespace(index + 1)
            value, value_end = decoder.raw_decode(text, value_start)
            child = (*path, key)
            if child in GRAPH_PATHS:
                if not isinstance(value, dict):
                    raise ValueError("Parent graph must be an object: " + "/".join(child))
                result[child] = (value_start, value_end, value)
            elif any(target[:len(child)] == child for target in GRAPH_PATHS):
                visit(value_start, child)
            index = whitespace(value_end)
            if text[index] == "}":
                break
            if text[index] != ",":
                raise ValueError("Invalid JSON member separator")
            index = whitespace(index + 1)

    visit(0, ())
    if set(result) != set(GRAPH_PATHS):
        raise ValueError("Expected all eight explicitly located parent source graphs")
    return result


def compare_parent_graph_contract(left: Path, right: Path) -> dict[str, Any]:
    """Permit only the reviewed v1 metadata migration and graph edge ordering.

    Every graph body, guard, unknown, identity and field outside the allowlist
    remains equal. Full serialized bytes outside the eight graphs remain equal.
    This cannot be used as evidence of exact cross-version payload byte parity.
    """
    before_text, after_text = left.read_bytes().decode("utf-8"), right.read_bytes().decode("utf-8")
    before, after = _graph_spans(before_text), _graph_spans(after_text)
    replacements: list[tuple[int, int, str]] = []
    reordered_edges = 0
    for path in GRAPH_PATHS:
        b_start, b_end, original = before[path]
        c_start, c_end, changed = after[path]
        label = "/".join(path)
        if original.get("scope") != GRAPH_BASELINE_SCOPE or changed.get("scope") != GRAPH_CANDIDATE_SCOPE:
            raise ValueError(label + ": unrecognized graph scope migration")
        if (_canonical(original.get("limits")) != _canonical(GRAPH_BASELINE_LIMITS)
                or _canonical(changed.get("limits")) != _canonical(GRAPH_CANDIDATE_LIMITS)):
            raise ValueError(label + ": unrecognized graph limit migration")
        for key in GRAPH_ZERO_COUNTS:
            if key in original or type(changed.get(key)) is not int or changed[key] != 0:
                raise ValueError(label + ": missing, nonzero or invalid " + key)
        b, c = dict(original), dict(changed)
        for key in ("scope", "limits"):
            b.pop(key)
            c.pop(key)
        for key in GRAPH_ZERO_COUNTS:
            c.pop(key)
        for graph in (b, c):
            if not isinstance(graph.get("edges"), list) or any(not isinstance(edge, dict) for edge in graph["edges"]):
                raise ValueError(label + ": graph edges must be object records")
        if _canonical(b["edges"]) != _canonical(c["edges"]):
            reordered_edges += 1
        # Sorting complete records, not using sets, preserves duplicate edges.
        b["edges"] = sorted(_canonical(edge) for edge in b["edges"])
        c["edges"] = sorted(_canonical(edge) for edge in c["edges"])
        if _canonical(b) != _canonical(c):
            raise ValueError(label + ": graph evidence differs outside the metadata allowlist")
        replacements.append((c_start, c_end, before_text[b_start:b_end]))
    for start, end, replacement in sorted(replacements, reverse=True):
        after_text = after_text[:start] + replacement + after_text[end:]
    if before_text != after_text:
        raise ValueError("Payload bytes outside parent source graphs differ")
    return {"contract": GRAPH_CONTRACT_MODE, "graphsCompared": len(GRAPH_PATHS),
            "edgeOrderChanges": reordered_edges, "outsideGraphBytesEqual": True,
            "allowedGraphMetadataChanges": ["scope", "limits", *GRAPH_ZERO_COUNTS]}


def _number(row: dict[str, Any], name: str, integer: bool = False) -> float | int:
    value = row.get(name)
    types = (int,) if integer else (int, float)
    if type(value) not in types or not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid nonnegative {'integer' if integer else 'number'} {name}: {value!r}")
    return value


def _measurements(report: dict[str, Any], scenario: str) -> dict[str, dict[str, Any]]:
    if not isinstance(report, dict):
        raise ValueError(f"{scenario}: report must be a JSON object")
    if report.get("scenario") != scenario or report.get("kind") != "actual-deferred-craft":
        raise ValueError(f"Wrong report identity for {scenario}")
    measurements = report.get("measurements")
    if not isinstance(measurements, list) or len(measurements) != len(PHASES):
        raise ValueError(f"{scenario}: expected exactly four phases")
    result: dict[str, dict[str, Any]] = {}
    for row in measurements:
        if not isinstance(row, dict) or row.get("case") not in PHASES or row["case"] in result:
            raise ValueError(f"{scenario}: missing/duplicate/unknown phase")
        if type(row.get("equalToFirstRequest")) is not bool or not row["equalToFirstRequest"]:
            raise ValueError(f"{scenario}/{row['case']}: within-variant structural parity failed")
        if not isinstance(row.get("sha256"), str) or not SHA256.fullmatch(row["sha256"]):
            raise ValueError(f"{scenario}/{row['case']}: malformed SHA-256")
        for key in ("wallMs", "captureMs", "resolveMs", "pumpMs", "maxPumpMs"):
            _number(row, key)
        for key in ("totalAllocatedBytes", "utf8Bytes", "characters", "frames", "pumpIntervalMs"):
            _number(row, key, integer=True)
        result[row["case"]] = row
    return result


def native_source_pack_pin(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        entry = archive.getinfo("manifest.json")
        if entry.file_size > 4 * 1024 * 1024:
            raise ValueError("native source pack manifest exceeds the runtime bound")
        manifest = json.loads(archive.read(entry), parse_constant=_reject_constant)
    if not isinstance(manifest, dict) or not SHA256.fullmatch(str(manifest.get("projectionSha256", ""))):
        raise ValueError("native source pack has an invalid projection SHA-256")
    return {"sha256": digest(path), "bytes": path.stat().st_size,
            "projectionSha256": manifest["projectionSha256"]}


def _pins(root: Path, required: bool) -> tuple[dict[str, Any], list[str]]:
    path = root / "input-pins.json"
    if not path.is_file():
        return {"status": "unavailable"}, ["missing input-pins.json"] if required else []
    pins = load_json(path)
    if not isinstance(pins, dict):
        raise ValueError("input-pins.json must contain an object")
    errors: list[str] = []
    for variant in ("baseline", "candidate"):
        item = pins.get(variant, {})
        if not isinstance(item, dict):
            raise ValueError(f"{variant}: input pins must be an object")
        if not SHA1.fullmatch(str(item.get("sourceSha", ""))):
            errors.append(f"{variant}: invalid source SHA")
        if not SHA256.fullmatch(str(item.get("harnessSha256", ""))):
            errors.append(f"{variant}: invalid harness SHA-256")
        dependencies = item.get("dependencies")
        if not isinstance(dependencies, dict) or not dependencies:
            errors.append(f"{variant}: empty dependency byte roster")
        elif any(not isinstance(k, str) or not SHA256.fullmatch(str(v)) for k, v in dependencies.items()):
            errors.append(f"{variant}: malformed dependency hashes")
        pack = item.get("nativeSourcePack")
        if pack is not None:
            if (not isinstance(pack, dict) or not SHA256.fullmatch(str(pack.get("sha256", "")))
                    or not SHA256.fullmatch(str(pack.get("projectionSha256", "")))
                    or type(pack.get("bytes")) is not int or pack["bytes"] <= 0):
                errors.append(f"{variant}: malformed native source pack pin")
                continue
            archive = root / ("native-source-pack.zip" if variant == "candidate" else "baseline-native-source-pack.zip")
            if not archive.is_file():
                errors.append(f"{variant}: pinned native source pack archive missing")
                continue
            try:
                actual = native_source_pack_pin(archive)
                for field in ("sha256", "bytes", "projectionSha256"):
                    if actual[field] != pack[field]:
                        errors.append(f"{variant}: native source pack {field} differs from input pin")
            except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
                errors.append(f"{variant}: invalid native source pack archive: {error}")
    if pins.get("baseline", {}).get("dependencies") != pins.get("candidate", {}).get("dependencies"):
        errors.append("baseline/candidate dependency bytes differ")
    return {"status": "matched" if not errors else "failed", "inputs": pins}, errors


def verify(root: Path, *, require_payloads: bool = False, require_pins: bool = False,
           max_cold_ms: float = 5000.0, comparison_mode: str = "exact-bytes") -> dict[str, Any]:
    if not math.isfinite(max_cold_ms) or max_cold_ms <= 0:
        raise ValueError("max_cold_ms must be finite and positive")
    if comparison_mode not in ("exact-bytes", GRAPH_CONTRACT_MODE):
        raise ValueError("Unknown comparison mode: " + comparison_mode)
    migration = comparison_mode == GRAPH_CONTRACT_MODE
    # A migration comparison cannot be inferred from report hashes alone.
    require_payloads = require_payloads or migration
    require_pins = require_pins or migration
    errors: list[str] = []
    compared: list[dict[str, Any]] = []
    scenarios: list[dict[str, Any]] = []
    verified_payloads = 0
    cohort_environment: dict[str, Any] | None = None
    for scenario in SCENARIOS:
        baseline = load_json(root / f"baseline-{scenario}.json")
        candidate = load_json(root / f"candidate-{scenario}.json")
        before = _measurements(baseline, scenario)
        after = _measurements(candidate, scenario)
        current_environment = {name: baseline.get(name) for name in ENVIRONMENT_FIELDS if name != "parentTypes"}
        if cohort_environment is None:
            cohort_environment = current_environment
        elif current_environment != cohort_environment:
            errors.append(f"{scenario}: runtime/loadout or measurement scope changed within cohort")
        for variant, rows in (("baseline", before), ("candidate", after)):
            if any(row["sha256"] != rows[PHASES[0]]["sha256"] for row in rows.values()):
                errors.append(f"{variant}/{scenario}: within-variant byte hashes are not stable")
        for field in ENVIRONMENT_FIELDS:
            if field not in baseline or field not in candidate or baseline[field] != candidate[field]:
                errors.append(f"{scenario}: incompatible/missing environment field {field}")
        for phase in PHASES:
            b, c = before[phase], after[phase]
            hashes_match = b["sha256"] == c["sha256"]
            if not hashes_match and not migration:
                errors.append(f"{scenario}/{phase}: cross-variant SHA-256 mismatch")
            if not migration and (b["utf8Bytes"] != c["utf8Bytes"] or b["characters"] != c["characters"]):
                errors.append(f"{scenario}/{phase}: wire length mismatch")
            # The source-cache-reset phase is never classified as a cold process.
            paths = [root / "payloads" / variant / scenario / f"{phase}.json"
                     for variant in ("baseline", "candidate")]
            available = all(path.is_file() for path in paths)
            byte_equal: bool | None = None
            contract_comparison: dict[str, Any] | None = None
            if available:
                for variant, path, measurement in zip(("baseline", "candidate"), paths, (b, c)):
                    if digest(path) != measurement["sha256"] or path.stat().st_size != measurement["utf8Bytes"]:
                        errors.append(f"{variant}/{scenario}/{phase}: payload does not match receipt")
                    cold_path = path.with_name(PHASES[0] + ".json")
                    if not cold_path.is_file() or not exact_bytes(cold_path, path):
                        errors.append(f"{variant}/{scenario}/{phase}: actual within-variant payload bytes differ")
                byte_equal = exact_bytes(*paths)
                if migration:
                    try:
                        contract_comparison = compare_parent_graph_contract(*paths)
                    except (ValueError, KeyError, TypeError) as error:
                        errors.append(f"{scenario}/{phase}: {error}")
                elif not byte_equal:
                    errors.append(f"{scenario}/{phase}: actual payload bytes differ")
                verified_payloads += 1
            elif require_payloads:
                errors.append(f"{scenario}/{phase}: baseline/candidate payload files missing")
            compared.append({"scenario": scenario, "phase": phase, "reportedHashesMatch": hashes_match,
                             "payloadBytesEqual": byte_equal, "sha256": c["sha256"],
                             "contractComparison": contract_comparison})
        b, c = before[PHASES[0]], after[PHASES[0]]
        scenarios.append({
            "scenario": scenario, "baselineWallMs": b["wallMs"], "candidateWallMs": c["wallMs"],
            "baselineAllocatedBytes": b["totalAllocatedBytes"], "candidateAllocatedBytes": c["totalAllocatedBytes"],
            "allocationRatio": c["totalAllocatedBytes"] / b["totalAllocatedBytes"] if b["totalAllocatedBytes"] else None,
            "underTarget": c["wallMs"] < max_cold_ms,
        })
    pins, pin_errors = _pins(root, require_pins)
    errors.extend(pin_errors)
    if migration and pins.get("inputs", {}).get("baseline", {}).get("sourceSha") != GRAPH_CONTRACT_BASELINE:
        errors.append("graph contract migration requires the pinned d5dd52d historical baseline")
    byte_parity = not errors and verified_payloads == 16 and all(row["reportedHashesMatch"] and row["payloadBytesEqual"] is not False for row in compared)
    return {
        "schema": "ifc_parent_cohort_verification_v2" if migration else "ifc_parent_cohort_verification_v1",
        "comparisonMode": comparison_mode, "parityPass": not errors, "byteParityPass": byte_parity,
        "contractParityPass": not errors if migration else None,
        "targetPass": all(row["underTarget"] for row in scenarios), "coldTargetMs": max_cold_ms,
        "crossVariantPhaseComparisons": len(compared), "payloadPairsVerified": verified_payloads,
        "proofStrength": ("actual_payload_graph_contract_migration" if migration and verified_payloads == 16
                          else "actual_payload_bytes" if verified_payloads == 16 else "reported_sha256_only_or_partial"),
        "checksPeakRss": False, "checksModdedLoadout": False, "checksModelTraffic": False,
        "inputPins": pins, "cohortEnvironment": cohort_environment, "errors": errors, "scenarios": scenarios, "phases": compared,
    }


def collect(report_path: Path, capture_root: Path, destination: Path, variant: str, scenario: str) -> None:
    report = load_json(report_path)
    measurements = _measurements(report, scenario)
    capture_root = capture_root.resolve(strict=True)
    destination.mkdir(parents=True, exist_ok=True)
    for phase, row in measurements.items():
        source = Path(row["jsonPath"]).resolve(strict=True)
        if not source.is_relative_to(capture_root) or not source.is_file():
            raise ValueError(f"Refusing payload outside capture directory: {source}")
        target = destination / "payloads" / variant / scenario / f"{phase}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copyfile(source, target)
        if digest(target) != row["sha256"] or target.stat().st_size != row["utf8Bytes"]:
            raise ValueError(f"Captured payload mismatch: {scenario}/{phase}")
    (destination / f"{variant}-{scenario}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pin_inputs(repository: Path, harness: Path) -> dict[str, Any]:
    source_sha = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], check=True,
                                capture_output=True, text=True, timeout=15).stdout.strip()
    if not SHA1.fullmatch(source_sha):
        raise ValueError("Unexpected Git commit identity")
    harness = harness.resolve(strict=True)
    dependencies = {str(path.relative_to(harness.parent)).replace("\\", "/"): digest(path)
                    for path in sorted(harness.parent.rglob("*.dll")) if path.resolve() != harness}
    if not dependencies:
        raise ValueError("No runtime dependency DLLs alongside the harness")
    result: dict[str, Any] = {"sourceSha": source_sha, "harnessSha256": digest(harness), "dependencies": dependencies}
    source_pack = harness.parent / "Data/native-source-pack.zip"
    if source_pack.is_file():
        result["nativeSourcePack"] = native_source_pack_pin(source_pack)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    check = modes.add_parser("verify")
    check.add_argument("root", type=Path)
    check.add_argument("--out", type=Path)
    check.add_argument("--require-payloads", action="store_true")
    check.add_argument("--require-pins", action="store_true")
    check.add_argument("--require-target", action="store_true")
    check.add_argument("--max-cold-ms", type=float, default=5000.0)
    check.add_argument("--comparison-mode", choices=("exact-bytes", GRAPH_CONTRACT_MODE), default="exact-bytes")
    capture = modes.add_parser("collect")
    capture.add_argument("--report", type=Path, required=True)
    capture.add_argument("--capture-root", type=Path, required=True)
    capture.add_argument("--destination", type=Path, required=True)
    capture.add_argument("--variant", choices=("baseline", "candidate"), required=True)
    capture.add_argument("--scenario", choices=SCENARIOS, required=True)
    pin = modes.add_parser("pin")
    for name in ("baseline-repo", "candidate-repo", "baseline-harness", "candidate-harness", "out"):
        pin.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "collect":
            collect(args.report, args.capture_root, args.destination, args.variant, args.scenario)
            return 0
        if args.mode == "pin":
            result = {variant: pin_inputs(getattr(args, variant + "_repo"), getattr(args, variant + "_harness"))
                      for variant in ("baseline", "candidate")}
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            return 0
        result = verify(args.root, require_payloads=args.require_payloads,
                        require_pins=args.require_pins, max_cold_ms=args.max_cold_ms,
                        comparison_mode=args.comparison_mode)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in result.items() if key not in ("phases", "inputPins")}, ensure_ascii=False))
        return 0 if result["parityPass"] and (result["targetPass"] or not args.require_target) else 1
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "invalid_or_incomplete_evidence", "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
