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
           max_cold_ms: float = 5000.0) -> dict[str, Any]:
    if not math.isfinite(max_cold_ms) or max_cold_ms <= 0:
        raise ValueError("max_cold_ms must be finite and positive")
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
            if not hashes_match:
                errors.append(f"{scenario}/{phase}: cross-variant SHA-256 mismatch")
            if b["utf8Bytes"] != c["utf8Bytes"] or b["characters"] != c["characters"]:
                errors.append(f"{scenario}/{phase}: wire length mismatch")
            # The source-cache-reset phase is never classified as a cold process.
            paths = [root / "payloads" / variant / scenario / f"{phase}.json"
                     for variant in ("baseline", "candidate")]
            available = all(path.is_file() for path in paths)
            byte_equal: bool | None = None
            if available:
                for variant, path, measurement in zip(("baseline", "candidate"), paths, (b, c)):
                    if digest(path) != measurement["sha256"] or path.stat().st_size != measurement["utf8Bytes"]:
                        errors.append(f"{variant}/{scenario}/{phase}: payload does not match receipt")
                byte_equal = exact_bytes(*paths)
                if not byte_equal:
                    errors.append(f"{scenario}/{phase}: actual payload bytes differ")
                verified_payloads += 1
            elif require_payloads:
                errors.append(f"{scenario}/{phase}: baseline/candidate payload files missing")
            compared.append({"scenario": scenario, "phase": phase, "reportedHashesMatch": hashes_match,
                             "payloadBytesEqual": byte_equal, "sha256": c["sha256"]})
        b, c = before[PHASES[0]], after[PHASES[0]]
        scenarios.append({
            "scenario": scenario, "baselineWallMs": b["wallMs"], "candidateWallMs": c["wallMs"],
            "baselineAllocatedBytes": b["totalAllocatedBytes"], "candidateAllocatedBytes": c["totalAllocatedBytes"],
            "allocationRatio": c["totalAllocatedBytes"] / b["totalAllocatedBytes"] if b["totalAllocatedBytes"] else None,
            "underTarget": c["wallMs"] < max_cold_ms,
        })
    pins, pin_errors = _pins(root, require_pins)
    errors.extend(pin_errors)
    return {
        "schema": "ifc_parent_cohort_verification_v1", "parityPass": not errors,
        "targetPass": all(row["underTarget"] for row in scenarios), "coldTargetMs": max_cold_ms,
        "crossVariantPhaseComparisons": len(compared), "payloadPairsVerified": verified_payloads,
        "proofStrength": "actual_payload_bytes" if verified_payloads == 16 else "reported_sha256_only_or_partial",
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
                        require_pins=args.require_pins, max_cold_ms=args.max_cold_ms)
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
