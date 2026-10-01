# InfiniCrafterLocal v0.4.246

InfiniCrafterLocal генерирует предмет Terraria из двух parent items. Gameplay Author за один LLM-вызов составляет bounded low-level `runtimeProgram`; Python проверяет и компилирует точные entities/components/events; C# tModLoader исполняет только typed v5 DTO.

## Архитектурный принцип

```text
parents
→ Gameplay Author: entities + inputs + capabilities + events
→ deterministic validation/technical compile
→ Visual Director: exact entity roles/assets
→ VFX Director: exact entity/event slots + explicit effect-image ingredients
→ image generation: accepted body/impact/VFX asset requests
→ strict world storage
→ C# bounded runtime
```

Код не выбирает weapon family и не выводит gameplay из name/tooltip/category/prose. Старые `AttackSpec`, `runtimeFamily`, whole-weapon macros, schema/cache migration и fallback удалены.

## Поставка 0.4.246

Обновляй **мод и LocalGenerator вместе**. В 0.4.246 один исполнитель владеет image-attempt lifecycle, промежуточные файлы изолированы, а все новые итоговые PNG публикуются атомарно под immutable именами. Validation/delivery/cache используют одну проекцию выбранного VFX PNG producer; неисполняемые ссылки отвергаются без изменения Visual или механики. Включены безопасное deferred освобождение текстур, retirement Item-эффектов при смерти и exact-leaf Repair пустого asset-domain.

Модели, личная конфигурация, cache и внешние `ParticleLibrary`/`Luminance` не входят в source-generator ZIP. Старые корректные recipes/PNG не мигрируют и не перерисовываются автоматически. VFX Director/условный Repair сохраняют лимит ответа 8000 по умолчанию и приоритет явной настройки. Native/контрактные проверки не заменяют Terraria/MP, live image campaign или художественную приёмку.

## Документы

- `docs/IMAGE_ASSET_LIFECYCLE_RU.md` — единый image executor, private output ownership, immutable publication, failure phases и общая VFX PNG dependency projection;

- `docs/VFX_MATERIAL_ELEMENTS_RU.md` — индивидуальные VFX-ассеты, spriteElement/texturedPath, механический read-only context; исправленные item-periodic budgets, nonowner lifecycle, ordered replay, unresolved Item forwarding, точная readiness, conflict-safe PNG byte authority, O(1) descriptor-reference lookup и backoff по selected canonical key;
- `AGENTS.md` — hard rules;
- `PROJECT_ARCHITECTURE_RU.md` / `PROJECT_MAP_RU.md` — архитектура и карта;
- `docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md` — generated inventory 52 capabilities;
- `lowery.md` — generated canonical Author/Repair/Lowery boundary, owner routing и finite mappings;
- `docs/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md` — граница official tModLoader mappings и custom runtime;
- `docs/CAPABILITY_LIBRARY_MACHINE_READABILITY_AUDIT_RU.md` — machine-readable quality audit;
- `docs/LOW_LEVEL_RUNTIME_AUTHORING_RU.md` — короткая projection канонического Author contract;
- `docs/THREE_STAGE_LLM_PIPELINE_RU.md` — baseline 3 calls;
- `TECHNICAL_LOWERING_AUDIT_RU.md` — lossless lowering proof.

## LLM и PNG через подписку ChatGPT / Codex

В GUI нажми **Sign in with ChatGPT**, выбери независимо `LLM provider = openai_codex` и/или `Image backend = openai_codex`, обнови каталог текстовых моделей, сохрани настройки и перезапусти LocalGenerator. OAuth-сессия принадлежит InfiniCrafter: Platform API key, Hermes и Codex CLI не требуются. Текстовый каталог не подтверждает доступность image-моделей; quality управляет image-запросом, а отдельный reasoning — только текстовым Visual Director. [Инструкция, расходы, ограничения и хранение сессии](docs/CODEX_IMAGE_OAUTH_RU.md).

## Portable validation

```bash
python tools/validate_sandbox.py
```

Полный Python QA:

```bash
PYTHONPATH=LocalGenerator pytest -q
```

C# build требует .NET 8, stable tModLoader SDK и реальные `ParticleLibrary.dll`/`Luminance.dll`.
