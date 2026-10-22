import json
from pathlib import Path


def _load(case, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "tools"))
    from experiment_capability_selection_followup import functional_checks
    source = root / "docs/development/experiments/capability_selection_2026-10-22/outputs/capabilities" / f"{case}.json"
    return json.loads(source.read_text()), functional_checks


def test_configured_child_without_producer_does_not_count(monkeypatch):
    doc, score = _load("musket", monkeypatch)
    assert score(doc, "musket")["reachable_hit_homing_child"]
    doc["runtimeProgram"]["calls"] = [c for c in doc["runtimeProgram"]["calls"] if c["fn"] != "spawn_entity_on_event"]
    assert not score(doc, "musket")["reachable_hit_homing_child"]


def test_held_effect_requires_matching_refresher_group(monkeypatch):
    doc, score = _load("tool", monkeypatch)
    assert score(doc, "tool")["held_ore_regeneration"]
    for call in doc["runtimeProgram"]["calls"]:
        if call["fn"] == "refresh_generated_effect_group_while_held":
            call["params"]["effectGroupId"] = "unrelated_group"
    assert not score(doc, "tool")["held_ore_regeneration"]


def test_shared_on_use_path_breaks_alternate_isolation(monkeypatch):
    doc, score = _load("tool", monkeypatch)
    assert score(doc, "tool")["isolated_alternate_returner"]
    program = doc["runtimeProgram"]
    body = next(e["id"] for e in program["entities"] if e["kind"] == "item_body")
    target = next(b["action"]["targetId"] for b in program["bindings"] if b["input"] == "alternate_use")
    program["calls"].append({"id": "duplicate_returner", "fn": "spawn_entity_on_event", "target": body,
                             "params": {"when": "on_use", "entity": target}})
    assert not score(doc, "tool")["isolated_alternate_returner"]


def test_shared_on_use_straight_shot_breaks_reverse_input_isolation(monkeypatch):
    doc, score = _load("tool", monkeypatch)
    assert score(doc, "tool")["isolated_alternate_returner"]
    program = doc["runtimeProgram"]
    body = next(e["id"] for e in program["entities"] if e["kind"] == "item_body")
    target = next(b["action"]["targetId"] for b in program["bindings"] if b["input"] == "primary_use")
    program["calls"].append({"id": "duplicate_straight", "fn": "spawn_entity_on_event", "target": body,
                             "params": {"when": "on_use", "entity": target}})
    assert not score(doc, "tool")["isolated_alternate_returner"]


def test_live_parent_damage_requires_enabled_child_but_not_positive_authored_base(monkeypatch):
    doc, score = _load("musket", monkeypatch)
    calls = doc["runtimeProgram"]["calls"]
    event = next(c for c in calls if c["fn"] == "spawn_entity_on_event")
    event["params"]["damageBasis"] = "live_parent"
    child = event["params"]["entity"]
    damage_call = next(c for c in calls if c["fn"] == "set_projectile_damage" and c["target"] == child)
    damage_call["params"]["damage"] = 0
    assert score(doc, "musket")["reachable_hit_homing_child"]
    calls.remove(damage_call)
    assert not score(doc, "musket")["reachable_hit_homing_child"]


def test_held_group_must_not_occupy_active_action_in_followup_brief(monkeypatch):
    doc, score = _load("tool", monkeypatch)
    program = doc["runtimeProgram"]
    held = next(c for c in program["calls"] if c["fn"] == "refresh_generated_effect_group_while_held")
    binding = next(b for b in program["bindings"] if b["input"] == "alternate_use")
    binding["action"] = {"kind": "apply_item_effects", "targetId": held["target"], "effectGroupId": held["params"]["effectGroupId"]}
    assert not score(doc, "tool")["held_ore_regeneration"]
