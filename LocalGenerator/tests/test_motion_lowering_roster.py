"""The generated reference must describe real selected projections, not ban them."""
from dataclasses import fields, replace
from pathlib import Path
import runpy
from types import SimpleNamespace

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.technical_lowering import capability_fixed_outputs


def test_lowery_reference_lists_current_exact_aliases_and_fn_selected_outputs():
    root = Path(__file__).resolve().parents[2]
    rendered = runpy.run_path(str(root / "tools/generate/generate_lowery.py"))["render"]()
    assert "Gameplay Author-visible semantic aliases: **нет**" not in rendered
    assert "## Запрет на добавление alias" not in rendered
    assert "authoredSourceChecked=false" in rendered
    for fn, cap in CAPABILITY_REGISTRY.items():
        if cap.wire_action:
            assert fn in rendered and cap.wire_action in rendered
        for path in capability_fixed_outputs(fn):
            assert path in rendered, (fn, path)
    # These are selected, independently executable choices, not weapon presets.
    assert "pull_owner_to_event_target" in rendered
    assert "owner_to_target" in rendered
    assert "declared_neutral_omission" in rendered


def test_lowery_renders_player_effect_producer_predicate_from_event_metadata(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    render = runpy.run_path(str(root / "tools/generate/generate_lowery.py"))["render"]
    events = render.__globals__["EVENT_KIND_REGISTRY"]
    rendered = render()
    for event in events.values():
        member = getattr(event, "producer_player_effect_member", "")
        if member:
            row = next(line for line in rendered.splitlines() if line.startswith(f"| {event.name} |"))
            assert row.endswith(f"| playerEffect.{member} present |")

    # A changed owner fact must reach the output, including on branches whose
    # EventKindSpec predates this optional presentation metadata.
    event = next(iter(events.values()))
    event_values = {field.name: getattr(event, field.name) for field in fields(event)}
    event_values["producer_player_effect_member"] = "futureJump"
    monkeypatch.setitem(render.__globals__, "EVENT_KIND_REGISTRY", {
        **events, event.name: SimpleNamespace(**event_values),
    })
    row = next(line for line in render().splitlines() if line.startswith(f"| {event.name} |"))
    assert row.endswith("| playerEffect.futureJump present |")
    del event_values["producer_player_effect_member"]
    monkeypatch.setitem(render.__globals__, "EVENT_KIND_REGISTRY", {
        **events, event.name: SimpleNamespace(**event_values),
    })
    row = next(line for line in render().splitlines() if line.startswith(f"| {event.name} |"))
    assert row.endswith("| — |")


def test_lowery_mapping_rows_distinguish_author_choices_from_retained_runtime(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    render = runpy.run_path(str(root / "tools/generate/generate_lowery.py"))["render"]
    registry = render.__globals__["CAPABILITY_REGISTRY"]
    examples = ("move_straight", "move_orbit", "spawn_entity_from_hit_target", "pull_owner_to_event_target")

    def assert_availability(rendered, capabilities):
        for fn in examples:
            rows = [line for line in rendered.splitlines() if line.startswith(f"| {fn} |")]
            availability = "fresh Author" if capabilities[fn].author_visible else "retained runtime"
            # Selected-output and explicit event-projection rows carry a label;
            # the separate native opcode inventory remains an opcode inventory.
            wire_action = capabilities[fn].wire_action
            mapping_rows = [line for line in rows if "runtimeProgram." in line
                            or (wire_action and wire_action in line)]
            assert len(mapping_rows) == len(capability_fixed_outputs(fn)) + bool(wire_action), fn
            assert all(line.startswith(f"| {fn} | {availability} |") for line in mapping_rows), mapping_rows

    assert_availability(render(), registry)
    changed = {**registry, **{fn: replace(registry[fn], author_visible=not registry[fn].author_visible)
                             for fn in examples}}
    monkeypatch.setitem(render.__globals__, "CAPABILITY_REGISTRY", changed)
    assert_availability(render(), changed)
