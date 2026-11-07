"""Producer-owned native projectile reference-envelope admission."""
from __future__ import annotations

from typing import Any


def known_projectile_references(value: Any) -> bool:
    """Recognize the producer's one-hop profile links without guessing future fields."""
    return (isinstance(value, dict)
            and value.get("source") == "native_single_hop_projectile_references"
            and type(value.get("version")) is int and value["version"] == 1
            and set(value) <= {"source", "version", "scope", "profileLimit", "sourceCalls", "references"}
            and isinstance(value.get("sourceCalls"), list)
            and isinstance(value.get("references"), list)
            and all(isinstance(row, dict) and set(row) <= {"type", "sourceCallIndices", "profile", "unresolved"}
                    for row in value["references"]))


