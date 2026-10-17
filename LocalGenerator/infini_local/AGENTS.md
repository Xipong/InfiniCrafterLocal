# Python: начинай с владельца задачи

Общие правила области задачи — в корневом [AGENTS](../../AGENTS.md). Gameplay vertical slice относится к новой runtime capability, не к любому изменению Python или Studio. Не читай все соседние файлы по очереди; выбери entrypoint и следуй реальным вызовам.

- Craft/cache/commit: `pipelines/combine_pipeline.py::combine`.
- Strict Author → compile → wire → единственный conditional Repair: `pipelines/gameplay_stage.py::compile_and_validate_authored_runtime`. Здесь stage lifecycle; canonical validation/compiler остаются в `core/runtime_authoring/`.
- Author/Repair request: `pipelines/llm_authoring_pipeline.py`; shape/cards — `author_item_contract.py`, prose packet — `llm_authoring_prompt.py` в той же папке.
- Visual: `pipelines/visual_generation_pipeline.py`; VFX request: `pipelines/vfx_generation_pipeline.py`, VFX contract/Repair: `core/vfx_manifest.py`.
- Чтение уже принятого wire для presentation: `core/runtime_authoring/wire_views.py`. Не вызывай compiler для чтения сохранённой вещи.
- Runtime факты/shape/lowering: импортируй прямо defining module. `runtime_authoring/__init__.py` не реэкспортирует API и не запускает другие owners. Общий JSON helper не должен требовать импорта другой LLM-стадии.
- Image attempts/delivery: `pipelines/visual_sprite_generation.py` / `visual_delivery_gate.py`; world recipe persistence: `storage/world_storage.py`.
- Browser Studio: `desktop/webui/{index.html,studio.css,studio.js}` — представление; `desktop/web_studio.py` — HTTP bridge; `desktop/settings_controller.py` и `desktop/studio_operations.py` — состояние и запуск генератора.

[Карта задач и проверок](../../docs/development/CODE_MAP_RU.md#fast-start) · [границы модулей](../../docs/development/MODULES_RU.md) · [tests](../../docs/development/TESTING_RU.md).
