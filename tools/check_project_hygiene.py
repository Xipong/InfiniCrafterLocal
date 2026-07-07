from __future__ import annotations

"""Repository hygiene guard for release archives.

This is intentionally static: it checks packaging/documentation invariants that are
easy to regress while refactoring architecture, without executing tModLoader.
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DOC_DIRS = {".git", "agent_reports", ".tml-build-cache", ".nuget", "build_logs", ".wiki_guided_playthrough_cache", "Runtime_dumps", "obj", "bin"}
RUNTIME_JUNK_NAMES = {"__pycache__", ".pytest_cache"}
PACKAGED_METADATA_DIRS = {".git"}
FORBIDDEN_RELEASE_FILE_NAMES = {"Zone.Identifier", ".DS_Store", "Thumbs.db"}
FORBIDDEN_RELEASE_SUFFIXES = (":Zone.Identifier",)
PYTHON_BROAD_EXCEPTION_BASELINE = 227
PYTHON_BARE_EXCEPT_BASELINE = 0


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    raise SystemExit(1)


def iter_project_dirs() -> list[Path]:
    dirs: list[Path] = []
    for p in ROOT.rglob("*"):
        if not p.is_dir():
            continue
        rel = p.relative_to(ROOT)
        if any(part in IGNORED_DOC_DIRS for part in rel.parts):
            continue
        if any(part in RUNTIME_JUNK_NAMES for part in rel.parts):
            continue
        if _is_forbidden_release_metadata(rel, p):
            continue
        if rel.parts[:2] == ("LocalGenerator", "cache"):
            continue
        dirs.append(p)
    return [ROOT] + dirs


def check_folder_docs() -> None:
    missing = [str(p.relative_to(ROOT) or ".") for p in iter_project_dirs() if not (p / "FOLDER_DOCS_RU.md").exists()]
    if missing:
        fail("folders without FOLDER_DOCS_RU.md: " + ", ".join(missing[:30]))


def _is_runtime_junk(rel: Path, p: Path) -> bool:
    if any(part in PACKAGED_METADATA_DIRS for part in rel.parts):
        return True
    if any(part == "cache" and rel.parts[:1] == ("LocalGenerator",) for part in rel.parts):
        return True
    return p.name in RUNTIME_JUNK_NAMES or p.suffix == ".pyc"


def _is_forbidden_release_metadata(rel: Path, p: Path) -> bool:
    name = p.name
    if name in FORBIDDEN_RELEASE_FILE_NAMES:
        return True
    if any(name.endswith(suffix) for suffix in FORBIDDEN_RELEASE_SUFFIXES):
        return True
    # On Windows downloaded archives often unpack to ADS metadata that tools may
    # expose as literal files named `anything:Zone.Identifier`.  Those files should
    # never enter release zips or folder-doc coverage.
    if any(part in FORBIDDEN_RELEASE_FILE_NAMES for part in rel.parts):
        return True
    return False


def check_no_packaged_runtime_junk(strict_archive: bool = False) -> None:
    """Check release junk without making local test runs fight the checker.

    Pytest/compileall legitimately create __pycache__, .pytest_cache and
    LocalGenerator/cache during local checks. Default mode ignores those
    auto-generated artifacts so `pytest && python tools/check_project_hygiene.py`
    stays green. Use `--strict-archive` before zipping a release if you want
    this script to fail on those files being physically present in the tree.

    Platform metadata such as Zone.Identifier, .DS_Store and Thumbs.db is
    also strict-archive-only in this workspace because imported Windows trees
    can contain many ADS marker files that are not source/runtime state.
    """
    metadata = []
    junk = []
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT)
        if strict_archive and _is_forbidden_release_metadata(rel, p):
            metadata.append(str(rel))
        elif strict_archive and _is_runtime_junk(rel, p):
            junk.append(str(rel))
    if metadata:
        fail("forbidden release metadata present: " + ", ".join(metadata[:30]))
    if junk:
        fail("runtime junk present in archive tree: " + ", ".join(junk[:30]))




def _count_python_exception_handlers(root: Path | None = None) -> dict[str, int]:
    """Return broad-exception counts for source hygiene checks.

    Broad `except Exception` is tolerated in the generator because many paths are
    diagnostic/recovery boundaries around LLM, image, filesystem and debug
    tooling.  The release guard does not pretend to fix that debt; it makes the
    current debt visible and prevents accidental growth.
    """
    source_root = root or (ROOT / "LocalGenerator" / "infini_local")
    broad = 0
    bare = 0
    for py in sorted(source_root.rglob("*.py")):
        text = py.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            stripped = line.strip()
            if re.match(r"^except\s+Exception\b", stripped):
                broad += 1
            if re.match(r"^except\s*:\s*(#.*)?$", stripped):
                bare += 1
    return {"broad_exception": broad, "bare_except": bare}


def check_python_exception_hygiene() -> None:
    stats = _count_python_exception_handlers()
    if stats["bare_except"] > PYTHON_BARE_EXCEPT_BASELINE:
        fail(f"bare except handlers increased: {stats['bare_except']} > {PYTHON_BARE_EXCEPT_BASELINE}")
    if stats["broad_exception"] > PYTHON_BROAD_EXCEPTION_BASELINE:
        fail(f"broad except Exception handlers increased: {stats['broad_exception']} > {PYTHON_BROAD_EXCEPTION_BASELINE}")

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _version_literal(path: str, pattern: str, label: str) -> str:
    match = re.search(pattern, read(path))
    if not match:
        fail(f"could not read {label} version from {path}")
    return match.group(1)


def check_version_sync() -> None:
    versions = {
        "LocalGenerator/server.py APP_VERSION": _version_literal("LocalGenerator/server.py", r'APP_VERSION = "([^"]+)"', "launcher APP_VERSION"),
        "config_bootstrap.py APP_VERSION": _version_literal("LocalGenerator/infini_local/core/config_bootstrap.py", r'APP_VERSION = "([^"]+)"', "bootstrap APP_VERSION"),
        "InfiniCrafterLocal.cs Version": _version_literal("ModSources/InfiniCrafterLocal/InfiniCrafterLocal.cs", r'Version = "([^"]+)"', "C# mod Version"),
        "build.txt version": _version_literal("ModSources/InfiniCrafterLocal/build.txt", r'version = ([^\s]+)', "tModLoader build.txt"),
    }
    web = read("LocalGenerator/infini_local/web/server.py")
    pipeline = read("LocalGenerator/infini_local/pipelines/pipeline_support.py")
    if "from infini_local.core.config_bootstrap import (" not in web:
        fail("web server does not import canonical config_bootstrap APP_VERSION")
    if "from infini_local.core.config_bootstrap import (" not in pipeline:
        fail("pipeline_support does not import canonical config_bootstrap APP_VERSION")
    if len(set(versions.values())) != 1:
        detail = "; ".join(f"{label}={value}" for label, value in versions.items())
        fail("version mismatch: " + detail)






def check_runtime_api_sync() -> None:
    py_runtime_api = _version_literal(
        "LocalGenerator/infini_local/core/runtime_authoring.py",
        r'ENGINE_RUNTIME_API_VERSION = "([^"]+)"',
        "Python engine runtime API",
    )
    cs_runtime_api = _version_literal(
        "ModSources/InfiniCrafterLocal/Common/InfiniRuntimeLimits.cs",
        r'RuntimeApiCurrent = "([^"]+)"',
        "C# runtime API",
    )
    if py_runtime_api != cs_runtime_api:
        fail(f"runtime API mismatch: Python ENGINE_RUNTIME_API_VERSION={py_runtime_api}; C# RuntimeApiCurrent={cs_runtime_api}")


def check_no_flat_helper_shims() -> None:
    flat_py = sorted(p.name for p in (ROOT / "LocalGenerator").glob("*.py"))
    allowed = ["server.py", "settings_gui.py"]
    if flat_py != allowed:
        fail("flat LocalGenerator helper shims still present: " + ", ".join(flat_py))


def check_release_docs_version() -> None:
    version = re.search(r'APP_VERSION = "([^"]+)"', read("LocalGenerator/server.py"))
    if not version:
        fail("could not read APP_VERSION for docs check")
    current = version.group(1)
    docs = [
        "README_RU.md",
        "PROJECT_ARCHITECTURE_RU.md",
        "PROJECT_MAP_RU.md",
        "QUICK_START_RU.md",
        "LocalGenerator/README_RU.md",
        "LocalGenerator/PROJECT_ARCHITECTURE_RU.md",
        "LocalGenerator/PROJECT_MAP_RU.md",
        "LocalGenerator/QUICK_START_RU.md",
        "ModSources/InfiniCrafterLocal/description.txt",
    ]
    stale = []
    for doc in docs:
        text = read(doc)
        head = "\n".join(text.splitlines()[:16])
        if current not in head:
            stale.append(doc)
    if stale:
        fail("release docs missing current version in header: " + ", ".join(stale))


def check_architecture_split_markers() -> None:
    server = read("LocalGenerator/infini_local/web/server.py")
    fallback = read("LocalGenerator/infini_local/core/dev_fallback.py")
    json_tools = read("LocalGenerator/infini_local/core/llm_json_tools.py")
    world_storage = read("LocalGenerator/infini_local/storage/world_storage.py")
    trace_tools = read("LocalGenerator/infini_local/storage/trace_tools.py")
    sdcpp_backend = read("LocalGenerator/infini_local/services/sdcpp_backend.py")
    asset_sync_service = read("LocalGenerator/infini_local/services/asset_sync_service.py")
    combine_endpoint = read("LocalGenerator/infini_local/services/combine_endpoint.py")
    runtime_dump_service = read("LocalGenerator/infini_local/services/runtime_dump_service.py")
    trace_dashboard = read("LocalGenerator/infini_local/web/trace_dashboard.py")
    visual_asset_pipeline = read("LocalGenerator/infini_local/services/visual_asset_pipeline.py")
    network_info_service = read("LocalGenerator/infini_local/services/network_info_service.py")
    if "def _base_spec" in server or "def accessory_plan" in server:
        fail("developer fallback builders leaked back into server.py")
    if "def _base_spec" not in fallback or "DEV" not in fallback.upper():
        fail("dev_fallback.py no longer owns its fallback builders/contract wording")
    if "def parse_first_valid_llm_json" not in json_tools:
        fail("llm_json_tools.py missing JSON parser")
    if 'payload.setdefault("recipeMeta", {})' in server or "def sanitize_recipe_for_delivery" not in world_storage:
        fail("world recipe storage/delivery logic leaked back into server.py or is missing from world_storage.py")
    if "target = prompt_trace_file" in server or "def tail_ndjson" not in trace_tools:
        fail("trace writer/tail logic leaked back into server.py or is missing from trace_tools.py")
    if "pipeline_preset_text_inside_template" in server or "def build_server_command" not in sdcpp_backend or "def server_payload" not in sdcpp_backend:
        fail("sd.cpp backend command/payload helpers leaked back into server.py or are missing from sdcpp_backend.py")
    if "world_recipes_dir.rglob" in server or "def safe_asset_file_from_query" not in asset_sync_service:
        fail("asset sync lookup helpers leaked back into server.py or are missing from asset_sync_service.py")
    if "threading.BoundedSemaphore" in server or "def handle_combine_request" not in combine_endpoint:
        fail("/combine endpoint concurrency logic leaked back into server.py or is missing from combine_endpoint.py")
    if "My Games" in server or "def runtime_dump_candidates" not in runtime_dump_service:
        fail("runtime dump discovery/index helpers leaked back into server.py or are missing from runtime_dump_service.py")
    if "body{font-family" in server or "def render_trace_snapshot_html" not in trace_dashboard:
        fail("trace dashboard HTML renderer leaked back into server.py or is missing from trace_dashboard.py")
    if "d.rounded_rectangle" in server or "def generate_procedural_sprite" not in visual_asset_pipeline:
        fail("procedural sprite fallback drawing leaked back into server.py or is missing from visual_asset_pipeline.py")
    if (
        "def zimage_pe_clean_text" in server
        or "def sanitize_image_prompt_background" in server
        or "def compact_zimage_asset_prompt" not in visual_asset_pipeline
        or "def zimage_text_policy_sentence" not in visual_asset_pipeline
    ):
        fail("visual/Z-Image prompt helpers leaked back into server.py or are missing from visual_asset_pipeline.py")
    if "socket.getaddrinfo" in server or "def multiplayer_connect_info" in server or "def multiplayer_connect_info" not in network_info_service:
        fail("Radmin/LAN multiplayer connect helpers leaked back into server.py or are missing from network_info_service.py")


def main() -> int:
    strict_archive = "--strict-archive" in sys.argv[1:]
    check_folder_docs()
    check_no_packaged_runtime_junk(strict_archive=strict_archive)
    check_version_sync()
    check_runtime_api_sync()
    check_python_exception_hygiene()
    check_no_flat_helper_shims()
    check_release_docs_version()
    check_architecture_split_markers()
    print("[OK] project hygiene checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
