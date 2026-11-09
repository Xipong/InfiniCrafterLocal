"""Producer-owned native projectile reference-envelope admission."""
from __future__ import annotations

from typing import Any


def known_projectile_references(value: Any) -> bool:
    """Recognize the producer's bounded profile links without guessing future fields."""
    if not isinstance(value, dict):
        return False
    bounded = value.get("source") == "native_bounded_projectile_references"
    envelope_fields = {"source", "version", "scope", "profileLimit", "sourceCalls", "references"}
    reference_fields = {"type", "sourceCallIndices", "profile", "unresolved"}
    if bounded:
        envelope_fields.add("depthLimit")
        reference_fields.add("profileRefType")
    return (value.get("source") in ("native_single_hop_projectile_references", "native_bounded_projectile_references")
            and type(value.get("version")) is int and value["version"] == 1
            and set(value) <= envelope_fields
            and isinstance(value.get("sourceCalls"), list)
            and isinstance(value.get("references"), list)
            and all(isinstance(row, dict) and set(row) <= reference_fields
                    for row in value["references"]))


