# Текущий результат эксперимента

Дата проверки: 2026-11-05. Исходный срез: `be864d011d72cb9101fa02d76c9b19894b3a6eb1`. Работа выполняется отдельно от main и speed-only PR #330.

## Что включено

Оружие сохраняет свою категорию боеприпасов и доказанные преобразования; самостоятельный ammo-parent сохраняет собственную идентичность. Inventory/fallback ammo не подбирается. Bounded CFG извлекает условия literal projectile stores, включая состояние анимации; неизвестный итог фактического выстрела остаётся неизвестным.

Helper extraction дополняет доказанные source calls и one-hop profiles дочерних снарядов. Inline source capture сохраняет actor field writes, setters и mutable calls в собственном work budget. Отказ отдельного slice остаётся явным и не удаляет прежний baseline program. Source local dataflow обрабатывает используемые slots; независимый dense oracle проверяет сохранение результата.

Для модели определения значений, addressed-local uses/stores, effects и switch находятся в одной последовательности операций с source steps и guards. Alias uncertainty и snapshots остаются явными. Model-facing проекция согласована для прямых и связанных native profiles.

Source table union сопоставляет локальные member aliases по точной полной сигнатуре. Существующие baseline rows и их имена сохраняются; строковые константы не переписываются. Неизвестная схема или конфликт дают отказ объединения. Generic member names проверены отдельным regression после обнаружения настоящего ``Nullable`1..ctor`` в Last Prism.

Один Author ответ по-прежнему содержит полный предмет. Дополнительного classifier, обязательного LLM pass или вызовов инструментов моделью нет.

## Свежая проверка native данных

Независимый baseline checkout содержит только исходный срез и ту же capture-команду. Оба checkout используют один native pin, seed и восемь пар родителей. Полные canonical `GeneratorClient.Prepare` packets сохранены отдельно от model-facing dossier.

- Last Prism baseline не содержал дочерних profiles; новая версия содержит profile632 и условный candidate601 с девятью source sites. Candidate601 не объявляется безусловным ребёнком Last Prism.
- Native inline regression подтверждает сохранение source admission, opacity и LaserScan. Helper checks покрывают неизвестные условия/типы, loops, отдельные budget refusals и nonmutating table conflicts.
- Независимое сравнение восьми capture-пар сохранило все 226 baseline programs, 1384 observations, 1568 dependencies, 2562 predicates и 2666 symbols без изменений. Новое evidence добавляется отдельно.
- Четыре полных raw packets — Molten Fury, Daedalus Stormbow, Wooden Arrow и обычные материалы — остались побайтно равны baseline.

Текущий полный raw Prepare для Last Prism занимает 1618661 знак против 483029 в свежем baseline. Это размер native transport packet, а не Author dossier или число токенов. Первый последовательный capture выделил около 1.91 GB managed memory cumulatively против 0.94 GB baseline; это не resident RAM и не независимый cold benchmark. Улучшение скорости или памяти этим экспериментом не объявляется.

## Проверки и admission

| Проверка | Свежий результат |
|---|---|
| Linked-source MSBuild с реальными references | PASS; 0 warnings / 0 errors |
| Native sparse-local dense oracle | PASS 1/1 |
| Native helper source regressions после alias alignment | PASS 4/4 |
| Native inline source regressions после alias alignment | PASS 2/2 |
| Соседние source projection / effect slice | PASS 3/3 и 1/1 |
| Полный native baseline | 400 PASS / 270 FAIL |
| Полный native integrated coverage до финального alias alignment | 407 PASS / 270 FAIL; тот же точный набор 270 failures |
| Actual Prepare → Author state-condition/profile preservation | PASS в обоих response formats; offline |
| Стандартный Author admission на восьми свежих capture-парах | Семь PASS; Last Prism RED: 311563 > 300000 |

Полный native прогон в этой среде не GREEN: MonoMod не находит загруженный clrjit через numeric process lookup при несовпадении PID namespace и `/proc`. 247 failures прямо связаны с этой инициализацией; ещё 23 возникают в последующем состоянии того же процесса. Полный старый baseline воспроизводит тот же набор failures. Три проверенных отдельно motion/persistence cases проходят в обоих checkout. Это не основание объявлять полноценный release acceptance.

Последний размерный blocker относится к реальному текущему capture с восстановленными source effects, а не к старому неполному input. Увеличение лимита и удаление capabilities в этих результатах не использовались. Следующий критерий — сделать эту же полную проекцию допустимой в стандартном Author budget.

## Повторение и границы

Команды native build/capture находятся в [README](README.md). Проверить настоящий Author admission без model calls:

```sh
python tools/checks/check_planner_prompt_usability.py \
  --parent-captures /path/to/capture-output --out /path/to/report.json
```

Проверенная среда: .NET SDK 8.0.427, tModLoader 2026.08.3.0, ParticleLibrary/Luminance. SHA256 `tModLoader.dll`:

```text
fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5
```

Assembly SHA совпадает с native catalogs; source module MVID — `033e87cd-cefe-4dc6-a1fb-e14aa938bbb2`. Другие версии tML и полный Calamity roster этим результатом не подтверждаются.

Игра, графика, multiplayer, model/provider calls и `.tmod` packaging не запускались. Packet preservation подтверждает передачу доступных source observations; оно не доказывает полноту произвольного native поведения, читаемость моделью или качество первого созданного предмета. Архивные counts и старые diagnostics не прибавляются к этим результатам.
