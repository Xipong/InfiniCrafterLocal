# Три поддерживаемые панели

- `live10` / [live10-midgame](panels/live10-midgame.json): девять прежних midgame-пар и Nebula Blaze + Last Prism вместо Star Cannon + Meteor Staff. Это обновлённый набор, не неизменный исторический cohort. Последняя пара расширяет покрытие условных атак и channelled beams вместо второго дорогого rain-крафта.
- `live20` / [live20-classic](panels/live20-classic.json): исходные 20 пар, преимущественно ранний прогресс, включая early-Hardmode sentry. [39 родителей](items.jsonl) и [provenance](classic_provenance.json) сохранены побайтно.
- `live40` / [live40-diverse](panels/live40-diverse.json): новый разнообразный набор аудита 2026-11-06. Все 40 пар, порядок и ориентация A/B сохранены; `sourceCase` связывает нормализованный CLI ID с исходным ID аудита. Это не прежняя галерея 40 GIF.

## Входы и запуск

Для генерационного preflight обновлённого Live10 и нового Live40 обязателен актуальный внешний JSONL родителей:

```bash
python -m toolbox panels
python -m toolbox live10 --runtime-dump /path/to/current-parents.jsonl
python -m toolbox live20
python -m toolbox live40 --runtime-dump /path/to/current-parents.jsonl --expected-case-count 40
```

Дамп должен содержать все выбранные `internalName`. Отсутствующий родитель — ошибка, без синтетической подстановки или смешивания snapshots. Частные игровые packets, исходники, конфиги и ответы моделей не публикуются вместе с панелями. Указание внешнего файла не доказывает его свежесть: оператор отвечает за экспорт с нужной версии, preflight фиксирует hash входа.

`coverageIntent` и `inventory` в Live40 описывают исходный аудит. Они не исполняют сценарий, не меняют инвентарь генератора и не обещают игровую приёмку.

Команды выше выполняют только read-only preflight. Для генерации см. [явный запуск](../live/README.md). Custom-пары по-прежнему можно передать через `--cases-file` вместе с `--runtime-dump`; формат — список `{ "case", "itemA", "itemB" }` либо объект `cases`. `--cases` выбирает подмножество по CLI ID, не меняя исходный порядок.

Для отдельного детерминированного снятия raw Prepare по новому Live40 используйте
[`live40 --offline`](../README.md#детерминированный-native-capture40): входы создаёт
уже собранный native harness, внешний JSONL и provider configuration не нужны.
Это не генерационный запуск и не independent Author audit.
