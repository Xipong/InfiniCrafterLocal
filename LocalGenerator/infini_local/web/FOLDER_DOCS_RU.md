# infini_local/web

HTTP server/routes/debug UI.

- `server.py` executable HTTP entrypoint and route wiring.
- `server_services.py` named service/pipeline dependencies used by the HTTP entrypoint.
- `api.py` canonical Python API for diagnostics, tests and tooling that need generator services without starting the server.
- `server_handler.py` `BaseHTTPRequestHandler` class factory and JSON/error response loop.
- `http_response_helpers.py` low-level HTTP/client-disconnect and combine-failure response shaping.
- `server_trace_snapshot.py` debug trace snapshot payload/html shaping.
- `server_utility_routes.py` utility routes.
- `vfx_debug_routes.py`, `trace_dashboard.py` debug/inspection surfaces.

Routes are boundary code: keep request validation, failure messages, and asset serving honest. Do not claim gameplay implementation from dashboard/debug-only data.
