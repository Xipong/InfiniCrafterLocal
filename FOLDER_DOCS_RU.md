# Репозиторий v0.4.239 — что здесь важно

Активная Terraria/tModLoader часть: `ModSources/InfiniCrafterLocal`.

Навигация:
- `PROJECT_ARCHITECTURE_RU.md` — полная архитектура модовой части.
- `PROJECT_MAP_RU.md` — карта директорий и source-of-truth файлов.
- `README_RU.md` — краткое описание runtime flow.
- `BUILD_QOL_RU.md` — сборка, runtime dependencies, MP asset caveats.
- `TODO_ROADMAP_VERY_LATER_RU.md` — единый будущий backlog в корне версии.
- `docs/` — дополнительные канонические материалы:
  - `docs/RUNTIME_AUTHORING_CURRENT_RU.md` — текущий Python authoring/runtime contract;
  - `docs/CONTRACT_SAFETY_STACK_RU.md` — границы и проверочный стек;
  - `docs/PRE_LIVETEST_MANUAL_TRACES_V12_RU.md` — негативные author/image примеры;
  - `docs/ZIMAGE_WEAPON_TOPOLOGY_RU.md` — model-authored positive item topology без code-owned geometry;


Не считать архитектурой мода:
- `.tml-build-cache/`, `.nuget/`, `bin/`, `obj/`, `build_logs/`, `artifacts/`;
- `agent_reports/` — одноразовые отчёты и результаты экспериментов;
- `LocalGenerator/cache/` — runtime/test cache;
- `LocalGenerator/` — Python generator boundary, не C# runtime.
