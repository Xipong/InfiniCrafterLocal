"""Request-local loaded-content identities, separate from parent mechanics."""
from __future__ import annotations

from typing import Any


_IDENTITY_SCOPE = (
    "Current loaded buff identities, not evidence that either parent inflicts them. "
    "byMod[mod][registeredName] is the exact loaded buffId. Effect conditions and immunity remain separate."
)


def loaded_status_identity_choices(parent_a: dict[str, Any], parent_b: dict[str, Any]) -> dict[str, Any] | None:
    """Merge request-local identity observations without resolving conflicting IDs.

    This is a choice vocabulary, not a mechanical parent fact. In particular, an
    absent entry in a partial observation is not proof a buff does not exist.
    """
    observed: list[set[tuple[int, str]]] = []
    complete_sets: list[set[tuple[int, str]]] = []
    malformed = False
    for parent in (parent_a, parent_b):
        registry = parent.get("loadedBuffIdentitiesRaw") if isinstance(parent, dict) else None
        if not isinstance(registry, dict) or registry.get("source") != "native_loaded_buff_registry":
            continue
        entries = registry.get("entries")
        if not isinstance(entries, list):
            malformed = True
            continue
        current: set[tuple[int, str]] = set()
        registry_malformed = False
        for entry in entries:
            if not isinstance(entry, dict):
                registry_malformed = True
                continue
            identity, name = entry.get("id"), entry.get("fullName")
            if (type(identity) is not int or not 1 <= identity <= 65535
                    or not isinstance(name, str) or len(name) > 256
                    or name.count("/") != 1 or not all(name.split("/"))):
                registry_malformed = True
                continue
            current.add((identity, name))
        observed.append(current)
        if registry.get("complete") is True and not registry_malformed:
            complete_sets.append(current)
        malformed |= registry_malformed
    if not observed:
        return None
    by_id: dict[int, set[str]] = {}
    by_name: dict[str, set[int]] = {}
    for current in observed:
        for identity, name in current:
            by_id.setdefault(identity, set()).add(name)
            by_name.setdefault(name, set()).add(identity)
    entries = [
        {"id": identity, "fullName": name}
        for identity, names in sorted(by_id.items())
        for name in sorted(names)
        if len(names) == 1 and len(by_name[name]) == 1
    ]
    if not entries:
        return None
    conflict = any(len(names) != 1 for names in by_id.values()) or any(len(ids) != 1 for ids in by_name.values())
    complete = (bool(complete_sets) and not malformed and not conflict
        and all(current == complete_sets[0] for current in complete_sets)
        and all(current <= complete_sets[0] for current in observed))
    by_mod: dict[str, dict[str, int]] = {}
    for entry in entries:
        mod, name = entry["fullName"].split("/", 1)
        by_mod.setdefault(mod, {})[name] = entry["id"]
    return {"source": "native_loaded_buff_registry", "scope": _IDENTITY_SCOPE,
        "complete": complete, "byMod": by_mod}
