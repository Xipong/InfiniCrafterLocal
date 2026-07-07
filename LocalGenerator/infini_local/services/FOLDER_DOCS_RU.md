# infini_local/services

Service helpers for endpoints/assets/visual/runtime integration.

- `combine_endpoint.py` wraps `/combine` request/response behavior.
- `asset_sync_service.py` selects safe final asset filenames and `/get_asset` query behavior.
- `visual_asset_pipeline.py`, `sdcpp_service.py`, `sdcpp_backend.py` visual/backend services.
- `runtime_dump_service.py`, `network_info_service.py` diagnostics/support.

Do not expose raw generation intermediates as MP assets; C# expects final `.png/.json` filenames only.
