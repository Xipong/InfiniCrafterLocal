"""Generator process entrypoint; endpoint owners live beside this module."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import os

from infini_local.core.config_bootstrap import APP_VERSION, CACHE_DIR, WORLD_RECIPES_DIR
from infini_local.core.env_utils import env_str
from infini_local.core.server_endpoint import resolve_server_endpoint
from infini_local.core.image_dependencies import Image, PILLOW_IMPORT_ERROR
from infini_local.core.images import config as visual_config
from infini_local.core.llm_config import ALLOW_DETERMINISTIC_DEV_FALLBACK, USE_LLM
from infini_local.pipelines.transport.client import resolve_llm_model
from infini_local.pipelines.transport.profiles import active_llm_provider
from infini_local.services.sdcpp_service import SDCPP_SERVER_STATE, install_cleanup_handlers
from infini_local.storage.trace_runtime import CONSOLE_EVENT_LEVELS, TRACE_PROMPTS_ENABLED, initialize_trace_storage, log_event
from infini_local.web.server_handler import Handler


def main() -> None:
    endpoint = resolve_server_endpoint(os.environ)
    # Autostart happens in ThreadingHTTPServer workers, where Python forbids
    # signal registration. Install the process-tree cleanup on the main thread
    # before any request can launch sd.cpp.
    initialize_trace_storage()
    install_cleanup_handlers(SDCPP_SERVER_STATE, log_event)
    if visual_config.REQUIRE_PILLOW and Image is None and env_str("INFINI_IMAGE_BACKEND", visual_config.IMAGE_BACKEND).lower() != "off":
        raise SystemExit("Pillow is required for InfiniCrafterLocal visual generation/postprocess. Run OPEN_INFINICRAFT.bat setup. Import error: " + PILLOW_IMPORT_ERROR)
    host, port = endpoint.bind_host, endpoint.port
    print(f"InfiniCrafterLocal v{APP_VERSION} listening on http://{host}:{port}")
    print(f"LLM={USE_LLM} provider={active_llm_provider()} model={resolve_llm_model() if USE_LLM else '<off>'} deterministicDevFallback={ALLOW_DETERMINISTIC_DEV_FALLBACK} imageBackend={visual_config.IMAGE_BACKEND} worldRecipes={WORLD_RECIPES_DIR}")
    if visual_config.IMAGE_BACKEND in {"sdcpp", "stablediffusioncpp", "stable-diffusion.cpp", "stable_diffusion_cpp"}:
        print(f"stable-diffusion.cpp server={visual_config.SDCPP_SERVER_URL} autostart={visual_config.SDCPP_SERVER_AUTOSTART} exe={visual_config.SDCPP_SERVER_EXE or '<external>'} model={visual_config.SDCPP_MODEL or '<external>'} steps={visual_config.SDCPP_STEPS} cfg={visual_config.SDCPP_CFG} size={visual_config.SDCPP_WIDTH}x{visual_config.SDCPP_HEIGHT}")
    if USE_LLM:
        print("Tip: set INFINI_LLM_PROVIDER=openrouter + INFINI_OPENROUTER_API_KEY + INFINI_OPENROUTER_MODEL to use OpenRouter instead of LM Studio.")
    if not TRACE_PROMPTS_ENABLED:
        print("Full logging: OFF; optional diagnostics disabled, concise fatal errors only.")
    elif CONSOLE_EVENT_LEVELS:
        print(f"Console events: {'/'.join(CONSOLE_EVENT_LEVELS)} mirrored here; full record in {CACHE_DIR / 'events.ndjson'} (INFINI_CONSOLE_EVENT_LEVEL=off to silence)")
    else:
        print(f"Console events: off; craft diagnostics only in {CACHE_DIR / 'events.ndjson'} (INFINI_CONSOLE_EVENT_LEVEL=warn to show them here)")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
