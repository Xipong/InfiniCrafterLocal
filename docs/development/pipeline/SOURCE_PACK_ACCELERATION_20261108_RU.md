# Source pack: короткие методы и дедупликация, 2026-11-08

## Проверенный результат

Baseline — `0f766496538ec11f0788445e700bc3c91bf2bdc8`, текущий контракт PR #339 до этой оптимизации. Candidate — production sources с fingerprint `3aa167116ea4c806327725d6686d42bd041806fb09328032b757c4c1c6a7ac35`, сопровождающие этот отчёт. Обе версии используют свой полный source pack, одинаковые tModLoader 2026.09.3.1, ILSpy и зависимости.

Linux x64, **точная .NET 8.0.0, `--roll-forward Disable`**. По три независимых свежих процесса на каждую пару и версию: 24 процесса, 96 payloads, **48/48 межверсионных сравнений фактических JSON bytes совпали**. Внутри каждой пары все 24 payloads также совпали между фазами, версиями и повторами. Ни нормализация graph, ни сравнение только hashes вместо files не использовались.

Cold — от первого `PrepareDeferred` через `CompleteAnalysis` до `PayloadJson`, после создания harness, родителей и Player. Загрузка/проверка pack входит в интервал. Startup процесса, игра, GPU, model/API traffic не входят. До первого запроса нет dump/capture полного каталога. Порядок baseline/candidate менялся между повторами; build, collector и локальные tests в момент этих профилей не выполнялись. Это process-cold, не cold дискового кэша ОС.

Медиана и диапазон трёх cold измерений, секунды:

| Пара | Baseline median (min–max) | Candidate median (min–max) | Отношение медиан |
|---|---:|---:|---:|
| Wood + Stone | 1.100 (1.076–1.564) | 0.876 (0.848–1.066) | 1.26× |
| Terra Blade + Mining Potion | 2.674 (2.518–3.232) | 1.717 (1.619–1.721) | 1.56× |
| Nebula Blaze + Last Prism | 4.262 (4.122–4.348) | 3.666 (3.476–3.867) | 1.16× |
| Eventide + Wooden Arrow | 3.562 (3.495–3.563) | 2.709 (2.697–2.709) | 1.31× |

**Все 12 candidate cold измерений ниже 5 секунд.** Три наблюдения на пару не дают p95 или гарантии для произвольного компьютера, пары или modded loadout.

## Warm и память: есть ограничения

`warm-1` и `warm-2` повторяют **ту же пару** в одном процессе с новыми Item, Player и request. Это не новые рецепты. `source-cache-reset` очищает shared source/attack/native-document caches и reader pack, но не перезапускает CLR/JIT и все static certificates. Поэтому эту фазу тоже нельзя считать полностью cold.

Медианы фаз, миллисекунды, baseline → candidate:

| Пара | warm-1 | warm-2 | source-cache-reset |
|---|---:|---:|---:|
| Wood + Stone | 18.7 → 19.2 | 18.3 → 18.3 | 389.9 → 362.0 |
| Terra Blade + Mining Potion | 184.3 → 119.2 | 188.3 → 142.1 | 1043.8 → 851.6 |
| Nebula Blaze + Last Prism | 553.7 → 491.6 | 460.6 → 607.7 | 2523.2 → 2412.5 |
| Eventide + Wooden Arrow | 333.2 → 388.4 | 463.7 → 389.9 | 2172.8 → 1731.9 |

**Ускорение не распространяется на каждую warm-фазу.** У Nebula/Prism warm-2 вырос с 461 до 608 мс, у Eventide warm-1 — с 333 до 388 мс. В этих candidate фазах зарегистрированы GC gen0/gen1, которых в соответствующих baseline фазах не было; в соседних фазах GC также распределён иначе. Это наблюдаемое смещение GC, не доказательство единственной причины разницы. Искусственный `GC.Collect` для улучшения таблицы не добавлялся.

| Пара | Median peak RSS subprocess, MiB | Cold cumulative managed allocation, MiB |
|---|---:|---:|
| Wood + Stone | 405.8 → 396.3 | 141.5 → 133.6 |
| Terra Blade + Mining Potion | 532.6 → 395.0 | 269.4 → 242.0 |
| Nebula Blaze + Last Prism | 557.7 → 584.4 | 570.2 → 543.5 |
| Eventide + Wooden Arrow | 561.8 → 543.1 | 456.7 → 429.3 |

RSS получен через Linux `wait4.ru_maxrss` для **целого subprocess с четырьмя фазами**, startup и записью evidence. Это не peak RAM одного cold интервала. Allocations — process-wide delta `GC.GetTotalAllocatedBytes(precise:true)` внутри timed interval, не retained/peak RAM. Nebula/Prism peak RSS вырос примерно на 27 MiB, хотя cold allocations снизились. **200 MB RAM не достигнуты; всеобщего снижения памяти не заявляем.**

## Последовательность разных новых пар

Дополнительный замер сравнивает baseline `0f766496` и опубликованный candidate `41f6a52f`. В каждом свежем процессе идут **8 уникальных комбинаций**, без сброса кэшей и принудительного GC. Для каждой пары заново создаются Item, Player и request. По 3 процесса на версию, порядок версий BC/CB/BC. Использован тот же native pipeline `PrepareDeferred` → `CompleteAnalysis` → `PayloadJson` с simulated pump 16 мс; новая точка входа находится только в изолированном измерительном harness, production не меняется.

«Знакомый» означает, что именно этот родительский ItemID уже встречался раньше в этой последовательности. Это **не** обещает полного покрытия внутренних методов кэшем. Только первая строка process-cold; даже у двух новых родителей ниже могут повторяться общие методы, исходники и attack projections.

| Порядок | Новая комбинация | Знакомых родителей | Baseline median, мс | Candidate median, мс |
|---|---|---:|---:|---:|
| 1 | Wood + Stone | 0, первый запрос | 1076.85 | 920.84 |
| 2 | Terra Blade + Mining Potion | 0 | 1697.42 | 818.21 |
| 3 | Nebula Blaze + Last Prism | 0 | 2700.55 | 2522.43 |
| 4 | Eventide + Wooden Arrow | 0 | 1251.53 | 1341.21 |
| 5 | Terra Blade + Healing Potion | 1 | 73.08 | 78.02 |
| 6 | Nebula Blaze + Musket Ball | 1 | 505.53 | 438.37 |
| 7 | Terra Blade + Last Prism | 2 | 412.21 | 382.41 |
| 8 | Eventide + Mining Potion | 2 | 151.20 | 230.06 |

Медиана суммы восьми pipeline-интервалов одного процесса: **7904.31 → 6781.73 мс**, на **14.2% меньше времени (1.17×)**. Это медиана трёх сумм, не сумма построчных медиан. Два новых родителя после первого запроса вместе: 5887.72 → 4664.34 мс; один знакомый: 578.60 → 514.86 мс; оба знакомы, но комбинация новая: **563.40 → 622.87 мс**, то есть эта группа замедлилась.

У последней пары в каждом candidate-процессе были GC gen0/gen1 `[1,1]`, у baseline `[0,0]`. Сборка мусора может оплачиваться следующим запросом; это наблюдение, не доказательство единственной причины. Для всех новых рецептов ускорение не подтверждено: три отдельные строки и группа двух знакомых родителей регрессируют.

Суммарные managed allocations: 1085.32 → 1054.05 MiB (−2.88%). Median peak RSS всего процесса: **565.76 → 506.72 MiB**. В RSS входят fixture setup, все восемь запросов и запись evidence; это не память одной пары и не величина для прямого сравнения с четырёхфазным benchmark выше. Construction, разбор report, hashing и writes находятся вне request timer. Дисковый кэш ОС не сбрасывался.

**Все 24 межверсионных сравнения полных raw payload bytes совпали**, без нормализации. Для каждой пары bytes также стабильны между тремя независимыми процессами каждой версии. Linked production sources и native packs не менялись; оба временных harness прошли actual CLR target verifier, остальные DLL bytes совпадают. Порядок пар фиксирован: это проверка конкретной последовательности, не причинный эксперимент по каждому слою кэша и не статистическая гарантия. Игра, Calamity, API/model latency и качество генерации сюда не входят.

[Полные наблюдения последовательности, payload hashes, GC и input pins](source_pack_new_pairs_20261108.json).

## Что изменено

1. Порог существующего recorder/reader снижен с 2048 до 1 байта IL. Методы без тела по-прежнему не записываются. Полный collector уже посещал короткие native builders, теперь сохраняет их проекции: UpdatePosition, AI_181_FairyQueenRangedItemShot, cone helpers и остальные подходящие методы. В actual candidate профилях короткие методы дают pack hits вместо прежнего `verified_decompile`.
2. Формат v2 сохраняет отдельные полные input keys и kind, но одинаковые projection bytes записывает один раз. Row `[key, kind, blobIndex]` ссылается непосредственно на уникальный SHA-256 blob; цепочек aliases нет. Каждый hit создаёт отдельный JsonObject, поэтому mutation одного caller не заражает другой.
3. `indexSha256` связывает ordered entries и blobs. Это обнаруживает в том числе валидный по диапазону, но неверный redirect, при котором обе цели всё ещё используются. Отдельные blob length/SHA и live PE/reflection verification остаются обязательными. Checksum — контроль целостности manifest, не подпись и не новая граница аутентификации.
4. Resolve больше не удаляет/вставляет неизменённые JSON children; deferred replacement и optional-null deletion сохраняются. Выключенный lifecycle recorder больше не создаёт два ненужных DeepClone. Проверены порядок JSON, null/numeric формы, repeated/nested markers, overlays, независимость копий и cancellation. Нового graph planner, raw-body pack, request memo или ослабления guards нет.

## Полный pack и каталог

| Показатель | Baseline v1 | Candidate v2 |
|---|---:|---:|
| Полных input keys | 13 372 | 14 526 |
| Уникальных payloads | 1 909 | 1 991 |
| ZIP bytes | 14 058 720 | 8 060 023 |
| Manifest bytes | 2 526 560 | 1 524 633 |
| Projectile method keys | 1 441 | 2 595 |

Archive уменьшился на **42,67%**, одновременно добавлено 1 154 проекции. **Для каждого из прежних 13 372 ключей kind и полные payload bytes совпали.** Полный collector прошёл 1 021 projectile + 5 455 item identities; все **6 476** итоговых reference hashes, длины и gaps совпали с baseline с сохранением multiplicity. Ошибок collector нет. Это сравнение всего native каталога, не только четырёх benchmark-пар. Final generation заняла около 284 секунд отдельным процессом; это не controlled build-speed benchmark.

Все прежние bounds сохранены: не более 30 000 input keys, 4 MiB на manifest/entry, 128 MiB archive. Проверяются duplicate ZIP names/keys/blobs, отсутствующие и лишние blobs, повреждённые bytes/length, kind, out-of-range и wrong-valid aliases, неправильный checksum, cancellation/retry. Отсутствующий, старый v1, несовместимый или повреждённый pack остаётся cache miss и использует прежний live reader. Полные native method/dependency проверки не сокращены.

## Приёмка и воспроизведение

- Final Debug/Release native builds: 0 warnings, 0 errors.
- Final Debug suite: **754 passed, 0 failed**; live fallback и v2 synthetic safety fixtures. Final Release suite с полным v2 pack: **754 passed, 0 failed**. Дополнительно прошли 9 focused checks.
- **104 focused Python tests passed**: source-pack checker, target staging, cohort verifier.
- Все 12 static gates прошли; offline handbook обновлён штатным генератором и повторно проверен после добавления отчёта.
- Точные host dependencies совпали между вариантами: 70 DLL hashes и `EngineRuntimeChecks.deps.json`; CLR отдельно подтвердил 67 официально выбранных runtime assets.
- Полный локальный Python shard-run был намеренно прерван до завершения, чтобы убрать фоновую нагрузку перед измерениями. Он **не объявляется PASS**. Полную Python/package приёмку выполняет CI для текущего head PR; обычный pull_request workflow проверяет его merge-ref с целевой веткой, а A/B отдельно фиксирует source commits.
- Windows workflow теперь сравнивает `0f766496` с candidate, собирает полный pack **обеих** версий и требует `exact-bytes`, actual payloads, input pins и cold target. Исторический graph-migration verifier сохранён как отдельный opt-in режим, но этот A/B его не использует.

[Все наблюдения по трём повторам, payload hashes, allocations, GC и pins](source_pack_acceleration_20261108.json).

Для воспроизведения: собрать baseline `0f766496` и candidate штатным `tools/generate/build_native_source_pack.py --build` с одинаковыми official target inputs, exact runtime host/config и `--target-rid`; после Content copy выполнить штатный target stager и `--verify-native-target`. В свежем процессе выполнить `--profile-parent-craft plain|mixed|nebula-prism|eventide`, собрать actual payloads через `verify_parent_analysis_cohort.py collect`, проверить `verify --comparison-mode exact-bytes --require-payloads --require-pins --require-target`. Полный workflow содержит executable Windows recipe.

Calamity, полный modded roster, client tooltip hooks, gameplay/GPU, multiplayer и качество новых ответов Author не запускались. Равенство source evidence не подменяет эти проверки.
