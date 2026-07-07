# LocalGenerator

Python authoring/validation side. It receives `/combine` requests from the C# mod, builds validated `GeneratedItemData`/`VfxManifest` plus final asset filenames, and serves assets/debug routes. Read `PROJECT_ARCHITECTURE_RU.md` before editing.

Subdirs: `infini_local/` active package, `tests/` contracts/regressions, `tools/` diagnostics, `data/` compact references, `docs/` supplemental notes.
