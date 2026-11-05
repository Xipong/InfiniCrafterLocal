# Эксперименты с анализом родителей

Это исследовательская ветка `experiment/parent-analysis-20261105`, не предложение слить все идеи в main. Пользователь попросил отделить патроны и текущие эксперименты от speed-only PR #330. Нового PR и merge не выполнялось.

## Рабочая основа и история

- Исходный main: `9e21dff12d89a148f2fc14f776c433b56b680846`.
- `a6fdcb6aa8c2d00343ef8ade23533557a72ffd2a` сохраняет точный старый PR330 head `b12908dc06dc88da4baa6203f99a6cebd5e9e2a5` вторым родителем. Его первый родитель и дерево равны main. Это явное сохранение истории, не скрытая интеграция.
- `66ecc94e2bd28d4f3e7d47ee4ba7f7c190be85da` возвращает реально работающий эксперимент отделения ammo, восстановленные canonical replacement profiles и внешний projectile guard. В него сохранена уже проверенная интеграция с main, включая Atlas/workbench, объединённый registry и handbook.
- Все 1436 файлов этого integration tree `bf83845e5db505b290fc7bf79c1bf4e67f74210c` сверены по Git blob SHA с проверенной копией. Историческая проверка этого точного дерева: 9156 Python PASS / 30 SKIP, 670 native PASS, 17 static gates PASS, 34 workbench Python PASS. Direct Roslyn не является MSBuild/.tmod build. Это не новые CI-прогоны опубликованной ветки.

После `66ecc94` runtime-код намеренно не меняется. Остальные направления сохранены отдельными осмысленными коммитами ниже `experiments/parent-analysis/`, как исходники, review patches, проверки и ограничения. Для каждого patch есть manifest исходных и конечных SHA256. Патч не применяется автоматически при сборке.

## Что сохранено и что действительно работает

### 1. Ammo и восстановление профилей

`ammo/`: отчёты и проверки **активного кода ветки**. Оружие не выбирает inventory/fallback ammo examples; настоящий ammo-parent сохраняет собственные facts; собственные source-proven replacement outputs сохраняют полные profiles. Условия и unknown не заменены догадками. Скоростные изменения первоначального PR также остаются в этой экспериментальной основе.

### 2. CFG извлечение native ammo

`cfg/native-ammo-control-flow.patch`: самостоятельный кандидат поверх `66ecc94`. Все 10 исходных файлов совпали по base SHA256, `git apply --check` прошёл. Это bounded CFG/local-definition proof, без item-ID router. Исторические проверки кандидата: 107 Python, 52 actual shot cases и 3 profile checks. Меняются две source rows, для 4953 и 3859.

Он **не включён в runtime дерева ветки**: совместный full acceptance с нынешним main не повторялся. После применения нужен handbook refresh и проверки интегрированного дерева. Код, regression tests, generated catalog и diff результатов сохранены целиком в patch.

### 3. Child helper и copy-on-write

`helper/helper-spawns.patch` сохраняет доказанные helper spawn sites, canonical child632 и все условные/unknown ветви. Кандидат извлечения проверен, но default Author **RED: 325379 > 300000 знаков**. Рост cold allocations также является блокером. Это не production-ready feature.

`helper/copy-on-write-after-helper.patch` применим после helper patch и включает independent deep-copy oracle. 669 native checks прошли в прежнем exact candidate; 13 packet hashes совпали. `copy-on-write-standalone.patch` сохраняет отдельную идею без helper расширения. Это **альтернативы**, их нельзя складывать друг с другом. COW не доказывает полноту извлечения и не устраняет Author budget. Копирование HashSet заменено immutable state sharing с клонированием только изменённого join.

Применимость helper к рабочей основе и COW к helper повторно проверена через `git apply --check`. Это не повторный native или full repo acceptance.

### 4. Last Prism: причины потерь и отвергнутые упрощения

`diagnostics/effect-summary/`: generalized closed-call proof, 39 исторических standalone checks; integration patch применяется после helper. Настоящие source factory / Kill callback escapes остаются unknown. Packet остаётся тем же, budget не проходит. Нет оснований считать эти вызовы pure.

`diagnostics/prism-inline/`: source-only harness показывает окно style84, недостающие roots и sparse-local направление. Существующие 575 preservation assertions и 2376 sparse map comparisons не являются production patch или замером общего speedup.

`diagnostics/source-relevance/`: исходники и итог исследования. Доказуемое удаление лишних source facts равно нулю. Контрфактическое отключение hazards сохранено как диагностика, не оптимизация.

Здесь сохранены авторские harness sources, summaries и отчёты. Большие generated IL/CFG captures, внешние DLL, tML/Calamity binaries и локальная toolchain намеренно не включены. Для повторения native diagnostic capture нужны законно полученные pinned tML references и исходный harness setup; отчёты содержат hashes и границы. Не считать эти diagnostics самодостаточной игровой сборкой.

### 5. Представление для модели

`ifc-parent-graph-prototype-20261105/`: один graph/timeline, точный inverse; полный dossier всё ещё 325010 знаков, с прежними tables 319119. Размерный gate не пройден.

`ifc-source-listing-experiment-20261105/`: единый listing с reached-ветвями, inverse и independent ledger. На **старом неполном capture** 299402 знака, либо 295359 с tables. Запас 598 знаков не доказывает admission после восстановления missing Last Prism motion/effects. Model A/B не выполнялся.

`fixtures/` содержит точные JSON values всех 13 stage-card snapshots и request-only projection старого captured builder request. Whitespace компактизирован; неиспользуемые top-level audit/context/evidence поля не копируются. Каждое извлечение и original SHA описаны в `representations-provenance.json`. Это тестовые inputs, не изменение отправляемых production запросов и не обещание provider acceptance.

Проверить оба representation codecs из корня репозитория:

```sh
python experiments/parent-analysis/run_representation_tests.py all
python experiments/parent-analysis/run_representation_tests.py measure-graph
python experiments/parent-analysis/run_representation_tests.py measure-listing
```

Нужна обычная Python-среда проекта. Обёртка задаёт пути к frozen inputs; исходные codec/test файлы не меняются. Network/model calls запрещены кодом evaluation. `EVALUATION-PLAN.md` отделяет preservation, читаемость и качество первого Author ответа; последние два нельзя объявлять доказанными roundtrip-тестами.

## Правила чтения архива

- `ORIGINAL_*` и исходные отчёты описывают состояние **до публикации этой ветки**. Их слова «unpublished», «non-Git» и старые workspace paths являются историческим контекстом; текущий статус задаёт этот README.
- Старые counts относятся только к конкретным snapshots. Не складывать их в новый acceptance и не переносить на сочетания патчей.
- Оригиналы workspace не переписывались. `*-provenance.json` закрепляют исходные и сохранённые hashes.
- Ни capability registry, ни модельная игровая композиция не заменены classifier, fallback, ID whitelist или дополнительным обязательным LLM pass.
- Следующий шаг: выбрать одну идею, применить в отдельном checkout, проверить реальные invariants/negative cases и полный combined tree. Не переносить весь исследовательский архив в runtime одним squash.
