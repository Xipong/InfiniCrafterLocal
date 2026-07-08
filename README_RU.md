# InfiniCrafterLocal v0.4.239 — Terraria/tModLoader мод

InfiniCrafterLocal добавляет InfiniCraft: ручную станцию, где два предмета превращаются в локально сгенерированный предмет. Модовая часть находится в `ModSources/InfiniCrafterLocal` и отвечает за UI, транзакцию крафта, применение generated runtime contract, multiplayer authority, asset sync, runtime sprites, projectiles, VFX/audio.

## Архитектурный принцип

```text
Python/LLM authoring validates and emits GeneratedItemData + VfxManifest
C# tModLoader runtime applies explicit fields and safety clamps
```

C# не должен угадывать gameplay из имени/tooltip/prompt/prose. Если механика должна работать в Terraria, она должна быть скомпилирована в явные поля: `Gameplay`, `Attack`, `Accessory`, `Armor`, `VfxManifest`, sprite paths, sound profiles.

## Основные документы

- `AGENTS.md` — короткие hard rules для любых ИИ/агентов перед изменениями.
- `PROJECT_ARCHITECTURE_RU.md` — полная текущая архитектура Terraria/tModLoader части и boundary matrix.
- `PROJECT_MAP_RU.md` — карта папок, source-of-truth файлов и ловушек.
- `LocalGenerator/PROJECT_ARCHITECTURE_RU.md` — Python generator/authoring/runtime contract boundary.
- `docs/runtime_archetype_contract.md` — v0.4.239 typed runtime archetype/contract schema, promise-truth validator, migration notes.
- `BUILD_QOL_RU.md` — сборка/QoL/MP asset notes.
- `QUICK_START_RU.md` — минимальный запуск.
- `ModSources/InfiniCrafterLocal/FOLDER_DOCS_RU.md` — карта активного мода.

## Runtime flow

1. Игрок крафтит/держит `InfiniCore`.
2. В inventory появляется station panel с двумя явными слотами A/B.
3. В singleplayer/host мод вызывает `LocalGenerator` через HTTP `/combine`.
4. В multiplayer клиент отправляет только craft intent; host/server берёт реальные ингредиенты и генерирует сам.
5. Host/server коммитит `GeneratedItemData` в world-scoped registry.
6. PNG/JSON assets синкаются через HTTP `/get_asset`, а Terraria packets несут только ids/filenames/compact visual state.
7. `GeneratedItem` / `GeneratedProjectile` исполняют только явные runtime fields.

MP asset sync note: Steam не проксирует HTTP. Для LAN/Radmin/hosted MP host должен рекламировать base URL, который клиенты реально открывают; клиенту не нужно руками открывать `/get_asset`, мод сам тянет final assets через `/get_asset`.

## Важное для агентов

Если нужно менять/понимать модовую архитектуру — начинай с C# файлов в `ModSources/InfiniCrafterLocal`, а не с устаревших кратких md-заглушек. Не трогай build/cache директории как архитектуру.
