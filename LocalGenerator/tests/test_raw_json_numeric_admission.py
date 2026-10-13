"""Source registration checks only; native numeric behavior is parent-run C# evidence."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "ModSources/InfiniCrafterLocal/Common/Models"


def test_hitbox_scales_declare_raw_property_domain_before_float_storage():
    source = (MODELS / "RuntimeProgramSpec.cs").read_text(encoding="utf-8")
    curve = source.split("public sealed class RuntimeHitboxCurveSpec", 1)[1].split("public sealed class RuntimeHitboxSpec", 1)[0]
    for name in ("StartScale", "EndScale"):
        assert re.search(r"\[JsonConverter\(typeof\(" + name + r"JsonConverter\)\)\]\s*\[JsonRequired\] public float " + name, curve), name
        assert re.search(r"public sealed class " + name + r'JsonConverter\s*:\s*RawJsonFloatDomainConverter\s*\{\s*public ' + name + r'JsonConverter\(\)\s*:\s*base\("0\.25",\s*"8"\)', curve), name
