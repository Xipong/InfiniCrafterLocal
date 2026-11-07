#!/usr/bin/env python3
"""Stage declared tML managed runtime assets, excluding nested build-tool DLLs.

The official deps manifest selects primary and RID-specific assets. --harness
also updates an executable's host dependency graph, including framework package
overrides which MSBuild may otherwise omit from CopyLocal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys

RID_CHAINS = {
    "win-x64": ("win-x64", "win", "any"),
    "linux-x64": ("linux-x64", "linux", "unix-x64", "unix", "any"),
    "osx-x64": ("osx-x64", "osx", "unix-x64", "unix", "any"),
    "win-arm64": ("win-arm64", "win", "any"),
    "linux-arm64": ("linux-arm64", "linux", "unix-arm64", "unix", "any"),
    "osx-arm64": ("osx-arm64", "osx", "unix-arm64", "unix", "any"),
}
RECEIPT = "native-target-staging.json"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in ("..", ".") for part in path.parts) or "\\" in value or ":" in value:
        raise ValueError(f"Unexpected path in official dependency manifest: {value!r}")
    return path


def selected_assets(runtime: Path, rid: str) -> dict:
    runtime = runtime.resolve(strict=True)
    chain = RID_CHAINS[rid]
    deps_path = runtime / "tModLoader.deps.json"
    config_path = runtime / "tModLoader.runtimeconfig.json"
    deps = json.loads(deps_path.read_text(encoding="utf-8-sig"))
    framework = json.loads(config_path.read_text(encoding="utf-8-sig"))["runtimeOptions"]["framework"]
    if framework["name"] != "Microsoft.NETCore.App":
        raise ValueError("Expected the official tML Microsoft.NETCore.App framework")
    target = deps["targets"][deps["runtimeTarget"]["name"]]
    groups: dict[str, list[dict]] = {}
    for library, entry in target.items():
        info = deps["libraries"][library]
        choices = {relative(asset).name: (asset, metadata, None, len(chain))
                   for asset, metadata in entry.get("runtime", {}).items() if asset.endswith(".dll")}
        for asset, metadata in entry.get("runtimeTargets", {}).items():
            if metadata.get("assetType") != "runtime" or metadata.get("rid") not in chain or not asset.endswith(".dll"):
                continue
            name = relative(asset).name
            rank = chain.index(metadata["rid"])
            prior = choices.get(name)
            if prior is not None and prior[3] == rank and prior[0] != asset:
                raise ValueError(f"Ambiguous runtime asset for {library}: {name}")
            if prior is None or rank < prior[3]:
                choices[name] = (asset, {key: value for key, value in metadata.items()
                                        if key not in ("rid", "assetType")}, metadata["rid"], rank)
        for name, (asset, metadata, selected_rid, _) in choices.items():
            if info["type"] == "package":
                source = PurePosixPath("Libraries") / relative(info["path"]) / relative(asset)
            elif name == "tModLoader.dll":
                source = relative(asset)
            else:
                source = PurePosixPath("Libraries") / relative(library) / relative(asset)
            groups.setdefault(name.casefold(), []).append({
                "fileName": name, "source": source.as_posix(), "library": library,
                "libraryType": info["type"], "runtime": metadata, "selectedRid": selected_rid,
            })
    assets = []
    for candidates in groups.values():
        existing = [row for row in candidates if (runtime / row["source"]).is_file()]
        if not existing:
            raise ValueError(f"Missing official primary runtime asset: {candidates[0]['source']}")
        hashes = {digest(runtime / row["source"]) for row in existing}
        if len(hashes) != 1:
            raise ValueError(f"Conflicting primary assets for {candidates[0]['fileName']}")
        # Reference-only aliases can reuse only a unique declared primary PE.
        for row in candidates:
            if row not in existing and row["libraryType"] != "reference":
                raise ValueError(f"Missing declared runtime asset: {row['source']}")
        metadata = {}
        for row in candidates:
            for key, value in row["runtime"].items():
                if key in metadata and metadata[key] != value:
                    raise ValueError(f"Conflicting primary metadata for {row['fileName']}: {key}")
                metadata[key] = value
        chosen = existing[0]
        source = runtime / chosen["source"]
        assets.append({"fileName": chosen["fileName"], "source": chosen["source"],
                       "sha256": next(iter(hashes)), "bytes": source.stat().st_size,
                       "runtime": metadata, "selectedRid": chosen["selectedRid"],
                       "libraries": sorted(row["library"] for row in candidates)})
    assets.sort(key=lambda row: row["fileName"].casefold())
    if not any(row["fileName"] == "tModLoader.dll" for row in assets):
        raise ValueError("Official manifest does not declare tModLoader.dll")
    return {"schema": "ifc_native_target_staging_v1", "runtimeIdentifier": rid,
            "runtimeVersion": framework["version"], "depsSha256": digest(deps_path),
            "runtimeconfigSha256": digest(config_path), "assets": assets}


def copy_assets(runtime: Path, destination: Path, manifest: dict) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for row in manifest["assets"]:
        output = destination / row["fileName"]
        shutil.copyfile(runtime / row["source"], output)
        if digest(output) != row["sha256"]:
            raise ValueError(f"Runtime asset changed during staging: {row['fileName']}")


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def stage_references(runtime: Path, destination: Path, manifest: dict) -> None:
    destination = destination.resolve()
    if destination == runtime.resolve() or runtime.resolve() in destination.parents:
        raise ValueError("Reference staging must be outside the official runtime")
    previous = destination / RECEIPT
    owned = set()
    if previous.is_file():
        old = json.loads(previous.read_text(encoding="utf-8"))
        if old.get("schema") != manifest["schema"]:
            raise ValueError("Existing reference directory has a different owner")
        owned = {row["fileName"] for row in old["assets"]} | {RECEIPT}
    if destination.exists() and any(path.name not in owned or not path.is_file() for path in destination.iterdir()):
        raise ValueError("Reference staging destination must be empty or owned by this tool")
    copy_assets(runtime, destination, manifest)
    current = {row["fileName"] for row in manifest["assets"]} | {RECEIPT}
    for name in owned - current:
        (destination / name).unlink()
    write_json(previous, manifest)


def stage_harness(runtime: Path, harness: Path, manifest: dict) -> None:
    harness = harness.resolve(strict=True)
    deps_path = harness.with_suffix(".deps.json")
    deps = json.loads(deps_path.read_text(encoding="utf-8-sig"))
    target = deps["targets"][deps["runtimeTarget"]["name"]]
    roots = [key for key, value in target.items() if harness.name in value.get("runtime", {})]
    if len(roots) != 1:
        raise ValueError("Expected one executable root in the native harness dependency graph")
    names = {row["fileName"].casefold() for row in manifest["assets"]}
    removed = set()
    for key in list(target):
        runtime_assets = target[key].get("runtime", {})
        if any(PurePosixPath(asset).name.casefold() in names for asset in runtime_assets):
            if not all(PurePosixPath(asset).name.casefold() in names for asset in runtime_assets):
                raise ValueError(f"Cannot partially replace a harness dependency: {key}")
            removed.add(key.split("/")[0])
            del target[key]
            deps["libraries"].pop(key, None)
    for entry in target.values():
        entry["dependencies"] = {key: value for key, value in entry.get("dependencies", {}).items() if key not in removed}
    root = target[roots[0]]
    for row in manifest["assets"]:
        name = PurePosixPath(row["fileName"]).stem
        version = row["runtime"].get("assemblyVersion", "0.0.0.0")
        key = f"{name}/{version}"
        if key in target:
            raise ValueError(f"Harness dependency collision: {key}")
        target[key] = {"runtime": {row["fileName"]: row["runtime"]}}
        deps["libraries"][key] = {"type": "reference", "serviceable": False, "sha512": ""}
        root["dependencies"][name] = version
    copy_assets(runtime, harness.parent, manifest)
    write_json(deps_path, deps)
    write_json(harness.parent / RECEIPT, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True, help="Official unpacked tModLoader directory")
    parser.add_argument("--rid", choices=RID_CHAINS, required=True)
    parser.add_argument("--destination", type=Path, required=True, help="Owned curated compiler-reference directory")
    parser.add_argument("--harness", type=Path, help="Also stage this built executable's bytes and host dependency graph")
    args = parser.parse_args()
    try:
        runtime = args.runtime.resolve(strict=True)
        manifest = selected_assets(runtime, args.rid)
        stage_references(runtime, args.destination, manifest)
        if args.harness is not None:
            stage_harness(runtime, args.harness, manifest)
        print(json.dumps({"status": "staged", "runtimeIdentifier": args.rid,
                          "runtimeVersion": manifest["runtimeVersion"], "assets": len(manifest["assets"]),
                          "references": str(args.destination.resolve()), "harness": str(args.harness) if args.harness else None}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"native target staging: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
