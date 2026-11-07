"""Readable source observations, not an evaluator or runtime lowering.

This explicitly lossy presentation removes only listed source receipts. Full
unknown/new expression shapes remain literal. Native opcode names retain their
typed/overflow/unordered semantics instead of guessing Python/C# arithmetic.
Use one renderer for the entire mechanics card, then include ``finish()``.
"""
from __future__ import annotations

import copy
import json
from typing import Any


_RECEIPTS = frozenset({
    "sourceIlOffset", "sourceStoreIlOffset", "sourceBranchIlOffset",
    "sourceAddressIlOffsets", "sourceMethodSha256", "sourceModuleVersionId",
    "sourceVerification", "provenance", "sourceCertificate", "observedModuleVersionId",
    "sourceRandomCallIlOffset", "sourceFlagTestIlOffset", "accumulatorAddIlOffset",
    "negativeAccumulatorStepIlOffset", "healthStoreIlOffset", "loopCheckIlOffset",
})


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _index(value: Any) -> bool:
    return type(value) is int and value >= 0


class MechanicsRenderer:
    """Render known source AST shapes; retain unfamiliar observations literally."""

    def __init__(self):
        self._aliases = {}
        self._snapshots = {}
        self._unknowns = set()

    def finish(self):
        return {"snapshots": copy.deepcopy(self._snapshots),
                "unknowns": sorted(self._unknowns)}

    def render(self, value: Any, *, source_path: str = "$") -> Any:
        return self._render(value, None, source_path)

    def _render(self, value: Any, owner: dict[str, Any] | None, path: str) -> Any:
        if isinstance(value, list):
            return [self._render(child, owner, f"{path}[{index}]") for index, child in enumerate(value)]
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        if {"fields", "localValues", "controlFlow"} <= value.keys():
            summary = self._spawn_coverage(value)
            return summary if summary is not None else copy.deepcopy(value)
        if "kind" in value:
            result = self._expression(value, owner)
            if result is not None:
                return result
            self._collect_unknowns(value)
            # No recursive reinterpretation of an unfamiliar expression shape.
            return copy.deepcopy(value)
        if isinstance(value.get("method"), str):
            # Capture location namespaces even uncertified/same-named methods;
            # a nested callee's certificate must not become its caller's owner.
            owner = {"sourcePath": path, **{key: value[key] for key in
                     ("method", "sourceMethodSha256", "sourceModuleVersionId") if key in value}}
        return {key: self._render(child, owner, path + "." + key) for key, child in value.items()
                if key not in _RECEIPTS}

    def _spawn_coverage(self, value: dict[str, Any]) -> dict[str, Any] | None:
        """Summarize only the known diagnostic envelope, never its sibling inputs."""
        fixed = {
            "scope": "source_call_arguments_only; not_final_values_or_guaranteed_execution",
            "localValues": "guarded_reaching_definitions; branch_entry_values_unknown_not_item_defaults",
            "controlFlow": "normal_flow_from_item_branch_entry; external_gates_hooks_and_player_state_not_evaluated",
            "calls": "symbolic_source_only; helpers_hooks_getters_and_constructors_not_executed",
        }
        if set(value) != {*fixed, "limits", "condition", "fields"} or any(value[k] != v for k, v in fixed.items()):
            return None
        limits = value["limits"]
        if (not isinstance(limits, dict) or set(limits) != {"instructions", "expressionNodes", "predicateNodes",
                "definitionAlternatives", "expressionDepth", "localDefinitionDepth"}
                or any(not _index(n) for n in limits.values()) or not isinstance(value["fields"], dict)):
            return None
        def row_summary(row: Any) -> dict[str, Any] | None:
            if (not isinstance(row, dict) or set(row) != {"status", "unresolved"}
                    or row["status"] not in ("unknown", "partial_source_expression", "source_expression")
                    or not isinstance(row["unresolved"], list)):
                return None
            reasons = []
            for diagnostic in row["unresolved"]:
                if (not isinstance(diagnostic, dict) or not {"path", "reason", "sourceIlOffset"} <= diagnostic.keys()
                        or not diagnostic.keys() <= {"path", "reason", "sourceIlOffset", "sourceAddressIlOffsets", "local", "member"}
                        or not isinstance(diagnostic["path"], str) or not isinstance(diagnostic["reason"], str)
                        or not _index(diagnostic["sourceIlOffset"])):
                    return None
                if "local" in diagnostic and not _index(diagnostic["local"]):
                    return None
                if "member" in diagnostic and not isinstance(diagnostic["member"], str):
                    return None
                if "sourceAddressIlOffsets" in diagnostic and (not isinstance(diagnostic["sourceAddressIlOffsets"], list)
                        or any(not _index(n) for n in diagnostic["sourceAddressIlOffsets"])):
                    return None
                if diagnostic["reason"] not in reasons:
                    reasons.append(diagnostic["reason"])
            return {"status": row["status"], "reasons": reasons}
        condition = row_summary(value["condition"])
        fields = {name: row_summary(row) for name, row in value["fields"].items()}
        if condition is None or any(row is None for row in fields.values()):
            return None
        return {"fields": fields, "condition": condition,
                "scope": "Source expressions only; branch-entry values, external gates, helpers and hooks remain unknown. "
                         "Repeated diagnostic paths, local/member receipts and extraction limits remain in audit; not final values or guaranteed execution."}

    def _collect_unknowns(self, value: Any) -> None:
        if isinstance(value, dict):
            if value.get("kind") == "unknown" and isinstance(value.get("reason"), str):
                self._unknowns.add(value["reason"])
            for child in value.values():
                self._collect_unknowns(child)
        elif isinstance(value, list):
            for child in value:
                self._collect_unknowns(child)

    def _text(self, value: Any, owner: dict[str, Any] | None) -> str:
        rendered = self._render(value, owner, owner["sourcePath"] if owner else "$")
        return rendered if isinstance(rendered, str) else _json(rendered)

    def _expression(self, value: dict[str, Any], owner: dict[str, Any] | None) -> str | None:
        clean = {key: child for key, child in value.items() if key not in _RECEIPTS}
        keys = set(clean)
        kind = clean.get("kind")
        def text(child: Any) -> str:
            return self._text(child, owner)
        if kind == "constant" and keys == {"kind", "value"}:
            if clean["value"] is None or type(clean["value"]) in (bool, int, float, str):
                return _json(clean["value"])
        if kind == "argument" and keys in ({"kind", "index"}, {"kind", "argument"}):
            index = clean.get("index", clean.get("argument"))
            if _index(index):
                return "arg" + str(index)
        if kind == "argument_field" and keys == {"kind", "argument", "field"}:
            if _index(clean["argument"]) and isinstance(clean["field"], str):
                return "arg" + str(clean["argument"]) + ".[" + clean["field"] + "]"
        if kind == "field" and keys == {"kind", "member", "receiver"}:
            if isinstance(clean["member"], str):
                return text(clean["receiver"]) + ".[" + clean["member"] + "]"
        if kind == "binary" and keys == {"kind", "operator", "left", "right"}:
            if isinstance(clean["operator"], str) and clean["operator"] in {"add", "add.ovf", "add.ovf.un", "sub", "sub.ovf", "sub.ovf.un",
                                     "mul", "mul.ovf", "mul.ovf.un", "div", "div.un", "rem", "rem.un",
                                     "and", "or", "xor", "shl", "shr", "shr.un"}:
                return clean["operator"] + "(" + text(clean["left"]) + ", " + text(clean["right"]) + ")"
        if kind == "conversion" and keys == {"kind", "operator", "value"}:
            op = clean["operator"]
            if isinstance(op, str) and op in {
                "conv.i", "conv.u", "conv.i1", "conv.i2", "conv.i4", "conv.i8",
                "conv.u1", "conv.u2", "conv.u4", "conv.u8", "conv.r4", "conv.r8", "conv.r.un",
            }:
                return op + "(" + text(clean["value"]) + ")"
        if kind in ("call", "data_constructor"):
            expected = {"kind", "member", "arguments"}
            if kind == "call":
                expected.add("evaluation")
            else:
                expected.add("signature")
            if keys == expected and isinstance(clean["member"], str) and isinstance(clean["arguments"], list):
                if kind == "call" and clean["evaluation"] == "unresolved_helper_or_hook_output":
                    return "unexecuted " + clean["member"] + "(" + ", ".join(text(x) for x in clean["arguments"]) + ")"
                if kind == "data_constructor" and isinstance(clean["signature"], str):
                    return "construct " + clean["member"] + "[" + clean["signature"] + "](" + ", ".join(text(x) for x in clean["arguments"]) + ")"
        if kind == "local_definition" and keys == {"kind", "local", "scope", "value"}:
            if (_index(clean["local"]) and clean["scope"] == "value_at_store"
                    and owner is not None and _index(value.get("sourceStoreIlOffset"))):
                # A load's IL offset is not the store identity. Retain the
                # method/capture owner and store anchor; conflicting definitions
                # stay distinct rather than merging on their printed values.
                key = _json([owner, {k: v for k, v in value.items() if k != "sourceIlOffset"}])
                if key not in self._aliases:
                    name = "snapshot" + str(len(self._aliases) + 1)
                    self._aliases[key] = name
                    self._snapshots[name] = {"local": clean["local"], "scope": "value_at_store",
                        "method": owner["method"], "sourcePath": owner["sourcePath"],
                        "sourceStoreIlOffset": value["sourceStoreIlOffset"],
                        "value": self._render(clean["value"], owner, owner["sourcePath"])}
                return self._aliases[key]
        if kind == "branch" and type(clean.get("taken")) is bool:
            op = clean.get("opcode")
            comparisons = {"beq", "bne", "bne.un", "bgt", "bgt.un", "bge", "bge.un",
                           "blt", "blt.un", "ble", "ble.un"}
            if keys == {"kind", "opcode", "taken", "left", "right"} and isinstance(op, str) and op in comparisons:
                result = op + "(" + text(clean["left"]) + ", " + text(clean["right"]) + ")"
                return result if clean["taken"] else "not(" + result + ")"
            if keys == {"kind", "opcode", "taken", "operands"} and op in ("brtrue", "brfalse"):
                operands = clean["operands"]
                if isinstance(operands, list) and len(operands) == 1:
                    result = op + "(" + text(operands[0]) + ")"
                    return result if clean["taken"] else "not(" + result + ")"
        if kind == "if" and keys == {"kind", "condition", "then", "else"}:
            return "(" + text(clean["condition"]) + " ? " + text(clean["then"]) + " : " + text(clean["else"]) + ")"
        if kind == "source_alternatives" and keys == {"kind", "local", "scope", "alternatives"}:
            alternatives = clean["alternatives"]
            if (_index(clean["local"]) and clean["scope"] == "last_local_definition_on_source_path_to_read; predicates_not_evaluated"
                    and isinstance(alternatives, list) and all(isinstance(row, dict)
                    and set(row) == {"whenSourceCondition", "value"} for row in alternatives)):
                return "local" + str(clean["local"]) + " path_value{" + "; ".join(
                    "when " + text(row["whenSourceCondition"]) + ": " + text(row["value"])
                    for row in alternatives) + "}"
        return None
