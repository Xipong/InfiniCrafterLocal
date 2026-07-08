from __future__ import annotations

from typing import Any

from infini_local.core.item_identity_tools import (
    dict_get_ci,
    fingerprint_of,
    generated_data_of,
    name_of,
    slug,
    tags_of,
)
from infini_local.core.vfx_manifest_config import (
    VFX_LLM_WEAK_HINTS_CONFIDENCE_CAP,
    VFX_LLM_WEAK_HINTS_ENABLED,
    VFX_LLM_WEAK_HINTS_MAX,
)


# AGENT MAP: parent/child context packet for the optional LLM VFX Director.
# These helpers are prompt context only; they must not select recipes, route gameplay,
# or become executable runtime authority.

def _vfx_clean_tag(value: Any) -> str:
    return slug(str(value or "").strip()).lower()


def _vfx_list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        s = _vfx_clean_tag(raw)
        if s and s not in seen:
            out.append(s)
            seen.add(s)
    return out


def _vfx_director_name_tokens(item: dict[str, Any]) -> list[str]:
    fp = fingerprint_of(item)
    tokens = _vfx_list_strings(item.get("nameTokens"))
    if not tokens:
        tokens = _vfx_list_strings(fp.get("nameTokens") if isinstance(fp, dict) else [])
    return tokens


def _vfx_director_runtime_auto_features(item: dict[str, Any]) -> list[str]:
    fp = fingerprint_of(item)
    features = _vfx_list_strings(item.get("autoFeatures"))
    if isinstance(fp, dict):
        for tag in _vfx_list_strings(fp.get("autoFeatures")):
            if tag not in features:
                features.append(tag)
    return features


def _vfx_generated_authored_tags(item: dict[str, Any]) -> list[str]:
    gd = generated_data_of(item)
    out: list[str] = []
    for tag in _vfx_list_strings(dict_get_ci(gd, "tags", [])):
        if tag not in out:
            out.append(tag)
    can = dict_get_ci(gd, "canonical", {}) if isinstance(gd, dict) else {}
    if isinstance(can, dict):
        for field in ("hardTags", "softTags"):
            for tag in _vfx_list_strings(dict_get_ci(can, field, [])):
                if tag not in out:
                    out.append(tag)
    return out


def _vfx_semantic_expansion_for_director(name_tokens: list[str], runtime_features: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Transparent Director-only semantic expansion; not used by recipe selector scoring.

    This exists so Gemma can see why a parent got tags such as light/mana, without
    pretending that vanilla items have hand-authored tags.
    """
    derived: list[str] = []
    provenance: list[dict[str, str]] = []

    def add(tag: str, matched: str, source: str = "pythonSemanticExpansion") -> None:
        tag = _vfx_clean_tag(tag)
        if not tag or tag in derived:
            return
        derived.append(tag)
        provenance.append({"tag": tag, "source": source, "matched": matched})

    token_set = set(name_tokens)
    phrase = " ".join(name_tokens)

    # Include name/runtime tags in pythonDerivedTags as a complete readable bag.
    # Provenance for those source categories is emitted by _vfx_director_tag_packet,
    # so we do not duplicate it here.
    for token in name_tokens:
        token = _vfx_clean_tag(token)
        if token and token not in derived:
            derived.append(token)
    for feature in runtime_features:
        feature = _vfx_clean_tag(feature)
        if feature and feature not in derived:
            derived.append(feature)

    if "star" in token_set:
        add("light", "star")
        add("mana", "star")
    if "fallen" in token_set and "star" in token_set:
        add("light", "fallen star")
        add("mana", "fallen star")
    if "gel" in token_set or "slime" in token_set:
        add("slime", "gel/slime")
    if "wire" in token_set:
        add("electric", "wire")
        add("mechanism", "wire")
    if "lens" in token_set:
        add("glass", "lens")
        add("light", "lens")
    if "crystal" in token_set:
        add("crystal", "crystal")
        add("light", "crystal")
    if "torch" in token_set or "flame" in token_set or "fire" in token_set:
        add("fire", "torch/flame/fire")
        add("light", "torch/flame/fire")
    if "shadow" in token_set or "demon" in token_set or "corrupt" in token_set or "corruption" in token_set:
        add("shadow", "shadow/demon/corrupt")
    if "holy" in token_set or "hallowed" in token_set:
        add("holy", "holy/hallowed")
        add("light", "holy/hallowed")
    if "meteor" in token_set or "meteorite" in token_set:
        add("fire", "meteor/meteorite")
        add("star", "meteor/meteorite")
    if "mana" in token_set:
        add("mana", "mana")
        add("magic", "mana")
    if "book" in token_set or "tome" in token_set:
        add("magic", "book/tome")
    if "bullet" in token_set or "musket" in token_set or "gun" in token_set:
        add("metal", "bullet/musket/gun")
        add("ranged", "bullet/musket/gun")
    if "sword" in token_set or "blade" in token_set or "saber" in token_set:
        add("blade", "sword/blade/saber")
        add("melee", "sword/blade/saber")
    if "bow" in token_set or "arrow" in token_set:
        add("ranged", "bow/arrow")
    if phrase.strip():
        if "fallen star" in phrase:
            add("light", "fallen star")
            add("mana", "fallen star")

    return derived, provenance


def _vfx_director_tag_packet(item: dict[str, Any]) -> dict[str, Any]:
    name_tokens = _vfx_director_name_tokens(item)
    runtime_features = _vfx_director_runtime_auto_features(item)
    generated_tags = _vfx_generated_authored_tags(item)
    python_derived, derived_prov = _vfx_semantic_expansion_for_director(name_tokens, runtime_features)

    provenance: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add_prov(tag: str, source: str, matched: str) -> None:
        tag = _vfx_clean_tag(tag)
        if not tag:
            return
        key = (tag, source, matched)
        if key in seen:
            return
        seen.add(key)
        provenance.append({"tag": tag, "source": source, "matched": matched})

    raw_match = "/".join(str(x or "") for x in [item.get("internalName") or fingerprint_of(item).get("internalName"), name_of(item)] if str(x or "").strip())
    for token in name_tokens:
        add_prov(token, "nameToken", raw_match or token)
    for feature in runtime_features:
        add_prov(feature, "runtimeAutoFeature", "runtime/item facts")
    for tag in generated_tags:
        add_prov(tag, "generatedData", "generatedData.tags/canonical")
    for entry in derived_prov:
        add_prov(entry.get("tag", ""), entry.get("source", "pythonSemanticExpansion"), entry.get("matched", ""))

    return {
        "nameTokens": name_tokens,
        "runtimeAutoFeatures": runtime_features,
        "pythonDerivedTags": python_derived,
        "generatedAuthoredTags": generated_tags,
        "tagProvenance": provenance[:64],
        "provenanceNote": "Vanilla/modded parent items do not have hand-authored tags here; pythonDerivedTags are transparent substring/semantic expansion for the VFX Director packet only.",
    }


def _vfx_weak_hint_confidence(tag: str, sources: set[str], count: int, notes: list[str] | None = None) -> float:
    """Tiny, non-authoritative confidence for legacy codifier hints.

    This score is deliberately low. It is only prompt context for Gemma, never a
    Python-side selector or composer weight.
    """
    notes = notes or []
    score = 0.22
    if any(n.startswith("tags_of:") for n in notes):
        score += 0.08
    if any(n.startswith("pythonDerivedTags:") for n in notes):
        score += 0.05
    if any(n.startswith("generatedData:") for n in notes):
        score += 0.09
    if "child" in sources:
        score += 0.04
    if "parentA" in sources and "parentB" in sources:
        score += 0.04
    if count >= 2:
        score += 0.05
    if count >= 3:
        score += 0.03
    try:
        cap = float(VFX_LLM_WEAK_HINTS_CONFIDENCE_CAP)
    except Exception:
        cap = 0.45
    return round(max(0.05, min(cap, score)), 3)


def _vfx_collect_legacy_hint_tags(item: dict[str, Any] | None, label: str) -> list[tuple[str, str]]:
    """Collect weak prompt hints from the legacy tag/codifier surface.

    The return value is intentionally just (tag, source-note). Callers must not
    feed this back into recipe selection or slot routing.
    """
    if not isinstance(item, dict):
        return []
    tags: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(tag: Any, note: str) -> None:
        t = _vfx_clean_tag(tag)
        key = (t, note)
        if not t or key in seen:
            return
        seen.add(key)
        tags.append((t, note))

    # tags_of is the old mixed semantic/codifier bag. Keep it visible only as weak context.
    for tag in sorted(tags_of(item)):
        add(tag, f"tags_of:{label}")

    packet = _vfx_director_tag_packet(item)
    for tag in packet.get("pythonDerivedTags", []):
        add(tag, f"pythonDerivedTags:{label}")
    for tag in packet.get("generatedAuthoredTags", []):
        add(tag, f"generatedData:{label}")
    return tags


def build_vfx_director_weak_hints(parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, child_item: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Optional non-authoritative weak hints for the LLM VFX Director.

    These hints are visible prompt context only. They do not select renderers,
    particle systems, recipes, slots, channels, or colors in Python.
    """
    if not VFX_LLM_WEAK_HINTS_ENABLED:
        return []
    counts: dict[str, int] = {}
    sources: dict[str, set[str]] = {}
    notes: dict[str, list[str]] = {}

    for label, item in (("parentA", parent_a), ("parentB", parent_b), ("child", child_item)):
        for tag, note in _vfx_collect_legacy_hint_tags(item, label):
            counts[tag] = counts.get(tag, 0) + 1
            sources.setdefault(tag, set()).add(label)
            if note.startswith("generatedData"):
                sources[tag].add("generatedData")
            notes.setdefault(tag, [])
            if note not in notes[tag]:
                notes[tag].append(note)

    ranked: list[tuple[float, str]] = []
    for tag, count in counts.items():
        score = _vfx_weak_hint_confidence(tag, sources.get(tag, set()), count, notes.get(tag, []))
        ranked.append((score, tag))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    max_hints = max(0, int(VFX_LLM_WEAK_HINTS_MAX))
    out: list[dict[str, Any]] = []
    for score, tag in ranked[:max_hints]:
        out.append({
            "hint": tag,
            "source": "legacy_codifier",
            "confidence": score,
            "nonAuthoritative": True,
            "matched": notes.get(tag, [])[:4],
        })
    return out


__all__ = [
    "_vfx_clean_tag",
    "_vfx_list_strings",
    "_vfx_director_name_tokens",
    "_vfx_director_runtime_auto_features",
    "_vfx_generated_authored_tags",
    "_vfx_semantic_expansion_for_director",
    "_vfx_director_tag_packet",
    "_vfx_weak_hint_confidence",
    "_vfx_collect_legacy_hint_tags",
    "build_vfx_director_weak_hints",
]
