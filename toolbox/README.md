# Toolbox: QA для пользователя и агента

Один вход из корня репозитория, без установки пакета:

```bash
python -m toolbox --help
python -m toolbox panels
python -m toolbox doctor
python -m toolbox live10
python -m toolbox live20
python -m toolbox workbench --help
python -m toolbox workbench doctor
```

**`live10` / `live20` без `--run` — только read-only preflight:** выбор родителей из
fixture, проверка аргументов, явных ожиданий конфигурации и Git identity. Нет
LLM/image-запросов, импорта runtime, создания cache/PNG/каталога результатов.
Успешный preflight не означает доступность провайдера или качество генерации.
Нужны обычный Python проекта и его зависимости; toolbox ничего не устанавливает.

## Найти нужную утилиту

| Задача | Команда | Что действительно проверяет |
|---|---|---|
| Исторический midgame / классический Live20 | `python -m toolbox live10` / `live20` | Исходные 10 / 20 комбинаций с их собственными parent inputs |
| Собственная панель, в том числе 40 случаев | `python -m toolbox live20 --cases-file /path/to/cases.json --runtime-dump /path/to/parents.jsonl --expected-case-count 40` | Явно предоставленные оператором пары и parent inputs; [формат и границы](fixtures/README.md#частная-панель-из-40-случаев) |
| Найти все пакеты запросов | `python -m toolbox panels` | Пары ингредиентов, provenance, число cases и пути к исходным fixtures |
| Узнать prerequisites | `python -m toolbox doctor` | Пути, доступность Python-модулей/команд, native-команда из manifest; без чтения credentials |
| Разобрать сохранённую кампанию | `python -m toolbox summary /path/to/campaign` | Results + logical/HTTP/retry/image ledgers, пропуски, дубликаты и незавершённые запросы |
| Проверить сохранённый предмет | `python -m toolbox replay /path/to/case --compare` | Настоящие strict wire / delivery projection и сравнение `compiled_runtime.json`; без inference |
| Исполнить предмет и посмотреть записанный цикл | `python -m toolbox workbench --help` | [Native Item Test Workbench](../tools/item-test-workbench/README.md): настоящий C# runtime, телеметрия и поддерживаемые native render passes; без LLM |
| Проверить затронутый код | `python -m toolbox verify --path LocalGenerator/infini_local/pipelines/transport/client.py` | Делегирует существующему `tools/agentctl.py verify`, сохраняет аргументы и exit code |
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

## Стенд предметов рядом с Live10

`workbench` — тонкий вход в существующий `tools/item-test-workbench/workbench.py`,
не второй движок. Аргументы, код возврата и рабочий каталог вызывающего процесса
сохраняются; относительные пути не переносятся в корень checkout.

```bash
python -m toolbox workbench doctor
python -m toolbox workbench run --item /path/item.json --scenario /path/scenario.json --out /path/new-run
python -m toolbox workbench native-review /path/new-run/native.json --out /path/new-review --gif
```

`workbench --help` и `workbench doctor` только читают: не собирают C#, не запускают
игру/модель и не создают результаты. `doctor` возвращает 2 при отсутствии зависимостей,
а не успешное native-тестирование. `build` и `run` запускаются явно, без Live10-флага
`--run`; команды экспорта записывают указанный output. Зависимости, границы исполнения,
сценарии и реальный пример Lunar Harpoon описаны в [руководстве стенда](../tools/item-test-workbench/README.md).

## Где лежит код

```text
toolbox/
  __main__.py, cli.py      публичные команды
  infini_toolbox.py        discovery выбранного проекта
  live/                   одна реализация исторических и custom panels
    catalog.py            каталог JSON-пакетов и defaults
    panels.py             загрузка выбранных пар и их собственных родителей
    preflight.py          read-only admission/config/source checks
    runner.py             настоящий producer + accounting + no-image boundary
    support.py            stages, concurrency, retry accounting
    summary.py            offline сверка сохранённых ledgers
    README.md             настройки и явный live-запуск
  fixtures/
    panels/               исходные пары Live10 midgame / Live20 / sprite-вариант
    parents/              исторические snapshots встроенных пакетов
    items.jsonl           неизменённые 39 родителей классического Live20
    *_provenance.json      SHA256 и источники входов
  testing/                adapters к существующим verify/replay owners, doctor
  tests/                  offline CLI, transport, pipeline и accounting tests
  live-generation/        только безопасный shim старой команды Live20
```

**Исторические входы восстановлены:** `live10` — прежние 10 midgame-кейсов,
а не сокращение Live20; `live20` — прежние 20 пар, преимущественно pre-Hardmode,
но с early-Hardmode sentry. Сохранены порядок, ориентация A/B и точные исходные
parent rows, включая различия контекста общего `QueenSpiderStaff`.
Оригинальный вариант Live20 со sprite references доступен через
`live20 --preset live20-classic-sprites`. Новый subset из PR141 сохранён только
как явно отдельный `live10 --preset live10-starter`, не исторический midgame.
Все пары, файлы и происхождение — в [каталоге входов](fixtures/README.md).

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
