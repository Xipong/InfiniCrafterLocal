from __future__ import annotations

from typing import Any

from infini_local.core.item_identity_tools import (
    dict_get_ci,
    fingerprint_of,
    generated_data_of,
    name_of,
    slug,
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


def _vfx_director_tag_packet(item: dict[str, Any]) -> dict[str, Any]:
    """Transparent VFX Director context; no Python semantic expansion or tag inference."""
    name_tokens = _vfx_director_name_tokens(item)
    runtime_features = _vfx_director_runtime_auto_features(item)
    generated_tags = _vfx_generated_authored_tags(item)
    provenance: list[dict[str, str]] = []
    raw_match = "/".join(str(x or "") for x in [item.get("internalName") or fingerprint_of(item).get("internalName"), name_of(item)] if str(x or "").strip())
    for token in name_tokens:
        provenance.append({"tag": token, "source": "nameToken", "matched": raw_match or token})
    for feature in runtime_features:
        provenance.append({"tag": feature, "source": "runtimeAutoFeature", "matched": "runtime/item facts"})
    for tag in generated_tags:
        provenance.append({"tag": tag, "source": "generatedData", "matched": "generatedData.tags/canonical"})
    return {
        "nameTokens": name_tokens,
        "runtimeAutoFeatures": runtime_features,
        "generatedAuthoredTags": generated_tags,
        "tagProvenance": provenance[:64],
        "provenanceNote": "No Python semantic expansion is applied; these are raw name tokens, exact runtime facts and authored generated tags only.",
    }

__all__ = [
    "_vfx_clean_tag",
    "_vfx_list_strings",
    "_vfx_director_name_tokens",
    "_vfx_director_runtime_auto_features",
    "_vfx_generated_authored_tags",
    "_vfx_director_tag_packet",
]
