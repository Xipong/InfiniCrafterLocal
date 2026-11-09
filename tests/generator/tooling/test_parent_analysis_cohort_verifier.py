"""Negative controls for exact native benchmark evidence, not speed benchmarks."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
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
    assert not result["byteParityPass"]
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


def graph_contract_payload(*, candidate: bool) -> dict:
    graph = {
        "source": "unit-test read-only source", "version": 1,
        "roots": [0], "nodes": [{"id": 0, "method": 0, "values": {"v1": ["ldfld", {"member": 1}, [], 0]},
                                 "blocks": [[0, [], "v1", ["v1"]]]}],
        "members": [{"name": "Helper", "module": 0}, {"name": "Player.wet", "module": 0}],
        "modules": [{"mvid": "fixture-module"}],
        "edges": [{"from": 0, "to": 0, "kind": "call"}, {"kind": "buff_request", "context": {"admission": "unknown"}},
                  {"from": 0, "to": 0, "kind": "call"}],
        "unresolved": ["runtime detour unknown"], "completeness": "partial",
        "nativeCatalogCoverage": {"status": "fixture"},
        "scope": verifier.GRAPH_CANDIDATE_SCOPE if candidate else verifier.GRAPH_BASELINE_SCOPE,
        "limits": copy.deepcopy(verifier.GRAPH_CANDIDATE_LIMITS if candidate else verifier.GRAPH_BASELINE_LIMITS),
    }
    if candidate:
        graph.update({name: 0 for name in verifier.GRAPH_ZERO_COUNTS})
        graph["edges"].reverse()
        graph["edges"] = graph["edges"][1:] + graph["edges"][:1]
    payload = {"outside": {"mechanics": [1, 2, 3], "note": 'literal "parentSourceGraph": is not a property'}}
    for path in verifier.GRAPH_PATHS:
        parent = payload
        for key in path[:-1]:
            parent = parent.setdefault(key, {})
        parent[path[-1]] = copy.deepcopy(graph)
    return payload


def contract_pair(root: Path) -> tuple[Path, Path]:
    paths = root / "baseline.json", root / "candidate.json"
    for candidate, path in enumerate(paths):
        write(path, graph_contract_payload(candidate=bool(candidate)))
    return paths


def contract_fixture(root: Path) -> None:
    fixture(root)
    pins = verifier.load_json(root / "input-pins.json")
    pins["baseline"]["sourceSha"] = verifier.GRAPH_CONTRACT_BASELINE
    write(root / "input-pins.json", pins)
    for variant in ("baseline", "candidate"):
        payload = json.dumps(graph_contract_payload(candidate=variant == "candidate")).encode()
        for scenario in verifier.SCENARIOS:
            report_path = root / f"{variant}-{scenario}.json"
            report = verifier.load_json(report_path)
            for row in report["measurements"]:
                row.update(sha256=hashlib.sha256(payload).hexdigest(), utf8Bytes=len(payload), characters=len(payload))
                (root / "payloads" / variant / scenario / (row["case"] + ".json")).write_bytes(payload)
            write(report_path, report)


def test_reviewed_metadata_migration_accepts_reordered_duplicate_edges(tmp_path):
    paths = contract_pair(tmp_path)
    result = verifier.compare_parent_graph_contract(*paths)
    assert result["graphsCompared"] == result["edgeOrderChanges"] == 8
    assert result["outsideGraphBytesEqual"]
    assert paths[0].read_bytes() != paths[1].read_bytes()


@pytest.mark.parametrize("mutation", [
    "missing_node", "changed_guard", "changed_source", "changed_unknown", "changed_member", "changed_module",
    "missing_edge", "duplicate_edge", "changed_edge", "node_type", "new_field", "new_scope", "new_limit",
    "nonzero_omission", "bool_omission", "missing_omission", "outside_mechanic", "missing_graph",
    "missing_container", "extra_graph", "positional_array",
])
def test_graph_contract_rejects_every_non_allowlisted_evidence_change(tmp_path, mutation):
    paths = contract_pair(tmp_path)
    payload = verifier.load_json(paths[1])
    graph = payload["itemB"]["fingerprint"]["runtimeFacts"]["parentSourceGraph"]
    if mutation == "missing_node":
        graph["nodes"].pop()
    elif mutation == "changed_guard":
        graph["nodes"][0]["blocks"][0][3] = []
    elif mutation == "changed_source":
        graph["nodes"][0]["values"]["v1"][0] = "ldsfld"
    elif mutation == "changed_unknown":
        graph["unresolved"] = []
    elif mutation == "changed_member":
        graph["members"][1]["name"] = "Player.statLife"
    elif mutation == "changed_module":
        graph["modules"][0]["mvid"] = "wrong-owner"
    elif mutation == "missing_edge":
        graph["edges"].pop()
    elif mutation == "duplicate_edge":
        graph["edges"].append(copy.deepcopy(graph["edges"][0]))
    elif mutation == "changed_edge":
        graph["edges"][0]["context"]["admission"] = "accepted"
    elif mutation == "node_type":
        graph["nodes"][0]["id"] = False
    elif mutation == "new_field":
        graph["unreviewedEvidence"] = True
    elif mutation == "new_scope":
        graph["scope"] += " Runtime predicates evaluated."
    elif mutation == "new_limit":
        graph["limits"]["characters"] = 50000
    elif mutation == "nonzero_omission":
        graph["omittedBodyCount"] = 1
    elif mutation == "bool_omission":
        graph["omittedBodyCount"] = False
    elif mutation == "missing_omission":
        del graph["omittedBodyCount"]
    elif mutation == "outside_mechanic":
        payload["outside"]["mechanics"][0] = True
    elif mutation == "missing_graph":
        del payload["itemA"]["parentSourceGraph"]
    elif mutation == "missing_container":
        payload["itemA"]["fingerprint"] = []
    elif mutation == "extra_graph":
        payload["extra"] = {"parentSourceGraph": graph}
    else:
        graph["nodes"][0]["values"]["v1"].reverse()
    write(paths[1], payload)
    with pytest.raises(ValueError):
        verifier.compare_parent_graph_contract(*paths)


@pytest.mark.parametrize("mutation", ["outside_whitespace", "duplicate_key", "trailing_text", "nan"])
def test_graph_contract_does_not_reserialize_or_hide_invalid_payload(tmp_path, mutation):
    paths = contract_pair(tmp_path)
    text = paths[1].read_text()
    if mutation == "outside_whitespace":
        text = text.replace('"outside": ', '"outside":  ', 1)
    elif mutation == "duplicate_key":
        text = text.replace('"version": 1', '"version": 1, "version": 1', 1)
    elif mutation == "trailing_text":
        text += "ignored?"
    else:
        text = text.replace('"version": 1', '"version": NaN', 1)
    paths[1].write_text(text)
    with pytest.raises(ValueError):
        verifier.compare_parent_graph_contract(*paths)


def test_contract_audit_is_explicit_not_false_byte_parity_and_cli_defaults_stay_strict(tmp_path):
    contract_fixture(tmp_path)
    assert not verifier.verify(tmp_path)["parityPass"]
    result = verifier.verify(tmp_path, comparison_mode=verifier.GRAPH_CONTRACT_MODE)
    assert result["contractParityPass"] and result["targetPass"]
    assert not result["byteParityPass"]
    assert result["proofStrength"] == "actual_payload_graph_contract_migration"
    assert result["payloadPairsVerified"] == 16
    assert all(row["payloadBytesEqual"] is False for row in result["phases"])
    command = [sys.executable, str(TOOL), "verify", str(tmp_path), "--require-target"]
    assert subprocess.run(command, capture_output=True, timeout=15).returncode == 1
    assert subprocess.run(command + ["--comparison-mode", verifier.GRAPH_CONTRACT_MODE], capture_output=True, timeout=15).returncode == 0


@pytest.mark.parametrize("mutation", ["missing_payload", "missing_pins", "wrong_baseline", "dependency", "receipt", "warm_change", "target"])
def test_contract_mode_retains_evidence_provenance_stability_and_target_gates(tmp_path, mutation):
    contract_fixture(tmp_path)
    if mutation == "missing_payload":
        (tmp_path / "payloads/candidate/plain/warm-2.json").unlink()
    elif mutation == "missing_pins":
        (tmp_path / "input-pins.json").unlink()
    elif mutation in ("wrong_baseline", "dependency"):
        pins = verifier.load_json(tmp_path / "input-pins.json")
        if mutation == "wrong_baseline":
            pins["baseline"]["sourceSha"] = "f" * 40
        else:
            pins["candidate"]["dependencies"]["tModLoader.dll"] = "f" * 64
        write(tmp_path / "input-pins.json", pins)
    else:
        path = tmp_path / "candidate-plain.json"
        report = verifier.load_json(path)
        if mutation == "receipt":
            report["measurements"][0]["sha256"] = "0" * 64
        elif mutation == "target":
            report["measurements"][0]["wallMs"] = 5000.0
        else:
            # Edge order is allowed cross-version but must remain byte-stable
            # across cold/warm/reset within a variant, even with valid receipts.
            payload_path = tmp_path / "payloads/candidate/plain/warm-1.json"
            payload = verifier.load_json(payload_path)
            payload["itemA"]["parentSourceGraph"]["edges"].reverse()
            write(payload_path, payload)
            wire = payload_path.read_bytes()
            report["measurements"][1].update(sha256=hashlib.sha256(wire).hexdigest(), utf8Bytes=len(wire), characters=len(wire))
        write(path, report)
    result = verifier.verify(tmp_path, comparison_mode=verifier.GRAPH_CONTRACT_MODE)
    assert not (result["parityPass"] and result["targetPass"])


def test_source_pack_workflow_requires_same_contract_byte_parity():
    text = (ROOT / ".github/workflows/pr333-cold-after-audit.yml").read_text()
    assert "--comparison-mode exact-bytes" in text
    assert "BASELINE_SHA: 83955df9a0d9f8392cb57641f5e44aca347e2b75" in text
    assert "baseline-native-source-pack" in text
    assert "--require-payloads --require-pins --require-target" in text
    assert "$result.byteParityPass" in text


def _source_pack_workflow_step(name: str) -> str:
    text = (ROOT / ".github/workflows/pr333-cold-after-audit.yml").read_text()
    return text.split(f"      - name: {name}\n", 1)[1].split("\n      - ", 1)[0]


def test_source_pack_workflow_restores_inside_the_candidate_checkout():
    # These are workflow configuration guards, not PowerShell/native execution.
    # dotnet resolves global.json from cwd, not the project argument's directory.
    step = _source_pack_workflow_step("Restore and locate tModLoader references")
    assert re.search(r"^        working-directory: candidate$", step, re.MULTILINE)
    projects = re.findall(r"^\s*dotnet restore (\S+)", step, re.MULTILINE)
    assert projects and all(project == "mod/InfiniCrafterLocal/InfiniCrafterLocal.csproj" for project in projects)


def test_source_pack_workflow_rebuilds_inside_each_variant_and_restores_location():
    step = _source_pack_workflow_step("Build complete source packs for both revisions")
    scope = re.search(
        r"Push-Location \$variant\s+try\s*\{(?P<body>.*?)\}\s*finally\s*\{\s*Pop-Location\s*\}",
        step, re.DOTALL,
    )
    assert scope is not None, "Both builds must use their own global.json and restore the caller's location."
    builds = re.findall(r"^\s*dotnet build (\S+)", scope["body"], re.MULTILINE)
    assert builds == ["tests/native/EngineRuntimeChecks.csproj"]
    assert len(re.findall(r"^\s*dotnet build\b", step, re.MULTILINE)) == len(builds)


def test_pr333_benchmark_uses_the_same_populated_contract_and_strict_pipeline():
    # Historical baseline had empty catalogs and uncompilable legacy Reverse
    # calls. Do not patch its semantics or compare it to populated data.
    old = (ROOT / ".github/workflows/pr333-parent-analysis-benchmark.yml").read_text()
    current = (ROOT / ".github/workflows/pr333-cold-after-audit.yml").read_text()
    assert old.split("jobs:\n", 1)[1] == current.split("jobs:\n", 1)[1]
    assert "BASELINE_SHA: 83955df9a0d9f8392cb57641f5e44aca347e2b75" in old
    assert "tests/native/EngineRuntimeChecks.csproj" in old
    assert "baseline/tools/native" not in old
    assert "scenarios.Reverse()" not in old
    assert "--comparison-mode exact-bytes --require-payloads --require-pins --require-target --max-cold-ms 5000" in old
    assert "--roll-forward Disable" in old
    assert "PopulatedParentProfiling.cs" in old
