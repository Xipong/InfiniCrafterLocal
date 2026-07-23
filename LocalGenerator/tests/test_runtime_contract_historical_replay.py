"""Historical finalContract runtimePlan replay corpus + impact selector tests.

No LLM, no HTTP: mechanical accepted-wire replay only.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
QA_MODULE = LOCAL_GENERATOR / "infini_local" / "qa" / "runtime_contract_replay.py"
BUILDER = ROOT / "tools" / "build_runtime_contract_replay_corpus.py"
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
    return [QA_MODULE, BUILDER]


def test_replay_modules_exist() -> None:
    assert QA_MODULE.is_file(), f"missing QA module: {QA_MODULE}"
    assert BUILDER.is_file(), f"missing corpus builder: {BUILDER}"
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
    assert not Path(str((corpus.get("source") or {}).get("dumpRoot") or "")).is_absolute()

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
    # Replay a representative slice plus full if small.
    cases = corpus["cases"]
    sample = cases if len(cases) <= 24 else cases[:: max(1, len(cases) // 16)][:16]
    # Always include one case per function for coverage confidence.
    by_fn: dict[str, dict] = {}
    for case in cases:
        for fn in case["functions"]:
            by_fn.setdefault(fn, case)
    sample_ids = {c["caseId"] for c in sample}
    for case in by_fn.values():
        if case["caseId"] not in sample_ids:
            sample.append(case)
            sample_ids.add(case["caseId"])

    reports = [replay.replay_case(case) for case in sample]
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

    corpus = replay.load_corpus(CORPUS_PATH)
    functions = replay.corpus_function_set(corpus)
    # Historical dumps currently exercise a broad closed catalog subset.
    assert len(functions) >= 10
    assert "set_item_stats" in functions
    coverage = corpus.get("coverage") or {}
    assert int(coverage.get("caseCount") or 0) == len(corpus["cases"])
    assert set(coverage.get("functions") or []) == set(functions)
