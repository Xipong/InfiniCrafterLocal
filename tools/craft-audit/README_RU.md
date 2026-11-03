# Офлайн-аудит сохранённого крафта

Для `stage_requests`, builder captures и provider HTTP bodies предназначен [просмотрщик запросов](../diagnostics/PROMPT_AUDIT_RU.md). Эта утилита читает сам сохранённый предмет или полный Author JSON; запрос модели не подменяет исполняемые данные.

Из корня репозитория, Python 3.10+:

```sh
python tools/craft-audit/audit.py --item /path/to/item.json --out artifacts/my-craft-audit
```

Откройте `artifacts/my-craft-audit/audit.html` в браузере. Он автономный: без
сервера, JavaScript, сетевых запросов и загрузки картинок. Рядом лежит полный
машиночитаемый `audit.json`. Каталог `--out` должен быть новым. Утилита не меняет
предметы, runtime, промпты, настройки и кэш; не вызывает LLM или image API.
Зависимости — стандартная библиотека Python и существующие локальные модули
репозитория. Устанавливать пакеты для самого отчёта не нужно.

Если сохранились исходники, передайте их явно:

```sh
python tools/craft-audit/audit.py --item /path/to/item.json \
  --author-source /path/to/author.json \
  --visual-source /path/to/visual.json --vfx-source /path/to/vfx.json \
  --evidence /path/to/native-report.json --out artifacts/my-craft-audit-with-source
```

`--item` также принимает полный Author JSON вместо исполняемого wire. В этом
случае wire-проверка будет `notRun`: компиляция и исполнение не объявляются
наблюдавшимися. `--evidence` повторяется для нескольких внешних JSON-отчётов;
их содержание и SHA256 сохраняются отдельно от проверок, выполненных сейчас.
Они не получают доверие к происхождению или принадлежности этому предмету.

Отчёт разделяет:

- `concept` / `realization`: авторский замысел и advisory-пояснения;
- bindings, entities, calls, события, effect groups и фактический wire;
- Visual / VFX исходники и сохранённые визуальные настройки;
- результаты текущих статических валидаторов и предоставленные результаты;
- поля без документации, неизвестные поля и полный исходный JSON.

Названия, единицы, вложенные параметры, descriptions и defaults читаются из
`contracts/schemas/runtime_program_author.schema.json` и остальных канонических
схем. Поддерживаемого вручную словаря capabilities или правил в утилите нет.
Для wire используются текущие `ParamSpec.projection_paths`,
`wire_projection_card` и канонический `_parameter_outputs` из registry/lowering.
Это read-only introspection существующего владельца, не отдельный lowerer.
Неоднозначные схемные варианты не выбираются по сходству: значения остаются
видимыми с отметкой отсутствия однозначного описания. `$ref` разрешаются только
внутри локального документа. Экспортированные Visual/VFX схемы содержат ID
репозиторного примера; они используются для документации, а не для проверки
допустимости ID другого предмета.

Присутствующие значения и отсутствующие defaults показаны раздельно. Default
не дописывается в JSON, и отсутствующий optional-объект не создаётся ради его
вложенных defaults. Массивы, повторения и неизвестные поля сохраняются целиком.
Повторяющиеся идентификаторы делают связи неоднозначными, а не исчезают при
дедупликации. Дубли ключей JSON и нечисловые/бесконечные JSON-числа отклоняются,
поскольку их обычное чтение могло бы потерять данные.

## Author и wire — разные значения

Если receipts сохранены в `runtimeContract.finalWireReceipts`, они показываются
как `saved`. Текущий `audit_compiler_receipts` проверяет их относительно
фактического wire и переданного Author, если он есть. Провал проверки оставляет
receipts видимыми с `unverified`.

Delivery sanitizer удаляет `runtimeContract`. Если передан Author, утилита
пересчитывает receipts каноническим компилятором **только в памяти**, затем
проверяет их относительно исходного Author и переданного сохранённого wire.
Отчёт отмечает `recomputed_from_supplied_author`; это статическое сравнение, не
запуск runtime. Несовпадение wire не исправляется.

Без Author точные исходные значения не восстанавливаются даже при наличии
receipts: проверяется только согласованность wire. Если нет и receipts, поля
wire всё равно получают доступные описания из канонических projections;
неоднозначные соответствия показываются как кандидаты. Исходные числа не
вычисляются обратным преобразованием. Единицы Author подписаны отдельно от
wire, для которого доступно исходное правило перевода из registry. Нет
предположений о DPS, частоте попаданий или гарантированном уроне.

## Воспроизводимый образец Lunar Harpoon

Уже существующий builder создаёт JSON через канонические owners, без API и
запуска игры. Аргумент `--player-assets` только записывается в подготовленный
scenario; для этого статического аудита достаточно явно указать ещё не
настроенный каталог. Это не подтверждает наличие игровых ассетов.

```sh
python tools/item-test-workbench/examples/lunar-harpoon/build.py \
  --player-assets artifacts/unconfigured-player-assets --out artifacts/lunar-audit-input
python tools/craft-audit/audit.py --item artifacts/lunar-audit-input/item.json \
  --author-source tools/item-test-workbench/examples/lunar-harpoon/author-source.json \
  --visual-source tools/item-test-workbench/examples/lunar-harpoon/visual-author-source.json \
  --vfx-source tools/item-test-workbench/examples/lunar-harpoon/vfx-author-source.json \
  --out artifacts/lunar-audit
```

В отчёте отдельно видны `durationSeconds=0.5` (время до полного заряда),
`autoReleaseAfterActiveSeconds=1` (возраст автоматического выпуска),
`releaseEffect.damageMultiplier=2` (множитель при полном заряде, интерполяция от
1), вместе с исходными путями и каноническими descriptions. В переданном wire
первые два значения — `durationTicks=30` и `autoReleaseAfterActiveTicks=60`.
Образец assistant-authored; он не является найденным пользовательским крафтом
или новой генерацией модели.

## Проверки и пределы

```sh
python -m pytest -q toolbox/tests/test_craft_audit.py
python tools/agentctl.py verify --changed --base origin/main
```

Тесты проверяют реальные результаты на вложенных `releaseEffect` и `$ref`
motion windows, отсутствие Author и receipts, пересчёт после delivery,
несовпадение source/wire, неизвестные поля и capabilities, defaults без
мутации, актуальность схемных описаний, неоднозначные ID, события, внешние
результаты без повышения доверия, HTML escaping и отказ перезаписи.

Код возврата `0` означает, что отчёт создан и текущие запущенные статические
проверки не нашли ошибки; `1` — отчёт создан, но есть `failed`; `2` — ошибка
входа/записи. Статусы `notRun` остаются в отчёте и не считаются PASS.
SHA256 входных файлов и схем позволяют установить, какие байты читались.
HTML и JSON не удостоверяют происхождение произвольного внешнего отчёта.

Утилита не исполняет Terraria/tModLoader, не проверяет сетевую игру, PNG,
визуальное качество, игровой баланс или свежую генерацию. Порядок calls в
таблице — порядок сохранённых данных, не временная шкала исполнения. Ошибка
схемы не препятствует сохранению доступных данных в диагностическом отчёте.
