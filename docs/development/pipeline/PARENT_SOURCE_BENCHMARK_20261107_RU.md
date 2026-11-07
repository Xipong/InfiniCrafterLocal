# Холодный анализ пары: приёмка 7 ноября 2026

Цель **менее 5 секунд** достигнута для четырёх контрольных пар на Windows и Linux. В каждом окружении проверены реальные bytes всех 16 пар payload: cold-first-request, warm-1, warm-2 и source-cache-reset. Различий нет; порог скорости проверяется отдельно от совпадения содержимого.

## Результат

Время в секундах; каждый cold запуск — отдельный свежий процесс.

| Пара | Windows до | Windows после | Ускорение Windows | Linux до | Linux после |
|---|---:|---:|---:|---:|---:|
| Wood + Stone | 1.722 | **0.796** | 2.16× | 1.411 | **0.671** |
| Terra Blade + Mining Potion | 11.252 | **1.979** | 5.68× | 9.334 | **1.822** |
| Nebula Blaze + Last Prism | 16.964 | **3.730** | 4.55× | 12.369 | **3.284** |
| Eventide + Wooden Arrow | 14.483 | **3.059** | 4.73× | 11.474 | **2.988** |

Windows сравнивает pre-audit baseline `d5dd52da8eb9f5910eef4962254a86d6d2d87323` с candidate `aed99cac6976f386e25a13b98848f271bfc5fcdf`. Linux сравнивает исходный head PR перед этой работой `6e75c420a80df22088aac7b301e833cedf344b80` с тем же candidate source tree. Разные baseline и машины не следует объединять в одну выборку ускорения. Исходники baseline не изменялись.

[Windows CI: полный успешный прогон](https://github.com/Xipong/InfiniCrafterLocal/actions/runs/42385718178). Артефакт `pr333-parent-analysis-ab`, ID `13579687219`, содержит native reports, все 32 исходных payload, input pins, готовый source pack и отчёт полной генерации. ZIP скачан, его SHA проверен, строгая проверка повторена независимо после скачивания. [Машиночитаемые результаты и хеши](parent_source_benchmark_20261107.json) сохраняют оба cohort, каждое сравнение фаз, DLL roster, параметры сборки и границы измерений.

## Что входит в пять секунд

Измеряется первый `PrepareDeferred → CompleteAnalysis → PayloadJson`: capture, работа analysis worker, ожидание через native harness и получение полного сериализованного payload. Загрузка source pack и проверки его совместимости происходят внутри этого интервала. До него создаются harness и родительские Item/Player. Не измеряются запуск приложения, обращение к модели и генерация нового предмета через API.

Перед cold запросом нет capture, dump или перечисления каталога. Пакет подготовлен отдельным процессом при сборке продукта. Для каждой пары и варианта выполнено одно cold измерение; это не p95 и не гарантия максимума на произвольном компьютере. Reset очищает source/attack caches, но оставляет CLR/JIT и lazy certificates прогретыми, поэтому он показан отдельной фазой.

## За счёт чего получено ускорение

Повторяемая декомпиляция больших native-методов перенесена в сборку выпуска. Генератор использует прежние source builders и проходит все положительные native IDs: **1 021 projectile и 5 455 item, всего 6 476 identities**, с нулём ошибок генерации. Для обоих target созданы **13 372 проекции**. На Windows сборка каталога заняла 220.5 секунды, архив — 14 148 620 bytes; на Linux — 229.6 секунды и 14 058 718 bytes. Эта работа не выполняется перед игровым craft.

Пакет хранит exact source-проекции, их guards, ссылки, unknowns и детерминированные отказы. Он не хранит готовые пары, состояние игрока или решения Author. Каждый hit проверяет live native method и точный вход проекции; manifest фиксирует native PE, ILSpy, fingerprint исходников и разрешённые dependency bytes. Другие inputs или несовместимый ресурс переходят к прежнему live reader. Механика, полнота исходных evidence и ваншотный контракт Author не меняются.

## Проверка реальной поставки

Оба cohort используют официальный tModLoader `v2026.09.3.1`, native MVID `7b8a9f2a-b51f-4957-bcbc-cf6609b474c8`, точную **.NET 8.0.0** и `--roll-forward Disable`. SDK компиляции отделён от runtime исполнения. Выбор assets следует официальному `tModLoader.deps.json` и RID; DLL вложенного MSBuild/BuildHost не подмешиваются.

Linux framework-only probe запущен с оригинальными tML manifests без Terraria entrypoint: все **67/67** выбранных assets совпали с фактическими host paths и SHA. В Windows CI native target verifier подтвердил **68** фактически связанных assets. Resolver читает выбранные CLR `TRUSTED_PLATFORM_ASSEMBLIES`, включая вложенные Libraries. Реальный `EntryReadStream` из `.tmod` воспроизвёл ошибку ZIP seek; ограниченное буферизованное чтение исправило её, regression входит в native suite.

Финальная сборка на exact .NET 8.0.0 прошла **722 native checks, 0 failed**, включая пять проверок source pack: полнота ключей, точный JSON и отмена, повреждённые manifests/entries, повторная проверка live method header и атомарный отказ при конфликте записи. Дополнительно прошли 33 Python-проверки staging/cohort, 23 package-проверки и 8 workflow-регрессий.

## Память и оставшиеся границы

Linux peak RSS ниже относится к каждому целому subprocess: startup, создание родителей, четыре фазы, сравнение и запись evidence. Значения получены отдельным `os.wait4`, без наследования максимума от предшествующей компиляции. Это **не peak RAM одного cold interval**.

| Пара | Baseline peak RSS, MiB | Candidate peak RSS, MiB |
|---|---:|---:|
| Wood + Stone | 312.6 | 366.6 |
| Terra Blade + Mining Potion | 508.1 | 468.4 |
| Nebula Blaze + Last Prism | 712.3 | 592.4 |
| Eventide + Wooden Arrow | 658.5 | 549.9 |

Цель 200 MB не достигнута. Индекс пакета увеличивает расход памяти простого случая; на тяжёлых случаях пик снижается. Cumulative managed allocations в JSON-отчёте также не являются retained/peak RAM. Windows cohort peak RSS не измеряет.

Не проверены Calamity и произвольные modded loadouts, client tooltip hooks, world/gameplay, GPU и multiplayer. Полное перечисление source identities не доказывает пятисекундный предел для каждой возможной пары и состояния игры. При смене native/runtime dependencies требуется пакет для точного target; старый пакет не считается совместимым автоматически. Команды сборки и runtime contract описаны в [PARENT_SOURCE_ANALYSIS_RU.md](PARENT_SOURCE_ANALYSIS_RU.md).
