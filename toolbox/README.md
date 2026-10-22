# Toolbox: QA для пользователя и агента

Один вход из корня репозитория, без установки пакета:

```bash
python -m toolbox --help
python -m toolbox doctor
python -m toolbox live10
python -m toolbox live20
```

**`live10` / `live20` без `--run` — только read-only preflight:** выбор родителей из
fixture, проверка аргументов, явных ожиданий конфигурации и Git identity. Нет
LLM/image-запросов, импорта runtime, создания cache/PNG/каталога результатов.
Успешный preflight не означает доступность провайдера или качество генерации.
Нужны обычный Python проекта и его зависимости; toolbox ничего не устанавливает.

## Найти нужную утилиту

| Задача | Команда | Что действительно проверяет |
|---|---|---|
| Подготовить короткую / полную панель | `python -m toolbox live10` / `live20` | 10 / 20 конкретных комбинаций, наличие родителей, входные ограничения |
| Узнать prerequisites | `python -m toolbox doctor` | Пути, доступность Python-модулей/команд, native-команда из manifest; без чтения credentials |
| Разобрать сохранённую кампанию | `python -m toolbox summary /path/to/campaign` | Results + logical/HTTP/retry/image ledgers, пропуски, дубликаты и незавершённые запросы |
| Проверить сохранённый предмет | `python -m toolbox replay /path/to/case --compare` | Настоящие strict wire / delivery projection и сравнение `compiled_runtime.json`; без inference |
| Проверить затронутый код | `python -m toolbox verify --path LocalGenerator/infini_local/pipelines/llm_transport.py` | Делегирует существующему `tools/agentctl.py verify`, сохраняет аргументы и exit code |
| Показать owner-проверки без запуска | `python -m toolbox verify --area csharp --plan` | Только план; это не PASS и не native execution |

`replay` читает `final_item.json` в каталоге case; `--compare` дополнительно требует
`compiled_runtime.json` канонического replay owner. Флаги `save` / `--rerun` здесь
не предоставлены. Команда выполняется в отдельном offline-процессе с запрещённой
сетью, временным cache и без operator config; игровые saves не затрагиваются.

`summary` пересчитывает учёт из исходных NDJSON, **не доверяя старому `summary.json`**.
Отсутствующий ledger — unknown (`null` для соответствующего счётчика), а не ноль.
Exit 0 означает согласованный завершённый учёт, 1 — incomplete/failed, 2 — неверный
вход. Это не повторная semantic/art/game приёмка. Raw provider traces остаются
приватными: не прикладывайте их автоматически к PR.

## Где лежит код

```text
toolbox/
  __main__.py, cli.py      публичные команды
  infini_toolbox.py        discovery выбранного проекта
  live/                   одна реализация Live10 и Live20
    panels.py             явные панели и загрузка родителей
    preflight.py          read-only admission/config/source checks
    runner.py             настоящий producer + accounting + no-image boundary
    support.py            stages, concurrency, retry accounting
    summary.py            offline сверка сохранённых ledgers
    README.md             настройки и явный live-запуск
  fixtures/items.jsonl     неизменённый Terraria snapshot (39 родителей)
  testing/                adapters к существующим verify/replay owners, doctor
  tests/                  offline CLI, transport, pipeline и accounting tests
  live-generation/        только безопасный shim старой команды Live20
```

**Происхождение панелей:** Live20 сохраняет первые 20 комбинаций существовавшего
tracked harness. Live10 — новый **явно выбранный тематический subset** этой панели,
не восстановленная историческая кампания и не заявление о её результатах.
Точные IDs и родители видны в JSON preflight и [panels.py](live/panels.py).

## Реальные текстовые вызовы — отдельно

[Live10/Live20: конфигурация и запуск](live/README.md) описывает `--config`, обязательные
`--expected-*`, clean HEAD, отдельный output и явный **`--run`**. Поддерживается
HTTP-accounted `openai_compat` (Chat Completions / Responses), не OAuth/native adapters.
Ни модель, ни endpoint, ни reasoning effort не назначаются toolbox как «актуальный» preset.

Image backend всегда запрещён. Детерминированный QA PNG — **synthetic execution
control, не настоящее изображение**: он только позволяет пройти приватную копию
readiness-проверки. Production readiness остаётся строгой, authored механика и VFX
не подменяются. Нет game/GPU/MP приёмки.

Native не имеет второго build framework: doctor показывает текущую регистрацию
`.agent/manifest.json`; выполнение — существующий `verify --area csharp` с .NET,
tML/FNA references и external dependencies. Одной сборки недостаточно для заявления
об исполнении. Результат при отсутствии среды — notRun/unavailable, а не PASS.
См. [правила тестирования](../docs/development/TESTING_RU.md).

## Проверить сам toolbox offline

```bash
python -m pytest -q toolbox/tests LocalGenerator/tests/test_live20_no_image_harness.py
```

Тесты запрещают сеть. Cold-process тесты проходят настоящий request builder →
campaign hooks → Chat/Responses transport → JSON parser; подменён только внешний
HTTP sender. Полный runner проверяется на synthetic успешном трёхстадийном ответе
и отказе sender, включая реальные no-image/readiness gates. Это **не live inference**.
Canonical pytest shard runner уже включает `toolbox/tests`; новая регистрация не нужна.
