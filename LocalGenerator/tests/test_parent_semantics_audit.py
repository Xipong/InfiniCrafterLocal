"""Audit the executed parent projection, not implementation spelling."""
import importlib.util
from pathlib import Path


def test_standardization_audit_accepts_exact_deepcopy_parent_projection(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("parent_semantics_audit", root / "tools/checks/audit_terraria_standardization.py")
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    row = next(row for row in audit.report()["checks"] if row["name"] == "generated_parent_preserves_exact_item_semantics")
    assert row["ok"], row
    from infini_local.pipelines import parent_context_cards
    original = parent_context_cards.raw_parent_card_for_llm

    def lossy(*args, **kwargs):
        card = original(*args, **kwargs)
        card["raw"]["generatedParent"]["gameplay"].pop("potion", None)
        return card

    monkeypatch.setattr(parent_context_cards, "raw_parent_card_for_llm", lossy)
    row = next(row for row in audit.report()["checks"] if row["name"] == "generated_parent_preserves_exact_item_semantics")
    assert not row["ok"]


def test_value_audit_checks_projection_not_negative_prose(monkeypatch):
    from dataclasses import replace

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("value_semantics_audit", root / "tools/checks/audit_terraria_standardization.py")
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    registry = dict(audit.CAPABILITY_REGISTRY)
    stats = registry["configure_item_stats"]
    params = dict(stats.params)
    value = replace(params["valueCopper"], description="NPC shop base price (Item.value).")
    params["valueCopper"] = value
    registry["configure_item_stats"] = replace(stats, params=params)
    monkeypatch.setattr(audit, "CAPABILITY_REGISTRY", registry)

    def accepted():
        return next(row["ok"] for row in audit.report()["checks"] if row["name"] == "item_value_semantics")

    assert accepted()
    params["valueCopper"] = replace(value, wire_divisor=5)
    assert not accepted(), "a resale-style conversion must not pass as exact Item.value"
    params["valueCopper"] = replace(value, wire_name="resaleValue")
    assert not accepted(), "the destination field matters independently of numeric identity"
