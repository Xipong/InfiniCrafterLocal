#!/usr/bin/env python3
"""Export an offline cache snapshot without truncating or deleting its history.

Use standard solid tar.xz compression so repeated prompts compress across files.
The default core bundle omits private image intermediates, not model history.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

from infini_local.core.env_utils import env_credential_values  # noqa: E402
from infini_local.services.codex_auth import redact_credentials  # noqa: E402

class BundleError(ValueError):
    """Safe operator-facing refusal, never containing cache contents or paths."""


MANIFEST = "support-manifest.json"
_TRACE = re.compile(r"(?:events|prompt_trace|pipeline_trace)\.ndjson(?:\.\d+)?\Z")
_TREE_SUFFIXES = {
    "stage_requests": {".json"}, "transport_artifacts": {".txt"},
    "world_recipes": {".json", ".png"}, "sprites": {".json", ".png"},
    "image-diagnostics": {".png"},
}


def _allowed(path: Path) -> bool:
    if path.is_absolute() or any(part in {".", ".."} or "\\" in part or ":" in part for part in path.parts):
        return False
    if len(path.parts) == 1:
        return bool(_TRACE.fullmatch(path.name)) or path.name in {"last_combine_failure.json", "sdcpp_server.log"}
    return path.suffix in _TREE_SUFFIXES.get(path.parts[0], ()) and not any(
        part.startswith(".") for part in path.parts
    )


def _inventory(cache: Path) -> tuple[dict[str, tuple], int]:
    """Never follow links or read unrecognized configuration/authentication files."""
    found: dict[str, tuple] = {}
    ignored = 0
    for directory, dirs, files in os.walk(cache, followlinks=False):
        dirs[:] = sorted(name for name in dirs if not (Path(directory) / name).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(cache)
            info = path.lstat()
            if not _allowed(relative) or not stat.S_ISREG(info.st_mode):
                ignored += 1
                continue
            found[relative.as_posix()] = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    return found, ignored


def _read_unchanged(cache: Path, name: str, expected: tuple) -> bytes:
    path = cache / name
    # Check every parent too: a replaced directory must not turn into a link.
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise BundleError("linked cache entry")
    with path.open("rb") as handle:
        info = os.fstat(handle.fileno())
        observed = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if observed != expected:
            raise BundleError("cache changed; stop generation and retry")
        data = handle.read()
        info = os.fstat(handle.fileno())
        after = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if after != expected or len(data) != expected[2]:
            raise BundleError("cache changed; stop generation and retry")
    return data


def _png_text(kind: bytes, data: bytes) -> str:
    keyword, separator, rest = data.partition(b"\0")
    if not separator:
        raise BundleError("invalid PNG text")
    if kind == b"tEXt":
        return data.decode("latin-1")
    if kind == b"zTXt":
        if rest[:1] != b"\0":
            raise BundleError("unsupported PNG text compression")
        compressed, payload, prefix = True, rest[1:], keyword
    else:
        if rest[:2] not in {b"\0\0", b"\1\0"}:
            raise BundleError("unsupported PNG text compression")
        language, separator, remainder = rest[2:].partition(b"\0")
        translated, separator2, payload = remainder.partition(b"\0")
        if not separator or not separator2:
            raise BundleError("invalid international PNG text")
        compressed = rest[0] == 1
        prefix = keyword + b"\0" + language + b"\0" + translated
    if compressed:
        decoder = zlib.decompressobj()
        payload = decoder.decompress(payload, 2 * 1024 * 1024)
        if not decoder.eof or decoder.unused_data:
            raise BundleError("invalid or oversized PNG text")
    return (prefix + b"\0" + payload).decode("utf-8" if kind == b"iTXt" else "latin-1")


def _safe_bytes(name: str, data: bytes, secrets: tuple[str, ...]) -> bytes:
    if name.endswith(".png"):
        # Never re-encode pixels or alter metadata. Check textual metadata using
        # the same redactor; refuse sensitive/unknown chunks rather than silently
        # changing raw visual evidence or publishing unchecked private metadata.
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise BundleError("invalid PNG in diagnostic cache")
        offset = 8
        while offset + 12 <= len(data):
            size = int.from_bytes(data[offset:offset + 4], "big")
            kind = data[offset + 4:offset + 8]
            payload = data[offset + 8:offset + 8 + size]
            crc = data[offset + 8 + size:offset + 12 + size]
            if len(crc) != 4 or zlib.crc32(kind + payload) != int.from_bytes(crc, "big"):
                raise BundleError("invalid PNG chunk checksum")
            if kind in {b"tEXt", b"zTXt", b"iTXt"}:
                text = _png_text(kind, payload)
                if redact_credentials(text, secrets) != text:
                    raise BundleError("PNG contains credentials; review separately")
            elif kind not in {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"sRGB", b"cHRM", b"pHYs", b"sBIT", b"bKGD", b"hIST", b"tIME", b"acTL", b"fcTL", b"fdAT"}:
                raise BundleError("PNG contains unsupported private metadata; review separately")
            offset += size + 12
            if offset > len(data):
                raise BundleError("invalid PNG in diagnostic cache")
            if kind == b"IEND":
                if offset != len(data):
                    raise BundleError("PNG has trailing private data; review separately")
                return data
        raise BundleError("incomplete PNG in diagnostic cache")
    text = data.decode("utf-8")
    clean = redact_credentials(text, secrets)
    if clean != text and (name.endswith(".json") or ".ndjson" in name):
        original_rows = text.splitlines() if ".ndjson" in name else [text]
        clean_rows = clean.splitlines() if ".ndjson" in name else [clean]
        if len(original_rows) != len(clean_rows):
            raise BundleError("redaction changed structured record boundaries")
        for original, redacted in zip(original_rows, clean_rows):
            try:
                json.loads(original)
            except ValueError:
                continue  # A captured malformed response remains evidence, not repaired input.
            try:
                json.loads(redacted)
            except ValueError:
                raise BundleError("redaction would invalidate JSON; review separately") from None
    return clean.encode("utf-8")


def _add(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    entry = tarfile.TarInfo(name)
    entry.size = len(data)
    entry.mode = 0o600
    archive.addfile(entry, io.BytesIO(data))


def verify_bundle(path: Path) -> dict:
    """Verify every member without extracting files or following archive links."""
    with tarfile.open(path, "r:xz") as archive:
        seen = {}
        names = set()
        manifest = None
        for member in archive:
            if not member.isfile() or member.name in names:
                raise BundleError("duplicate or non-file archive member")
            names.add(member.name)
            if member.name != MANIFEST and (not member.name.startswith("cache/") or not _allowed(Path(member.name[6:]))):
                raise BundleError("unsupported archive member path")
            stream = archive.extractfile(member)
            if stream is None:
                raise BundleError("unreadable archive member")
            data = stream.read()
            if member.name == MANIFEST:
                manifest = json.loads(data)
            else:
                seen[member.name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if not isinstance(manifest, dict) or manifest.get("schema") != "infini.support-bundle.v1":
            raise BundleError("missing support manifest")
        entries = manifest["included"]
        expected = {entry["path"]: {key: entry[key] for key in ("bytes", "sha256")} for entry in entries}
        if len(expected) != len(entries) or seen != expected:
            raise BundleError("archive contents do not match the manifest")
        return manifest


def export_bundle(cache: Path, output: Path, *, include_images: bool = False) -> dict:
    if not cache.is_dir() or any(path.is_symlink() for path in (cache, *cache.parents)):
        raise BundleError("cache must be an existing unlinked directory")
    cache = cache.resolve()
    output = output.absolute()
    if output.resolve().is_relative_to(cache) or output.exists() or output.is_symlink():
        raise BundleError("output must be a new file outside the cache")
    inventory, ignored = _inventory(cache)
    if not inventory:
        raise BundleError("no supported diagnostic files found")
    secrets = env_credential_values()
    manifest = {
        "schema": "infini.support-bundle.v1", "mode": "full" if include_images else "core",
        "included": [], "omittedImageFiles": [], "ignoredFileCount": ignored,
        "notes": [
            "Source cache is unchanged. No record truncation, sampling or retention deletion.",
            "Core excludes image-diagnostics only; use full for original raw/master visual evidence.",
            "Known environment credentials and recognized credential patterns are redacted in text.",
            "Redacted copies are not original backups; sourceSha256 records identity, not recoverable secret values.",
            "Arbitrary personal text and local paths are not anonymized; review before sharing.",
            "Extract to a new empty directory for analysis, never over a live gameplay cache.",
        ],
    }
    fd, temporary_name = tempfile.mkstemp(prefix=".support-", suffix=".tar.xz", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream, tarfile.open(fileobj=stream, mode="w:xz", preset=6) as archive:
            for name, snapshot in sorted(inventory.items()):
                if redact_credentials(name, secrets) != name:
                    raise BundleError("cache filename contains credentials; review separately")
                raw = _read_unchanged(cache, name, snapshot)
                source_hash = hashlib.sha256(raw).hexdigest()
                if name.startswith("image-diagnostics/") and not include_images:
                    manifest["omittedImageFiles"].append({"path": "cache/" + name, "bytes": len(raw), "sha256": source_hash})
                    continue
                clean = _safe_bytes(name, raw, secrets)
                entry = {"path": "cache/" + name, "bytes": len(clean), "sha256": hashlib.sha256(clean).hexdigest(),
                         "sourceSha256": source_hash, "redacted": clean != raw}
                manifest["included"].append(entry)
                _add(archive, entry["path"], clean)
            if _inventory(cache)[0] != inventory:
                raise BundleError("cache changed; stop generation and retry")
            _add(archive, MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        verify_bundle(temporary)
        # Atomic, exclusive publication. An existing output is never overwritten.
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"mode": manifest["mode"], "files": len(manifest["included"]),
            "omittedImages": len(manifest["omittedImageFiles"]), "bytes": output.stat().st_size,
            "redactedFiles": sum(entry["redacted"] for entry in manifest["included"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, help="Stopped generator's cache directory")
    parser.add_argument("--out", type=Path, help="New .tar.xz file outside cache")
    parser.add_argument("--include-image-diagnostics", action="store_true", help="Include original private raw/master images")
    parser.add_argument("--verify", type=Path, help="Verify an existing bundle without extracting it")
    args = parser.parse_args()
    if args.verify:
        if args.cache or args.out or args.include_image_diagnostics:
            parser.error("--verify cannot be combined with export arguments")
        manifest = verify_bundle(args.verify)
        print(json.dumps({"verified": True, "mode": manifest["mode"], "files": len(manifest["included"])}))
    else:
        if not args.cache or not args.out:
            parser.error("export requires --cache and --out")
        print(json.dumps(export_bundle(args.cache, args.out, include_images=args.include_image_diagnostics)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BundleError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, zlib.error):
        # Do not echo arbitrary file contents, paths, or exception details.
        print("Export/verification failed. Use a stopped cache, supported PNG metadata and a new output on a filesystem supporting hard links.", file=sys.stderr)
        raise SystemExit(1)
