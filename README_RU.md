# InfiniCrafterLocal v0.4.241

InfiniCrafterLocal генерирует предмет Terraria из двух parent items. Gameplay Author за один LLM-вызов составляет bounded low-level `runtimeProgram`; Python проверяет и компилирует точные entities/components/events; C# tModLoader исполняет только typed v5 DTO.

## Архитектурный принцип

```text
parents
→ Gameplay Author: entities + inputs + capabilities + events
→ deterministic validation/technical compile
→ Visual Director: exact entity roles/assets
→ VFX Director: exact entity/event slots
→ strict world storage
→ C# bounded runtime
```

Код не выбирает weapon family и не выводит gameplay из name/tooltip/category/prose. Старые `AttackSpec`, `runtimeFamily`, whole-weapon macros, schema/cache migration и fallback удалены.

## Документы

- `AGENTS.md` — hard rules;
- `PROJECT_ARCHITECTURE_RU.md` / `PROJECT_MAP_RU.md` — архитектура и карта;
- `docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md` — generated inventory 52 capabilities;
- `lowery.md` — generated canonical Author/Repair/Lowery boundary, owner routing и finite mappings;
- `docs/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md` — граница official tModLoader mappings и custom runtime;
- `docs/CAPABILITY_LIBRARY_MACHINE_READABILITY_AUDIT_RU.md` — machine-readable quality audit;
- `docs/LOW_LEVEL_RUNTIME_AUTHORING_RU.md` — короткая projection канонического Author contract;
- `docs/THREE_STAGE_LLM_PIPELINE_RU.md` — baseline 3 calls;
- `TECHNICAL_LOWERING_AUDIT_RU.md` — lossless lowering proof.

## PNG через подписку ChatGPT / Codex

В GUI выбери `Image backend = openai_codex`, нажми **Sign in with ChatGPT**, сохрани настройки и перезапусти LocalGenerator. Это отдельный OAuth backend: Platform API key, Hermes и Codex CLI не требуются. Настройки LLM не меняются. [Инструкция, хранение сессии и границы проверки](docs/CODEX_IMAGE_OAUTH_RU.md).

## Portable validation

```bash
python tools/validate_sandbox.py
```

Полный Python QA:

```bash
PYTHONPATH=LocalGenerator pytest -q
```

C# build требует .NET 8, stable tModLoader SDK и реальные `ParticleLibrary.dll`/`Luminance.dll`.
