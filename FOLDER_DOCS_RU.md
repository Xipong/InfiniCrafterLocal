# Репозиторий v0.4.234 — что здесь важно

Активная Terraria/tModLoader часть: `ModSources/InfiniCrafterLocal`.

Навигация:
- `PROJECT_ARCHITECTURE_RU.md` — полная архитектура модовой части.
- `PROJECT_MAP_RU.md` — карта директорий и source-of-truth файлов.
- `README_RU.md` — краткое описание runtime flow.
- `BUILD_QOL_RU.md` — сборка, runtime dependencies, MP asset caveats.
- `docs/` — дополнительные balance/runtime/TODO материалы, часть из них относится к Python authoring.

Не считать архитектурой мода:
- `.tml-build-cache/`, `.nuget/`, `build_logs/`;
- `agent_reports/` — исторические отчёты;
- `LocalGenerator/` — Python generator boundary, не C# runtime.
