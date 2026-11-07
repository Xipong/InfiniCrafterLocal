"""Validate an exact successful-CI package and prepare tracked-source release assets.

No network, credentials, package execution, tag or release mutation lives here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from verify_tmod_package import read_info, read_package
from tools.build.build_studio_bundle import RESOURCE_MANIFEST, verify_resources

ROOT = Path(__file__).resolve().parents[2]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_package(root: Path, artifact: Path, version: str, sha: str) -> dict:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid release identity")
    owners = (("generator/infini_local/__init__.py", r'APP_VERSION = "([^"]+)"'),
              ("mod/InfiniCrafterLocal/InfiniCrafterLocal.cs", r'ModVersion = "([^"]+)"'),
              ("mod/InfiniCrafterLocal/build.txt", r'(?m)^version = (\S+)$'))
    for name, pattern in owners:
        match = re.search(pattern, root.joinpath(name).read_text(encoding="utf-8"))
        if not match or match[1] != version:
            raise ValueError("Release version differs from source")
    provenance = json.loads(artifact.joinpath("build-provenance.json").read_text(encoding="utf-8-sig"))
    verified = json.loads(artifact.joinpath("package-verification.json").read_text(encoding="utf-8-sig"))
    package = artifact.joinpath("InfiniCrafterLocal.tmod").read_bytes()
    if provenance.get("sourceCommit") != sha or provenance.get("packageSha256") != digest(package):
        raise ValueError("CI package source/hash mismatch")
    if verified.get("status") != "passed" or verified.get("sha256") != digest(package) or verified.get("bytes") != len(package):
        raise ValueError("CI package verification missing or inconsistent")
    tml, name, internal_version, files = read_package(package)
    info = read_info(files["Info"])
    if (name != "InfiniCrafterLocal" or internal_version != version or info.get("version") != version
            or verified.get("version") != version or verified.get("name") != name
            or tml != provenance.get("tmlVersion") or tml != verified.get("tmlVersion")):
        raise ValueError("Internal package identity mismatch")
    assembly = files.get("InfiniCrafterLocal.dll", b"")
    if not assembly.startswith(b"MZ") or digest(assembly) != provenance.get("assemblySha256"):
        raise ValueError("Packaged assembly differs from CI build")
    manifest = root.joinpath("mod/InfiniCrafterLocal/build.txt").read_text()
    refs = next(line.split("=", 1)[1].strip().split(",") for line in manifest.splitlines() if line.startswith("modReferences ="))
    if info.get("modReferences") != [ref.strip() for ref in refs]:
        raise ValueError("Package dependencies differ from source")
    studio = verify_resources(files.__getitem__, source_root=root)
    if verified.get("studio") != studio or provenance.get("studioManifest") != json.loads(files[RESOURCE_MANIFEST]):
        raise ValueError("Embedded Studio differs from CI verification/provenance")
    if provenance.get("studioRuntimeSmoke") != "passed: embedded interpreter imports, HTTP frontend and managed shutdown":
        raise ValueError("Official bundled Studio startup smoke was not successful")
    return provenance


def prepare(root: Path, artifact: Path, output: Path, version: str, sha: str, run_id: str) -> None:
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip() != sha:
        raise ValueError("Checkout is not release source")
    if output.exists():
        raise ValueError("Output must be new; publication preparation is not an overwrite")
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "source.zip"
        subprocess.run(["git", "archive", "--format=zip", "--output", str(archive), sha], cwd=root, check=True)
        extracted = Path(temporary) / "source"
        with zipfile.ZipFile(archive) as zipped:
            for item in zipped.infolist():
                if item.filename.startswith("/") or ".." in Path(item.filename).parts or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unsafe tracked source archive member")
            zipped.extractall(extracted)
        subprocess.run([sys.executable, "tools/checks/check_project_hygiene.py", "--strict-archive"], cwd=extracted, check=True)
        provenance = validate_package(extracted, artifact, version, sha)
        output.mkdir(parents=True)
        shutil.copyfile(archive, output / f"InfiniCrafterLocal_{version}_Source_and_LocalGenerator.zip")
    for name in ("InfiniCrafterLocal.tmod", "package-verification.json", "build-provenance.json"):
        shutil.copyfile(artifact / name, output / name)
    provenance = {"sourceCommit": sha, "version": version, "ciRunId": run_id,
                  "packageSha256": provenance["packageSha256"],
                  "runtimeSmoke": "notRun: CI package validation is not an in-game test"}
    (output / "release-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    (output / "SHA256SUMS.txt").write_text("".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(output.iterdir())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    prepare(ROOT, args.artifact, args.output, args.version, args.sha, args.run_id)
