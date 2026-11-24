"""Keep certificate regeneration intact without storing duplicate gameplay facts."""
from __future__ import annotations

from collections import Counter
import json
import re
import sys

import pytest

from suite_paths import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tools/generate"))
import generate_native_ammo_facts as generator


def test_ammo_generator_keeps_full_report_optional(tmp_path, monkeypatch):
    sources = [{
        "method": "Player.PickAmmo", "sourceMethodSha256": "method-proof",
        "sourceModuleVersionId": "module-proof", "assemblyVersion": "1.0.0.0",
        "assemblySha256": "assembly-proof", "itemTypeMentions": [7],
        "defaultProjectileSelection": None, "hookDispatchTrace": [],
        "sourceStageCallSites": [], "scope": "Source evidence, not execution",
        "records": [{"itemId": 7, "rules": [], "unrecognizedProjectileWriteOffsets": [3]}],
    }]
    assembly = tmp_path / "native.dll"
    def extract(path):
        assert path == assembly
        return sources

    monkeypatch.setattr(generator, "extract", extract)
    catalog = tmp_path / "NativeAmmoFactsCatalog.g.cs"
    monkeypatch.setattr(generator, "OUTPUT", catalog)
    certificate_path = tmp_path / "certificates.json"
    monkeypatch.setattr(generator, "REPORT", certificate_path)

    def run(*options):
        monkeypatch.setattr(sys, "argv", ["generate_native_ammo_facts.py", "--assembly", str(assembly), *map(str, options)])
        generator.main()

    run()
    expected_catalog = catalog.read_bytes()
    runtime_rows = [json.loads(row) for row in re.findall(r'"""(.*?)"""', expected_catalog.decode())]
    assert [row for row in runtime_rows if "itemId" in row] == [
        {"itemId": 7, "rules": [], "unrecognizedProjectileWriteOffsets": [3]}
    ]
    assert [row["itemTypeMentions"] for row in runtime_rows if "itemTypeMentions" in row] == [[7]]
    assert json.loads(certificate_path.read_text()) == {
        "schema": "infini.native-ammo-certificates.v1",
        "certificates": [{"method": "Player.PickAmmo", "sourceMethodSha256": "method-proof",
                          "sourceModuleVersionId": "module-proof", "assemblyVersion": "1.0.0.0",
                          "assemblySha256": "assembly-proof", "scope": "Source evidence, not execution"}],
    }
    expected_certificates = certificate_path.read_bytes()
    run("--check")

    report = tmp_path / "exports" / "audit.json"
    run("--report", report)
    assert json.loads(report.read_text()) == {"schema": "infini.native-ammo-sources.v1", "sources": sources}
    assert catalog.read_bytes() == expected_catalog
    run("--check", "--report", report)

    report.write_text("{}\n")
    with pytest.raises(SystemExit, match="stale ammo source facts"):
        run("--check", "--report", report)
    certificate_path.write_text("{}\n")
    with pytest.raises(SystemExit, match="stale ammo source facts"):
        run("--check")
    assert certificate_path.read_text() == "{}\n"
    certificate_path.unlink()
    with pytest.raises(SystemExit, match="stale ammo source facts"):
        run("--check")
    assert not certificate_path.exists()
    certificate_path.write_bytes(expected_certificates)
    assert report.read_text() == "{}\n"
    report.unlink()
    run("--check")
    with pytest.raises(SystemExit, match="stale ammo source facts"):
        run("--check", "--report", report)
    catalog.write_text("stale runtime catalog\n")
    with pytest.raises(SystemExit, match="stale ammo source facts"):
        run("--check")
    assert catalog.read_text() == "stale runtime catalog\n"


def test_ammo_certificate_report_preserves_nested_proof_and_distinct_identities():
    first = {"member": "Fixture.get_Value", "sourceMethodSha256": "body-a", "sourceModuleVersionId": "module-a"}
    second = {**first, "sourceMethodSha256": "body-b"}
    third = {**first, "sourceModuleVersionId": "module-b"}
    lookup = {"specificMatchLookupCertificate": "lookup:module-a"}
    interpreted = {"nativeMember": "Fixture.op_Addition"}
    assembly = {"assemblySha256": "assembly", "assemblyVersion": "1.0", "scope": "Source evidence"}
    parent = {"method": "Player.PickAmmo", "sourceMethodSha256": "parent", "records": [
        {"spawnSites": [{"spawnInputs": {"provenance": first, "branches": [second, third, first]}}]},
        {"nested": {"lookup": lookup, "interpreted": interpreted, "assembly": assembly}},
    ]}
    before = json.dumps(parent)
    report = generator.certificate_report([parent])
    assert report["schema"] == "infini.native-ammo-certificates.v1"
    expected = [{"method": "Player.PickAmmo", "sourceMethodSha256": "parent"},
                first, second, third, lookup, interpreted, assembly]
    assert Counter(json.dumps(row, sort_keys=True) for row in report["certificates"]) == Counter(
        json.dumps(row, sort_keys=True) for row in expected)
    assert json.dumps(parent) == before
