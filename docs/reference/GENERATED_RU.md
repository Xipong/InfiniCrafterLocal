# Автоматически собранные справочники

Папка `generated/` содержит полные таблицы из исходного кода. Здесь проверяют точные имена, параметры, единицы и соответствие C#; с неё не начинают установку или изучение архитектуры.

| Нужно проверить | Справочник | Генератор |
|---|---|---|
| Границы авторства модели и технических преобразований | [Lowery](generated/LOWERY_RU.md) | `tools/generate_lowery.py` |
| Полный набор возможностей и параметров | [Каталог](generated/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) | `tools/generate_low_level_runtime_docs.py` |
| Проверку полноты и доступности каталога модели | [Аудит каталога](generated/CAPABILITY_LIBRARY_MACHINE_READABILITY_AUDIT_RU.md) | тот же |
| Точный перевод авторского описания в исполняемый формат | [Аудит lowering](generated/TECHNICAL_LOWERING_AUDIT_RU.md) | тот же |
| Соответствие возможностей Terraria/tModLoader | [Parity](generated/PRIMITIVE_PARITY_RU.md) | `tools/generate_primitive_parity.py` |

## Обновление

Не редактируй сгенерированные таблицы вручную. Измени соответствующий исходник и выполни нужный генератор из корня проекта:

```bash
python tools/validate_release.py --refresh runtime
```

Команда вызывает существующие schema, bounds, parity, Lowery, inventory и audit producers, затем обновляет офлайн-книгу. Для настроек — `--refresh config`; только для документации — `--refresh docs`. Сами producers по-прежнему доступны отдельно для точечной работы. Проверка всех производных артефактов без записи: `python tools/validate_release.py --group static`.

## Источники

- [capability_registry.py](../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py) — операции, параметры, единицы и ограничения.
- [program_schema.py](../../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py) — формат ответа модели.
- [technical_lowering.py](../../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py) — точные преобразования и записи об их происхождении.
- [author_item_contract.py](../../LocalGenerator/infini_local/pipelines/author_item_contract.py) — инструкции модели.

Проверка актуальности подтверждает совпадение таблиц с кодом, а не выполнение механики в игре. Статические и игровые проверки описаны в [руководстве по тестированию](../development/TESTING_RU.md).
