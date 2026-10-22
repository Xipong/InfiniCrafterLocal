"""Offline two-pass documentation experiments; never called by production craft.

Selection changes documentation detail, never registry admission or runtime code.
The original non_drivers policy reserves secondary-function documentation.
The follow-up selected_only policy tests selection across all registry groups.
Every operation remains discoverable; index-only is not full parameter grammar.
An explicit fullCatalog choice restores the original packet.
These are prompt experiments, not a new provider adapter or a gameplay router.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY

MODES = ("groups", "capabilities")
POLICIES = ("non_drivers", "selected_only")
_SELECTIVE_CATEGORIES = frozenset({"movement", "controller"})
_NEGATIVE_REQUIREMENTS = frozenset({
    "capability_absent", "capability_param_absent", "present_param_forbids_capability",
    "present_params_forbid_item_capability_when_active_spawn",
})


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _cards(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    cards = payload["runtimeCapabilityContract"]["catalog"]["capabilities"]
    names = [row["fn"] for row in cards]
    if len(names) != len(set(names)) or set(names) != set(CAPABILITY_REGISTRY):
        raise ValueError("Experiment requires a complete current registry snapshot")
    return cards


def catalog_revision(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json(_cards(payload)).encode("utf-8")).hexdigest()


def catalogue_index(payload: Mapping[str, Any], *, compact: bool = False) -> list[dict[str, Any]]:
    """Every capability and parameter name; compact mode omits requirements."""
    rows = []
    for card in _cards(payload):
        cap = CAPABILITY_REGISTRY[card["fn"]]
        row = {key: deepcopy(card[key]) for key in (
            "fn", "does", "targets", "requires", "acceptedEvents", "emitsEvents",
            "exclusiveGroup", "effectGroups", "multiplicity",
        ) if key in card}
        row.update(group=cap.category, parameters=list(card["params"]), dependencies=list(cap.dependencies))
        if compact:
            # Discovery descriptions stay verbatim. Parameter grammar belongs to
            # the selected full cards; dependency expansion uses the registry.
            row.pop("requires", None)
            for key in ("positionOwnership", "constructionMeaning", "budget"):
                if key in card:
                    row[key] = deepcopy(card[key])
        rows.append(row)
    return rows


def selection_schema(payload: Mapping[str, Any], mode: str) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"Unknown selection mode: {mode}")
    choices = sorted({CAPABILITY_REGISTRY[row["fn"]].category for row in _cards(payload)}) if mode == "groups" else sorted(CAPABILITY_REGISTRY)
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "catalogRevision": {"type": "string", "const": catalog_revision(payload)},
            "selected": {"type": "array", "items": {"type": "string", "enum": choices}, "uniqueItems": True},
            "fullCatalog": {"type": "boolean"},
            "intent": {"type": "string", "maxLength": 1600},
        },
        "required": ["catalogRevision", "selected", "fullCatalog", "intent"],
    }


def build_selector_packet(payload: Mapping[str, Any], mode: str, *, policy: str = "non_drivers") -> dict[str, Any]:
    if policy not in POLICIES:
        raise ValueError(f"Unknown documentation policy: {policy}")
    schema = selection_schema(payload, mode)
    catalog = payload["runtimeCapabilityContract"]["catalog"]
    return {
        "system": (
            "Choose documentation for one Terraria item; return only the requested JSON. "
            "Use the complete catalogue, not an item/weapon family classifier. "
            "Consider secondary active inputs, held effects, equipment reactions, placement, "
            "tools, ammunition and child entities as well as the main action. "
            "Do not promise unsupported effects. Keep source facts distinct from invented design. "
            + ("The next Author receives full documentation for all non-movement/non-controller "
            "capabilities automatically. Your selection decides which movement/controller "
            "documentation is also detailed. " if policy == "non_drivers" else
            "There is no automatic secondary-function reserve. Select documentation for every "
            "required operation, including secondary functions, event producers, buffs and bindings. "
            "The compact index is discovery information, not a complete feasibility contract. ")
            + "Consider every entity, including secondary shots. "
            "Select multiple alternatives if the implementation may need them. "
            "Conflicts are per target, not global. Selection is permission to consider, not an "
            "instruction to instantiate every capability. fullCatalog=true explicitly keeps "
            "all detail when the design needs broad freedom; it is a valid outcome. "
            "Only one selection pass is allowed; no later retrieval or corrective selection. "
            + ("Select registry documentation groups; every member is included. " if mode == "groups"
               else "Select exact capability IDs; declared positive dependencies are included. ")
        ),
        "static": {
            "mode": mode, "catalogRevision": catalog_revision(payload),
            "completeCatalogue": catalogue_index(payload, compact=policy == "selected_only"),
            "topology": {key: deepcopy(catalog[key]) for key in (
                "entityKinds", "inputs", "bindingActions", "events", "limits",
            )},
            "outputSchema": schema,
        },
        "context": {key: deepcopy(payload[key]) for key in (
            "recipeKey", "parents", "balanceCorridor", "sourceWireUnits", "experimentBrief",
        ) if key in payload},
    }


def _validate_selection(payload: Mapping[str, Any], mode: str, selection: Mapping[str, Any]) -> None:
    schema = selection_schema(payload, mode)
    if not isinstance(selection, Mapping) or set(selection) != set(schema["required"]):
        raise ValueError("Selection must have exactly the declared JSON fields")
    if selection["catalogRevision"] != catalog_revision(payload):
        raise ValueError("Stale or mismatched catalogue revision")
    if type(selection["fullCatalog"]) is not bool:
        raise ValueError("fullCatalog must be boolean")
    if not isinstance(selection["intent"], str) or len(selection["intent"]) > 1600:
        raise ValueError("intent must be a string of at most 1600 characters")
    values = selection["selected"]
    allowed = schema["properties"]["selected"]["items"]["enum"]
    if not isinstance(values, list) or any(not isinstance(v, str) or v not in allowed for v in values):
        raise ValueError("Selection contains an unknown group/capability")
    if len(values) != len(set(values)):
        raise ValueError("Selection contains duplicates")


def _positive_dependencies(names: set[str]) -> tuple[set[str], list[dict[str, str]]]:
    """Conservative documentation closure; alternatives add docs, never calls.

    Conditional requirements may add more documentation than a specific graph
    needs. Forbidden capabilities must never become positive dependencies.
    """
    result = set(names)
    receipts = []
    while True:
        additions = set()
        for name in sorted(result):
            cap = CAPABILITY_REGISTRY[name]
            dependencies = set(cap.dependencies)
            for requirement in cap.requirements:
                if requirement.kind in _NEGATIVE_REQUIREMENTS:
                    continue
                if requirement.capability in CAPABILITY_REGISTRY:
                    dependencies.add(requirement.capability)
                dependencies.update(v for v in requirement.any_of if v in CAPABILITY_REGISTRY)
            for dependency in sorted(dependencies - result):
                additions.add(dependency)
                receipts.append({"from": name, "includeDocumentation": dependency})
        if not additions:
            return result, receipts
        result.update(additions)


def build_author_variant(payload: Mapping[str, Any], mode: str, selection: Mapping[str, Any], *, policy: str = "non_drivers") -> tuple[dict[str, Any], dict[str, Any]]:
    """Two implementations: whole registry groups, or exact capability selection.

    Runtime admission stays global. No enum, validator, compiler or production
    prompt is patched. A valid call outside the detailed subset stays valid.
    """
    if policy not in POLICIES:
        raise ValueError(f"Unknown documentation policy: {policy}")
    _validate_selection(payload, mode, selection)
    all_cards = _cards(payload)
    selected = set(selection["selected"])
    requested = {name for name, cap in CAPABILITY_REGISTRY.items() if cap.category in selected} if mode == "groups" else selected
    reserve = {name for name, cap in CAPABILITY_REGISTRY.items() if cap.category not in _SELECTIVE_CATEGORIES} if policy == "non_drivers" else set()
    detailed, receipts = _positive_dependencies(requested | reserve)
    if selection["fullCatalog"]:
        detailed = set(CAPABILITY_REGISTRY)
    result = deepcopy(dict(payload))
    if not selection["fullCatalog"]:
        result["runtimeCapabilityContract"]["catalog"]["capabilities"] = [deepcopy(row) for row in all_cards if row["fn"] in detailed]
        # Detailed cards already expose their full meaning. Index only omitted
        # cards, so preserving catalogue discovery does not duplicate all docs.
        result["runtimeCapabilityContract"]["indexOnlyCapabilities"] = [
            row for row in catalogue_index(payload, compact=policy == "selected_only") if row["fn"] not in detailed
        ]
        header = result["priorityHeader"]
        original = "Use only capabilities present in runtimeCapabilityContract.catalog.capabilities."
        if original not in header:
            raise ValueError("Author catalogue authority rule changed; review experiment framing")
        header[header.index(original)] = (
            "Every capability in catalog.capabilities or indexOnlyCapabilities remains legal. catalog.capabilities supplies "
            "exact detailed parameter contracts. The selector's intent is advisory; preserve useful "
            "secondary functions and author every effect explicitly. Do not fabricate parameters "
            "for an index-only capability: missing detail is not proof of incompatibility. "
            "No extra documentation request is available in this experiment."
        )
    result["selectionIntent"] = selection["intent"]
    audit = {
        "mode": mode, "catalogRevision": catalog_revision(payload),
        "catalogueIds": sorted(CAPABILITY_REGISTRY), "requestedIds": sorted(requested),
        "secondaryReserveIds": sorted(reserve), "detailedIds": sorted(detailed),
        "indexOnlyIds": sorted(set(CAPABILITY_REGISTRY) - detailed),
        "dependencyDocumentation": receipts, "explicitFullCatalog": selection["fullCatalog"],
        "runtimeAdmissionChanged": False,
    }
    if policy != "non_drivers":
        audit["documentationPolicy"] = policy
    return result, audit
