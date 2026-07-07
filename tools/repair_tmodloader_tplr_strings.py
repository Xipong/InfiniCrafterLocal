from __future__ import annotations

"""Repair oversized InfiniCrafterLocal JSON strings inside tModLoader .tplr saves.

Why this exists:
  tModLoader TagIO stores NBT string payload lengths as signed Int16. If a generated
  item writes a JSON blob above ~32767 bytes, the .tplr can become unreadable before
  the mod's defensive LoadData code runs. This script trims InfiniCrafterLocal's
  `infiniJson` payloads to a safe player-save representation and rewrites the gzip file.

Usage:
  python tools/repair_tmodloader_tplr_strings.py path/to/Character.tplr
  python tools/repair_tmodloader_tplr_strings.py broken.tplr fixed.tplr
"""

from pathlib import Path
import gzip
import json
import sys

KEY = b"infiniJson"
MAX_BYTES = 30_000
ROOT = Path(__file__).resolve().parents[1]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
if str(LOCAL_GENERATOR) not in sys.path:
    sys.path.insert(0, str(LOCAL_GENERATOR))

try:
    from infini_local.core.runtime_authoring import ENGINE_RUNTIME_API_VERSION
except Exception:
    # Last-resort tool fallback only.  Keep this value in sync with
    # LocalGenerator/infini_local/core/runtime_authoring.py; the normal path imports it.
    ENGINE_RUNTIME_API_VERSION = "v0.4.47"

PROMPT_VISUAL_KEYS = [
    "ImagePrompt", "ProjectileImagePrompt", "ImpactImagePrompt", "ChildImagePrompt",
    "FieldImagePrompt", "NegativePrompt", "AssetManifestPath", "SpriteRawPath",
]
PROMPT_ATTACK_KEYS = [
    "ProjectileSpritePrompt", "ImpactSpritePrompt", "ChildSpritePrompt", "FieldSpritePrompt",
]


def compact_infini_json(raw: str) -> str:
    try:
        data = json.loads(raw)
    except Exception:
        return raw

    def dump() -> str:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    data["Debug"] = {}
    data["debug"] = {}
    visual = data.get("Visual") if isinstance(data.get("Visual"), dict) else {}
    attack = data.get("Attack") if isinstance(data.get("Attack"), dict) else {}
    for key in PROMPT_VISUAL_KEYS:
        visual[key] = ""
    for key in PROMPT_ATTACK_KEYS:
        attack[key] = ""

    text = dump()
    if len(text.encode("utf-8")) <= MAX_BYTES:
        return text

    data["VfxManifest"] = {}
    attack["VfxManifestJson"] = ""
    attack["VisualAnimationPlan"] = ""
    text = dump()
    if len(text.encode("utf-8")) <= MAX_BYTES:
        return text

    data["SourceRepresentation"] = []
    data["Inheritance"] = []
    data["ItemKnowledge"] = {}
    data["PresentationGenome"] = {}
    data["SoundProfile"] = {}
    recipe = data.get("RecipeMeta") if isinstance(data.get("RecipeMeta"), dict) else {}
    for key in ["ParentIdentities", "ParentCategories", "AssetFiles"]:
        recipe[key] = []
    for key in ["WorldId", "AssetBaseUrl"]:
        recipe[key] = ""
    recipe["WorldScoped"] = False
    text = dump()
    if len(text.encode("utf-8")) <= MAX_BYTES:
        return text

    # Last resort: keep the player selectable and the item recognizable; behavior can be
    # restored from the local registry/cache if available, otherwise it becomes a safe minimal payload.
    minimal = {
        "SchemaVersion": data.get("SchemaVersion", 1),
        "RuntimeApiVersion": data.get("RuntimeApiVersion") or data.get("runtimeApiVersion") or ENGINE_RUNTIME_API_VERSION,
        "Id": data.get("Id", "placeholder"),
        "RecipeKey": data.get("RecipeKey", ""),
        "Name": data.get("Name", "Generated Item"),
        "ParentA": data.get("ParentA", "Unknown"),
        "ParentB": data.get("ParentB", "Unknown"),
        "Tooltip": data.get("Tooltip", "Compacted oversized generated item save payload."),
        "MergeMode": data.get("MergeMode", "literal"),
        "Category": data.get("Category", "generic"),
        "SourceMode": data.get("SourceMode", "generated"),
        "Tags": data.get("Tags", [])[:8] if isinstance(data.get("Tags"), list) else [],
        "Gameplay": data.get("Gameplay", {}),
        "Accessory": data.get("Accessory", {}),
        "Attack": attack,
        "Visual": visual,
        "Debug": {},
    }
    return json.dumps(minimal, ensure_ascii=False, separators=(",", ":"))


def repair_bytes(payload: bytes) -> tuple[bytes, int]:
    out = bytearray()
    pos = 0
    changed = 0
    while True:
        idx = payload.find(KEY, pos)
        if idx < 0:
            out.extend(payload[pos:])
            break

        len_pos = idx + len(KEY)
        if len_pos + 2 > len(payload):
            out.extend(payload[pos:])
            break

        old_len = int.from_bytes(payload[len_pos:len_pos + 2], "big", signed=False)
        data_start = len_pos + 2
        data_end = data_start + old_len
        if data_end > len(payload):
            out.extend(payload[pos:data_start])
            pos = data_start
            continue

        raw_bytes = payload[data_start:data_end]
        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            out.extend(payload[pos:data_end])
            pos = data_end
            continue

        new_text = compact_infini_json(raw_text)
        new_bytes = new_text.encode("utf-8")
        if len(new_bytes) > 32767:
            raise ValueError(f"compacted infiniJson is still too large: {len(new_bytes)} bytes")

        out.extend(payload[pos:len_pos])
        out.extend(len(new_bytes).to_bytes(2, "big", signed=True))
        out.extend(new_bytes)
        if new_bytes != raw_bytes:
            changed += 1
        pos = data_end

    return bytes(out), changed


def main(argv: list[str]) -> int:
    if len(argv) not in {2, 3}:
        print("usage: repair_tmodloader_tplr_strings.py INPUT.tplr [OUTPUT.tplr]", file=sys.stderr)
        return 2
    src = Path(argv[1])
    dst = Path(argv[2]) if len(argv) == 3 else src
    raw = src.read_bytes()
    inflated = gzip.decompress(raw)
    repaired, changed = repair_bytes(inflated)
    dst.write_bytes(gzip.compress(repaired))
    print(f"changed={changed} input={src} output={dst} inflated={len(inflated)}->{len(repaired)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
