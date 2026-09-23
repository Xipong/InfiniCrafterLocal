"""Contract: a stale config registry must say what drifted.

``tools/config_registry.py --check`` used to print a single verdict::

    {"ok": false, "error": "config registry is stale", "path": "..."}

That is true but unactionable: it does not distinguish "a new setting appeared"
from "a default moved" from "only the fingerprint needs refreshing", so the only
way to learn the cause is to regenerate and diff the artifact by hand. The check
already holds both the stored and the freshly built document, so it can name the
difference directly.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_TOOL = ROOT / "tools" / "config_registry.py"


def _load_registry_module():
    module_name = "config_registry_for_tests"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, REGISTRY_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The tool defines dataclasses; dataclasses resolves annotations through
    # sys.modules[cls.__module__], so the module must be registered before exec.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _document(entries: list[dict]) -> str:
    return json.dumps({"entries": entries}, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _contract_check_added_and_removed_fields_are_named() -> None:
    module = _load_registry_module()
    previous = _document([
        {"name": "INFINI_KEPT", "default": "1"},
        {"name": "INFINI_GONE", "default": "0"},
    ])
    current = _document([
        {"name": "INFINI_KEPT", "default": "1"},
        {"name": "INFINI_NEW", "default": "warn"},
    ])

    report = module._stale_registry_report(previous, current, Path("registry.json"))

    assert report["ok"] is False
    assert report["addedFields"] == ["INFINI_NEW"]
    assert report["removedFields"] == ["INFINI_GONE"]
    # The operator must be told how to fix it, not just that it is broken.
    assert "config_registry.py" in report["regenerate"]
    assert "changedFields" not in report


def _contract_check_changed_attributes_report_before_and_after() -> None:
    module = _load_registry_module()
    previous = _document([
        {"name": "INFINI_LEVEL", "default": "error", "gui": False, "documented": False},
    ])
    current = _document([
        {"name": "INFINI_LEVEL", "default": "warn", "gui": True, "documented": False},
    ])

    report = module._stale_registry_report(previous, current, Path("registry.json"))

    changed = report["changedFields"]["INFINI_LEVEL"]
    assert changed["default"] == {"was": "error", "now": "warn"}
    assert changed["gui"] == {"was": False, "now": True}
    # Attributes that did not move must not be listed as drift.
    assert "documented" not in changed
    assert "addedFields" not in report
    assert "removedFields" not in report


def _contract_check_counter_only_drift_is_stated_rather_than_left_blank() -> None:
    module = _load_registry_module()
    # Identical field content: only derived counters/fingerprint would differ.
    same = _document([{"name": "INFINI_KEPT", "default": "1"}])

    report = module._stale_registry_report(same, same, Path("registry.json"))

    assert "counters" in report["reason"] or "fingerprint" in report["reason"]
    assert "addedFields" not in report
    assert "changedFields" not in report


def _contract_check_missing_or_unreadable_registry_is_distinguished() -> None:
    module = _load_registry_module()
    current = _document([{"name": "INFINI_KEPT", "default": "1"}])

    missing = module._stale_registry_report("", current, Path("registry.json"))
    assert missing["reason"] == "registry file is missing"

    corrupt = module._stale_registry_report("{not json", current, Path("registry.json"))
    assert "not readable" in corrupt["reason"]


def _contract_check_real_tool_reports_a_named_difference_not_only_stale(tmp_path) -> None:
    """End-to-end through the tool's own CLI path, on the real project registry."""
    module = _load_registry_module()
    report = module.build_registry()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    # Drop one real field to simulate the drift an agent has to diagnose.
    document = json.loads(text)
    dropped = document["entries"].pop()["name"]
    stale_path = tmp_path / "config_registry.json"
    stale_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    diagnosis = module._stale_registry_report(
        stale_path.read_text(encoding="utf-8"), text, stale_path
    )
    assert diagnosis["addedFields"] == [dropped]


# One collected item per contract module: the checks above keep source order and
# their own tracebacks. The shared runner discovers them by prefix, so a new check
# cannot be silently left out of a hand-maintained dispatch list.
def test_config_registry_staleness_diagnostics_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request)
