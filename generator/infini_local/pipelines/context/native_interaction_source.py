"""Project only the known, independently certified hit/movement source family."""
from __future__ import annotations

import copy
import hashlib
import re
from typing import Any

from infini_local.pipelines.context.csharp_source_view import _CERT, _certificate, _identity, _integer, _sha

_SOURCE = "verified_conditional_native_interaction_csharp"
_SCOPE = ("Conditional source only: reach the shown guard first. Enclosing flow, hooks, captured-entry identity preservation, external local values and unshown callees remain unknown. Live predicates are not evaluated; no record proves execution or absence of other effects. Helper bodies are one-hop source, not inlined or executed.")
_COMMON = {*_CERT, "id", "metadataToken", "assemblySha256", "coverage", "code", "codeSha256", "decompiler", "spawnSites"}
_REGION = {"regionIndex", "entryCondition", "externalInputs", "identityWitnesses", "helperCalls"}


def project_interaction_source(reference: dict[str, Any]) -> dict[str, Any]:
    """Remove certificate duplication, never source or unknown entry dependencies."""
    out = copy.deepcopy(reference)
    value = reference.get("interactionSources")
    if (reference.get("source") != "read_only_native_attack_source" or type(reference.get("version")) is not int
            or reference["version"] != 1 or not isinstance(value, dict) or set(value) != {"source", "version", "relevanceIdentity", "scope", "roots"}
            or value["source"] != _SOURCE or type(value["version"]) is not int or value["version"] != 1
            or value["scope"] != _SCOPE or not _identity(value["relevanceIdentity"])
            or value["relevanceIdentity"] != reference.get("identityPredicates")
            or not isinstance(value["roots"], list)):
        return out
    projected = []
    for root in value["roots"]:
        if (not isinstance(root, dict) or set(root) != {"root", "rootCertificate", "records", "helpers", "unresolved"}
                or not isinstance(root["root"], str) or root["root"] not in {"Damage", "StatusNPC", "HandleMovement"}
                or _certificate(root["rootCertificate"]) is None or set(root["rootCertificate"]) != set(_CERT)
                or not _sha(root["rootCertificate"]["sourceMethodSha256"])
                or root["rootCertificate"]["method"] != "Terraria.Projectile." + root["root"]
                or not isinstance(root["records"], list) or not isinstance(root["helpers"], list)
                or not isinstance(root["unresolved"], list) or any(not isinstance(gap, str) for gap in root["unresolved"])):
            return out
        regions, helpers, helper_ids = [], [], {}
        for helper in root["helpers"]:
            if not _record(helper, helper=True):
                return out
            cert = _certificate(helper)
            if cert in helper_ids:
                return out
            helper_ids[cert] = f"h{len(helpers)}"
            helpers.append({"id": helper_ids[cert], **{key: copy.deepcopy(helper[key]) for key in ("method", "coverage", "code", "spawnSites")}})
        for record in root["records"]:
            if (not _record(record, helper=False) or _certificate(record) != _certificate(root["rootCertificate"])
                    or not _integer(record["regionIndex"]) or not isinstance(record["entryCondition"], str)
                    or not any(record["code"].startswith(prefix + record["entryCondition"] + ")") for prefix in ("if (", "switch ("))
                    or not isinstance(record["externalInputs"], list) or not isinstance(record["helperCalls"], list)
                    or not isinstance(record["identityWitnesses"], list) or not record["identityWitnesses"]):
                return out
            for entry in record["externalInputs"]:
                if (not isinstance(entry, dict) or set(entry) != {"name", "type", "kind", "scope"}
                        or any(not isinstance(text, str) or not text for text in entry.values())
                        or entry["kind"] not in {"method_parameter", "external_local"}
                        or entry["scope"] != "symbolic_entry_value; reaching_definitions_and_current_value_not_captured"):
                    return out
            for witness in record["identityWitnesses"]:
                if (not isinstance(witness, dict) or set(witness) != {"field", "literal"}
                        or not isinstance(witness["field"], str) or witness["field"] not in {"Terraria.Projectile.type", "Terraria.Projectile.aiStyle"}
                        or type(witness["literal"]) is not int
                        or witness["literal"] != value["relevanceIdentity"][witness["field"].removeprefix("Terraria.")]):
                    return out
            calls = []
            for call in record["helperCalls"]:
                if (not isinstance(call, dict) or set(call) not in ({*_CERT, "at"}, {*_CERT, "at", "unresolved"})
                        or _certificate(call) is None or not _integer(call["at"])
                        or "unresolved" in call and not isinstance(call["unresolved"], str)):
                    return out
                cert = _certificate(call)
                if cert not in helper_ids and "unresolved" not in call:
                    return out
                calls.append({"at": call["at"], "method": call["method"],
                    **({"sourceRecord": helper_ids[cert]} if cert in helper_ids and "unresolved" not in call else {}),
                    **({"unresolved": call["unresolved"]} if "unresolved" in call else {})})
            regions.append({**{key: copy.deepcopy(record[key]) for key in ("method", "coverage", "code", "regionIndex",
                "entryCondition", "externalInputs", "identityWitnesses", "spawnSites")}, "helperCalls": calls})
        projected.append({"root": root["root"], "records": regions, "helpers": helpers, "unresolved": copy.deepcopy(root["unresolved"])})
    out["interactionSources"] = {**{key: copy.deepcopy(value[key]) for key in ("version", "relevanceIdentity", "scope")},
        "source": "read_only_conditional_native_interaction_csharp", "roots": projected}
    return out


def _record(value: Any, *, helper: bool) -> bool:
    fields = _COMMON if helper else _COMMON | _REGION
    if (not isinstance(value, dict) or set(value) != fields or _certificate(value) is None
            or not _sha(value["sourceMethodSha256"]) or not value["method"].startswith("Terraria.Projectile.")
            or not _integer(value["metadataToken"]) or not _sha(value["assemblySha256"])
            or not isinstance(value["code"], str) or not value["code"].strip() or not _sha(value["codeSha256"])
            or value["codeSha256"] != hashlib.sha256(value["code"].encode("utf-8")).hexdigest()
            or value["id"] != f'interaction:{value["sourceModuleVersionId"]}:{value["metadataToken"]}:{value["codeSha256"]}'
            or value["coverage"] != ("whole_method_source_only; one_hop_no_call_evaluation" if helper else "conditional_source_region; external_inputs_explicit")):
        return False
    if not isinstance(value["spawnSites"], list):
        return False
    for call in value["spawnSites"]:
        if (not isinstance(call, dict) or set(call) != {*_CERT, "at", "projectileTypes", "requiredPredicates", "unresolved"}
                or _certificate(call) != _certificate(value) or not _integer(call["at"])
                or not isinstance(call["projectileTypes"], list) or len(call["projectileTypes"]) > 1
                or any(type(kind) is not int for kind in call["projectileTypes"])
                or not isinstance(call["requiredPredicates"], list)
                or any(not isinstance(guard, str) or re.fullmatch(r"b\d+", guard) is None for guard in call["requiredPredicates"])
                or call["unresolved"] != "conditional_interaction_source_candidate; guards_and_external_inputs_in_source; enclosing_flow_hooks_and_entry_identity_unknown; not_an_executed_spawn"
                    + ("; spawn_type_requires_runtime_expression" if not call["projectileTypes"] else "")):
            return False
    return value["decompiler"] == {"name": "ICSharpCode.Decompiler", "version": "8.2.0.7535",
        "assemblySha256": "d174072a16aa758a39d160f70ce924103898fae2b8506b48f70d6909e25a1fd0", "settings": "csharp_default_no_indentation_v1"}
