import json
from pathlib import Path


def _check_vfx_morph_recipes_schema_is_parseable_and_slot_shaped():
    path = Path(__file__).resolve().parents[1] / "data" / "vfx_morph_recipes.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("schema") == "infini.vfx.morph_recipes.v9_mundane_guard"
    recipes = data.get("recipes")
    assert isinstance(recipes, list) and recipes

    seen_ids: set[str] = set()
    for recipe in recipes:
        rid = recipe.get("id")
        assert isinstance(rid, str) and rid.strip(), recipe
        assert rid not in seen_ids, rid
        seen_ids.add(rid)
        assert isinstance(recipe.get("compatiblePatterns"), list), rid
        assert isinstance(recipe.get("requiredRoles"), list), rid

        slots = recipe.get("slots")
        macros = recipe.get("useMacros")
        assert isinstance(slots, list) or isinstance(macros, list), rid
        if isinstance(slots, list):
            assert slots, rid
            for slot in slots:
                assert isinstance(slot, dict), rid
                for key in ("event", "renderer", "textureRole"):
                    assert isinstance(slot.get(key), str) and slot.get(key).strip(), (rid, slot)
        if isinstance(macros, list):
            assert macros, rid
            for macro in macros:
                assert isinstance(macro, (str, dict)), (rid, macro)


def _check_authored_visual_effect_cue_becomes_frozen_vfx_slot():
    from infini_local.core.vfx_manifest import attach_hybrid_vfx_manifest

    data = {
        "id": "cue_test",
        "name": "Cue Test Wand",
        "category": "weapon",
        "gameplay": {"powerBudget": 1.0},
        "attack": {
            "enabled": True,
            "pattern": "projectile",
            "vfxCues": [
                {
                    "event": "hit",
                    "rendererKind": "impactRing",
                    "channel": "impactShape",
                    "lane": "primary",
                    "particleSystemId": "pl:spark",
                    "scale": 1.8,
                    "density": 0.6,
                    "duration": 20,
                    "alpha": 0.85,
                    "note": "authored ring",
                }
            ],
        },
        "visualKit": {"vfxCues": []},
    }
    out = attach_hybrid_vfx_manifest(data, "cue_test_key")
    manifest = out["vfxManifest"]
    slots = manifest["slots"]
    assert any(s.get("source") == "authoredCue" and s.get("rendererKind") == "impactRing" for s in slots)
    comp = manifest["debug"]["composition"]
    assert comp["authoredCueSlots"][0]["rendererKind"] == "impactRing"
    assert comp["mode"] in {"authored_cues_plus_recipe", "runtime_plan_direct_authored_cues"}

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_vfx_morph_recipes_schema_is_parseable_and_slot_shaped',
    '_check_authored_visual_effect_cue_becomes_frozen_vfx_slot'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_vfx_morph_recipes_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
