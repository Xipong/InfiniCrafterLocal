#!/usr/bin/env python3
"""Run a tModLoader workbench projectile scene in a new isolated server world.

This tool copies specified inputs into a new isolated directory and never loads
the original world or mod files in tModLoader. Use --prepare-only to inspect
the isolated setup without starting tModLoader. Game execution itself
requires the explicit --run flag. The client item-use path is not implemented
by this dedicated-server launcher. --mode client --prepare-only writes a
client-launch.json with isolated paths and environment for a manually operated
client. Create and enter a temporary player and world named workbench there.
This launcher does not create, join or drive a client.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time


NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,99}$")
DRIVER_NAME = "IFCWorkbenchDriver"
MAX_SCENARIO_BYTES = 1024 * 1024
MAX_WORLD_BYTES = 2 * 1024 * 1024 * 1024
MAX_ASSET_BYTES = 32 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EXTRA_ENV = re.compile(r"^IFC_WORKBENCH_[A-Z0-9_]+_OUTPUT$")
OUTPUT_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\.json$")
RESERVED_FILES = {"result.json", "scenario.json", "ifc-workbench-sandbox.json", "client-launch.json", "world-source-receipt.json", "asset-staging-receipt.json"}


def parse_mods(values: list[str]) -> dict[str, Path]:
    mods: dict[str, Path] = {}
    lower_names: set[str] = set()
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not NAME.fullmatch(name) or not raw_path:
            raise ValueError("Use --mod INTERNAL_NAME=/absolute/path/to/mod.tmod")
        if name.lower() in lower_names:
            raise ValueError(f"Duplicate mod name: {name}")
        path = Path(raw_path).expanduser().resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != ".tmod":
            raise ValueError(f"Not a .tmod file: {path}")
        mods[name] = path
        lower_names.add(name.lower())
    if DRIVER_NAME not in mods:
        raise ValueError(f"A built {DRIVER_NAME}.tmod is required via --mod {DRIVER_NAME}=PATH")
    return mods


def read_scene(path: Path, launch_mode: str = "server") -> tuple[dict, str]:
    path = path.expanduser().resolve(strict=True)
    if not path.is_file() or path.stat().st_size > MAX_SCENARIO_BYTES:
        raise ValueError("Scenario must be a file no larger than 1 MiB")
    original = path.read_bytes()
    if len(original) > MAX_SCENARIO_BYTES:
        raise ValueError("Scenario must be a file no larger than 1 MiB")
    data = json.loads(original.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Scenario JSON must be an object")
    if data.get("mode") == "item_use" and launch_mode == "server":
        raise ValueError("item_use requires a local client; this launcher only runs a dedicated server")
    if data.get("mode") not in ("projectile", "item_use"):
        raise ValueError('Scenario mode must be "projectile" or "item_use"')
    for key, minimum, maximum in (("ticks", 1, 3600), ("minHits", 1, 10000), ("minDamage", 1, 100000000)):
        value = data.get(key, 1 if key == "minDamage" else None)
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"{key} must be an integer in {minimum}..{maximum}")
    return data, hashlib.sha256(original).hexdigest()


def asset_slots(scene: dict) -> list[tuple[dict, str, str]]:
    """Known generated-item runtime asset owners; no traversal or prose rewriting."""
    item = scene.get("itemData")
    if item is None:
        return []
    if not isinstance(item, dict):
        raise ValueError("itemData must be an object")
    slots = []
    def fields(obj, prefix, keys):
        if obj is None:
            return
        if not isinstance(obj, dict):
            raise ValueError(f"{prefix} must be an object")
        for key in keys:
            if key in obj:
                if not isinstance(obj[key], str):
                    raise ValueError(f"{prefix}.{key} must be a string")
                if obj[key]:
                    slots.append((obj, key, f"{prefix}.{key}"))
    fields(item.get("visual"), "itemData.visual", ("spritePath", "equipOverlayPath"))
    program = item.get("runtimeProgram")
    if program is not None:
        if not isinstance(program, dict):
            raise ValueError("itemData.runtimeProgram must be an object")
        entities = program.get("entities", [])
        if not isinstance(entities, list):
            raise ValueError("itemData.runtimeProgram.entities must be an array")
        for index, entity in enumerate(entities):
            if not isinstance(entity, dict):
                raise ValueError("runtime entity must be an object")
            fields(entity.get("visual"), f"itemData.runtimeProgram.entities[{index}].visual", ("spritePath", "impactSpritePath"))
    manifest = item.get("vfxManifest")
    if manifest is not None:
        if not isinstance(manifest, dict):
            raise ValueError("itemData.vfxManifest must be an object")
        assets = manifest.get("assets", [])
        if assets is None:
            assets = []
        if not isinstance(assets, list):
            raise ValueError("itemData.vfxManifest.assets must be an array")
        for index, asset in enumerate(assets):
            fields(asset, f"itemData.vfxManifest.assets[{index}]", ("spritePath",))
    return slots


def plan_assets(scene: dict, values: list[str]) -> tuple[list[tuple[dict, str, str]], dict[str, tuple[Path, str, int, str]]]:
    slots = asset_slots(scene)
    refs = {owner[key] for owner, key, _ in slots}
    mappings = {}
    filenames = {}
    for value in values:
        original, separator, raw_path = value.partition("=")
        if not separator or not original or not raw_path:
            raise ValueError("Use --asset ORIGINAL_REF=/path/to/local.png")
        if original in mappings:
            raise ValueError(f"Duplicate asset mapping: {original}")
        if original not in refs:
            raise ValueError(f"Asset mapping does not match a runtime itemData path: {original}")
        basename = original.replace("\\", "/").rsplit("/", 1)[-1]
        if not basename or len(basename) > 120 or not basename.lower().endswith(".png") or any(c in basename for c in '<>:"|?*\0'):
            raise ValueError(f"Runtime asset reference needs a safe PNG filename: {original}")
        source = Path(raw_path).expanduser().resolve(strict=True)
        if not source.is_file() or source.suffix.lower() != ".png" or not 8 <= source.stat().st_size <= MAX_ASSET_BYTES:
            raise ValueError(f"Asset must be a PNG file of at most 32 MiB: {source}")
        with source.open("rb") as file:
            if file.read(8) != PNG_SIGNATURE:
                raise ValueError(f"Asset does not have a PNG signature: {source}")
        digest = hash_file(source)
        size = source.stat().st_size
        previous = filenames.setdefault(basename.lower(), digest)
        if previous != digest:
            raise ValueError(f"Conflicting runtime asset filename: {basename}")
        mappings[original] = (source, digest, size, basename)
    missing = refs - mappings.keys()
    if missing:
        raise ValueError("Missing explicit --asset mappings for runtime itemData paths: " + ", ".join(sorted(missing)))
    return slots, mappings


def parse_extra_outputs(values: list[str]) -> dict[str, str]:
    outputs: dict[str, str] = {}
    filenames: set[str] = set()
    for value in values:
        variable, separator, filename = value.partition("=")
        if not separator or not EXTRA_ENV.fullmatch(variable) or not OUTPUT_FILE.fullmatch(filename):
            raise ValueError("Use --extra-output IFC_WORKBENCH_NAME_OUTPUT=filename.json")
        if variable in outputs or filename.lower() in filenames or filename.lower() in RESERVED_FILES:
            raise ValueError("Duplicate or reserved extra output")
        outputs[variable] = filename
        filenames.add(filename.lower())
    return outputs


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def world_sources(world_source: Path) -> list[Path]:
    world = world_source.expanduser().resolve(strict=True)
    if world.suffix.lower() != ".wld":
        raise ValueError("--world-source must identify a .wld file")
    sidecar = world.with_suffix(".twld").resolve(strict=True)
    for path in (world, sidecar):
        if not path.is_file() or not 1 <= path.stat().st_size <= MAX_WORLD_BYTES:
            raise ValueError(f"World input must be a nonempty regular file of at most 2 GiB: {path}")
    return [world, sidecar]


def prepare(scenario: Path, mod_values: list[str], sandbox_root: Path | None = None,
            extra_output_values: list[str] | None = None, launch_mode: str = "server",
            world_source: Path | None = None, asset_values: list[str] | None = None) -> dict:
    """Prepare an unshared sandbox; returns paths and the in-memory opt-in token."""
    scene, original_scenario_hash = read_scene(scenario, launch_mode)
    mods = parse_mods(mod_values)
    extra_outputs = parse_extra_outputs(extra_output_values or [])
    source_files = world_sources(world_source) if world_source is not None else None
    slots, mappings = plan_assets(scene, asset_values or [])
    if sandbox_root is not None:
        sandbox_root = sandbox_root.expanduser().resolve(strict=True)
        if not sandbox_root.is_dir():
            raise ValueError("Sandbox root must be an existing directory")
    sandbox = Path(tempfile.mkdtemp(prefix="ifc-workbench-", dir=sandbox_root)).resolve()
    sandbox.chmod(0o700)
    mod_dir = sandbox / "Mods"
    world_dir = sandbox / "Worlds"
    workshop = sandbox / "empty-workshop"
    for directory in (mod_dir, world_dir, workshop):
        directory.mkdir()
    for name, source in mods.items():
        shutil.copyfile(source, mod_dir / f"{name}.tmod")
    (mod_dir / "enabled.json").write_text(json.dumps(sorted(mods)), encoding="utf-8")
    staged = {}
    asset_receipt = []
    for original, (source, digest, size, basename) in mappings.items():
        directory = sandbox / "Assets" / digest
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / basename
        if len(str(target)) > 260:
            raise ValueError("Sandbox asset path exceeds the IFC runtime path limit")
        shutil.copyfile(source, target)
        copied = hash_file(target)
        if copied != digest or target.stat().st_size != size:
            raise RuntimeError(f"Asset input changed during isolated copy: {source}")
        staged[original] = str(target)
        asset_receipt.append({"originalRef": original, "sourcePath": str(source), "sandboxPath": str(target),
                              "sizeBytes": size, "sourceSha256": digest, "sandboxSha256": copied,
                              "owners": [pointer for owner, key, pointer in slots if owner[key] == original]})
    for source, digest, size, _ in mappings.values():
        if hash_file(source) != digest or source.stat().st_size != size:
            raise RuntimeError(f"Asset input changed during isolated copy: {source}")
    for owner, key, _ in slots:
        owner[key] = staged[owner[key]]
    scenario_copy = sandbox / "scenario.json"
    scenario_copy.write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
    scenario_hash = hashlib.sha256(scenario_copy.read_bytes()).hexdigest()
    if mappings:
        (sandbox / "asset-staging-receipt.json").write_text(json.dumps({
            "originalScenarioSha256": original_scenario_hash, "runtimeScenarioSha256": scenario_hash,
            "assets": asset_receipt}, ensure_ascii=False, indent=2), encoding="utf-8")
    output = sandbox / "result.json"
    world = world_dir / "workbench.wld"
    if source_files is not None:
        receipt = []
        expected = [(source, hash_file(source), source.stat().st_size) for source in source_files]
        for (source, before, size), destination in zip(expected, (world, world.with_suffix(".twld"))):
            shutil.copyfile(source, destination)
            copied = hash_file(destination)
            if before != copied or size != destination.stat().st_size:
                raise RuntimeError(f"World input changed during isolated copy: {source}")
            receipt.append({"sourcePath": str(source), "sandboxPath": str(destination), "sizeBytes": size,
                            "sourceSha256": before, "sandboxSha256": copied})
        for source, before, size in expected:
            if before != hash_file(source) or size != source.stat().st_size:
                raise RuntimeError(f"World input changed during isolated copy: {source}")
        (sandbox / "world-source-receipt.json").write_text(json.dumps({"files": receipt}, indent=2), encoding="utf-8")
    token = secrets.token_hex(32)
    marker = {"token": token, "worldPath": str(world)}
    (sandbox / "ifc-workbench-sandbox.json").write_text(json.dumps(marker), encoding="utf-8")
    # A new blank config avoids inheriting any user-provided server settings.
    (sandbox / "serverconfig.txt").write_text("upnp=0\n", encoding="utf-8")
    return {"sandbox": sandbox, "mods": mod_dir, "workshop": workshop, "world": world,
            "scenario": scenario_copy, "output": output, "token": token,
            "scenario_sha256": scenario_hash, "scene": scene,
            "world_source": source_files is not None,
            "extra_outputs": {key: sandbox / value for key, value in extra_outputs.items()}}


def server_command(dotnet: str, tml: Path, state: dict, port: int) -> list[str]:
    command = [dotnet, str(tml / "tModLoader.dll"), "-server", "-nosteam",
            "-tmlsavedirectory", str(state["sandbox"]), "-modpath", str(state["mods"]),
            "-steamworkshopfolder", str(state["workshop"]),
            "-world", str(state["world"]),
            "-config", str(state["sandbox"] / "serverconfig.txt"),
            "-banlist", str(state["sandbox"] / "banlist.txt"),
            "-ip", "127.0.0.1", "-port", str(port), "-players", "1", "-noupnp"]
    if not state["world_source"]:
        command.extend(["-autocreate", "1", "-worldname", "workbench"])
    return command


def workbench_environment(state: dict) -> dict[str, str]:
    env = {"IFC_WORKBENCH_ENABLED": "1", "IFC_WORKBENCH_SANDBOX": str(state["sandbox"]),
           "IFC_WORKBENCH_SCENARIO": str(state["scenario"]),
           "IFC_WORKBENCH_OUTPUT": str(state["output"]), "IFC_WORKBENCH_TOKEN": state["token"]}
    env.update({key: str(path) for key, path in state["extra_outputs"].items()})
    return env


def write_client_plan(dotnet: str, tml: Path, state: dict) -> Path:
    path = state["sandbox"] / "client-launch.json"
    plan = {"workingDirectory": str(tml),
            "command": [dotnet, str(tml / "tModLoader.dll"), "-nosteam",
                        "-tmlsavedirectory", str(state["sandbox"]), "-modpath", str(state["mods"]),
                        "-steamworkshopfolder", str(state["workshop"])],
            "clearEnvironmentPrefix": "IFC_WORKBENCH_", "environment": workbench_environment(state),
            "manualSteps": ["Start the client using this command and environment; inherited IFC_WORKBENCH_* variables must be cleared first.",
                            ("Create a new local player in the isolated save directory and enter the copied world (file Worlds/workbench.wld; its displayed name remains unchanged)." if state["world_source"] else "Create a new local player and local world named workbench in the isolated save directory, then enter that world."),
                            "No remote connection, menu navigation or gameplay is performed by the launcher."],
            "expectedWorldPath": str(state["world"])}
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def choose_port() -> int:
    # Close before server starts; another process could still claim this port.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def validate_passed_result(result: dict, state: dict) -> None:
    """Require a complete report for the exact submitted scenario, not a status alone."""
    scene = state["scene"]
    if type(result.get("schemaVersion")) is not int or result["schemaVersion"] != 1:
        raise RuntimeError("Result schemaVersion is missing or unsupported")
    if result.get("mode") != "projectile" or result.get("scenarioSha256") != state["scenario_sha256"]:
        raise RuntimeError("Result mode or scenario SHA-256 does not match the submitted scenario")
    expected = {"requestedTicks": scene["ticks"], "completedTicks": scene["ticks"],
                "minHits": scene["minHits"], "minDamage": scene.get("minDamage", 1)}
    for field, value in expected.items():
        if type(result.get(field)) is not int or result[field] != value:
            raise RuntimeError(f"Result {field} does not match the submitted scenario")
    for field, minimum in (("hits", expected["minHits"]), ("totalDamage", expected["minDamage"])):
        if type(result.get(field)) is not int or result[field] < minimum:
            raise RuntimeError(f"Result {field} is missing or below the requested threshold")


def run_server(dotnet: str, tml: Path, state: dict, timeout: int, port: int) -> int:
    # Never inherit stale opt-in or output paths from a previous run.
    env = {key: value for key, value in os.environ.items() if not key.startswith("IFC_WORKBENCH_")}
    env.update(workbench_environment(state))
    command = server_command(dotnet, tml, state, port)
    log_path = state["sandbox"] / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(command, cwd=tml, env=env, stdin=subprocess.PIPE,
                                stdout=log, stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + timeout
        result = None
        try:
            while time.monotonic() < deadline:
                if state["output"].exists():
                    try:
                        result = json.loads(state["output"].read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        # The driver may still be writing; try again before accepting it.
                        result = None
                    if isinstance(result, dict):
                        break
                if proc.poll() is not None:
                    break
                time.sleep(0.25)
            if result is None:
                raise RuntimeError(f"tModLoader exited or timed out without a valid result; inspect {log_path}")
            if proc.poll() is None and proc.stdin is not None:
                try:
                    proc.stdin.write("exit\n")
                    proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
            try:
                exit_code = proc.wait(timeout=10)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"tModLoader did not exit cleanly after the scenario; inspect {log_path}") from exc
            if exit_code != 0:
                raise RuntimeError(f"tModLoader exited with code {exit_code} after writing a result; inspect {log_path}")
            if result.get("status") == "passed":
                validate_passed_result(result, state)
                return 0
            if result.get("status") == "failed":
                return 1
            raise RuntimeError(f"tModLoader reported an error or invalid status; inspect {state['output']}")
        finally:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tml-dir", required=True, type=Path, help="Installed tModLoader directory")
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--world-source", type=Path, help="Read-only .wld source with matching .twld, copied into the sandbox")
    parser.add_argument("--asset", action="append", default=[], metavar="ORIGINAL_REF=LOCAL_PNG",
                        help="Stage one exact generated-item runtime PNG reference; repeat for each distinct reference")
    parser.add_argument("--mod", action="append", default=[], metavar="NAME=PATH",
                        help="Internal tML mod name and .tmod file; include IFCWorkbenchDriver and all dependencies")
    parser.add_argument("--sandbox-root", type=Path, help="Existing parent for a new random test directory")
    parser.add_argument("--extra-output", action="append", default=[], metavar="ENV=FILE.json",
                        help="Map IFC_WORKBENCH_*_OUTPUT to a distinct JSON filename within the sandbox")
    parser.add_argument("--dotnet", default="dotnet", help=".NET executable compatible with this tModLoader")
    parser.add_argument("--timeout", type=int, default=900, help="Maximum seconds including world creation")
    parser.add_argument("--port", type=int, default=0, help="Loopback TCP port, or 0 to request a free port")
    parser.add_argument("--mode", choices=("server", "client"), default="server", help="Client mode prepares manual launch instructions only")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare-only", action="store_true", help="Prepare sandbox without launching the game")
    action.add_argument("--run", action="store_true", help="Explicitly run the isolated dedicated server")
    args = parser.parse_args(argv)
    if args.mode == "client" and args.run:
        parser.error("Client auto-launch and input are not implemented; use --mode client --prepare-only")
    if not 1 <= args.timeout <= 86400 or not 0 <= args.port <= 65535:
        parser.error("timeout must be 1..86400 and port 0..65535")
    tml = args.tml_dir.expanduser().resolve()
    if not (tml / "tModLoader.dll").is_file():
        parser.error("--tml-dir must contain tModLoader.dll")
    try:
        state = prepare(args.scenario, args.mod, args.sandbox_root, args.extra_output, args.mode, args.world_source, args.asset)
    except (ValueError, OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"Isolated sandbox: {state['sandbox']}", flush=True)
    if args.prepare_only:
        if args.mode == "client":
            print(f"Manual client launch configuration: {write_client_plan(args.dotnet, tml, state)}", flush=True)
        print("Prepared only; no game process started.", flush=True)
        return 0
    dotnet = shutil.which(args.dotnet)
    if not dotnet:
        parser.error(".NET executable not found")
    port = args.port or choose_port()
    try:
        return run_server(dotnet, tml, state, args.timeout, port)
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
