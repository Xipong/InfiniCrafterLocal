# infini_local

Активный Python-пакет LocalGenerator. [Карта кода](../../PROJECT_MAP_RU.md) показывает entrypoints; [архитектура](../../PROJECT_ARCHITECTURE_RU.md) — ownership и поток данных.

- [core](core/FOLDER_DOCS_RU.md): контракты, registry/compiler, VFX и config.
- [pipelines](pipelines/FOLDER_DOCS_RU.md): Author → Visual → VFX → images.
- [services](services/FOLDER_DOCS_RU.md), [web](web/FOLDER_DOCS_RU.md): внешние границы и HTTP.
- [storage](storage/FOLDER_DOCS_RU.md): world recipes/traces; [desktop](desktop/FOLDER_DOCS_RU.md): GUI.
- [qa](qa/FOLDER_DOCS_RU.md): только offline witnesses/proofs.

Gameplay выбирает Author, не prose/name/category routing.
