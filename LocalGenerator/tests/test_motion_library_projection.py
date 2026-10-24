"""Library QA distinguishes current Author choices from retained wire metadata."""
from dataclasses import replace
import pytest

from infini_local.qa import capability_library_audit as audit
from infini_local.core.schema_validation import strict_schema_errors


def issues(code):
    return [row for row in audit.capability_library_audit()["issues"] if row["code"] == code]


def test_current_author_projections_do_not_require_hidden_wire_capabilities():
    assert not issues("registry_projection_mismatch")


@pytest.mark.parametrize("projection", ["provider", "prompt"])
def test_hidden_capability_leak_is_still_an_audit_failure(monkeypatch, projection):
    fn = "move_phase"
    if projection == "provider":
        rows = audit.capability_provider_union()
        monkeypatch.setattr(audit, "capability_provider_union", lambda: rows + [{"properties": {"fn": {"const": fn}}}])
    else:
        rows = audit.compact_capability_catalog()
        monkeypatch.setattr(audit, "compact_capability_catalog", lambda: rows + [{"fn": fn}])
    assert any(row["path"] == projection and f"extra=['{fn}']" in row["message"]
               for row in issues("registry_projection_mismatch"))


def test_exclusive_numeric_endpoints_are_real_bounds_not_unbounded_params():
    assert not issues("unbounded_numeric_param")
    for fn in ("set_front_arm_pose", "set_projectile_reach_curve"):
        spec = audit.CAPABILITY_REGISTRY[fn].params["peakProgress"]
        assert not strict_schema_errors(0.5, spec.schema())
        assert strict_schema_errors(0, spec.schema())
        assert strict_schema_errors(1, spec.schema())


def test_truly_missing_numeric_endpoint_is_still_rejected(monkeypatch):
    fn = "configure_item_stats"
    caps = dict(audit.CAPABILITY_REGISTRY)
    cap = caps[fn]
    caps[fn] = replace(cap, params={**cap.params, "damage": replace(cap.params["damage"], minimum=None)})
    monkeypatch.setattr(audit, "CAPABILITY_REGISTRY", caps)
    assert any(row["path"] == f"capabilities.{fn}.params.damage" for row in issues("unbounded_numeric_param"))


def test_enabled_trigger_is_a_known_validated_requirement():
    assert not issues("unknown_requirement_kind")


def test_enabled_trigger_cannot_reference_an_unknown_parameter(monkeypatch):
    fn = "set_projectile_return_trigger"
    caps = dict(audit.CAPABILITY_REGISTRY)
    cap = caps[fn]
    caps[fn] = replace(cap, requirements=tuple(replace(rule, any_of=("unregistered",))
        if rule.kind == "enabled_trigger" else rule for rule in cap.requirements))
    monkeypatch.setattr(audit, "CAPABILITY_REGISTRY", caps)
    assert any(row["path"] == f"capabilities.{fn}.requirements"
               for row in issues("unknown_enabled_trigger_param"))


def test_inventory_marks_author_choices_and_retained_wire_rows_separately():
    import runpy
    from pathlib import Path
    renderer = runpy.run_path(str(Path(__file__).resolve().parents[2] / "tools/generate/generate_low_level_runtime_docs.py"))
    # Rendering metadata is a unit-test input, not a fabricated audit result.
    text = renderer["inventory_markdown"]({"score": 0, "scoreMax": 100, "errorCount": 1, "warningCount": 0})
    caps = audit.CAPABILITY_REGISTRY
    visible = sum(cap.author_visible for cap in caps.values())
    assert f"**{visible} Author-visible capabilities**" in text
    assert f"**{len(caps) - visible} saved-wire-only capabilities**" in text
    for fn, cap in caps.items():
        row = next(line for line in text.splitlines() if line.startswith(f"| `{fn}` |"))
        assert row.split("|")[2].strip() == ("да" if cap.author_visible else "нет (saved wire)")
    shape = renderer["param_shape"](caps["set_front_arm_pose"].params["peakProgress"])
    assert "exclusiveMinimum=0" in shape and "exclusiveMaximum=1" in shape
