# infini_local/web

HTTP server/routes/debug UI.

- `server.py` executable HTTP composition root and route wiring; not a test/tool import barrel.
- `server_handler.py` `BaseHTTPRequestHandler` class factory and strict object-JSON/error response loop.
- `http_response_helpers.py` low-level HTTP/client-disconnect and combine-failure response shaping.
- `server_trace_snapshot.py` debug trace snapshot payload/html shaping.
- `server_utility_routes.py` utility routes, including containment-checked sprite serving.
- `vfx_debug_routes.py`, `trace_dashboard.py` debug/inspection surfaces.

Routes are boundary code: keep request validation, failure messages, and asset serving honest. Do not claim gameplay implementation from dashboard/debug-only data.
Tests and tools import pipeline/service/config owners directly. Do not recreate `server_services.py`, `api.py`, wildcard imports or launcher module substitution.
