# Parent source analysis: измерения после аудита, 2026-11-07

База — `3c092e34403eefceea47665123be888a261cd820`; проверенный локальный снимок исходников
(tested local source snapshot) — `ae409dda172087e36037ac16b8e94254c8ba0790`,
code tree — `7fbc534416dbe47e59500bf4f4c6ff5658073fe9`.
База **уже содержит предоставленный патч поверх PR #333**; таблицы показывают
добавочный эффект последующих изменений, а не весь эффект PR относительно main.
При публикации commit metadata могут измениться; идентификатор выше относится к локальному снимку.
`testedSourceSubtrees` в receipt позволяет отдельно сверить точные деревья Python,
мода и tools с публикуемой веткой; после проверок добавляются только документы и receipt.

На двух тяжёлых native-сценариях наблюдалось уменьшение cold wall time на 14.82–20.57%
и накопленных managed allocations на 22.77–24.99%. Финальные Python-медианы тяжёлых
сценариев уменьшились на 26.55–49.90%; для `plain` ускорение не подтверждено.
Все 16 native payload совпали побайтово, SHA256 четырёх полных Author requests совпали.
Это результат ограниченной offline-выборки, без статистической гарантии.
Точные значения, hashes и статус проверок: [машинный receipt](../../../contracts/reports/parent_source_performance_20261107.json).

## Что изменилось

- CFG/local dataflow переиспользует анализ, числовые definition sets и worklist;
  временные reaching maps освобождаются после связывания, graph memo ограничен.
- AST-проекция избегает ненужного клонирования и повторного rendering;
  ограниченные LRU-кеши сохраняют прежние проверки identity и cancellation.
- Prepared request кодирует итоговый JSON один раз; разделяемые значения
  не позволяют изменению одной проекции менять другую.
- Python использует структурные IDs для exact sharing, копирование затронутых
  ветвей и переиспользование готового compact view. Прежние greedy/coverage rules
  сохранены: необходимые сравнения альтернатив всё ещё измеряют полный stage.

Контракт, unknowns, ограничения кешей и владельцы описаны в
[PARENT_SOURCE_ANALYSIS_RU.md](PARENT_SOURCE_ANALYSIS_RU.md).
Новые зависимости, постоянный дисковый кеш и дополнительный LLM-проход не вводились.

### Решения по MD-аудиту

Этапы A–C закрыты: меньше AST-копирований, reuse полного анализа с ограниченными
кешами и компактные CFG/dataflow состояния. Этап D применён с сохранением прежнего
выбора представлений; конкурирующие варианты по-прежнему сравниваются, когда это
может повлиять на полный Author stage. Дополнительно закрыто повторное кодирование
prepared JSON из §4.2 и удалены уже ненужные reaching maps после binding.

Этап E, кеш между запусками, требует отдельной схемы identity и invalidation для
dependencies и modded loadout. Этап F, `msgspec`/`orjson` или новый typed wire,
требует отдельного сравнения чисел, Unicode, character budgets и recipe identity.
Они не входят в этот патч. Postdominators сохраняют прежний fixed-point порядок и
границы; negative AST cache сохраняет только два детерминированных size-отказа,
не deadline, cancellation или resolver failures. Новый общий IR для всех slices
не введён: их входы и assumptions различаются.

## Методика native

Источник — восемь `report.json`, указанных строками `PROFILE report=` в
`baseline-<scenario>.log` и `final-<scenario>.log`; промежуточные замеры не использованы.
[Harness](../../../tools/native/EngineRuntimeChecks.ParentAnalysisProfiling.cs)
запускался отдельным процессом для каждого сценария и каждой ревизии.
Среда: .NET SDK `8.0.427`, CLR `8.0.33`, native MVID `7b8a9f2a-b51f-4957-bcbc-cf6609b474c8`;
71 dependency DLL совпала побайтово. Доступны 5456 item types и 1022 projectile types;
sample-каталоги до первого запроса пусты. Tooltip context —
`headless_dedicated_literal_not_local_client_tooltip_hooks`.

Каждый процесс последовательно выполнял `cold-first-request`, `warm-1`, `warm-2`
и `source-cache-reset`. Cold означает первый `PrepareDeferred` после настройки
harness и создания родительских Item/Player; запуск процесса в это время не входит.
Перед ним не выполнялись dump или прогрев полного каталога. Reset вызывает
`ParentAnalysis.Invalidate`; native certificate Lazy values и CLR/JIT остаются прогретыми.

`wallMs` охватывает `PrepareDeferred → Task.Run(CompleteAnalysis) → PayloadJson`,
включая `Pump` и ожидания по 16 мс. Это длительность headless-подготовки запроса.
`captureMs` и `resolveMs` — отдельные фазы внутри неё; simulated frames не измеряют FPS.
На сценарий и ревизию приходится один cold-замер и два последовательных warm-замера.
Другие test/build/profiling workers задачи завершены до серии; нагрузка shared host не контролируется.

### Cold: время и накопленные managed allocations

Δ = `(после / до − 1) × 100%`; отрицательное значение означает уменьшение.
MiB = 1 048 576 байт. Время приведено из `wallMs`, allocations — из `totalAllocatedBytes`.

| Сценарий | До, мс | После, мс | Δ времени | До, MiB | После, MiB | Δ allocations |
|---|---:|---:|---:|---:|---:|---:|
| `plain` | 1572.454 | 1551.518 | -1.33% | 168.009 | 167.846 | -0.10% |
| `mixed` | 9420.508 | 9326.452 | -1.00% | 1482.220 | 1423.332 | -3.97% |
| `nebula-prism` | 25860.577 | 22028.683 | -14.82% | 6356.234 | 4767.878 | -24.99% |
| `eventide` | 25649.889 | 20372.667 | -20.57% | 5857.099 | 4523.420 | -22.77% |

Allocations — process-wide delta `GC.GetTotalAllocatedBytes(precise: true)` за тот же
интервал, включая main/worker/runtime overhead. Создание родителей, invalidation,
parity parsing, hashing и запись evidence исключены. Принудительный GC не вызывался.
**Это сумма управляемых выделений, а не peak RAM, retained heap или размер кеша.**
Дельты `GC.CollectionCount` также относятся ко всему процессу: в фазе может собираться
мусор предыдущей фазы. Оценки `EstimatedMethodBytes` не являются измерением CLR heap.

### Тёплые запросы и сброс кеша

В каждой ячейке — `wallMs` до → после; уменьшение не наблюдалось во всех фазах.

| Сценарий | warm-1, мс | warm-2, мс | source-cache-reset, мс |
|---|---:|---:|---:|
| `plain` | 17.020 → 17.453 | 16.881 → 17.956 | 904.903 → 915.309 |
| `mixed` | 108.959 → 104.923 | 103.420 → 111.141 | 5434.671 → 5147.821 |
| `nebula-prism` | 508.533 → 555.994 | 378.790 → 326.755 | 18707.069 → 16197.370 |
| `eventide` | 155.004 → 156.523 | 166.637 → 193.312 | 19956.419 → 14877.370 |

### Побайтовая сохранность native payload

Фактические файлы прочитаны как bytes и сравнены между ревизиями: **16 из 16 пар равны**
(4 сценария × 4 фазы). Длины и SHA256 файлов дополнительно сверены с `report.json`.
Для каждого сценария ниже одинаковы все четыре фазы обеих ревизий; это сильнее
одного `equalToFirstRequest`, который внутри harness проверяет JSON-равенство.

| Сценарий / родители | UTF-8 байт | SHA256 payload |
|---|---:|---|
| `plain`: Wood + Stone Block | 32901 | `8c983cd7182bba43f9bb260be307fef9fd9b97f996b063ce477935fcf5f5a6f9` |
| `mixed`: Terra Blade + Mining Potion | 762635 | `73eff3bf1a22e4065970b732361ba5e34a2c65f91d0bbfd85d2c53677b38ef91` |
| `nebula-prism`: Nebula Blaze + Last Prism | 3737307 | `ecd8d27be562913281c81c6b5c2273684b4d589202a3e189d5df78b99d7635b7` |
| `eventide`: Eventide + Wooden Arrow | 2855886 | `b71c26e234b4e58ace5758392f5310a35822c3770ba0a65a393b7678b34e1083` |

## Python: финальная тихая серия

Источник — `python-matched-final.json`, Python `3.12.14`. Измерен полный
`build_initial_author_request(..., model_name="offline")` на заранее декодированных
фиксированных cold native captures. Импорты, чтение captures и последующий hashing
исключены. Ревизии запускались последовательно отдельными процессами после завершения
остальных build/test/profiling workers; на сценарий выполнено **три повтора**.

| Сценарий | Медиана до, мс | Медиана после, мс | Δ времени |
|---|---:|---:|---:|
| `plain` | 89.475 | 90.134 | +0.74% |
| `mixed` | 1247.087 | 624.736 | -49.90% |
| `nebula-prism` | 3580.693 | 2630.069 | -26.55% |
| `eventide` | 1117.691 | 677.156 | -39.41% |

SHA256 полного сериализованного request совпал **4/4**; также сохранены `recipeKey`,
SHA256 user-строки и её длины в символах/UTF-8 байтах. Хеши request обеих ревизий:

| Сценарий | SHA256 Author request |
|---|---|
| `plain` | `bafa1b3452527e95cc8d9ca62d2621b8cf3bab0f53e3afdedd600d17500b5be4` |
| `mixed` | `4c1a9294f382a06ec331c7017b79019ee6f0749d301f87b0c15fdc5e8308623d` |
| `nebula-prism` | `786fbff81a7154eafbecb03be84450e2ac7032c53650f321bb408be57cf44c66` |
| `eventide` | `1e5377bb178029cd644cfcbeb64a84e87b9e5920ed0a06edc6e15a418e24ba1d` |

Три повтора не дают статистической гарантии; разница `plain` составляет +0.659 мс.
Проценты C# и Python относятся к разным интервалам и **не складываются** в ускорение craft.

## Воспроизведение native

Выполнить из отдельных checkout baseline `3c092e3` и ветки этого изменения с одинаковыми
tModLoader/ParticleLibrary/Luminance references; не запускать параллельные benchmarks.
Переменные ниже указывают на существующие reference/dependency directories, как в
[TESTING_RU.md](../TESTING_RU.md).

```bash
set -eu
dotnet build tools/native/EngineRuntimeChecks.csproj -c Release \
  -p:InfiniTmlReferenceDir="$INFINI_TML_REFERENCE_DIR" \
  -p:InfiniExternalDepsRoot="$INFINI_TML_DEPS_SRC"
for scenario in plain mixed nebula-prism eventide; do
  dotnet tools/native/bin/Release/net8.0/EngineRuntimeChecks.dll \
    --profile-parent-craft "$scenario"
done
```

Каждый вызов DLL создаёт новый процесс и сохраняет `report.json` плюс четыре payload
в `artifacts/parent-profiling/craft-<scenario>-<run-id>/`; точный путь печатается в stdout.
Сравнивать соответствующие файлы между ревизиями до разбора или пересериализации JSON.

## Приёмка и NotRun

Полная приёмка проверенного локального снимка завершена:

- **Python: PASS**, все 6 shards, 9779 тестов в 297 файлах; объединённый результат `ok=True`.
- **Native: PASS**, 756 passed, 0 failed; Debug build — 0 warnings, 0 errors.
  `run_check(native_checks)` завершился за 604.131 с.

Профилирование выполнено в CPU/headless harness. Отдельно **NotRun**:
реальная игра/world/game-loop, GPU/rendering, сетевой multiplayer, полная установка
Calamity с полным набором сторонних hooks, внешний provider HTTP и LLM-вызовы.
End-to-end craft и качество Author/Visual/VFX из этих измерений не следуют.
Числа не гарантируют тот же эффект на другом CPU, CLR, mod roster или произвольном рецепте.
