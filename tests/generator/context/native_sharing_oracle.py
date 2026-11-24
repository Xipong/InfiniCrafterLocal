"""Decode the source-sharing wire independently of the production encoder."""
from __future__ import annotations

import copy


def expanded_native_parents(context):
    """Decode actual delivery independently, keeping literal/generated boundaries."""
    pool = context.get("nativeSourceFacts", [])
    def expand(value, active=()):
        if isinstance(value, list):
            return [expand(child, active) for child in value]
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        if set(value) == {"sourceSameAs"}:
            index = value["sourceSameAs"]
            assert type(index) is int and 0 <= index < len(pool)
            assert index not in active, "cyclic wire reference"
            return expand(pool[index], (*active, index))
        return {name: copy.deepcopy(child) if name in {"tooltipLines", "tooltipSource", "generatedParent"}
                else expand(child, active) for name, child in value.items()}
    parents = copy.deepcopy(context["parents"])
    for row in parents.values():
        raw = row.get("packet", {}).get("raw", {})
        if "generatedParent" not in raw:
            row["packet"]["raw"] = expand(raw)
    return parents
