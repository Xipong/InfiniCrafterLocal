# Анализ родителей: экспериментальная ветка

Цель ветки `experiment/parent-analysis-20261105` — передавать Gameplay Author понятное, связное описание поведения родителей за один запрос. Оружие, его боеприпас и условный результат преобразования должны сохранять свои роли; дочерние снаряды должны быть связаны с доказанными source calls и условиями появления.

Текущий проверенный срез и ограничения описаны в [CURRENT_RESULT.md](CURRENT_RESULT.md). Работа ведётся в этой ветке отдельно от speed-only PR #330 и main.

## Что исполняется, а что сохранено для исследования

| Направление | Где находится | Статус исходного опубликованного среза `be864d01` |
|---|---|---|
| Оружие без подбора inventory/fallback ammo | `GeneratorClient.AmmoFacts.cs`, Python parent context | Активный код; настоящий ammo-parent сохраняет свои факты |
| Canonical replacement profiles и outer guards | `GeneratorClient.AmmoFacts.cs`, source catalog | Активный код; неизвестный результат остаётся неизвестным |
| Bounded CFG для native ammo | `cfg/native-ammo-control-flow.patch` | Архив кандидата; не применяется сборкой |
| Child-spawn extraction из helper methods | `helper/helper-spawns.patch` | Архив кандидата; старый замер превышает стандартный Author budget |
| Copy-on-write source state | `helper/copy-on-write-*.patch` | Два альтернативных кандидата; не складывать друг с другом |
| Closed-call effect summary | `diagnostics/effect-summary/` | Исследование; на сохранённом Last Prism packet экономия равна нулю |
| Inline/sparse source analysis | `diagnostics/prism-inline/` | Исследование; production selector и packet integration отсутствуют |
| Source relevance | `diagnostics/source-relevance/` | Исследование; удаление фактов при сохранении имеющегося доказательства не обосновано |

В таблице зафиксирован исходный срез, чтобы последующие изменения кода не меняли смысл исторических результатов. Финальный статус включённых изменений следует проверять по текущему коду и свежей записи в `CURRENT_RESULT.md`.

## Граница корректности

Captured identity и последующее живое состояние — разные свидетельства. Передача родителя в source/callback и вызов `Kill` могут ослабить доказательство его неизменности. Условная ветвь общего helper после такого вызова не становится безусловной механикой данного предмета. Оставшиеся условия и unknown должны быть видны в представлении для модели.

Новый формат полезен, если по нему можно проследить последовательность исходных операций и их условия без восстановления связи между несколькими разрозненными списками. Сокращение JSON само по себе не подтверждает читаемость, полноту извлечения или качество первого ответа модели. Не требуется дополнительный LLM pass, classifier либо подбор игрового поведения кодом.

## Повторяемые проверки

Из корня checkout, в Python-окружении проекта:

```sh
python tools/testing/run_focused_pytests.py LocalGenerator/tests/test_parent_ammo_observations.py LocalGenerator/tests/test_parent_ammo_source_semantics.py LocalGenerator/tests/test_parent_attack_reference.py
python tools/checks/check_csharp_contracts.py
```

Native CPU harness компилирует канонические исходники и требует существующих .NET 8 SDK, tModLoader/FNA/ReLogic и ParticleLibrary/Luminance references:

```sh
dotnet build tools/native/EngineRuntimeChecks.csproj \
  -p:InfiniTmlReferenceDir=/path/to/tml-references \
  -p:InfiniExternalDepsRoot=/path/to/deps

dotnet tools/native/bin/Debug/net8.0/EngineRuntimeChecks.dll --check-filter parent
```

Этот harness не запускает Terraria.Main, мир или графику. CPU-проверка, игровой smoke и проверка качества генерации моделью — разные уровни результата.

## Как читать исторические материалы

`ORIGINAL_*`, старые отчёты, logs и `*-provenance.json` сохраняют результаты прежних workspace snapshots. Их counts, пути и утверждения «unpublished» относятся к этим snapshots. Manifest связывает patch с исходными и конечными SHA256; patch не применяется автоматически при сборке. Старые counts нельзя складывать или переносить на новое сочетание изменений.

Сохранены авторские harness sources и summaries. Внешние DLL, большие generated IL/CFG captures и часть исходных frozen inputs отсутствуют. Поэтому диагностические scripts внутри архива могут ссылаться на отсутствующие workspace inputs; они не являются готовыми командами проверки текущего checkout.

В исходном README ошибочно перечислялись `ifc-parent-graph-prototype-20261105/`, `ifc-source-listing-experiment-20261105/`, `fixtures/`, `representations-provenance.json`, `run_representation_tests.py` и `EVALUATION-PLAN.md`. Этих файлов в срезе `be864d01` нет; прежнее описание не подтверждает наличие codecs, их проверок или результатов в репозитории.
