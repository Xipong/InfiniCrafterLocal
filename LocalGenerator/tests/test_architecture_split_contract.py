from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LG = ROOT / "LocalGenerator"
PKG = LG / "infini_local"


def read(rel: str) -> str:
    return (LG / rel).read_text(encoding="utf-8")


def _check_root_entrypoints_are_the_only_flat_launchers() -> None:
    server = read("server.py")
    gui = read("settings_gui.py")
    assert "infini_local/web/server.py" in server
    assert "infini_local.desktop.settings_gui" in gui
    assert "sys.modules[__name__] = _impl" in server
    assert 'APP_VERSION = "0.4.239"' in server
    flat_py = sorted(p.name for p in LG.glob("*.py"))
    assert flat_py == ["server.py", "settings_gui.py"]


def _check_local_generator_python_code_is_sorted_into_texture_layers() -> None:
    assert (PKG / "core" / "runtime_authoring" / "__init__.py").exists()
    assert (PKG / "core" / "vfx_manifest.py").exists()
    assert (PKG / "services" / "sdcpp_backend.py").exists()
    assert (PKG / "services" / "asset_sync_service.py").exists()
    assert (PKG / "services" / "network_info_service.py").exists()
    assert (PKG / "services" / "visual_asset_pipeline.py").exists()
    assert (PKG / "web" / "vfx_debug_routes.py").exists()
    assert (PKG / "web" / "server_utility_routes.py").exists()
    assert (PKG / "pipelines" / "combine_pipeline.py").exists()
    assert (PKG / "pipelines" / "llm_authoring_pipeline.py").exists()
    assert (PKG / "pipelines" / "parent_context_pipeline.py").exists()
    assert (PKG / "pipelines" / "visual_generation_pipeline.py").exists()
    assert (PKG / "pipelines" / "image_backend_pipeline.py").exists()
    assert (PKG / "pipelines" / "sprite_processing_pipeline.py").exists()
    assert (PKG / "storage" / "world_storage.py").exists()
    assert (PKG / "web" / "server.py").exists()
    assert (PKG / "desktop" / "settings_gui.py").exists()




def _check_network_info_is_outside_http_server() -> None:
    server_impl = read("infini_local/web/server.py")
    network = read("infini_local/services/network_info_service.py")
    services = read("infini_local/web/server_services.py")
    assert "network_info_service" in services
    assert "def multiplayer_connect_info" not in server_impl
    assert "def multiplayer_connect_info" in network
    assert "def radmin_ipv4_candidates" in network
    assert "socket.getaddrinfo" not in server_impl
    assert "socket.getaddrinfo" in network


def _check_dev_fallback_builders_are_outside_http_server() -> None:
    server_impl = read("infini_local/web/server.py")
    fallback = read("infini_local/core/dev_fallback.py")
    assert "def _base_spec" not in server_impl
    assert "def accessory_plan" not in server_impl
    assert "def _base_spec" in fallback
    assert "INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK" in fallback


def _check_llm_json_extraction_is_in_core_and_imported_by_server() -> None:
    server_impl = read("infini_local/web/server.py")
    json_tools = read("infini_local/core/llm_json_tools.py")
    services = read("infini_local/web/server_services.py")
    assert "infini_local.core.llm_json_tools" in services
    assert "def json_object_candidates" not in server_impl
    assert "def parse_first_valid_llm_json" in json_tools


def _check_sdcpp_backend_and_lifecycle_are_in_services() -> None:
    server_impl = read("infini_local/web/server.py")
    backend = read("infini_local/services/sdcpp_backend.py")
    service = read("infini_local/services/sdcpp_service.py")
    services = read("infini_local/web/server_services.py")
    assert "sdcpp_backend" in services
    assert "sdcpp_service" in services
    assert "def repair_command_template" in backend
    assert "def build_server_command" in backend
    assert "def server_payload" in backend
    assert "def ensure_server" in service
    assert "pipeline_preset_text_inside_template" not in server_impl
    assert "def repair_command_template" not in server_impl
    assert "subprocess.Popen" not in server_impl
    assert "subprocess.Popen" in service




def _check_visual_asset_pipeline_helpers_are_outside_server_monolith() -> None:
    server_impl = read("infini_local/web/server.py")
    visual_assets = read("infini_local/services/visual_asset_pipeline.py")
    services = read("infini_local/web/server_services.py")
    assert "infini_local.services.visual_asset_pipeline" in services
    assert "visual_asset_pipeline" in services
    assert "def sanitize_image_prompt_background" not in server_impl
    assert "def zimage_pe_clean_text" not in server_impl
    assert "def compact_zimage_asset_prompt" not in server_impl
    assert "def strip_conflicting_sprite_prompt_bits" not in server_impl
    assert "def generate_procedural_asset" not in server_impl
    assert "def generate_procedural_sprite" not in server_impl
    assert "def sanitize_image_prompt_background" in visual_assets
    assert "def zimage_pe_clean_text" in visual_assets
    assert "def compact_zimage_asset_prompt" in visual_assets
    assert "def strip_conflicting_sprite_prompt_bits" in visual_assets
    assert "def generate_procedural_asset" in visual_assets
    assert "d.rounded_rectangle" in visual_assets
    assert "without letters, logos, or UI marks" in visual_assets


def _check_recipe_identity_helpers_are_in_core() -> None:
    server_impl = read("infini_local/web/server.py")
    identity = read("infini_local/core/item_identity_tools.py")
    world_runtime = read("infini_local/storage/world_recipe_runtime.py")
    services = read("infini_local/web/server_services.py")
    assert "infini_local.core.item_identity_tools" in services
    assert "infini_local.storage.world_recipe_runtime" in services
    assert "def recipe_key" not in server_impl
    assert "def recipe_key" in identity
    assert "def recipe_key" in world_runtime
    assert "def item_identity" not in server_impl
    assert "def item_identity" in identity
    assert "def item_num" not in server_impl
    assert "def item_num" in identity


def _check_asset_sync_and_combine_endpoint_are_in_services() -> None:
    server_impl = read("infini_local/web/server.py")
    asset_sync = read("infini_local/services/asset_sync_service.py")
    endpoint = read("infini_local/services/combine_endpoint.py")
    services = read("infini_local/web/server_services.py")
    assert "asset_sync_service" in services
    assert "combine_endpoint" in services
    assert "def runtime_asset_files" not in server_impl
    assert "def runtime_asset_files" in asset_sync
    assert "def safe_asset_file_from_query" in asset_sync
    assert "world_recipes_dir.rglob" not in server_impl
    assert "world_recipes_dir.rglob" in asset_sync
    handler = read("infini_local/web/server_handler.py")
    assert "handle_combine_request" in handler
    assert "def handle_combine_request" in endpoint
    assert "threading.BoundedSemaphore" not in server_impl
    assert "threading.BoundedSemaphore" in endpoint
    assert "cache_lookup_passthrough_errors=(world_scope_missing,)" in handler



def _check_combine_endpoint_uses_distinct_http_statuses_for_cache_busy_and_failures() -> None:
    endpoint = read("infini_local/services/combine_endpoint.py")
    server_impl = read("infini_local/web/server.py")
    services = read("infini_local/web/server_services.py")
    response_helpers = read("infini_local/web/http_response_helpers.py")
    assert '"status": "cache_miss"' in endpoint
    assert 'json_status(404' in endpoint
    assert '"cacheRecoveryAllowed": True' in endpoint
    assert '"status": "generator_busy"' in endpoint
    assert 'json_status(409' in endpoint
    assert "from infini_local.web.server_services import (" in server_impl
    assert "infini_local.web.http_response_helpers" in services
    assert "def _combine_failure_http_response" in response_helpers
    assert 'return 422, "llm_output_invalid"' in response_helpers
    assert 'return 424, "visual_dependency_failed"' in response_helpers
    assert "VisualDeliveryBlocked" in server_impl
    assert '"cacheRecoveryAllowed": False' in response_helpers

def _check_runtime_dump_trace_dashboard_and_sprite_fallback_are_outside_server() -> None:
    server_impl = read("infini_local/web/server.py")
    runtime_dump = read("infini_local/services/runtime_dump_service.py")
    dashboard = read("infini_local/web/trace_dashboard.py")
    trace_snapshot_payload = read("infini_local/web/server_trace_snapshot.py")
    visual_assets = read("infini_local/services/visual_asset_pipeline.py")
    services = read("infini_local/web/server_services.py")
    assert "runtime_dump_service" in services
    assert "trace_dashboard" in services
    assert "infini_local.web.server_trace_snapshot" in services
    assert "visual_asset_pipeline" in services
    assert "def runtime_item_lookup" in server_impl
    assert "def runtime_dump_candidates" not in server_impl
    assert "def runtime_dump_candidates" in runtime_dump
    assert "def load_jsonl_index" in runtime_dump
    assert "My Games" not in server_impl
    assert "My Games" in runtime_dump
    assert "def trace_snapshot_html" in server_impl
    assert "def build_trace_snapshot" in trace_snapshot_payload
    assert "def render_trace_snapshot_html" in trace_snapshot_payload
    assert "def render_trace_snapshot_html" in dashboard
    assert "body{font-family" not in server_impl
    assert "body{font-family" in dashboard
    assert "def generate_procedural_sprite" not in server_impl
    assert "def generate_procedural_sprite" in visual_assets
    assert "d.rounded_rectangle" not in server_impl
    assert "d.rounded_rectangle" in visual_assets



def _check_http_utility_routes_are_a_coarse_route_block() -> None:
    server_impl = read("infini_local/web/server.py")
    routes = read("infini_local/web/server_utility_routes.py")
    handler = read("infini_local/web/server_handler.py")
    services = read("infini_local/web/server_services.py")
    assert "from infini_local.web.server_handler import build_handler" in server_impl
    assert "infini_local.web.server_utility_routes" in services
    assert "class ServerUtilityRoutes" in routes
    assert "def handle_get" in routes
    assert "def generate_test_sprite" in routes
    assert "def debug_recipes" in routes
    assert "def get_asset" in routes
    assert "Handler = build_handler" in server_impl
    assert "def do_GET" in handler
    assert "if utility_routes().handle_get(self, self.path):" in handler
    assert "def do_GET" not in routes
    assert "def generate_test_sprite" not in server_impl
    assert "world_recipes_dir.iterdir" not in server_impl
    assert "world_recipes_dir.iterdir" in routes

def _check_vfx_debug_routes_are_one_coarse_endpoint_block() -> None:
    server_impl = read("infini_local/web/server.py")
    routes = read("infini_local/web/vfx_debug_routes.py")
    services = read("infini_local/web/server_services.py")
    assert "infini_local.web.vfx_debug_routes" in services
    assert "def debug_select_vfx_manifest" not in server_impl
    assert "def debug_vfx_lint" not in server_impl
    assert "class VfxDebugRoutes" in routes
    assert "def handle_get" in routes
    assert "def handle_post" in routes
    assert "def select_manifest" in routes
    assert "def composer" in routes
    assert "def lint" in routes


def _check_large_generation_pipelines_are_outside_server_shell() -> None:
    server_impl = read("infini_local/web/server.py")
    combine = read("infini_local/pipelines/combine_pipeline.py")
    llm = read("infini_local/pipelines/llm_authoring_pipeline.py")
    parent = read("infini_local/pipelines/parent_context_pipeline.py")
    parent_cards = read("infini_local/pipelines/parent_context_cards.py")
    visual = read("infini_local/pipelines/visual_generation_pipeline.py")
    image_backend = read("infini_local/pipelines/image_backend_pipeline.py")
    sprite = read("infini_local/pipelines/sprite_processing_pipeline.py")
    sprite_postprocess = read("infini_local/pipelines/sprite_postprocess.py")
    services = read("infini_local/web/server_services.py")
    assert "from infini_local.web.server_services import (" in server_impl
    assert "infini_local.pipelines.combine_pipeline" in services
    assert "def combine(" not in server_impl
    assert "def try_llm_plan" not in server_impl
    assert "def raw_parent_card_for_llm" not in server_impl
    assert "def apply_visual_director" not in server_impl
    assert "def generate_sdcpp_server" not in server_impl
    assert "def postprocess_sprite" not in server_impl
    assert "def combine(" in combine
    assert "def try_llm_plan" in llm
    assert "def raw_parent_card_for_llm" in parent_cards
    assert "parent_context_cards" in parent
    assert "def apply_visual_director" in visual
    assert "def generate_sdcpp_server" in image_backend
    assert "def postprocess_sprite" in sprite_postprocess
    assert "sprite_postprocess" in sprite
    assert "bind_runtime" not in server_impl
    assert "_PipelineMirroringServerModule" not in server_impl
    assert "from infini_local.pipelines.combine_balance import (" in combine

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_root_entrypoints_are_the_only_flat_launchers',
    '_check_local_generator_python_code_is_sorted_into_texture_layers',
    '_check_network_info_is_outside_http_server',
    '_check_dev_fallback_builders_are_outside_http_server',
    '_check_llm_json_extraction_is_in_core_and_imported_by_server',
    '_check_sdcpp_backend_and_lifecycle_are_in_services',
    '_check_visual_asset_pipeline_helpers_are_outside_server_monolith',
    '_check_recipe_identity_helpers_are_in_core',
    '_check_asset_sync_and_combine_endpoint_are_in_services',
    '_check_combine_endpoint_uses_distinct_http_statuses_for_cache_busy_and_failures',
    '_check_runtime_dump_trace_dashboard_and_sprite_fallback_are_outside_server',
    '_check_http_utility_routes_are_a_coarse_route_block',
    '_check_vfx_debug_routes_are_one_coarse_endpoint_block',
    '_check_large_generation_pipelines_are_outside_server_shell'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_architecture_split_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)



def test_postprocess_sprite_contract_returns_path_not_optional():
    sprite = (ROOT / "LocalGenerator" / "infini_local" / "pipelines" / "sprite_postprocess.py").read_text(encoding="utf-8")
    sprite_api = (ROOT / "LocalGenerator" / "infini_local" / "pipelines" / "sprite_processing_pipeline.py").read_text(encoding="utf-8")
    visual = (ROOT / "LocalGenerator" / "infini_local" / "pipelines" / "visual_generation_pipeline.py").read_text(encoding="utf-8")
    assert "def postprocess_sprite(path: str, sprite_id: str, target_size: int = 32, role: str = \"unknown\") -> str:" in sprite
    assert "on postprocess failure, return the original path" in sprite
    assert "postprocess_sprite" in sprite_api
    assert "-> str | None" not in sprite
    assert "postprocess_sprite(best, attempt_id, canvas, \"item\") or best" not in visual
    assert "postprocess_sprite(fallback, str(data.get(\"id\", \"sprite\")), canvas, \"item\") or fallback" not in visual
    assert "postprocess_sprite(best, attempt_id, canvas, role) or best" not in visual
    assert "postprocess_sprite(fallback, asset_id, canvas, role) or fallback" not in visual
