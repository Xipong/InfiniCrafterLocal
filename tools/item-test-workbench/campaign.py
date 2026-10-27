"""Explicit bounded native scenario suites; a detector pass never relabels an item."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys

import workbench as w
from agent_evidence import NATIVE_EXIT, report


def keys(obj, allowed, context):
    if not isinstance(obj, dict) or obj.keys() - set(allowed):
        raise ValueError("Invalid/unknown fields in " + context)


def expected_result(value):
    keys(value, ("status", "failedAssertions", "errorContains"), "case.expect")
    status = value.get("status")
    if status not in NATIVE_EXIT:
        raise ValueError("Every case needs explicit expect.status: passed, failed or error")
    failed = value.get("failedAssertions", [])
    if not isinstance(failed, list) or any(not isinstance(s, str) or not s for s in failed):
        raise ValueError("failedAssertions must list exact native assertion names")
    if status == "failed" and not failed:
        raise ValueError("Expected failures must name their exact failedAssertions")
    if status != "failed" and failed:
        raise ValueError("Only expect.status=failed can have failedAssertions")
    error = value.get("errorContains")
    if status == "error" and (not isinstance(error, str) or not error.strip()):
        raise ValueError("Expected errors require a specific errorContains substring")
    if status != "error" and error is not None:
        raise ValueError("errorContains is only valid with expect.status=error")
    return {"status": status, "failedAssertions": failed, **({"errorContains": error} if error else {})}


def plan_suite(manifest):
    manifest = Path(manifest).resolve()
    spec = w.read_json(manifest)
    keys(spec, ("schemaVersion", "cases"), "suite")
    if type(spec.get("schemaVersion")) is not int or spec["schemaVersion"] != 1:
        raise ValueError("Expected suite schemaVersion 1")
    cases = spec.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 128:
        raise ValueError("Suite requires 1..128 explicit cases")
    names, planned = set(), []
    for case in cases:
        keys(case, ("name", "item", "vanillaItem", "fixture", "scenario", "expect", "itemBoundary", "review", "timeout"), "suite case")
        name = case.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name) or name in names:
            raise ValueError("Case names must be unique safe directory names (1..64 characters)")
        names.add(name)
        sources = [k for k in ("item", "vanillaItem", "fixture") if k in case]
        if len(sources) != 1:
            raise ValueError("Each case needs exactly one item, vanillaItem or fixture")
        source = sources[0]
        value = case[source]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Case source must be a nonempty string")
        if source == "fixture" and not re.fullmatch(r"synthetic-[a-z0-9-]+\.json", value):
            raise ValueError("fixture must name a synthetic native fixture file, without directories")
        scenario_value = case.get("scenario")
        if not isinstance(scenario_value, str) or not scenario_value:
            raise ValueError("Case needs an explicit scenario path")
        scenario = (manifest.parent / scenario_value).resolve()
        scene = w.read_json(scenario)
        if not isinstance(scene, dict):
            raise ValueError("Scenario must be an object")
        planned_case = {**case, "expect": expected_result(case.get("expect")), "scenario": str(scenario),
                        "scenarioSha256": w.digest(scenario)}
        if source == "item":
            path = (manifest.parent / value).resolve()
            w.read_json(path)
            planned_case.update(item=str(path), itemSha256=w.digest(path))
        if case.get("itemBoundary", "fresh") not in ("fresh", "local_cache"):
            raise ValueError("itemBoundary must be fresh or local_cache")
        if source == "vanillaItem" and case.get("itemBoundary", "fresh") != "fresh":
            raise ValueError("vanillaItem cannot use local_cache boundary")
        if case.get("review", "none") not in ("none", "schematic", "native"):
            raise ValueError("review must be none, schematic or native")
        timeout = case.get("timeout", 180)
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise ValueError("Case timeout must be 1..3600 seconds")
        planned.append(planned_case)
    return {"schemaVersion": 1, "kind": "native-suite-plan", "manifest": str(manifest),
            "manifestSha256": w.digest(manifest), "cases": planned,
            "note": "Read-only plan; no build, game, fixtures or outputs created"}


def matches_expectation(data, expected, exit_code):
    failures = [a.get("name") for a in data["summary"]["failedAssertions"]]
    return (data["integrity"]["status"] == "verified"
            and exit_code == NATIVE_EXIT[expected["status"]]
            and data["nativeStatus"] == expected["status"]
            and Counter(failures) == Counter(expected["failedAssertions"])
            and (expected["status"] != "error" or expected["errorContains"] in (data["summary"]["error"] or "")))


def run_suite(manifest, output, no_build=False):
    plan = plan_suite(manifest)
    output = Path(output).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Use a fresh suite output directory")
    # Build once. Every child still verifies its actual source/runtime provenance.
    w.native_executable(no_build)
    output.mkdir(parents=True, exist_ok=True)
    (output / "suite.json").write_text(json.dumps(w.read_json(Path(plan["manifest"])), indent=2), encoding="utf-8")
    (output / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    fixture_root = output / "fixtures"
    if any("fixture" in c for c in plan["cases"]):
        w.fixtures(fixture_root, no_build=True)
    rows = []
    result = {"schemaVersion": 1, "kind": "native-suite-result", "passed": False,
              "manifestSha256": plan["manifestSha256"], "cases": rows,
              "wholeItemCertified": False,
              "note": "Suite success means each explicit expectation matched. Expected native failures remain failed items."}

    def save():
        (output / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")

    save()  # interrupted matrices remain visibly incomplete
    for case in plan["cases"]:
        name = case["name"]
        command = [sys.executable, str(w.HERE / "workbench.py"), "run", "--no-build",
                   "--scenario", case["scenario"], "--out", str(output / name),
                   "--review", case.get("review", "none"), "--timeout", str(case.get("timeout", 180)),
                   "--item-boundary", case.get("itemBoundary", "fresh")]
        if "vanillaItem" in case:
            command += ["--vanilla-item", case["vanillaItem"]]
        else:
            item = fixture_root / case["fixture"] if "fixture" in case else Path(case["item"])
            command += ["--item", str(item)]
        row = {"name": name, "expected": case["expect"], "expectationMatched": False,
               "nativeStatus": None, "run": name}
        try:
            if w.digest(Path(case["scenario"])) != case["scenarioSha256"] or (
                    "item" in case and w.digest(Path(case["item"])) != case["itemSha256"]):
                raise ValueError("Suite input changed after planning")
            proc = subprocess.run(command, cwd=w.ROOT, capture_output=True, text=True,
                                  timeout=case.get("timeout", 180) + 60)
            (output / (name + ".stdout.log")).write_text(proc.stdout, encoding="utf-8")
            (output / (name + ".stderr.log")).write_text(proc.stderr, encoding="utf-8")
            row["exitCode"] = proc.returncode
            data = report(output / name)
            row.update(nativeStatus=data["nativeStatus"], integrity=data["integrity"],
                       failedAssertions=data["summary"]["failedAssertions"], error=data["summary"]["error"],
                       observations={key: data["summary"][key] for key in
                                     ("eventCounts", "nativeHits", "resources", "activeProjectilesAtEnd")})
            row["expectationMatched"] = matches_expectation(data, case["expect"], proc.returncode)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            row["runnerError"] = str(exc)
        rows.append(row)
        save()
        print(f"{name}: native={row['nativeStatus']} expectation={'matched' if row['expectationMatched'] else 'MISMATCH'}", file=sys.stderr, flush=True)
    result.update(completedCases=len(rows), plannedCases=len(plan["cases"]),
                  nativeStatusCounts=dict(Counter(r["nativeStatus"] or "notRun" for r in rows)))
    result["passed"] = all(r["expectationMatched"] for r in rows) and w.digest(Path(plan["manifest"])) == plan["manifestSha256"]
    save()
    return result
