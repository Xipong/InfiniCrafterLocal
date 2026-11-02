"""Saved native observations enrich context only, not recipe/input authority."""
from __future__ import annotations

import copy
import json
import socket

import pytest

from infini_local.core.item_identity_tools import recipe_key
from infini_local.pipelines.context import cards, parents
from infini_local.pipelines.author import request as author
from infini_local.services import runtime_dump_service as dumps
from prompt_packet_helpers import expand_native_source_references, request_dossier
from test_runtime_dump_snapshot import manifest_pair, use_snapshot


@pytest.fixture
def saved_row(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("context-only fixture must not use the network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    row = {
        "type": 97, "id": 97, "sourceMod": "Example", "internalName": "Parent", "fullName": "Example/Parent",
        "name": "Stored name", "damage": 999, "manaCost": 99, "useTime": 30, "shoot": 42,
        "tooltipLines": ["Literal source tooltip", ""], "tooltipSource": {"source": "fixture", "status": "partial"},
        "nativeShootReference": {"source": "fixture", "children": [{"type": 42}], "scope": "conditional source only"},
        "nativeEquipmentReference": {"source": "fixture", "unknown": True},
        "parentSourceGraph": {"source": "fixture", "completeness": "partial_source_graph", "unresolved": ["opaque_hook"]},
        "spriteReferenceRaw": {"source": "TextureAssets.Item", "textureWidthPx": 34, "textureHeightPx": 32,
                               "currentFrame": {"source": "texture_bounds", "xPx": 0, "yPx": 0, "widthPx": 34, "heightPx": 32}},
        "directProjectileRaw": {"type": 42, "timeLeft": 900, "extraUpdates": 2, "framesRaw": 8,
            "attackReference": {"source": "fixture-not-native-execution", "children": [644], "coverage": "unknown"},
            "motionReference": {"source": "fixture", "firstGravityUpdate": 15},
            "spriteReferenceRaw": {"source": "TextureAssets.Projectile", "textureWidthPx": 26,
                                   "textureHeightPx": 400, "frameLayout": "unknown_custom_draw_possible"}},
        "ammoRaw": {"fixture_current_player_ammo": "must not be borrowed"},
        "effectiveProjectileRaw": {"fixture_player_projectile": "must not be borrowed"},
    }
    path, _ = manifest_pair(tmp_path, item_rows=[row])
    use_snapshot(monkeypatch, dumps.load_runtime_dump_snapshot(path, path))
    return row


def sparse_item():
    return {"id": 97, "sourceMod": "Example", "internalName": "Parent", "name": "Live name",
            "damage": 7, "manaCost": 0, "useTime": 0, "shoot": 42}


def test_sparse_author_and_visual_cards_receive_available_whole_observations(saved_row):
    item = sparse_item()
    before = copy.deepcopy(item)
    key_before = recipe_key(item, {}, 1, "fixture-version")
    request, _, _ = author.build_initial_author_request(item, {}, "dump-item-context", model_name="offline-test")
    dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    raw = dossier["parents"]["A"]["packet"]["raw"]
    assert raw["item"]["nativeShootReference"] == saved_row["nativeShootReference"]
    assert raw["item"]["parentSourceGraph"] == saved_row["parentSourceGraph"]
    assert raw["item"]["tooltipLines"] == saved_row["tooltipLines"]
    assert raw["item"]["damage"] == 7 and raw["item"]["manaCost"] == raw["item"]["useTime"] == 0
    assert raw["directProjectile"]["timeLeft"] == 900 and raw["directProjectile"]["extraUpdates"] == 2
    assert raw["directProjectile"]["attackReference"] == saved_row["directProjectileRaw"]["attackReference"]
    assert "ammo" not in raw
    assert "fixture_player_projectile" not in json.dumps(raw)
    provenance = raw["runtimeDumpProvenance"]
    assert provenance["status"] == "verified_snapshot"
    assert provenance["compatibility"] == "matched_available_identity"
    assert "nativeShootReference" in provenance["fields"] and "damage" not in provenance["fields"]
    visual = cards.raw_parent_card_for_llm(item, include_visual_reference=True)["raw"]
    assert visual["spriteReference"]["textureWidthPx"] == 34
    assert visual["spriteReference"]["currentFrame"] == saved_row["spriteReferenceRaw"]["currentFrame"]
    assert provenance["currentModSet"] == "unverified"
    projected = parents.native_item_context_from_dump(item)
    projectile = parents.projectile_profile_of(projected)
    assert projectile["fromRuntimeDump"] is True and "fromLiveWireRaw" not in projectile
    assert visual["directProjectile"]["spriteReference"]["textureHeightPx"] == 400
    assert item == before and recipe_key(item, {}, 1, "fixture-version") == key_before


@pytest.mark.parametrize("container", ["root", "fingerprint", "runtimeFacts", "fingerprint_runtimeFacts"])
@pytest.mark.parametrize("value", [None, {}, {"unavailable": True}, {"attackReference": {"coverage": "explicit_partial"}}])
def test_present_projectile_unknown_or_partial_is_not_filled(saved_row, container, value):
    item = sparse_item()
    observations = {"directProjectileRaw": copy.deepcopy(value), "nativeShootReference": None,
                    "parentSourceGraph": {"unresolved": ["live_unknown"]}}
    if container == "root":
        item.update(observations)
    elif container == "fingerprint":
        item["fingerprint"] = observations
    elif container == "runtimeFacts":
        item["runtimeFacts"] = observations
    else:
        item["fingerprint"] = {"runtimeFacts": observations}
    before = copy.deepcopy(item)
    raw = cards.raw_parent_card_for_llm(item)["raw"]
    assert raw["item"]["parentSourceGraph"] == {"unresolved": ["live_unknown"]}
    assert "nativeShootReference" not in raw["item"]
    if value:
        assert raw["directProjectile"] == value
    else:
        assert "directProjectile" not in raw
    assert item == before


def test_root_null_beats_older_fingerprint_and_runtime_observation(saved_row):
    item = sparse_item()
    item.update(directProjectileRaw=None, parentSourceGraph=None,
                fingerprint={"directProjectileRaw": saved_row["directProjectileRaw"], "parentSourceGraph": saved_row["parentSourceGraph"]})
    raw = cards.raw_parent_card_for_llm(item)["raw"]
    assert "directProjectile" not in raw and "parentSourceGraph" not in raw["item"]
    assert "directProjectileRaw" not in raw["runtimeDumpProvenance"].get("fields", [])


def test_tooltip_observation_is_not_spliced_and_scalars_are_never_added(saved_row):
    item = sparse_item()
    item["tooltipLines"] = []
    del item["manaCost"]
    raw = cards.raw_parent_card_for_llm(item)["raw"]
    assert raw["item"]["tooltipLines"] == []
    assert "tooltipSource" not in raw["item"] and "manaCost" not in raw["item"]


def test_full_live_card_is_identical_with_or_without_dump(saved_row, monkeypatch):
    item = copy.deepcopy(saved_row)
    before = copy.deepcopy(item)
    enriched = cards.raw_parent_card_for_llm(item, include_visual_reference=True)
    monkeypatch.setattr(dumps, "RUNTIME_ITEMS_BY_TYPE", {})
    without = cards.raw_parent_card_for_llm(item, include_visual_reference=True)
    assert enriched == without and item == before
    assert "runtimeDumpProvenance" not in enriched["raw"]


def test_broken_optional_manifest_does_not_change_full_live_card(saved_row, monkeypatch):
    item = copy.deepcopy(saved_row)
    before = cards.raw_parent_card_for_llm(item, include_visual_reference=True)
    invalid = dumps.RuntimeDumpSnapshot([], {}, {"status": "invalid_snapshot", "reason": "manifest_or_pair_validation_failed"}, {})
    use_snapshot(monkeypatch, invalid)
    after = cards.raw_parent_card_for_llm(item, include_visual_reference=True)
    assert after == before and item == saved_row
    assert "runtimeDumpProvenance" not in after["raw"]


@pytest.mark.parametrize("change,reason", [
    ({"internalName": "Different"}, "item_identity_mismatch"),
    ({"sourceMod": "OtherMod"}, "item_identity_mismatch"),
    ({"shoot": 0}, "item_shoot_identity_mismatch"),
    ({"parentSourceGraph": {"modules": [{"assembly": "tModLoader", "mvid": "different"}]}}, "observed_module_mismatch"),
])
def test_known_identity_collision_refuses_item_enrichment(saved_row, change, reason):
    item = {**sparse_item(), **change}
    raw = cards.raw_parent_card_for_llm(item)["raw"]
    assert "nativeShootReference" not in raw["item"] and "tooltipLines" not in raw["item"]
    assert "runtimeDumpProvenance" not in raw
    full_name = item["sourceMod"] + "/" + item["internalName"]
    result = dumps.runtime_item_lookup(97, expected_full_name=full_name,
        expected_modules=item.get("parentSourceGraph", {}).get("modules"), expected_shoot=item["shoot"])
    assert result["unavailable"] is True and result["runtimeDumpProvenance"]["reason"] == reason


def test_unknown_identity_and_legacy_do_not_enable_new_item_route(saved_row, monkeypatch):
    raw = cards.raw_parent_card_for_llm({"id": 97})["raw"]
    assert "nativeShootReference" not in raw["item"]
    assert "runtimeDumpProvenance" not in raw
    assert dumps.runtime_item_lookup(97)["runtimeDumpProvenance"]["reason"] == "stable_item_identity_unavailable"
    old = dumps.RUNTIME_DUMP_SNAPSHOT
    legacy = dumps.RuntimeDumpSnapshot(old.items, old.projectiles, {"status": "legacy_unverified"}, {})
    use_snapshot(monkeypatch, legacy)
    raw = cards.raw_parent_card_for_llm(sparse_item())["raw"]
    assert "runtimeDumpProvenance" not in raw
    assert dumps.runtime_item_lookup(97, expected_full_name="Example/Parent")["runtimeDumpProvenance"]["reason"] == "item_snapshot_not_integrity_verified"
    assert "nativeShootReference" not in raw["item"]
    assert raw["directProjectile"]["runtimeDumpProvenance"]["status"] == "legacy_unverified"


@pytest.mark.parametrize("marker", [{"generatedData": {}}, {"generatedData": {"runtimeProgram": {}}},
                                    {"runtimeFacts": None}, {"runtimeFacts": {"unavailable": True}}])
def test_generated_and_explicit_unavailable_item_envelopes_exclude_enrichment(saved_row, marker):
    item = {**sparse_item(), **marker}
    assert parents.native_item_context_from_dump(item) is item


@pytest.mark.parametrize("key", ["DirectProjectileRaw", "dIrEcTpRoJeCtIlErAw"])
@pytest.mark.parametrize("container", ["root", "fingerprint"])
@pytest.mark.parametrize("value", [None, {}, {"type": 900, "timeLeft": 11}])
def test_existing_case_insensitive_projectile_presence_is_preserved(saved_row, key, container, value):
    item = sparse_item()
    if container == "root":
        item[key] = value
    else:
        item["fingerprint"] = {key: value}
    raw = cards.raw_parent_card_for_llm(item)["raw"]
    if value:
        assert raw["directProjectile"] == value
    else:
        assert "directProjectile" not in raw
    assert "directProjectileRaw" not in raw["runtimeDumpProvenance"].get("fields", [])


def test_exact_case_key_and_root_runtime_presence_win(saved_row):
    item = {**sparse_item(), "directProjectileRaw": None, "DirectProjectileRaw": {"type": 900},
            "EffectiveProjectileRaw": None,
            "RuntimeFacts": {"NativeEquipmentReference": None, "ParentSourceGraph": {"unresolved": ["live"]}},
            "fingerprint": {"directProjectileRaw": saved_row["directProjectileRaw"]}}
    raw = cards.raw_parent_card_for_llm(item)["raw"]
    assert "directProjectile" not in raw and "effectiveProjectile" not in raw
    assert "nativeEquipmentReference" not in raw["item"]
    assert raw["item"]["parentSourceGraph"] == {"unresolved": ["live"]}


def test_existing_fingerprint_precedes_runtime_facts_when_both_observed(saved_row):
    item = {**sparse_item(),
            "fingerprint": {"directProjectileRaw": {"type": 81, "timeLeft": 10},
                            "nativeEquipmentReference": {"source": "fingerprint"},
                            "parentSourceGraph": {"source": "fingerprint"}},
            "runtimeFacts": {"directProjectileRaw": {"type": 82, "timeLeft": 20},
                             "nativeEquipmentReference": {"source": "runtime"},
                             "parentSourceGraph": {"source": "runtime"}}}
    raw = cards.raw_parent_card_for_llm(item)["raw"]
    assert raw["directProjectile"] == {"type": 81, "timeLeft": 10}
    assert raw["item"]["nativeEquipmentReference"] == {"source": "fingerprint"}
    assert raw["item"]["parentSourceGraph"] == {"source": "fingerprint"}
