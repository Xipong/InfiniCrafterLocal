from __future__ import annotations

from pathlib import Path

_PARTIAL_GLOBS = {
    "GeneratedItemData.cs": "GeneratedItemData*.cs",
    "GeneratedProjectile.cs": "GeneratedProjectile*.cs",
    "InfiniCraftPlayer.cs": "InfiniCraftPlayer*.cs",
}


def read_text_with_partial_bundles(path: str | Path, *, encoding: str = "utf-8") -> str:
    """Read C# source for static contract tests, expanding known partial god-file splits.

    Several contract tests predate the C# split and intentionally assert on the
    whole logical type, not on one physical file.  For those types, concatenate
    sibling partial files in deterministic filename order.  Other paths are read
    normally.
    """
    p = Path(path)
    pattern = _PARTIAL_GLOBS.get(p.name)
    if pattern:
        files = sorted(p.parent.glob(pattern))
        if files:
            return "\n".join(file.read_text(encoding=encoding) for file in files)
    return p.read_text(encoding=encoding)
