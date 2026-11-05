# Текущий результат эксперимента

Дата проверки: 2026-11-05. Исходный срез: `be864d011d72cb9101fa02d76c9b19894b3a6eb1`. Работа выполняется отдельно от main и speed-only PR #330.

## Что включено

Оружие сохраняет свою категорию боеприпасов и доказанные преобразования; самостоятельный ammo-parent сохраняет собственную идентичность. Inventory/fallback ammo не подбирается. Bounded CFG извлекает условия literal projectile stores, включая состояние анимации; неизвестный итог фактического выстрела остаётся неизвестным.

Helper extraction дополняет доказанные source calls и one-hop profiles дочерних снарядов. Inline source capture сохраняет actor field writes, setters и mutable calls в собственном work budget. Отказ отдельного slice остаётся явным и не удаляет прежний baseline program. Source local dataflow обрабатывает используемые slots; независимый dense oracle проверяет сохранение результата.

Модель получает читаемый C# из ILSpy там, где полный проверенный record с необходимыми references меньше compact graph. Это целый метод со всеми его ветвями либо закрытые lexical regions под исходными guards. Проверяются MVID, живые IL bytes и CLR metadata; source locations связывают текст с исходными calls. Все raw graphs остаются в diagnostic packet. Методы без подходящего view сохраняют связанную последовательность definitions, addressed-local uses/stores, effects, guards и switch. Alias uncertainty и snapshots остаются явными.

Для Last Prism доступны полный AI_075 (32044 знака), исходный dispatch guard и style84 body дочернего profile632 (13989 знаков), collision и position integration. Большие или неподдержанные records не подменяются догадками. Model-facing выбор работает по проверенным методам отдельно и сохраняет полные capabilities.

Pinned ILSpy 8.2.0.7535 и MIT notices поставляются внутри `.tmod`. Он читает metadata/IL без запуска исходного поведения, внешней программы или скачивания зависимости во время игры. Исследуемые методы, getters, constructors, source factories и callbacks ради этого view не вызываются. Root draw не входит в игровое C# view; исходные draw graphs сохраняются.

Source table union сопоставляет локальные member aliases по точной полной сигнатуре. Существующие baseline rows и их имена сохраняются; строковые константы не переписываются. Неизвестная схема или конфликт дают отказ объединения. Generic member names проверены отдельным regression после обнаружения настоящего ``Nullable`1..ctor`` в Last Prism.

Один Author ответ по-прежнему содержит полный предмет. Дополнительного classifier, обязательного LLM pass или вызовов инструментов моделью нет.

## Свежая проверка native данных

Независимый baseline checkout содержит только исходный срез и ту же capture-команду. Оба checkout используют один native pin, seed и восемь пар родителей. Полные canonical `GeneratorClient.Prepare` packets сохранены отдельно от model-facing dossier.

- Last Prism baseline не содержал дочерних profiles; новая версия содержит profile632 и условный candidate601 с девятью source sites. Candidate601 не объявляется безусловным ребёнком Last Prism.
- Native inline regression подтверждает сохранение source admission, opacity и LaserScan. Helper checks покрывают неизвестные условия/типы, loops, отдельные budget refusals и nonmutating table conflicts.
- Независимое сравнение восьми capture-пар сохранило все 226 baseline programs, 1384 observations, 1568 dependencies, 2562 predicates и 2666 symbols без изменений. Новое evidence добавляется отдельно.
- Перед добавлением C# view четыре полных raw packets — Molten Fury, Daedalus Stormbow, Wooden Arrow и обычные материалы — остались побайтно равны baseline.
- После добавления C# view все 16 fingerprints по-прежнему равны предыдущему срезу. Удаление только распознанных source views из восьми новых полных packets точно восстанавливает восемь предыдущих packets: native stats, graphs, sourceMethods и nulls сохранены.

Текущий полный raw Prepare для Last Prism занимает 1929657 знаков против 483029 в свежем baseline. Финальная проверка Author использует полную матрицу 8×8: все 64 упорядоченные пары из восьми настоящих captures, включая повторы и обратный порядок, проходят неизменённый лимит 300000. Максимум — StateConditionalBow + LastPrism: 289776 знаков, запас 10224. Raw transport packet и Author dossier — разные формы данных; эти числа не являются числом токенов.

Первый последовательный capture суммарно выделил около 2.98 GB управляемой памяти против 0.94 GB baseline. Счётчик всех allocations не равен одновременно занятой ОЗУ или RSS; этот запуск не является независимым cold benchmark. Извлечение source остаётся дорогим, улучшение скорости или памяти не объявляется.

## Проверки и admission

| Проверка | Свежий результат |
|---|---|
| Tomat SDK mod, linked-source native, workbench production mod и host | Все четыре build paths PASS с реальными references |
| Native sparse-local dense oracle | PASS 1/1 |
| Native helper source regressions после alias alignment | PASS 4/4 |
| Native inline source regressions после alias alignment | PASS 2/2 |
| Соседние source projection / effect slice | PASS 3/3 и 1/1 |
| Read-only C# provider: PE/metadata/IL identity, regions и actual Last Prism | PASS 3/3 |
| Source-view-free fingerprint: immediate и deferred capture | PASS 1/1; дополнительно совпали все 16 настоящих fingerprints |
| Официальный tML resource packager и `.tmod` reader | PASS 1/1; exact managed DLL, notices, Info loader entry и payload hash |
| Package/release verifier Python | PASS 61 tests и 5 subtests |
| Static gates | Все 17 PASS |
| Полный native baseline | 400 PASS / 270 FAIL |
| Финальный полный native прогон: 682 checks | 412 PASS / 270 FAIL; все 270 failed names и полные причины совпали с baseline |
| Actual Prepare → Author state-condition/profile preservation | PASS в обоих response formats; offline |
| Финальная canonical source-view матрица Author: 8×8 | Все 64 пары PASS; максимум StateConditionalBow + LastPrism 289776 / 300000, запас 10224 |
| Полный Python набор | 9243 PASS; все шесть canonical partitions прошли, итоговая агрегация PASS |

Полный native прогон в этой среде не GREEN: MonoMod не находит загруженный clrjit через numeric process lookup при несовпадении PID namespace и `/proc`. 247 failures прямо связаны с этой инициализацией; ещё 23 возникают в последующем состоянии того же процесса. Полный старый baseline воспроизводит тот же набор failures. Три проверенных отдельно motion/persistence cases проходят в обоих checkout. Это не основание объявлять полноценный release acceptance.

Во время финального прогона все 432 C# inputs и compiled harness оставались неизменными. Новых failures, исчезнувших failures и изменившихся причин нет; 12 добавленных checks проходят. Legacy root/fingerprint comparisons проверяют все native facts независимо от читаемого view: только expected root очищается от распознанной аннотации, actual fingerprint сравнивается без изменения.

Размерная проверка использует настоящие полные captures с восстановленными source effects и финальную canonical source-view проекцию. Проверены hashes всех восьми исходных packets и их соответствие каждой из 64 комбинаций. В каждой паре представлены все 71 author-visible capability без пропусков и лишних entries. Лимит не увеличен; capabilities не удалялись. Model/provider acceptance и качество первого предмета этой offline проверкой не подтверждаются.

## Повторение и границы

Команды native build/capture находятся в [README](README.md). Проверить настоящий Author admission без model calls:

```sh
python tools/checks/check_planner_prompt_usability.py \
  --parent-captures /path/to/capture-output --all-pairs --out /path/to/report.json
```

Проверенная среда: .NET SDK 8.0.427, tModLoader 2026.08.3.0, ParticleLibrary/Luminance. SHA256 `tModLoader.dll`:

```text
fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5
```

Assembly SHA совпадает с native catalogs; source module MVID — `033e87cd-cefe-4dc6-a1fb-e14aa938bbb2`. Другие версии tML и полный Calamity roster этим результатом не подтверждаются.

Игровая сессия, графика, multiplayer, model/provider calls и release-packaging полного `.tmod` со Studio не выполнялись. Packet preservation подтверждает передачу доступных source observations; оно не доказывает полноту произвольного native поведения, читаемость моделью или качество первого созданного предмета. Архивные counts и старые diagnostics не прибавляются к этим результатам.
