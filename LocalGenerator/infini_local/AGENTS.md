# Python: начинай с владельца задачи

Общие правила области задачи — в корневом [AGENTS](../../AGENTS.md). Gameplay vertical slice относится к новой runtime capability, не к любому изменению Python или Studio. Не читай все соседние файлы по очереди; выбери entrypoint и следуй реальным вызовам.

- Craft/cache/commit: `pipelines/combine_pipeline.py::combine`.
- Strict Author → compile → wire → единственный conditional Repair: `pipelines/author/stage.py::compile_and_validate_authored_runtime`. Здесь stage lifecycle; canonical validation/compiler остаются в `core/runtime_authoring/`.
- Author/Repair request: `pipelines/author/request.py`; shape/cards — `pipelines/author/item_contract.py`, prose packet — `pipelines/author/prompt.py`.
- Visual: `pipelines/visual/stage.py`; VFX request: `pipelines/vfx/request.py`, VFX grammar/validation/Repair: `core/vfx/{schema,validation,repair}.py`.
- Чтение уже принятого wire для presentation: `core/runtime_authoring/wire_views.py`. Не вызывай compiler для чтения сохранённой вещи.
- Runtime факты/shape/lowering: импортируй прямо defining module. `runtime_authoring/__init__.py` не реэкспортирует API и не запускает другие owners. Общий JSON helper не должен требовать импорта другой LLM-стадии. Lossless provider projection и nullable inverse — `core/provider_schema.py`; `core/vfx/` и `core/images/` не импортируют orchestration из `pipelines/`.
- LLM HTTP/deadline/retry: `pipelines/transport/client.py`; profiles/leases — `pipelines/transport/profiles.py`, quota/admission — `pipelines/transport/admission.py`, provider payload/cache shape — `pipelines/transport/provider_wire.py`. Импортируй defining owner; scalar settings принадлежат `core/llm_config.py`.
- Image attempts/delivery: `pipelines/images/stage.py` / `pipelines/visual/delivery.py`; world recipe persistence: `storage/world_storage.py`.
- Browser Studio: `desktop/webui/{index.html,studio.css,studio.js}` — представление; `desktop/web_studio.py` — HTTP bridge; `desktop/settings_controller.py` и `desktop/studio_operations.py` — состояние и запуск генератора.

[Карта задач и проверок](../../docs/development/CODE_MAP_RU.md#fast-start) · [границы модулей](../../docs/development/MODULES_RU.md) · [tests](../../docs/development/TESTING_RU.md).

## Промптинг современных моделей

Эти ориентиры действуют для всех model-facing инструкций в Python-пакете: system/user messages, Repair, image prompts, schema descriptions, registry cards и общих suffix. Расположение в `core/` не исключает такой текст из области правил. Этот AGENTS — инструкция контрибьютору, не часть запроса генерации предмета.

### Общий подход

Опирайся на возможности современных сильных моделей, а не на шаблоны сопровождения моделей 2024 года. Общая линия руководств ниже: ясно передать цель, замысел, нужный контекст и признаки хорошего результата — и оставить модели пространство самостоятельно найти решение. Объясняй, что важно и почему, вместо подробного управления каждым шагом.

Пересматривай накопленные инструкции по мере роста возможностей моделей: повторения, превентивные запреты и старые обходные приёмы могут уже мешать. Цель — лучшее решение, а не просто короткий промпт. В IFC особенно полезен контекст, который модель не может знать заранее: доступные механики, их реальное исполнение и смысл данных.

### Руководства и практика

Проверены 2026-10-29; это актуальные ориентиры на 2026 Q4.

- **OpenAI, 2026-10-02:** [A model guide for the GPT-6 family](https://openai.com/index/practical-guide-building-gpt-6/) — постановка задачи, контекст, результат и границы самостоятельной работы.
- **OpenAI, 2026-09-11:** [Rethinking skills and prompts for GPT-6 Astra](https://learn.chatgpt.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra) — пересмотр накопленных skills, AGENTS.md и избыточного сопровождения.
- **Anthropic:** [Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) — руководство для актуальных Claude и ссылки на особенности отдельных моделей.
- **Anthropic:** [Prompting Claude Opus 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5) — обновление промптов с учётом выросших возможностей модели.
- **Poteto / pstack:** [Практическое руководство](https://github.com/cursor/plugins/blob/main/pstack/docs/guide/README.md), [пост 2026-10-16](https://x.com/poteto/status/2111133080526495985), [пост 2026-10-24](https://x.com/poteto/status/2114099131845423142) — постановка целей вместо микроменеджмента и упрощение агентной обвязки по мере роста возможностей моделей.
