# LocalGenerator v0.4.239 — project map

Python generator side for InfiniCrafterLocal. Read this together with `../AGENTS.md`, `../PROJECT_MAP_RU.md`, and `PROJECT_ARCHITECTURE_RU.md`.

```text
LocalGenerator/
  infini_local/
    core/        contracts, env, runtime compiler, balance, VFX/effect catalogs
    pipelines/   combine/authoring/visual/final-normalize orchestration
    services/    endpoint helpers, asset sync, SD.cpp/visual/runtime dump services
    storage/     world recipe storage, traces, failure states
    web/         HTTP server/routes/dashboard/debug endpoints
    desktop/     settings GUI
  tests/          contract/regression tests
  tools/          diagnostics/replay/research helpers
  data/           compact reference/seed JSON; not a huge DB authority by itself
  docs/           supplemental docs/TODO/reference; verify against source
```

Do not use old folder docs or agent reports as proof. The active source files are listed in `PROJECT_ARCHITECTURE_RU.md`.

Boundary summary:
- Python authors/validates/repairs explicit data.
- `runtimePlan.engineCalls` remains the executable source.
- `runtimeArchetype` and `runtimeContract` are optional v0.4.239 data contracts for family/feel/promise truth; unsupported mechanics are preserved inertly.
- C# applies/executes supported fields only, including exact sound catalog ids and synced pitch variance; it never selects built-in audio from prose.
- Asset sync exposes final filenames for HTTP `/get_asset`.
- Contract stamps are provenance, not proof of implemented future behavior.

## Agent guardrails

- Source of truth: live files under `infini_local/` and tests under `tests/`.
- No prose gameplay: names/prompts/tooltips/debug strings do not become mechanics unless compiled into explicit fields.
- MP is server-authoritative on the C# side; LocalGenerator returns data to the host/server path.
- World-scoped storage/cache must not leak generated parents across worlds.
- If you change X, also check Y: Python compiler/validator, C# DTO/runtime, tests, docs.
- No second model-judge claim unless implemented in source.
- `dict[str, Any]` / dicts / dictionaries remain an architecture risk; keep provenance and field names explicit.

## Output contract reminder

LocalGenerator's important output is explicit `GeneratedItemData` plus `VfxManifest`/final asset filenames. The C# mod does not execute raw LLM prose.
