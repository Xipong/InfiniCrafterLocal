"""Historical finalContract runtimePlan replay corpus + impact selector tests.

No LLM, no HTTP: mechanical accepted-wire replay only.
"""
from __future__ import annotations

import ast
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
QA_MODULE = LOCAL_GENERATOR / "infini_local" / "qa" / "runtime_contract_replay.py"
BUILDER = ROOT / "tools" / "build_runtime_contract_replay_corpus.py"
CHECKER = ROOT / "tools" / "check_runtime_contract_replay.py"
FINGERPRINT_EXPORTER = ROOT / "tools" / "export_runtime_contract_fingerprints.py"
FINGERPRINT_PATH = ROOT / ".agent" / "runtime_contract_fingerprints.json"
FIXTURE_DIR = LOCAL_GENERATOR / "tests" / "fixtures" / "runtime_contract_history"
CORPUS_PATH = FIXTURE_DIR / "corpus.json"

# Free-text / presentation fields that must not appear in the committed corpus.
_PROSE_KEYS = frozenset(
    {
        "name",
        "tooltip",
        "concept",
        "description",
        "visualIntent",
        "sourceReading",
        "sourceRolePreservation",
        "balanceIntent",
        "runtimeStateIntent",
        "visual",
        "visualKit",
        "assetPlan",
        "imagePrompt",
        "itemIconPrompt",
        "fantasy",
        "mergeLogic",
        "coreMechanic",
        "parents",
    }
)

_NETWORK_TOKENS = frozenset(
    {
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "urllib3",
        "openai",
        "anthropic",
        "httplib",
        "socket",
        "websocket",
        "WebSocket",
        "urlopen",
        "http.client",
        "http.server",
    }
)


def _collect_string_keys(obj, out: set[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.add(str(key))
            _collect_string_keys(value, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_string_keys(item, out)


def _module_source_paths() -> list[Path]:
    return [QA_MODULE, BUILDER, CHECKER, FINGERPRINT_EXPORTER]


def test_replay_modules_exist() -> None:
    assert QA_MODULE.is_file(), f"missing QA module: {QA_MODULE}"
    assert BUILDER.is_file(), f"missing corpus builder: {BUILDER}"
    assert CHECKER.is_file(), f"missing replay gate: {CHECKER}"
    assert FINGERPRINT_EXPORTER.is_file(), f"missing fingerprint exporter: {FINGERPRINT_EXPORTER}"
    assert FINGERPRINT_PATH.is_file(), f"missing fingerprint manifest: {FINGERPRINT_PATH}"
    assert CORPUS_PATH.is_file(), f"missing corpus fixture: {CORPUS_PATH}"


def test_modules_contain_no_network_code() -> None:
    for path in _module_source_paths():
        assert path.is_file(), path
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
                    imported.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
                imported.add(node.module)
        for token in _NETWORK_TOKENS:
            top = token.split(".")[0]
            assert top not in imported and token not in imported, (
                f"{path.name} imports network module {token!r}"
            )


def test_corpus_is_deterministic_and_has_no_prose() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    corpus = replay.load_corpus(CORPUS_PATH)
    cases = corpus["cases"]
    assert isinstance(cases, list) and len(cases) >= 8
    dump_root_label = str((corpus.get("source") or {}).get("dumpRoot") or "")
    assert not Path(dump_root_label).is_absolute()
    assert not dump_root_label.startswith("icl-replay-rebuild-")

    # Stable ordering + unique case ids.
    case_ids = [case["caseId"] for case in cases]
    assert case_ids == sorted(case_ids)
    assert len(case_ids) == len(set(case_ids))

    # Canonical dump is byte-stable under re-serialize with sort_keys.
    raw = CORPUS_PATH.read_text(encoding="utf-8")
    loaded = json.loads(raw)
    reserialized = json.dumps(loaded, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    assert json.loads(reserialized) == loaded

    for case in cases:
        keys: set[str] = set()
        _collect_string_keys(case, keys)
        leaked = sorted(keys & _PROSE_KEYS)
        assert not leaked, f"{case.get('caseId')}: prose keys present: {leaked}"

        assert case.get("sourceRun")
        assert case.get("case") is not None
        assert case.get("category") or case.get("resultKind")
        plan = case["runtimePlan"]
        assert isinstance(plan, dict)
        assert isinstance(plan.get("engineCalls"), list) and plan["engineCalls"]
        assert "resultKind" in plan
        for call in plan["engineCalls"]:
            assert isinstance(call, dict)
            assert str(call.get("callId") or "").strip(), (
                f"{case['caseId']} dropped provenance callId"
            )
        # No prose envelopes inside runtimePlan.
        for banned in (
            "visualIntent",
            "sourceReading",
            "sourceRolePreservation",
            "balanceIntent",
            "runtimeStateIntent",
        ):
            assert banned not in plan, f"{case['caseId']} retains prose field {banned}"

        functions = case["functions"]
        assert isinstance(functions, list) and functions == sorted(set(functions))
        derived = replay.case_function_set(case)
        assert set(functions) == set(derived)
        assert derived == replay.functions_from_runtime_plan(plan)


def test_every_case_function_inventory_matches_engine_calls() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    corpus = replay.load_corpus(CORPUS_PATH)
    for case in corpus["cases"]:
        from_calls = {
            str(call.get("fn") or "").strip()
            for call in case["runtimePlan"]["engineCalls"]
            if isinstance(call, dict) and str(call.get("fn") or "").strip()
        }
        assert set(case["functions"]) == from_calls
        assert replay.case_function_set(case) == frozenset(from_calls)


def test_select_one_changed_function_only_touching_cases() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    corpus = replay.load_corpus(CORPUS_PATH)
    all_fns = sorted(replay.corpus_function_set(corpus))
    assert all_fns, "corpus has no functions"

    # Prefer a non-universal function so selection is a proper subset when possible.
    counts: dict[str, int] = {}
    for fn in all_fns:
        counts[fn] = sum(1 for case in corpus["cases"] if fn in case["functions"])
    target = min(all_fns, key=lambda fn: (counts[fn], fn))
    selected = replay.select_cases_by_changed_functions(corpus, [target])
    assert selected
    assert all(target in case["functions"] for case in selected)
    # No duplicates.
    ids = [case["caseId"] for case in selected]
    assert len(ids) == len(set(ids))
    # Only touching cases (compare against full filter).
    expected_ids = {
        case["caseId"] for case in corpus["cases"] if target in set(case["functions"])
    }
    assert set(ids) == expected_ids
    if counts[target] < len(corpus["cases"]):
        assert len(selected) < len(corpus["cases"])


def test_specialized_author_function_selects_exact_authored_witness() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    corpus = replay.load_corpus(CORPUS_PATH)
    selected = replay.select_cases_by_changed_functions(
        corpus,
        ["fire_ranged_weapon"],
    )
    assert len(selected) == 1
    assert "fire_ranged_weapon" in set(selected[0].get("authoredFunctions") or [])
    assert "fire_ranged_weapon" in selected[0]["functions"]


def test_provenance_aware_selector_uses_exact_typed_function_identity() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    corpus = {
        "coverage": {"authoredFunctionInventoryAvailable": True},
        "cases": [
            {
                "caseId": "cast",
                "functions": ["shoot_projectile"],
                "authoredFunctions": ["cast_magic_weapon"],
                "runtimePlan": {
                    "engineCalls": [
                        {"callId": "root", "fn": "shoot_projectile", "params": {}}
                    ]
                },
            },
            {
                "caseId": "ranged",
                "functions": ["shoot_projectile"],
                "authoredFunctions": ["fire_ranged_weapon"],
                "runtimePlan": {
                    "engineCalls": [
                        {"callId": "root", "fn": "shoot_projectile", "params": {}}
                    ]
                },
            },
        ],
    }
    selected = replay.select_cases_by_changed_functions(
        corpus,
        ["fire_ranged_weapon"],
    )
    assert [case["caseId"] for case in selected] == ["ranged"]
    with pytest.raises(ValueError, match="no coverage"):
        replay.select_cases_by_changed_functions(corpus, ["deploy_sentry"])


def test_selector_fails_closed_for_unknown_or_uncovered_function() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    corpus = replay.load_corpus(CORPUS_PATH)
    with pytest.raises(ValueError, match="unknown changed engine functions"):
        replay.select_cases_by_changed_functions(corpus, ["invented_function"])
    uncovered = {"coverage": {"authoredFunctionInventoryAvailable": True}, "cases": []}
    with pytest.raises(ValueError, match="no coverage"):
        replay.select_cases_by_changed_functions(uncovered, ["emit_light"])


def test_dump_builder_recovers_authored_function_provenance_without_leaking_internal_keys() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    dumped = {
        "resultKind": "weapon",
        "engineCalls": [
            {
                "callId": "ranged_root",
                "fn": "shoot_projectile",
                "_authoredFn": "fire_ranged_weapon",
                "_authoredParams": {
                    "family": "bow",
                    "ammoFor": "arrow",
                    "projectileFamily": "arrow",
                },
                "params": {"runtimeFamily": "shoot", "_internal": "drop"},
            }
        ],
    }
    assert replay.authored_functions_from_runtime_plan(dumped) == frozenset(
        {"fire_ranged_weapon"}
    )
    assert replay.authored_function_forms_from_runtime_plan(dumped) == frozenset(
        {
            ("fire_ranged_weapon", "$function"),
            ("fire_ranged_weapon", "family"),
            ("fire_ranged_weapon", "ammoFor"),
            ("fire_ranged_weapon", "projectileFamily"),
        }
    )
    executable = replay.executable_runtime_plan_from_dump(dumped)
    assert executable["engineCalls"] == [
        {
            "callId": "ranged_root",
            "fn": "shoot_projectile",
            "params": {"runtimeFamily": "shoot"},
        }
    ]


def test_authored_form_extraction_does_not_guess_from_legacy_normalized_calls() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    legacy = {
        "engineCalls": [
            {
                "callId": "root",
                "fn": "shoot_projectile",
                "params": {"runtimeFamily": "sentry", "sentryPlacement": "grounded"},
            }
        ]
    }
    assert replay.authored_function_forms_from_runtime_plan(legacy) == frozenset()
    assert replay.authored_function_forms_from_runtime_plan(
        legacy,
        assume_current_is_authored=True,
    ) == frozenset(
        {
            ("shoot_projectile", "$function"),
            ("shoot_projectile", "runtimeFamily"),
            ("shoot_projectile", "sentryPlacement"),
        }
    )


def test_select_exact_changed_form_uses_typed_lowerer_graph() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    corpus = replay.load_corpus(CORPUS_PATH)
    selected = replay.select_cases_by_changed_forms(
        corpus,
        ["deploy_sentry:placement"],
    )
    assert len(selected) == 1
    assert "deploy_sentry" in set(selected[0].get("authoredFunctions") or [])
    assert any(
        call.get("fn") == "deploy_sentry"
        and "placement" in (call.get("params") or {})
        for call in selected[0]["runtimePlan"]["engineCalls"]
    )
    with pytest.raises(ValueError, match="unknown or unbound"):
        replay.select_cases_by_changed_forms(corpus, ["deploy_sentry:invented"])
    uncovered = {"coverage": {"authoredFunctionInventoryAvailable": True}, "cases": []}
    with pytest.raises(ValueError, match="no coverage"):
        replay.select_cases_by_changed_forms(uncovered, ["emit_light:strength"])


def test_select_medium_changed_set_is_union_once() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    corpus = replay.load_corpus(CORPUS_PATH)
    all_fns = sorted(replay.corpus_function_set(corpus))
    assert len(all_fns) >= 2

    # Medium set: a few mid-frequency functions.
    ranked = sorted(all_fns, key=lambda fn: sum(fn in c["functions"] for c in corpus["cases"]))
    medium = ranked[: max(2, min(4, len(ranked)))]
    selected = replay.select_cases_by_changed_functions(corpus, medium)
    ids = [case["caseId"] for case in selected]
    assert len(ids) == len(set(ids)), "union must not duplicate cases"

    expected: set[str] = set()
    for fn in medium:
        for case in corpus["cases"]:
            if fn in case["functions"]:
                expected.add(case["caseId"])
    assert set(ids) == expected
    # Order is deterministic (corpus order / sorted caseId).
    assert ids == sorted(ids)


def test_select_empty_or_large_changed_set_returns_all() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    corpus = replay.load_corpus(CORPUS_PATH)
    all_cases = corpus["cases"]
    all_ids = [case["caseId"] for case in all_cases]

    empty = replay.select_cases_by_changed_functions(corpus, [])
    assert [c["caseId"] for c in empty] == all_ids

    none = replay.select_cases_by_changed_functions(corpus, None)
    assert [c["caseId"] for c in none] == all_ids

    large = sorted(replay.corpus_function_set(corpus))
    assert large
    selected_large = replay.select_cases_by_changed_functions(corpus, large)
    assert [c["caseId"] for c in selected_large] == all_ids

    # Superset of known functions still selects all (unknown names ignored for "all" path
    # when intersection covers every case, or when empty means all — large real set covers all).
    assert len(selected_large) == len(all_cases)


def test_replay_cases_succeed_and_expected_fingerprint_matches() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    corpus = replay.load_corpus(CORPUS_PATH)
    # The corpus is deliberately small and deterministic.  Sampling made this gate
    # green while three sentry rows had dropped wire receipts, so every committed
    # case is now part of the contract gate.
    cases = corpus["cases"]
    reports = [replay.replay_case(case) for case in cases]
    assert reports
    for report in reports:
        assert report.get("ok") is True, report
        assert report.get("error") is None, report
        assert report.get("fingerprint")
        expected = report.get("expectedFingerprint") or report.get("case", {}).get(
            "expectedFinalSectionsFingerprint"
        )
        # expected comes from case field
        case_id = report["caseId"]
        case = next(c for c in corpus["cases"] if c["caseId"] == case_id)
        expected_fp = case.get("expectedFinalSectionsFingerprint")
        assert expected_fp, f"{case_id} missing expected fingerprint"
        assert report["fingerprint"] == expected_fp, (
            f"{case_id}: fingerprint mismatch {report['fingerprint']} != {expected_fp}"
        )
        assert "finalSections" in (report.get("result") or {})
        assert not (report.get("result") or {}).get("rejectedEngineCalls")
        assert not [
            row
            for row in (report.get("result") or {}).get("finalWireReceipts", [])
            if row.get("status") == "dropped"
        ]


def test_replay_fails_closed_on_dropped_receipt_or_rejected_call(monkeypatch) -> None:
    import infini_local.qa.runtime_contract_replay as replay

    case = {
        "caseId": "synthetic_fail_closed",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "weapon"}},
            ],
        },
    }
    base = {
        "schema": "infini.runtime-final-compile-result.v2",
        "identity": {},
        "finalSections": {},
        "validation": {"ok": True},
        "finalWireReceipts": [],
        "rejectedEngineCalls": [],
    }

    dropped = dict(base)
    dropped["finalWireReceipts"] = [{"status": "dropped", "authoredParam": "damage"}]
    monkeypatch.setattr(replay, "compile_runtime_plan_to_final_result", lambda _data: dropped)
    dropped_report = replay.replay_case(case)
    assert dropped_report["ok"] is False
    assert "dropped" in str(dropped_report["error"]).lower()

    rejected = dict(base)
    rejected["rejectedEngineCalls"] = [{"callId": "root", "reason": "unsupported"}]
    monkeypatch.setattr(replay, "compile_runtime_plan_to_final_result", lambda _data: rejected)
    rejected_report = replay.replay_case(case)
    assert rejected_report["ok"] is False
    assert "rejected" in str(rejected_report["error"]).lower()


def test_corpus_preserves_engine_function_coverage_report() -> None:
    import infini_local.qa.runtime_contract_replay as replay
    from infini_local.core.runtime_authoring.function_contract_registry import (
        ENGINE_FUNCTION_CONTRACT_BY_NAME,
    )

    corpus = replay.load_corpus(CORPUS_PATH)
    functions = replay.corpus_function_set(corpus)
    # Historical rows plus nine deterministic mechanical witnesses cover the
    # complete canonical function inventory without new LLM spend.
    assert functions == set(ENGINE_FUNCTION_CONTRACT_BY_NAME)
    assert "set_item_stats" in functions
    coverage = corpus.get("coverage") or {}
    assert int(coverage.get("caseCount") or 0) == len(corpus["cases"])
    assert set(coverage.get("functions") or []) == set(functions)
    normalized_functions = {
        fn
        for case in corpus["cases"]
        for fn in replay.normalized_functions_from_runtime_plan(case["runtimePlan"])
    }
    assert set(coverage.get("normalizedFunctions") or []) == normalized_functions
    assert int(coverage.get("normalizedFunctionCount") or 0) == len(normalized_functions)
    registry_functions = set(ENGINE_FUNCTION_CONTRACT_BY_NAME)
    assert set(coverage.get("registryFunctions") or []) == registry_functions
    assert int(coverage.get("registryFunctionCount") or 0) == len(registry_functions)
    assert set(coverage.get("missingRegistryFunctions") or []) == (
        registry_functions - set(coverage.get("effectiveFunctions") or [])
    )
    assert coverage.get("authoredFunctionInventoryAvailable") is True
    assert int(coverage.get("deterministicWitnessCount") or 0) == 9
    assert coverage.get("missingRegistryFunctions") == []
    authored_forms = set(coverage.get("authoredForms") or [])
    assert int(coverage.get("authoredFormCount") or 0) == len(authored_forms)
    assert "deploy_sentry:placement" in authored_forms
    assert "fire_ranged_weapon:ammoFor" in authored_forms
    lowerer_functions = {
        name
        for name, spec in ENGINE_FUNCTION_CONTRACT_BY_NAME.items()
        if spec.lowerers
    }
    assert lowerer_functions <= set(coverage.get("authoredFunctions") or [])


def test_contract_fingerprint_diff_is_form_local_and_fail_closed_on_removal() -> None:
    import infini_local.qa.runtime_contract_replay as replay

    current = replay.runtime_contract_fingerprint_manifest()
    same = replay.diff_runtime_contract_fingerprints(current, current)
    assert same == {
        "fullReplay": False,
        "changedFunctions": [],
        "changedForms": [],
        "reason": "no_contract_diff",
    }

    changed = deepcopy(current)
    changed["functions"]["deploy_sentry"]["formFingerprints"]["placement"] = "changed"
    diff = replay.diff_runtime_contract_fingerprints(current, changed)
    assert diff["fullReplay"] is False
    assert diff["changedFunctions"] == []
    assert diff["changedForms"] == ["deploy_sentry:placement"]

    removed = deepcopy(current)
    del removed["functions"]["deploy_sentry"]["formFingerprints"]["placement"]
    diff = replay.diff_runtime_contract_fingerprints(current, removed)
    assert diff["changedFunctions"] == ["deploy_sentry"]
    assert diff["changedForms"] == []


def test_committed_fingerprints_are_derived_and_cli_routes_exact_contract_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import infini_local.qa.runtime_contract_replay as replay

    committed = json.loads(FINGERPRINT_PATH.read_text(encoding="utf-8"))
    current = replay.runtime_contract_fingerprint_manifest()
    assert committed == current

    spec = importlib.util.spec_from_file_location("runtime_replay_checker_test", CHECKER)
    assert spec and spec.loader
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)

    baseline = deepcopy(current)
    baseline["functions"]["deploy_sentry"]["formFingerprints"]["placement"] = "old"
    monkeypatch.setattr(checker, "_baseline_fingerprints", lambda _ref, _path: baseline)
    args = argparse.Namespace(
        corpus=CORPUS_PATH,
        functions=[],
        form=[],
        out=None,
        changed_contracts_from="BASE",
        fingerprints=FINGERPRINT_PATH,
        quiet=True,
    )
    report = checker.build_report(args)
    assert report["ok"] is True
    assert report["selectedCaseCount"] == 1
    assert report["selection"]["mode"] == "affected"
    assert report["selection"]["forms"] == ["deploy_sentry:placement"]
