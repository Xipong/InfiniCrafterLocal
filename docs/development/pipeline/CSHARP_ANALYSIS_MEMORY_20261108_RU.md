# C#-буферы и потоковые хеши для PR #339, 2026-11-08

## Решение

Создан небольшой модуль исходного C# `SourceAnalysisBuffers` для .NET 8 и подключён к существующему native-анализу. Он убирает большие промежуточные представления данных при вычислении SHA-256 и лишнюю копию при чтении ZIP. Внешние NuGet-зависимости не добавлены.

Это изменение технического представления и вычисления уже определённых данных. Оно не меняет gameplay, Author-контракт, доказательства исходного кода, полноту ключей, неизвестные условия или лимиты анализа. Проверяется равенство полных выходных bytes, а не только семантическое равенство JSON.

Исходники: [SourceAnalysisBuffers.cs](../../../mod/InfiniCrafterLocal/Common/Analysis/SourceAnalysisBuffers.cs). Воспроизводимый C#-микробенчмарк: [инструкция](../../../tools/benchmarks/source_analysis_buffers/README.md). Машиночитаемые измерения и provenance: [JSON](source_analysis_memory_20261108.json).

## Сквозной результат выбранного варианта

**Интеграция остаётся экспериментальной: общий расход ОЗУ улучшен не во всех сценариях.** В смешанном сценарии process peak RSS вырос на 56,48 МиБ / 14,3%. Снижение накопленных аллокаций само по себе не закрывает цель снижения RAM; этот регресс остаётся ограничением для merge.

Baseline — [`c4a7bc79`](https://github.com/Xipong/InfiniCrafterLocal/commit/c4a7bc7995dd99c28a589a582d7c5e381720edf7), head PR #339 на момент работы. Измеренный локальный implementation — `3bafea5e284e4b3de3b4d7ea4019601c76ae6e2b`. Опубликованный [`ff940bf0`](https://github.com/Xipong/InfiniCrafterLocal/commit/ff940bf06a6716d360c6426920be944ad22c9430) имеет **полностью идентичное Git tree** `071103a9db0cb939750914c6f229797af9e1d5ef`; отличаются только metadata commits. Документация добавлена после измерения и production bytes не меняет.

Linux x64, официальный tModLoader 2026.09.3.1, SDK сборки 8.0.427 и **отдельный runtime 8.0.0 с `--roll-forward Disable`**. По три независимых свежих процесса на каждую пару и версию: 24 процесса. В каждом — cold, warm-1, warm-2 и source-cache-reset. Порядок AB/BA/AB; параллельные сборки, collector и tests во время профилирования не выполнялись.

Cold — первый `PrepareDeferred → CompleteAnalysis → PayloadJson` после создания harness и родителей; загрузка и проверка pack входят. Startup процесса, родительский setup, проверка равенства и запись evidence исключены из таймера. Кэш файлов ОС не очищался. Это process-cold, не старт игры.

Медиана и диапазон трёх cold измерений, секунды; allocations — МиБ:

| Пара | Baseline time, median (min–max) | Candidate time, median (min–max) | Managed allocation, baseline → candidate |
|---|---:|---:|---:|
| Wood + Stone | 0.856 (0.795–1.278) | 0.960 (0.791–1.061) | 133.642 → 132.078 |
| Terra Blade + Mining Potion | 1.621 (1.470–1.950) | 1.645 (1.533–1.841) | 242.036 → 240.232 |
| Nebula Blaze + Last Prism | 3.553 (3.417–5.307) | 3.322 (3.000–3.944) | 543.288 → 541.056 |
| Eventide + Wooden Arrow | 2.749 (2.641–2.928) | 2.708 (2.659–2.724) | 429.256 → 426.932 |

**Все 12 candidate cold запросов этого варианта ниже 5 секунд.** Это отдельный PASS target, не доказательство ускорения: plain median вырос 856 → 960 мс, mixed — 1621 → 1645 мс. Nebula и Eventide улучшились по медиане. Три повтора не дают p95 и не гарантируют результат для других пар, машин или modded loadout. Большие временные выбросы сохранены в исходных наблюдениях.

### RSS и последующие запросы

| Пара | Median process peak RSS, baseline → candidate, МиБ | Изменение |
|---|---:|---:|
| Wood + Stone | 395.60 → 392.65 | -0.7% |
| Terra Blade + Mining Potion | 395.11 → 451.59 | +14.3% |
| Nebula Blaze + Last Prism | 585.01 → 577.66 | -1.3% |
| Eventide + Wooden Arrow | 556.74 → 550.90 | -1.0% |

RSS — Linux `wait4.ru_maxrss` для целого subprocess: startup, четыре фазы, parsing и evidence writes. Это не peak RAM одного cold запроса. Allocations — process-wide delta `GC.GetTotalAllocatedBytes(precise:true)` внутри каждого timed interval, не живые объекты или RSS. Принудительных сборок мусора нет. Пул свободных буферов helper существенно меньше обнаруженного регресса; размер idle pool нельзя трактовать как предел памяти процесса.

`warm-1` и `warm-2` повторяют ту же пару, а не новую комбинацию. Reset очищает shared source/attack caches; CLR/JIT и native certificate Lazy остаются тёплыми. Медианы последующих фаз, миллисекунды, baseline → candidate:

| Пара | warm-1 | warm-2 | source-cache-reset |
|---|---:|---:|---:|
| Wood + Stone | 18.46 → 19.00 | 18.12 → 18.00 | 322.34 → 340.62 |
| Terra Blade + Mining Potion | 124.08 → 121.91 | 155.06 → 138.16 | 819.49 → 820.39 |
| Nebula Blaze + Last Prism | 511.04 → 504.45 | 577.26 → 573.70 | 2122.16 → 2231.85 |
| Eventide + Wooden Arrow | 396.72 → 383.77 | 438.60 → 376.13 | 1790.77 → 1791.73 |

Есть замедления и в reset: plain +5,7%, Nebula +5,2%. Результат не описывается как всеобщее ускорение или достижение 200 MB RAM. Изолированные операции библиотеки ниже и сквозные фазы — разные уровни измерения.

### Полнота и контроль входов

**48/48 межверсионных сравнений фактических payload bytes прошли.** Дополнительно совпали 72/72 comparisons между фазами и 64/64 между повторами. Использован `exact-bytes`, без graph normalization и без подмены файлов одним сравнением digest. Все три canonical cohorts проверены; input pins стабильны.

Независимый полный collector каждой версии: **1 021 projectile + 5 455 item identities, ошибок 0/0**. Все **14 526** полных key/kind/payload bindings совпали; **1 991** уникальная пара blob непосредственно сравнена побайтно с независимой проверкой length/SHA/index. Все **6 476** полных reference receipts совпали с порядком, всеми полями, gaps и multiplicity. Reference receipts включают SHA/длину результатов; это отдельно от прямого сравнения ZIP payload bytes.

Archive bytes: **8,060,023 → 8,060,025**, это не оптимизация размера ZIP. Разница связана с новым source fingerprint в manifest. Индекс и все содержательные blobs сохранены.

Projection fingerprint baseline: `3aa167116ea4c806327725d6686d42bd041806fb09328032b757c4c1c6a7ac35`. Candidate: `a5015b9c8834bdabda350a553c4e77377a0da06ea0d3b6ed68ed4672d897dc49`. Candidate archive SHA256: `9668ee4afab42eaef0b5310ab4eb887f17564f8fabcc8767931d6c1d8ac7b548`.

Actual CLR verifier подтвердил 67 официальных target assets. В A/B совпадают 72 dependency DLL hashes и полные bytes `.deps.json`. Для нового отдельного output-каталога восстановлены два дополнительных служебных DLL и `.deps` graph исходного benchmark после строгой проверки, что различия ограничены только ими; production references не менялись. Эти два DLL не входят в 67 target assets или 80 source-pack dependency pins. Исходный `.deps` и receipt сохранены в evidence; первые preflight-отказы не содержат измерений и не включены в выборку.

### Проверки и готовность

- Финальная Release-сборка: **0 warnings, 0 errors**.
- Полный native suite выбранного implementation на exact .NET 8.0.0: **758 passed, 0 failed**. Четыре новых checks покрывают Unicode/surrogate и chunk boundaries, JSON order/escaping/numbers, parallel ownership, точные длины, границы, приоритет cancellation и retry.
- **107 focused Python tests passed**: source pack, dependency staging и strict cohort verifier. Проверки документации: **21 passed, 1 skipped**; browser acceptance пропущен из-за отсутствия Chromium. Проверены структура ссылок и построение handbook.
- **Все 12 static gates PASS**, включая Ruff, Pyright и штатный offline handbook check. Handbook обновлён генератором; проверка diff whitespace проходит.
- Новый helper включён в source fingerprint и CI path trigger, поэтому его последующие изменения не оставят незамеченным stale pack.

Это не `releaseReady`: mixed RSS остаётся известным регрессом. Полный Python release suite, Windows package, реальный клиент/мир, Calamity, multiplayer и качество ответов Author для этого изменения **notRun**. Результаты CI старого PR #339 не выдаются за проверку нового кода. Библиотека и её отдельные операции готовы для review; включение в основной runtime остаётся draft до решения ограничения по общей памяти.


## Почему выбрана эта библиотека

Для обнаруженных горячих операций достаточно стандартной библиотеки .NET:

| Вариант | Что даёт | Решение для PR #339 |
|---|---|---|
| `System.Buffers`, `Span<T>`, `IncrementalHash`, `Utf8JsonWriter` | Управление временными буферами, последовательная запись JSON и вычисление хеша без полного UTF-8 массива | Использованы внутри небольшого `SourceAnalysisBuffers` |
| `CommunityToolkit.HighPerformance` | `MemoryOwner<T>` и `SpanOwner<T>` упрощают владение арендованными буферами | Подходящий общий набор, но в этом изменении отдельная зависимость не нужна |
| `Microsoft.IO.RecyclableMemoryStream` | Переиспользование буферов для потока, длина которого может расти | Для ZIP-записи известной длины проще сразу выделить итоговый массив; `ToArray()` и у этой библиотеки создаёт копию |

Основания: официальные документы [ArrayPool.Create](https://learn.microsoft.com/en-us/dotnet/api/system.buffers.arraypool-1.create?view=net-8.0), [Utf8JsonWriter](https://learn.microsoft.com/en-us/dotnet/api/system.text.json.utf8jsonwriter?view=net-8.0), [SpanOwner](https://learn.microsoft.com/en-us/dotnet/communitytoolkit/high-performance/spanowner), [MemoryOwner](https://learn.microsoft.com/en-us/dotnet/communitytoolkit/high-performance/memoryowner) и [RecyclableMemoryStream.ToArray](https://github.com/microsoft/Microsoft.IO.RecyclableMemoryStream/blob/master/docs/Microsoft.IO/RecyclableMemoryStream/ToArray.md). Выбор для этого проекта — инженерный вывод из call sites и измерений, не сравнительный benchmark всех перечисленных пакетов.

## Устройство и границы модуля

Модуль поставляется исходным файлом с `internal` API и компилируется в ту же сборку. Это не отдельно опубликованный NuGet-пакет. Он не зависит от Terraria, ILSpy или состояния игрового мира.

| Метод | Поведение |
|---|---|
| `ReadExact(stream, length, maximum, token)` | Создаёт один итоговый массив известной длины, читает непосредственно в него порциями до 16 КиБ, проверяет недобор и лишний байт |
| `HashUtf8(text, token)` | Для короткой строки использует стековый буфер и однократный SHA-256; длинную строку кодирует по частям через `Encoder.Convert` и `IncrementalHash` |
| `HashUtf8AndJson(prefix, node, token)` | Хеширует UTF-8 префикса и последовательно записанный JSON без конкатенации полной строки |
| `HashJsonPair(first, second, token)` | Хеширует ровно прежнюю последовательность `JSON(first) + LF + JSON(second)` |

Все хеши сохраняют прежние lowercase hex, кодирование UTF-8, порядок свойств JSON, escaping и числовое представление. Используется стандартный renderer `JsonNode.WriteTo` с прежними defaults; canonicalization или сортировка полей не добавлены. Между двумя JSON-документами writer сначала сбрасывает bytes через `Flush`, затем выполняет `Reset`.

В итоговой интеграции изменены существующие места вычисления хешей source/projection и чтение entry source pack. **Хеширование большого индекса в загрузчике сохраняет прежнюю реализацию:** полное включение потокового пути снизило allocations, но в сквозном тесте сопровождалось ростом peak RSS. `HashJsonPair` остаётся доступным методом библиотеки и проверяется отдельно; его микроускорение не является выигрышем активного загрузчика. В `NativeCSharpSource` один и тот же SHA вычисляется один раз и используется для обеих прежних записей. Итоговые `byte[]` принадлежат caller и никогда не возвращаются в pool; параллельные вызовы получают независимые результаты. Cancellation проверяется до работы, между порциями и сразу после `Read`/`ReadByte`, включая одновременную отмену и ошибку длины.

Внутренний JSON writer арендует буферы из собственного `ArrayPool<byte>.Create(64 * 1024, 2)`. В .NET 8 суммарная ёмкость **доступных этому helper свободных byte-array buffers** ограничена 248 КиБ; заголовки объектов и metadata pool в это число не входят. Максимальная сохраняемая длина отдельного массива — 64 КиБ. Более крупный JSON-токен может потребовать большой непрерывный буфер; после возврата такой буфер не сохраняется pool.

Это ограничение **удержания свободных буферов**, не ограничение всей памяти метода или процесса. Одновременные вызовы, входной JSON, итоговый массив ZIP и крупный текущий токен имеют отдельную стоимость. Изменение не обещает нулевых аллокаций. Реализация buckets проверена по [исходнику .NET 8](https://github.com/dotnet/runtime/blob/v8.0.0/src/libraries/System.Private.CoreLib/src/System/Buffers/ConfigurableArrayPool.cs).

## Изолированные операции: измеренный результат

Микробенчмарк компилирует непосредственно production helper, сохраняет SHA-256 его embedded source и benchmark source. Baseline — соответствующие операции PR #339 на `c4a7bc7995dd99c28a589a582d7c5e381720edf7`. Helper bytes одинаковы в эксперименте с memo и в итоговом варианте без memo.

Exact .NET 8.0.0, Linux x64, Release. Для каждой операции: минимум 32 warmup вызова каждой версии и 250 мс суммарного прогрева, затем восемь чередующихся AB/BA samples с одинаковым числом вызовов. Результаты предварительно сравнены побайтно либо по точному digest. `GC.Collect` не вызывается. Время и выделения — на одну операцию; ниже медианы восьми samples.

| Операция | Время baseline → helper | Managed allocation baseline → helper | Использование в итоговой интеграции |
|---|---:|---:|---|
| Хеш реального manifest index, 14 526 rows и 1 991 blobs | 5,564 → 2,647 мс | 7 502 687 → 662 B | Только самостоятельный API; загрузчик сохраняет прежний путь |
| Чтение крупнейшей реальной ZIP-записи (`manifest.json`) | 10,569 → 9,775 мс | 3 066 088 → 1 524 984 B | Да |
| Небольшой representative projection key | 1,773 → 2,163 мкс | 1 408 → 704 B | Да |
| Хеш синтетического многоязычного текста, ровно 1 МиБ UTF-8 | 1,454 → 1,125 мс | 1 048 960 → 650 B | Метод используется для source strings; вход этой строки синтетический |

Для маленького ключа существует измеренный компромисс: выделения примерно вдвое ниже, но операция примерно на **0,39 мкс / 22% медленнее**. Это не скрывается за результатом большого индекса. ZIP-чтение по-прежнему должно выделить итоговый массив; снижение примерно вдвое относится к устранению второй копии, не к устранению всего буфера.

Подготовка fixtures, конструирование identity-префикса, чтение файла архива, разбор ZIP directory и JsonNode, проверки равенства и формирование отчёта находятся вне timed interval. Метрика `GC.GetAllocatedBytesForCurrentThread` измеряет накопленные managed allocation, не живую память и не RSS. Это warmed single-process microbenchmark, не cold startup и не ускорение всего craft в указанное число раз. Все samples и диапазоны сохранены в JSON.

## Отброшенный эксперимент с условиями ветвления

До итогового варианта проверялся observation-local memo для повторного поиска required branches. Локальный implementation commit эксперимента — `c0add0afa8d04fb1f0a2b7eff41858e67726cf48`. Он сохранял bytes и work/refusal ordering, но добавлял **563 880 B / 0,538 МиБ** к первому полному `AI_001` raw observation в фазе `cold-first-request` каждого повтора Nebula и Eventide.

В третьем повторе Nebula raw stage улучшился 176,972 → 155,347 мс, а Eventide ухудшился 288,094 → 329,196 мс. Сумма `identity_selection` и `raw_observation` для cold Nebula была 688,671 → 689,183 мс, для Eventide — 679,418 → 741,023 мс. Это суммы названных этапов, не отдельный причинный benchmark memo и не process CPU time.

Устойчивого суммарного выигрыша не подтверждено. Memo и его отдельные tests удалены; итоговый diff не меняет `ProjectileAttackFacts`. Данные этого эксперимента сохранены отдельно от окончательного A/B. Его результаты не подменяют измерения итогового implementation.

Первый mixed baseline этого раннего эксперимента занял 10,881 с, с 2,179 с внутри одного Pump. Задержки наблюдались и в нескольких неизменённых областях при почти одинаковых allocations. Причина не установлена; это не доказательство ускорения helper в 6,7 раза и не доказанный исключительно внешний шум. Все повторы сохранены.

Отдельная test-only диагностика раннего `c0` добавляла одинаковые memory snapshots в обе версии после таймера и перед/после evidence writes. Шесть mixed процессов повторили рост whole-process peak; median cumulative peak к концу cold был 356,29 → 354,96 МиБ, а к reset checkpoint — 396,19 → 471,07 МиБ. В cold различались GC counts, в reset — fragmentation последнего GC. Это указывает на различное распределение сборок и временных пиков, но не доказывает единственную причину. `GCMemoryInfo` описывает последний GC, а `GetTotalMemory(false)` не является переписью только живых объектов. Эти instrumented snapshots относятся к `c0`, не переносятся на выбранный `3bafea5` и не смешиваются с его canonical timings. Patch и исходные observations включены в JSON.

## Проверка полного включения потокового индекса

Вариант `bf917900e5ee4c022991a09246f2412f54737b10` уже не содержал memo, но включал `HashJsonPair` непосредственно в загрузчике индекса. Он прошёл 758 native checks, полный каталог и 48/48 межверсионных сравнений actual payload bytes. В каждом сценарии cold allocation уменьшался примерно на 11–12 МиБ. Однако mixed median whole-process peak RSS вырос **395,51 → 471,15 МиБ**, а Nebula cold median составил **4,295 → 4,697 с**. Один из 12 candidate cold запросов занял **5,296 с**, поэтому строгий five-second target был **FAIL**, при отдельном **PASS** byte parity.

Этот результат не скрыт и не объявлен готовой оптимизацией общей RAM. Для итогового варианта сохранены прямое чтение entries и хеши исходников/ключей, а только хеш индекса возвращён к исходной реализации. Принудительный GC, фиктивные аллокации и изменение GC-настроек не добавлялись. Данные `bf917900`, включая неблагоприятный результат, сохранены в JSON отдельно от выбранного варианта.

## Воспроизведение

Самостоятельный C# benchmark не требует NuGet-пакетов или Terraria assemblies. Для сборки нужен .NET SDK с поддержкой `net8.0`; для воспроизведения приведённых измерений — runtime .NET 8.0.0 и реальный source pack формата v2:

```bash
dotnet build tools/benchmarks/source_analysis_buffers/SourceAnalysisBuffers.Benchmarks.csproj -c Release
dotnet tools/benchmarks/source_analysis_buffers/bin/Release/net8.0/SourceAnalysisBuffers.Benchmarks.dll /absolute/path/native-source-pack.zip > source-analysis-buffers.json
```

Для сквозного сравнения baseline и candidate собираются в разные каталоги с одинаковыми official target inputs. SDK сборки отделён от runtime исполнения. Каждый pack создаётся полным live collector для собственного fingerprint; fingerprint не переносится на архив другой версии. После CopyLocal выполняются штатный target stager и actual CLR `--verify-native-target`.

В каждом новом процессе выполняется canonical harness:

```bash
"$IFC_RUNTIME_DOTNET" exec --runtimeconfig "$IFC_TML_RUNTIMECONFIG" --roll-forward Disable \
  /absolute/path/EngineRuntimeChecks.dll --profile-parent-craft mixed
```

Повторить для `plain`, `mixed`, `nebula-prism`, `eventide` по три раза для каждой версии, с порядком AB/BA/AB и без параллельной сборки/collector/tests. Включить `INFINI_PARENT_ANALYSIS_PROFILE=1` для диагностических stage logs. Сохранить исходные payload files, собрать cohort штатным `tools/testing/verify_parent_analysis_cohort.py collect` и проверить `verify --comparison-mode exact-bytes --require-payloads --require-pins --require-target`. Linux peak RSS измеряется отдельно для каждого subprocess через `wait4.ru_maxrss`; allocation counters берутся из canonical report.

Проверка byte parity и проверка cold target — отдельные условия. Прохождение этих условий не устанавливает универсальное ускорение, предел RAM или качество новых ответов модели.
