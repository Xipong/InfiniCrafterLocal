# Репозиторий v0.4.239 — что здесь важно

Активная Terraria/tModLoader часть: `ModSources/InfiniCrafterLocal`.

Навигация:
- `PROJECT_ARCHITECTURE_RU.md` — полная архитектура модовой части.
- `PROJECT_MAP_RU.md` — карта директорий и source-of-truth файлов.
- `README_RU.md` — краткое описание runtime flow.
- `BUILD_QOL_RU.md` — сборка, runtime dependencies, MP asset caveats.
- `docs/` — дополнительные balance/runtime/TODO материалы, часть из них относится к Python authoring.
- `CHATGPT_CHANGES_20260710_RU.md` — sound catalog v8 patch.
- `CHATGPT_CHANGES_20260710_V9_RU.md` — gameplay authoring/runtime v9: exact channel beam, dead-field/dataflow fixes, provenance and classifier cleanup.
- `CHATGPT_CHANGES_20260710_V10_RU.md` — maintainable runtime vertical slices, on_expire и balance modes.
- `CHATGPT_CHANGES_20260710_V11_RU.md` — generic overhead_barrage, Daedalus/Starfury carrier separation и theme preservation.

Не считать архитектурой мода:
- `.tml-build-cache/`, `.nuget/`, `build_logs/`;
- `agent_reports/` — исторические отчёты;
- `LocalGenerator/` — Python generator boundary, не C# runtime.

- `CHATGPT_CHANGES_20260710_V12_RU.md` — pre-livetest author/image patch and verification.
- `docs/PRE_LIVETEST_MANUAL_TRACES_V12_RU.md` — ten manual traces before live LLM/Image Gen testing.

- `docs/ZIMAGE_WEAPON_TOPOLOGY_RU.md` — simple visual-only topology guard against duplicate weapon handles/guards/stocks without a VL judge.

- `CHATGPT_CHANGES_20260710_V15_RU.md` — charge-release и true bounded sentry vertical slices; lifecycle details in `docs/CHARGE_RELEASE_SENTRY_RUNTIME_RU.md`.
- `CHATGPT_CHANGES_20260711_V16_RU.md` — восстановление критичной семантики compact planner prompt: pierce, use timing, ammo, family-only knobs, explicit zero и sentry budget.
