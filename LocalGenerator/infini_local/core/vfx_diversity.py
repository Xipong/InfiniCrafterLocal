from __future__ import annotations

from collections import Counter, defaultdict
import math
from typing import Any


def _slot_signature(slot: dict[str, Any]) -> str:
    fields = (
        "event", "rendererKind", "channel", "lane", "emissionMode",
        "particleSystemId", "textureRole", "particleRole",
    )
    return "|".join(str(slot.get(field) or "").strip() for field in fields)


def _item_signature(item: dict[str, Any]) -> tuple[str, list[str]]:
    manifest_raw = item.get("vfxManifest")
    manifest: dict[str, Any] = manifest_raw if isinstance(manifest_raw, dict) else {}
    slots_raw = manifest.get("slots")
    slots: list[Any] = slots_raw if isinstance(slots_raw, list) else []
    signatures = sorted({
        _slot_signature(slot)
        for slot in slots
        if isinstance(slot, dict) and str(slot.get("rendererKind") or "").strip()
    })
    return "\n".join(signatures), signatures


def vfx_batch_diversity_report(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure explicit manifest diversity without interpreting visual prose.

    This is a QA gate only. It never selects renderers or rewrites an authored VFX
    manifest. Empty manifests remain visible instead of being silently excluded.
    """
    rows: list[dict[str, Any]] = []
    renderer_counts: Counter[str] = Counter()
    signature_groups: dict[str, list[str]] = defaultdict(list)
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or item.get("name") or f"item_{index}")
        signature, slot_signatures = _item_signature(item)
        rows.append({"id": item_id, "slotCount": len(slot_signatures), "signature": signature})
        signature_groups[signature].append(item_id)
        for slot_signature in slot_signatures:
            renderer = slot_signature.split("|", 3)[1] if "|" in slot_signature else ""
            if renderer:
                renderer_counts[renderer] += 1

    count = len(rows)
    unique_count = len(signature_groups)
    duplicate_groups = [
        {"count": len(ids), "items": ids, "signature": signature}
        for signature, ids in signature_groups.items()
        if len(ids) > 1
    ]
    duplicate_groups.sort(key=lambda row: (-int(row["count"]), str(row["signature"])))
    largest_duplicate = max((int(row["count"]) for row in duplicate_groups), default=1 if count else 0)
    minimum_unique = max(1, math.ceil(count * 0.65)) if count >= 4 else count
    maximum_duplicate = max(2, math.ceil(count * 0.35)) if count >= 4 else max(1, count)
    warnings: list[str] = []
    if count >= 4 and unique_count < minimum_unique:
        warnings.append(f"only {unique_count}/{count} unique exact VFX signatures; require at least {minimum_unique}")
    if count >= 4 and largest_duplicate > maximum_duplicate:
        warnings.append(f"largest exact VFX duplicate group is {largest_duplicate}; maximum is {maximum_duplicate}")
    empty = [row["id"] for row in rows if not row["signature"]]
    if empty:
        warnings.append(f"{len(empty)} item(s) have no executable VFX slots")

    return {
        "schema": "infini.vfx-batch-diversity.v1",
        "ok": not warnings,
        "itemCount": count,
        "uniqueSignatureCount": unique_count,
        "minimumUniqueRequired": minimum_unique,
        "largestDuplicateGroup": largest_duplicate,
        "maximumDuplicateAllowed": maximum_duplicate,
        "duplicateGroups": duplicate_groups[:12],
        "rendererCounts": dict(sorted(renderer_counts.items())),
        "emptyManifestItems": empty,
        "warnings": warnings,
        "items": rows,
    }


__all__ = ["vfx_batch_diversity_report"]
