# infini_local/web

HTTP server/routes/debug UI.

- `server.py` main server and route wiring.
- `server_utility_routes.py` utility routes.
- `vfx_debug_routes.py`, `trace_dashboard.py` debug/inspection surfaces.

Routes are boundary code: keep request validation, failure messages, and asset serving honest. Do not claim gameplay implementation from dashboard/debug-only data.
