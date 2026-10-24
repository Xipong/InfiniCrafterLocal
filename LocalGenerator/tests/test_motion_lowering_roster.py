"""The generated reference must describe real selected projections, not ban them."""
from pathlib import Path
import runpy

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
