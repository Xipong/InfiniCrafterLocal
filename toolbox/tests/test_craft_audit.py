"""Observable offline audit output, using actual canonical compilers/validators."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("craft_audit", ROOT / "tools/craft-audit/audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.fixture
def author():
    return audit.read_document(ROOT / "tools/item-test-workbench/examples/lunar-harpoon/author-source.json")


def document(data):
    return {"file": "test.json", "sha256": "synthetic-test-input", "data": data}


@pytest.fixture
def wire(author):
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    return document(compile_runtime_program(author["data"]))


def test_nested_values_units_and_distinct_charge_meanings(author):
    before = deepcopy(author)
    report = audit.build_report(author)
    fields = {r["path"]: r for r in report["authorFields"]}
    base = "#/runtimeProgram/calls/12/params/"
    assert fields[base + "duration"]["value"] == 0.5
    assert fields[base + "duration"]["units"] == "seconds"
    assert "Time to full charge" in fields[base + "duration"]["description"]
    assert fields[base + "autoReleaseAge"]["value"] == 1
    assert "automatic release age" in fields[base + "autoReleaseAge"]["description"]
    multiplier = fields[base + "releaseEffect/damageMultiplier"]
    assert multiplier["value"] == 2
    assert "at full charge; interpolated from 1" in multiplier["description"]
    assert multiplier["default"] == 1
    assert "runtime_program_author.schema.json#/" in multiplier["schema"]
    window = fields["#/runtimeProgram/calls/8/params/window/duration"]
    assert window["value"] == 1 and window["units"] == "seconds"
    assert author == before
    assert all(c["status"] != "failed" for c in report["checks"])


def test_defaults_are_explicitly_absent_and_not_materialized(author):
    charge = author["data"]["runtimeProgram"]["calls"][12]["params"]["releaseEffect"]
    del charge["damageMultiplier"]
    before = deepcopy(author)
    report = audit.build_report(author)
    row = next(r for r in report["authorFields"] if r["path"].endswith("/releaseEffect/damageMultiplier"))
    assert row["state"] == "absent_schema_default" and row["value"] == 1
    assert "ОТСУТСТВУЕТ; default схемы" in audit.render(report)
    assert author == before and "damageMultiplier" not in charge


def test_no_author_explains_wire_without_reconstructing_values(wire):
    wire["data"].pop("concept", None)
    wire["data"].pop("realization", None)
    report = audit.build_report(wire)
    assert not report["authorAvailable"] and report["authorFields"] == []
    link = next(r for r in report["receipts"] if r["wirePath"].endswith("/charge/durationTicks"))
    assert link["wireValue"] == 30 and not link["authorValuePresent"]
    assert link["authorValue"] is None and "full charge" in link["description"]
    assert report["checks"][0]["status"] == "notRun"
    assert "Исходный Author JSON отсутствует" in audit.render(report)


def test_sanitized_wire_without_author_or_receipts_still_has_canonical_docs(wire):
    from infini_local.storage.world_storage import sanitize_recipe_for_delivery
    saved = document(sanitize_recipe_for_delivery(wire["data"]))
    report = audit.build_report(saved)
    assert report["receiptOrigin"] == "absent" and report["receipts"] == []
    row = next(r for r in report["wireFields"] if r["path"].endswith("/charge/durationTicks"))
    assert row["value"] == 30
    assert row["documentation"][0]["projection"]["multiplier"] == 60
    assert row["documentation"][0]["units"] == "seconds"
    multiplier = next(r for r in report["wireFields"] if r["path"].endswith("/chargeRelease/damageMultiplier"))
    assert multiplier["value"] == 2 and multiplier["documentation"][0]["default"] == 1
    assert "Time to full charge" in audit.render(report)
    assert not report["authorAvailable"]
    assert next(c for c in report["checks"] if "receipt" in c["name"])["status"] == "notRun"


def test_delivery_recomputes_receipts_from_actual_source_and_checks_final(wire, author):
    from infini_local.storage.world_storage import sanitize_recipe_for_delivery
    saved = document(sanitize_recipe_for_delivery(wire["data"]))
    before = deepcopy(saved)
    report = audit.build_report(saved, author)
    assert report["receiptOrigin"] == "recomputed_from_supplied_author"
    assert all(c["status"] == "passed" for c in report["checks"])
    assert saved == before and "runtimeContract" not in saved["data"]
    link = next(r for r in report["receipts"] if r["wirePath"].endswith("/charge/durationTicks"))
    assert link["wireValue"] == 30 and link["authorValue"] == 0.5 and link["trust"] == "checked"
    saved["data"]["runtimeProgram"]["entities"][1]["charge"]["durationTicks"] = 31
    bad = audit.build_report(saved, author)
    assert next(c for c in bad["checks"] if "receipt" in c["name"])["status"] == "failed"
    assert all(r["trust"] == "unverified" for r in bad["receipts"])


def test_unknown_nested_author_fields_and_capabilities_remain_visible(author):
    charge = author["data"]["runtimeProgram"]["calls"][12]["params"]
    charge["releaseEffect"]["future/field~"] = {"values": [7, 7, "<script>bad</script>"]}
    author["data"]["runtimeProgram"]["calls"].append({"id": "future", "fn": "future_capability", "params": {"new": 9}})
    report = audit.build_report(author)
    row = next(r for r in report["unknownFields"] if r["path"].endswith("/future~1field~0/values/2"))
    assert row["value"] == "<script>bad</script>"
    assert any(r["value"] == "future_capability" for r in report["unknownFields"])
    assert report["checks"][0]["status"] == "failed"
    page = audit.render(report)
    assert "&lt;script&gt;bad&lt;/script&gt;" in page and "<script>bad</script>" not in page
    assert "future_capability" in page and "future~1field~0" in page


def test_unknown_wire_fields_surface_validator_path_and_real_values(wire):
    wire["data"]["runtimeProgram"]["entities"][1]["charge"]["unexpected"] = {"nested": [3, 3]}
    report = audit.build_report(wire)
    unknown = next(r for r in report["unknownFields"] if r["path"].endswith(".charge.unexpected"))
    assert unknown["value"] == {"nested": [3, 3]}
    assert any(r["path"].endswith("/unexpected/nested/1") and r["value"] == 3 for r in report["wireFields"])
    assert "Неизвестные поля и поля без документации" in audit.render(report)


def test_schema_changes_reach_report_without_second_catalog(author, monkeypatch):
    original = audit.SchemaDocs.__init__

    def changed(self, filename):
        original(self, filename)
        if filename == "runtime_program_author.schema.json":
            call = next(c for c in self.root["properties"]["calls"]["items"]["oneOf"]
                        if c["properties"]["fn"]["const"] == "charge")
            call["properties"]["params"]["properties"]["duration"]["description"] = "CANONICAL_SENTINEL"

    monkeypatch.setattr(audit.SchemaDocs, "__init__", changed)
    assert "CANONICAL_SENTINEL" in audit.render(audit.build_report(author))


def test_explicit_control_links_preserve_duplicate_ids_as_ambiguous(author):
    report = audit.build_report(author)
    edge = next(e for e in report["connections"]["edges"] if e["from"] == "#/runtimeProgram/bindings/0/action/targetId")
    assert edge["to"] == "harpoon" and edge["resolution"] == "resolved"
    author["data"]["runtimeProgram"]["entities"].append({"id": "harpoon", "kind": "free_projectile"})
    report = audit.build_report(author)
    edge = next(e for e in report["connections"]["edges"] if e["from"] == "#/runtimeProgram/bindings/0/action/targetId")
    assert edge["resolution"] == "missing_or_ambiguous" and len(edge["targetPaths"]) == 2


def test_event_and_effect_connections_use_actual_wire():
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    # This fixture exercises event wiring through the real compiler.
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    report = audit.build_report(document(data))
    expected = [(e["id"], ev["event"], ev["action"]) for e in data["runtimeProgram"]["entities"] for ev in e.get("events", [])]
    assert expected
    for entity, event, action in expected:
        assert any(edge["relation"] == f"{entity}: {event} → {action}" for edge in report["connections"]["edges"])
    assert all(e["resolution"] == "resolved" for e in report["connections"]["edges"] if e["namespace"] == "event")


def test_external_evidence_does_not_become_current_pass_or_game_proof(author):
    evidence = document({"ok": True, "status": "passed", "claim": "<img src=x onerror=alert(1)>"})
    report = audit.build_report(author, evidence=[evidence])
    assert evidence in report["evidence"]
    assert len(report["checks"]) == 2
    page = audit.render(report)
    assert "Предоставленные внешние результаты" in page
    assert "&lt;img src=x" in page and "<img src=x" not in page


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"x":NaN}', '{"x":1e999}', '[]'])
def test_rejects_json_that_cannot_be_a_faithful_object(raw, tmp_path):
    path = tmp_path / "input.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError):
        audit.read_document(path)


def test_cli_preserves_inputs_reports_failures_and_refuses_overwrite(author, tmp_path):
    path = tmp_path / "item.json"
    author["data"]["runtimeProgram"]["calls"][12]["params"]["unknown"] = 123
    path.write_text(json.dumps(author["data"]), encoding="utf-8")
    before = path.read_bytes()
    out = tmp_path / "report"
    assert audit.main(["--item", str(path), "--out", str(out)]) == 1
    assert path.read_bytes() == before
    first = (out / "audit.html").read_bytes()
    assert "unknown" in first.decode()
    with pytest.raises(SystemExit) as exc:
        audit.main(["--item", str(path), "--out", str(out)])
    assert exc.value.code == 2 and (out / "audit.html").read_bytes() == first


def test_saved_v6_receipt_names_keep_documentation_without_rewriting_evidence():
    import gzip
    capture = json.loads(gzip.decompress((ROOT / "LocalGenerator/tests/fixtures/gameplay_vocabulary_wire_baseline.json.gz").read_bytes()))
    case = next(row for row in capture["cases"] if row["previousFn"] == "accumulate_projectile_charge")
    saved = document(deepcopy(case["wire"]))
    before = json.dumps(saved, sort_keys=True)
    report = audit.build_report(saved)
    row = next(row for row in report["receipts"]
               if row["receipt"].get("fn") == "accumulate_projectile_charge"
               and row["authorPath"].endswith("/durationSeconds"))
    assert row["authorUnits"] == "seconds" and "Time to full charge" in row["description"]
    assert row["schema"].endswith("/properties/duration")
    assert row["wireValue"] == 1 and not row["authorValuePresent"] and row["authorValue"] is None
    assert row["trust"] == "checked" and not report["authorAvailable"]
    assert json.dumps(saved, sort_keys=True) == before
    assert "Time to full charge" in audit.render(report)

    # A similar-looking undeclared historical name must not acquire either
    # documentation or trusted provenance by fuzzy spelling or wire proximity.
    for change in ("function", "parameter"):
        forged = deepcopy(saved)
        receipt = next(r for r in forged["data"]["runtimeContract"]["finalWireReceipts"]
                       if r == row["receipt"])
        if change == "function":
            receipt["fn"] = "accumulate_projectile_charge_unknown"
        else:
            receipt["authoredPath"] += "Unknown"
        denied = audit.build_report(forged)
        link = next(r for r in denied["receipts"] if r["receiptIndex"] == row["receiptIndex"])
        assert link["description"] == link["authorUnits"] == link["schema"] == ""
        assert link["trust"] == "unverified" and not link["authorValuePresent"]


def test_supplied_v6_author_gets_display_docs_but_never_current_authentication():
    import gzip
    capture = json.loads(gzip.decompress((ROOT / "LocalGenerator/tests/fixtures/gameplay_vocabulary_wire_baseline.json.gz").read_bytes()))
    case = next(row for row in capture["cases"] if row["previousFn"] == "accumulate_projectile_charge")
    saved, source = document(deepcopy(case["wire"])), document(deepcopy(case["previousAuthor"]))
    assert source["data"]["runtimeProgram"]["schema"] == "infini.runtime-program.authoring.v6"
    before = json.dumps([saved, source], sort_keys=True)
    report = audit.build_report(saved, author=source)
    link = next(row for row in report["receipts"] if row["receipt"].get("fn") == "accumulate_projectile_charge"
                and row["authorPath"].endswith("/durationSeconds"))
    field = next(row for row in report["authorFields"] if row["path"] == link["authorPath"])
    assert field["documented"] and field["units"] == link["authorUnits"] == "seconds"
    assert "Time to full charge" in field["description"] == link["description"]
    assert link["authorValuePresent"] and link["authorValue"] == field["value"]
    assert link["trust"] == "unverified"
    statuses = {row["name"]: row["status"] for row in report["checks"]}
    assert statuses["Текущий Author validator"] == statuses["Текущий compiler receipt audit"] == "failed"
    assert statuses["Текущий wire validator"] == "passed"
    assert json.dumps([saved, source], sort_keys=True) == before

    # Unknown versions and old engine-unit spellings must not be dressed up as
    # recognized v6 Author quantities merely because a similar wire slot exists.
    source["data"]["runtimeProgram"]["schema"] = "infini.runtime-program.authoring.v999"
    unknown = audit.build_report(saved, author=source)
    row = next(row for row in unknown["authorFields"] if row["path"] == field["path"])
    assert not row["documented"] and row["description"] == row["units"] == ""
    docs = audit.SchemaDocs("runtime_program_author.schema.json")
    assert docs.saved_param_docs("accumulate_projectile_charge", ("durationTicks",), same_units_only=True) == {}
