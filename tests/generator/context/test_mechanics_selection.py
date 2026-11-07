"""Generic connected gameplay projection, including explicit refusal cases."""

import copy
from infini_local.pipelines.context.mechanics_selection import select_gameplay_roots
from infini_local.pipelines.context.parents import _gameplay_identity_program


def _program():
    return {
        "method": "Fixture.AI",
        "observations": [
            {"kind": "state_write", "expression": "set((this).Entity.velocity,d1)", "requiredPredicates": ["b1"], "step": 5},
            {"kind": "state_write", "expression": "set((this).Projectile.alpha,0)", "requiredPredicates": [], "step": 6},
            {"kind": "motion_call", "call": "Utils.SelectRandom", "step": 7},
        ],
        "dependencies": {
            "d1": {"expression": "d2", "requiredPredicates": ["b2"], "step": 1},
            "d2": {"expression": "d1", "step": 2},
            "d3": {"expression": "unused", "step": 3},
        },
        "predicates": [
            {"id": "b1", "inputs": ["d2"], "step": 0},
            {"id": "b2", "inputs": ["1"], "step": 1},
            {"id": "b3", "inputs": ["unused"], "step": 3},
        ],
        "identitySelection": {"forCapturedIdentity": True, "fullMethodCapture": {"coverage": "unknown", "unresolved": "bound"}},
        "unresolved": ["source_unknown"],
    }


def test_roots_and_transitive_cyclic_closure_remain_literal_and_ordered():
    original = _program()
    before = copy.deepcopy(original)
    result, scope = select_gameplay_roots(original)
    assert result["observations"] == original["observations"][:1]
    assert result["dependencies"] == {k: original["dependencies"][k] for k in ("d1", "d2")}
    assert result["predicates"] == original["predicates"][:2]
    assert result["identitySelection"] == original["identitySelection"]
    assert result["unresolved"] == original["unresolved"]
    assert scope["omittedObservations"] == 2 and scope["omittedPredicates"] == 1
    assert "may affect" in scope["scope"] and original == before


def test_unknown_kind_or_missing_dependency_keeps_allowlisted_roots_with_explicit_unknown():
    for missing in ("dependency", "predicate"):
        program = _program()
        if missing == "dependency":
            program["dependencies"].pop("d2")
        else:
            program["predicates"] = [row for row in program["predicates"] if row["id"] != "b2"]
        result, scope = select_gameplay_roots(program)
        assert result == program and scope["unresolved"] == "gameplay_selection_unavailable"
    p = _program()
    p["observations"].append({"kind": "future_mod_specific_kind", "step": 8})
    result, scope = select_gameplay_roots(p)
    assert result == p and scope["mode"] == "all_allowlisted_roots"


def test_program_allowlist_drops_diagnostics_and_marks_omission():
    p = _program()
    p["diagnosticSecretMarker"] = "secret"
    p["observations"][0]["diagnosticSecretMarker"] = "secret"
    out, omitted = _gameplay_identity_program(p)
    assert "diagnosticSecretMarker" not in str(out)
    assert omitted and "diagnosticSecretMarker" not in str(omitted) and out["unresolved"] == p["unresolved"]


def test_graph_preserves_native_receiver_identity_and_stack_values_but_not_unknown_fields():
    from infini_local.pipelines.context.mechanics_context import _author_source_graph

    original = {
        "source": "parent_reachable_compiled_source_graph",
        "version": 1,
        "nodes": [
            {
                "id": 0,
                "receiverType": 1,
                "sourceSelection": "mechanical_core",
                "possibleLocalWrites": {"6074": ["5956", "6029"]},
                "nativeIdentity": {
                    "selection": "certified_receiver_identity_cfg",
                    "selectedEdgeCount": 333,
                    "blockedIdentityReadCount": 0,
                    "diagnosticSecretMarker": "secret",
                },
                "values": {"in968:0": ["predecessor_stack_alternatives", None, ["960", "967"], 968]},
            }
        ],
        "unresolved": ["source_unknown"],
        "diagnosticSecretMarker": "secret",
        "limits": {"reservedCatalogCoverageCharacters": 320, "allocatedCharacters": 40320},
    }
    projected = _author_source_graph(original)
    assert projected["nodes"][0]["nativeIdentity"]["selectedEdgeCount"] == 333
    assert projected["nodes"][0]["sourceSelection"] == "mechanical_core"
    assert projected["nodes"][0]["possibleLocalWrites"] == {"6074": ["5956", "6029"]}
    assert projected["nodes"][0]["values"] == original["nodes"][0]["values"]
    assert projected["unresolved"] == ["source_unknown"]
    assert projected["limits"]["reservedCatalogCoverageCharacters"] == 320
    assert projected["limits"]["allocatedCharacters"] == 40320
    assert projected["transportOmissions"]["unknownFieldCount"] == 2
    assert "diagnosticSecretMarker" not in str(projected)
    assert _author_source_graph({**original, "version": True}) is None


def test_partial_or_empty_strict_program_never_replaces_readable_source_body():
    from infini_local.pipelines.context.mechanics_context import mechanics_context

    raw = {
        "item": {},
        "directProjectile": {
            "type": 31,
            "mechanicsSource": {
                "source": "native_mechanics_source",
                "version": 1,
                "identity": {"type": 31, "aiStyle": 5},
                "unresolved": [],
                "records": [
                    {"method": "Terraria.Projectile.AI_001", "coverage": "approximate_identity_ast_method", "code": "damage *= 7; Kill();"}
                ],
            },
            "strictIdentitySelections": [
                {
                    "projection": "gameplay_source_conditions_allowlist",
                    "selectionScope": {"mode": "gameplay_roots_with_source_closure"},
                    "selectedProgram": {
                        "method": "T.Projectile.AI_001",
                        "observations": [],
                        "dependencies": {},
                        "predicates": [],
                        "identitySelection": {"forCapturedIdentity": True},
                    },
                }
            ],
        },
    }
    result = mechanics_context(raw)
    assert result["mechanics"]["source"][0]["code"] == "damage *= 7; Kill();"
    assert "sourceExcerptOmission" not in result["mechanics"]["source"][0]


def test_modded_author_without_mechanics_source_also_filters_graph_diagnostics():
    from infini_local.pipelines.context.parent_stage import parent_context_for_stage

    graph = {
        "source": "parent_reachable_compiled_source_graph",
        "version": 1,
        "nodes": [{"id": 0, "coverage": "source_slice", "possibleLocalWrites": {"4": ["1", "2"]},
                   "diagnosticSecretMarker": "secret"}],
        "unresolved": ["mod_hook_unknown"],
        "diagnosticSecretMarker": "secret",
    }
    original = {"A": {"packet": {"raw": {"item": {"parentSourceGraph": graph}}}}}
    before = copy.deepcopy(original)
    out = parent_context_for_stage(original, stage="author")
    raw = out["parents"]["A"]["packet"]["raw"]
    assert "diagnosticSecretMarker" not in str(out)
    assert raw["item"]["parentSourceGraph"]["unresolved"] == ["mod_hook_unknown"]
    assert raw["item"]["parentSourceGraph"]["transportOmissions"]["unknownFieldCount"] == 2
    assert "not reaching definitions or executed values" in raw["item"]["parentSourceGraphReading"]
    assert original == before
    malformed = copy.deepcopy(original)
    malformed["A"]["packet"]["raw"]["item"]["parentSourceGraph"] = {"diagnosticSecretMarker": "secret", "unresolved": ["opaque_hook"]}
    raw = parent_context_for_stage(malformed, stage="author")["parents"]["A"]["packet"]["raw"]
    assert "parentSourceGraph" not in raw["item"] and raw["parentSourceGraphOmission"] == {
        "reason": "unrecognized_parent_source_graph_omitted",
        "unresolved": ["opaque_hook"],
    }


def test_strict_gameplay_projection_not_sent_to_visual_or_vfx():
    from infini_local.pipelines.context.parent_stage import parent_context_for_stage

    selection = [{"selectedProgram": {"observations": [{"kind": "state_write"}]}}]
    raw = {
        "item": {},
        "directProjectile": {
            "type": 31,
            "strictIdentitySelections": selection,
            "mechanicsSource": {
                "source": "native_mechanics_source",
                "version": 1,
                "identity": {"type": 31, "aiStyle": 1},
                "unresolved": [],
                "records": [{"method": "Fixture.AI", "code": "visual();"}],
            },
        },
    }
    parents = {"A": {"packet": {"raw": raw}}}
    before = copy.deepcopy(parents)
    for stage in ("visual", "vfx"):
        projected = parent_context_for_stage(parents, stage=stage)["parents"]["A"]["packet"]["raw"]
        assert "strictIdentitySelections" not in projected["directProjectile"]
        assert projected["directProjectile"]["mechanicsSource"]["records"][0]["code"] == "visual();"
    assert parents == before
