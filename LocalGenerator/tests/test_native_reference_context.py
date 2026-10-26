"""Loaded status identities are design vocabulary, never inherited mechanics."""
from __future__ import annotations

import copy

from infini_local.pipelines.native_reference_context import loaded_status_identity_choices


def catalog(entries, complete=True):
    return {"loadedBuffIdentitiesRaw": {"source": "native_loaded_buff_registry", "complete": complete,
        "entries": [{"id": identity, "fullName": name} for identity, name in entries],
        "scope": "Current loaded identity registry; not parent behavior."}}


def test_loaded_identity_choices_are_shared_detached_and_include_mod_content():
    parent = catalog([(20, "Terraria/Poisoned"), (410, "ExampleMod/CorrosiveMark")])
    before = copy.deepcopy(parent)
    result = loaded_status_identity_choices(parent, parent)
    assert result is not None
    assert result["byMod"] == {"Terraria": {"Poisoned": 20}, "ExampleMod": {"CorrosiveMark": 410}}
    assert result["complete"] is True
    assert "not" in result["scope"].lower() and "parent" in result["scope"].lower()
    result["byMod"]["Terraria"]["Poisoned"] = 99
    assert parent == before


def test_missing_registry_stays_unknown_and_partial_choices_remain_usable():
    assert loaded_status_identity_choices({}, {}) is None
    result = loaded_status_identity_choices(catalog([(20, "Terraria/Poisoned")], complete=False), {})
    assert result is not None and result["complete"] is False
    assert result["byMod"] == {"Terraria": {"Poisoned": 20}}


def test_conflicting_native_identity_observations_never_choose_a_parent():
    a = catalog([(20, "Terraria/Poisoned"), (410, "ExampleMod/Mark"), (411, "ExampleMod/Other")])
    b = catalog([(20, "Terraria/Poisoned"), (410, "DifferentMod/Mark"), (412, "ExampleMod/Other")])
    for first, second in [(a, b), (b, a)]:
        result = loaded_status_identity_choices(first, second)
        assert result is not None and result["complete"] is False
        assert result["byMod"] == {"Terraria": {"Poisoned": 20}}


def test_registered_identity_names_are_preserved_not_repaired_or_lexically_reclassified():
    name = "Example-Mod/Residual Flame"
    result = loaded_status_identity_choices(catalog([(410, name)]), {})
    assert result is not None
    assert result["byMod"] == {"Example-Mod": {"Residual Flame": 410}}


def test_malformed_identity_rows_do_not_invent_or_coerce_a_runtime_id():
    value = catalog([(20, "Terraria/Poisoned")])
    value["loadedBuffIdentitiesRaw"]["entries"] += [
        {"id": True, "fullName": "ExampleMod/Bool"}, {"id": "410", "fullName": "ExampleMod/Text"},
        {"id": 0, "fullName": "ExampleMod/Zero"}, {"id": 65536, "fullName": "ExampleMod/Overflow"},
        {"id": 400, "fullName": "not_registered_full_name"},
    ]
    result = loaded_status_identity_choices(value, {})
    assert result is not None and result["complete"] is False
    assert result["byMod"] == {"Terraria": {"Poisoned": 20}}
