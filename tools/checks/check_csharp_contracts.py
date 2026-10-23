#!/usr/bin/env python3
"""Source-language policies only; compilation and native checks own runtime behavior.

Do not add implementation-presence or method-order assertions here. This gate
checks warning suppression, authored tooltip ownership, named engine sentinels,
forbidden gameplay routers, inert opt-in self-test and public packet identity,
not runtime correctness.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "ModSources" / "InfiniCrafterLocal"
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


def stripped(text: str, keep_strings: bool = False) -> str:
    # A single lexical pass prevents // inside a URL/string from hiding code.
    # Spaces preserve offsets for structural observers and line diagnostics.
    pattern = r'//[^\n]*|/\*.*?\*/|@"(?:[^"]|"")*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    def mask(match: re.Match[str]) -> str:
        value = match.group()
        if keep_strings and not value.startswith(("//", "/*")):
            return value
        return re.sub(r"[^\n]", " ", value)
    return re.sub(pattern, mask, text, flags=re.S)


def source_policy_issues(sources: dict[str, str]) -> list[str]:
    """Genuine source-language policies, not snapshots of unrelated implementation.

    Named Terraria sentinels, no authored tooltip renderer and no suppressed
    diagnostics are centralized here; comments/string decoys cannot satisfy them.
    """
    issues: list[str] = []
    for path, text in sources.items():
        code = stripped(text)
        if re.search(r"#\s*(?:pragma\s+warning\s+disable|nullable\s+disable\s+warnings)\b", code):
            issues.append(f"warning_suppression:{path}")
        if (Path(path).parent.as_posix() in {"Common/Models/Contracts", "Common/Models/Runtime"}
                and Path(path).name.startswith("GeneratedItemData")) or (
                    Path(path).parent.as_posix() == "Content/Items"
                    and Path(path).name.startswith("GeneratedItem.")
                    and not Path(path).name.startswith("GeneratedItem.Tooltips")):
            if re.search(r"\b(?:Tooltip|TooltipLine|ModifyTooltips|SetBonusText)\b|\bplayer\s*\.\s*setBonus\b", code):
                issues.append(f"authored_tooltip:{path}")
        if path == "Common/Systems/Diagnostics/InfiniAgentContractSelfTestSystem.cs":
            # This auto-loaded diagnostic must return before any work unless opted in.
            # Keep the narrow safety policy here, not a separate aggregate QA gate.
            body = stripped(method_body(text, "PostSetupContent"), keep_strings=True)
            guard = (r'\s*if\s*\(\s*!string\.Equals\(\s*Environment\.GetEnvironmentVariable'
                     r'\(\s*EnabledEnv\s*\)\s*,\s*"1"\s*,\s*StringComparison\.Ordinal\s*\)\s*\)'
                     r'\s*(?:\{\s*return\s*;\s*\}|return\s*;)')
            if (not re.search(r'\bconst\s+string\s+EnabledEnv\s*=\s*"INFINI_AGENT_SELFTEST"\s*;',
                              stripped(text, keep_strings=True)) or not re.match(guard, body)):
                issues.append(f"selftest_opt_in:{path}")
            if re.search(r"\bProjectile\s*\.\s*NewProjectile(?:Direct)?\s*\(", code):
                issues.append(f"selftest_projectile_spawn:{path}")
        patterns = []
        if path.startswith("Localization/") and path.endswith(".hjson"):
            for name in ("GeneratedItem", "GeneratedHeadArmor", "GeneratedBodyArmor", "GeneratedLegsArmor"):
                blocks = re.findall(r"\b" + name + r":\s*\{([^}]*)\}", stripped(text, keep_strings=True))
                root_catalog = Path(path).name.endswith("_Mods.InfiniCrafterLocal.hjson")
                if (root_catalog and not blocks) or any(re.search(r"\bTooltip\s*:", block) for block in blocks):
                    issues.append(f"proxy_tooltip:{path}:{name}")
        if path == "Common/Models/Runtime/GeneratedItemData.Apply.cs":
            patterns = [r"\b(?:item|Item)\s*\.\s*useStyle\s*=\s*0\s*;"]
        elif (Path(path).parent.as_posix() == "Common/Services/Generation"
              and (Path(path).name == "GeneratorClient.cs" or Path(path).name.startswith("GeneratorClient."))):
            patterns = [r"\.\s*shoot\s*(?:>|<=)\s*0\b", r"\bprojectileType\s*(?:<=|>=)\s*0\b",
                        r"\.\s*create(?:Tile|Wall)\s*>=\s*0\b", r"\.\s*rare\s*>=\s*3\b"]
        elif path in {"Common/Commands/InfiniDumpCommand.cs", "Common/Commands/InfiniDumpPictureCommand.cs"}:
            patterns = [r"\.\s*shoot\s*>\s*0\b", r"\bprojectileType\s*>?=\s*0\b"]
        if any(re.search(pattern, code) for pattern in patterns):
            issues.append(f"numeric_sentinel:{path}")
    return issues


def check_source_policies() -> None:
    sources = {path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
               for pattern in ("*.cs", "*.hjson") for path in sorted(SRC.rglob(pattern))}
    ERRORS.extend(source_policy_issues(sources))
    project = read("InfiniCrafterLocal.csproj")
    if re.search(r"<NoWarn(?:\s|>)", project):
        fail("warning_suppression:InfiniCrafterLocal.csproj:NoWarn")


def braced_body(text: str, opening: int) -> str:
    mask = stripped(text)
    depth = 1
    for end in range(opening + 1, len(mask)):
        depth += (mask[end] == "{") - (mask[end] == "}")
        if depth == 0:
            return text[opening + 1:end]
    fail("unbalanced C# scope")
    return ""


def method_body(text: str, name: str, overload: int = 0) -> str:
    """Select a declaration and balanced body, not a call/comment or next-method split."""
    mask = stripped(text)
    matches = list(re.finditer(r"(?m)^[ \t]*(?:public|private|internal|protected)\s+[^;{=]*?\b"
                              + re.escape(name) + r"\s*\([^;{}]*\)\s*(\{|=>)", mask))
    if not matches:
        fail(f"missing C# method declaration: {name}")
        return ""
    match = matches[overload]
    if match.group(1) == "=>":
        return text[match.end():mask.index(";", match.end())]
    return braced_body(text, match.end() - 1)


def check_packet_ids() -> None:
    packet_source = read("Common/InfiniNetPacketIds.cs")
    values = re.findall(r"public const byte\s+(\w+)\s*=\s*(\d+)\s*;", stripped(packet_source))
    # Public protocol identities are stable, not merely non-colliding.
    ids = {name: int(raw) for name, raw in values}
    if ids.get("SyncGeneratedProjectileVfxEvent") != 9:
        fail("stable packet id: SyncGeneratedProjectileVfxEvent must remain 9")
    seen: dict[int, str] = {}
    for name, raw in values:
        value = int(raw)
        if value in seen:
            fail(f"packet id collision: {name} and {seen[value]} both use {value}")
        seen[value] = name


def architecture_issues(sources: dict[str, str]) -> list[str]:
    """Reject prohibited gameplay authorities regardless of file/helper layout."""
    forbidden = r"\b(?:AttackSpec|WeaponFamily|RuntimeFamily|GeneratedRuntimeFamilyPolicy|GeneratedChildSpecPolicy)\b"
    return [f"forbidden_gameplay_router:{path}:{match.group()}"
            for path, text in sources.items() for match in re.finditer(forbidden, stripped(text))]


def main() -> int:
    ERRORS.clear()
    check_source_policies()
    sources = {p.relative_to(SRC).as_posix(): p.read_text(encoding="utf-8") for p in SRC.rglob("*.cs")}
    ERRORS.extend(architecture_issues(sources))
    check_packet_ids()
    if ERRORS:
        print("[FAIL] C# source policy issues:")
        for message in ERRORS:
            print(" -", message)
        return 1
    print("[OK] C# source policies passed (runtime behavior requires native checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
