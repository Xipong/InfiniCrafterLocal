"""Negative controls for exact native benchmark evidence, not speed benchmarks."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "testing" / "verify_parent_analysis_cohort.py"
SPEC = importlib.util.spec_from_file_location("ifc_cohort_verifier_tests", TOOL)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def fixture(root: Path, *, payloads: bool = True) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for scenario in verifier.SCENARIOS:
        payload = json.dumps({"scenario": scenario, "proof": "unit-test data; no native execution"}).encode()
        sha = hashlib.sha256(payload).hexdigest()
        rows = []
        for phase in verifier.PHASES:
            row = {"case": phase, "sha256": sha, "equalToFirstRequest": True,
                   "utf8Bytes": len(payload), "characters": len(payload), "totalAllocatedBytes": 100,
                   "wallMs": 1000.0, "captureMs": 20.0, "resolveMs": 980.0, "pumpMs": 1.0,
                   "maxPumpMs": 0.1, "frames": 60, "pumpIntervalMs": 16}
            rows.append(row)
            if payloads:
                for variant in ("baseline", "candidate"):
                    path = root / "payloads" / variant / scenario / (phase + ".json")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(payload)
        for variant in ("baseline", "candidate"):
            report = {"kind": "actual-deferred-craft", "scenario": scenario, "measurements": copy.deepcopy(rows)}
            report.update({name: "unit-test scope" for name in verifier.ENVIRONMENT_FIELDS})
            write(root / f"{variant}-{scenario}.json", report)
    write(root / "input-pins.json", {variant: {
        "sourceSha": "a" * 40, "harnessSha256": "b" * 64,
        "dependencies": {"tModLoader.dll": "c" * 64},
    } for variant in ("baseline", "candidate")})


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_all_sixteen_pairs_require_real_bytes_and_pins(tmp_path):
    fixture(tmp_path)
    result = verifier.verify(tmp_path, require_payloads=True, require_pins=True)
    assert result["parityPass"] and result["targetPass"]
    assert result["crossVariantPhaseComparisons"] == result["payloadPairsVerified"] == 16
    assert result["proofStrength"] == "actual_payload_bytes"


@pytest.mark.parametrize("phase", verifier.PHASES)
def test_each_phase_has_a_cross_variant_check(tmp_path, phase):
    fixture(tmp_path)
    path = tmp_path / "candidate-nebula-prism.json"
    report = verifier.load_json(path)
    next(row for row in report["measurements"] if row["case"] == phase)["sha256"] = "0" * 64
    write(path, report)
    result = verifier.verify(tmp_path, require_payloads=True, require_pins=True)
    assert not result["parityPass"]
    assert any("SHA-256 mismatch" in error for error in result["errors"])


def test_report_hashes_do_not_impersonate_downloaded_payloads(tmp_path):
    fixture(tmp_path, payloads=False)
    result = verifier.verify(tmp_path)
    assert result["parityPass"] and result["payloadPairsVerified"] == 0
    assert result["proofStrength"] == "reported_sha256_only_or_partial"
    assert not verifier.verify(tmp_path, require_payloads=True)["parityPass"]


def test_corrupt_payload_rejected_even_with_matching_report_hashes(tmp_path):
    fixture(tmp_path)
    (tmp_path / "payloads/candidate/eventide/warm-2.json").write_bytes(b"corruption")
    result = verifier.verify(tmp_path, require_payloads=True)
    assert not result["parityPass"]
    assert any("does not match receipt" in error for error in result["errors"])


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "bool_wall", "negative_allocations", "false_parity", "nan"])
def test_incomplete_or_invalid_measurement_rejected(tmp_path, mutation):
    fixture(tmp_path)
    path = tmp_path / "candidate-plain.json"
    report = verifier.load_json(path)
    rows = report["measurements"]
    if mutation == "duplicate":
        rows[1]["case"] = rows[0]["case"]
    elif mutation == "missing":
        rows.pop()
    elif mutation == "bool_wall":
        rows[0]["wallMs"] = True
    elif mutation == "negative_allocations":
        rows[0]["totalAllocatedBytes"] = -1
    elif mutation == "false_parity":
        rows[2]["equalToFirstRequest"] = False
    else:
        rows[0]["wallMs"] = float("nan")
    write(path, report)
    with pytest.raises(ValueError):
        verifier.verify(tmp_path)


@pytest.mark.parametrize("field", ["runtimeVersion", "nativeMvid", "parentTypes", "resetScope"])
def test_incompatible_environments_are_not_a_matched_comparison(tmp_path, field):
    fixture(tmp_path)
    path = tmp_path / "candidate-eventide.json"
    report = verifier.load_json(path)
    report[field] = "changed"
    write(path, report)
    assert not verifier.verify(tmp_path)["parityPass"]


def test_changed_dependency_bytes_are_not_accepted(tmp_path):
    fixture(tmp_path)
    pins = verifier.load_json(tmp_path / "input-pins.json")
    pins["candidate"]["dependencies"]["tModLoader.dll"] = "f" * 64
    write(tmp_path / "input-pins.json", pins)
    assert not verifier.verify(tmp_path, require_pins=True)["parityPass"]


def source_pack_fixture(path: Path, projection: str = "e" * 64) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(zipfile.ZipInfo("manifest.json", date_time=(2000, 1, 1, 0, 0, 0)), json.dumps({"projectionSha256": projection,
                         "scope": "unit-test archive provenance; not native projections"}))
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size,
            "projectionSha256": projection}


def test_candidate_native_source_pack_is_optional_but_pins_actual_bytes(tmp_path, monkeypatch):
    fixture(tmp_path)
    archive = tmp_path / "native-source-pack.zip"
    expected = source_pack_fixture(archive)
    pins = verifier.load_json(tmp_path / "input-pins.json")
    pins["candidate"]["nativeSourcePack"] = expected
    write(tmp_path / "input-pins.json", pins)
    assert verifier.verify(tmp_path, require_pins=True)["parityPass"]
    harness = tmp_path / "bin/EngineRuntimeChecks.dll"
    harness.parent.mkdir()
    harness.write_bytes(b"unit-test harness bytes; not executable")
    harness.with_name("tModLoader.dll").write_bytes(b"unit-test native dependency bytes")
    source_pack_fixture(harness.parent / "Data/native-source-pack.zip")
    monkeypatch.setattr(verifier.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="a" * 40))
    emitted = verifier.pin_inputs(tmp_path, harness)
    assert emitted["nativeSourcePack"] == expected
    (harness.parent / "Data/native-source-pack.zip").unlink()
    assert "nativeSourcePack" not in verifier.pin_inputs(tmp_path, harness)


@pytest.mark.parametrize("mutation", ["missing", "bytes", "projection"])
def test_pinned_native_source_pack_missing_or_changed_is_rejected(tmp_path, mutation):
    fixture(tmp_path)
    archive = tmp_path / "native-source-pack.zip"
    pins = verifier.load_json(tmp_path / "input-pins.json")
    pins["candidate"]["nativeSourcePack"] = source_pack_fixture(archive)
    if mutation == "missing":
        archive.unlink()
    elif mutation == "bytes":
        archive.write_bytes(archive.read_bytes() + b"changed bytes")
    else:
        changed = source_pack_fixture(archive, "f" * 64)
        # Even matching container bytes cannot excuse a different source pin.
        pins["candidate"]["nativeSourcePack"].update(sha256=changed["sha256"], bytes=changed["bytes"])
    write(tmp_path / "input-pins.json", pins)
    result = verifier.verify(tmp_path, require_pins=True)
    assert not result["parityPass"]
    assert any("native source pack" in error for error in result["errors"])


@pytest.mark.parametrize("ms, expected", [(4999.0, True), (5000.0, False), (5001.0, False)])
def test_target_is_strictly_under_five_seconds_not_just_successful_parity(tmp_path, ms, expected):
    fixture(tmp_path)
    path = tmp_path / "candidate-nebula-prism.json"
    report = verifier.load_json(path)
    report["measurements"][0]["wallMs"] = ms
    write(path, report)
    result = verifier.verify(tmp_path, require_payloads=True, require_pins=True)
    assert result["parityPass"]
    assert result["targetPass"] is expected
    completed = subprocess.run([sys.executable, str(TOOL), "verify", str(tmp_path), "--require-target"],
                               check=False, capture_output=True, text=True, timeout=15)
    assert completed.returncode == (0 if expected else 1)


def test_collector_does_not_follow_report_paths_outside_capture_root(tmp_path):
    fixture(tmp_path / "receipts")
    capture = tmp_path / "captures"
    capture.mkdir()
    outside = tmp_path / "not-a-payload.json"
    outside.write_text("private fixture")
    report = verifier.load_json(tmp_path / "receipts/candidate-plain.json")
    for row in report["measurements"]:
        row["jsonPath"] = str(outside)
    report_path = capture / "report.json"
    write(report_path, report)
    destination = tmp_path / "collected"
    with pytest.raises(ValueError, match="outside capture"):
        verifier.collect(report_path, capture, destination, "candidate", "plain")
    assert not (destination / "payloads").exists()


@pytest.mark.parametrize("target", ["report", "pins", "variant_pins"])
def test_non_object_metadata_fails_with_an_explicit_validation_error(tmp_path, target):
    fixture(tmp_path)
    if target == "report":
        write(tmp_path / "candidate-plain.json", [])
    elif target == "pins":
        write(tmp_path / "input-pins.json", [])
    else:
        pins = verifier.load_json(tmp_path / "input-pins.json")
        pins["candidate"] = []
        write(tmp_path / "input-pins.json", pins)
    with pytest.raises(ValueError, match="object"):
        verifier.verify(tmp_path, require_pins=True)
