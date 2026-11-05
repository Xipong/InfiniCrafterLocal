# Анализ родителей: экспериментальная ветка

Цель ветки `experiment/parent-analysis-20261105` — передавать Gameplay Author понятное, связное описание поведения родителей за один запрос. Оружие, его боеприпас и условный результат преобразования должны сохранять свои роли; дочерние снаряды должны быть связаны с доказанными source calls и условиями появления.

Текущий проверенный срез и ограничения описаны в [CURRENT_RESULT.md](CURRENT_RESULT.md). Работа ведётся в этой ветке отдельно от speed-only PR #330 и main.

## Что исполняется, а что сохранено для исследования

| Направление | Текущая реализация | Статус |
|---|---|---|
| Оружие и ammo-parent | `GeneratorClient.AmmoFacts.cs`, Python parent context | Активно; inventory/fallback ammo не выбирается |
| Canonical replacement profiles и outer guards | Native source catalog и ammo capture | Активно; условия и неизвестный итог сохраняются |
| Bounded CFG для native ammo | `tools/generate/native_ammo_control_flow.py` | Включено; сохраняются state-dependent условия |
| Child-spawn extraction из helpers | `GeneratorClient.ProjectileSpawnFacts.cs` | Включено; source calls, guards и one-hop profiles связаны |
| Inline actor effects и sparse locals | `GeneratorClient.SourceGraph.cs`, `GeneratorClient.SourceMethod.cs` | Включено; собственные bounds и явные отказы |
| Читаемый C# исходных методов | `GeneratorClient.NativeCSharpSource.cs`, Python `native_csharp_source.py` | Включено; PE/IL/metadata proof, полные методы или закрытые условные regions |
| Последовательность source operations | Python `attack_behavior.py` и stage projections | Сохраняет методы без подходящего C# view; definitions, alias uses, guards и switch связаны |
| Copy-on-write source state | `helper/copy-on-write-*.patch` | Архив альтернатив; автоматически не применяется |
| Closed-call summaries, relevance и старый inline study | `diagnostics/` | Исследовательские материалы; не являются активным runtime |

Свежие проверки и ограничения находятся в `CURRENT_RESULT.md`. Исторические patches не применяются автоматически; включённые реализации принадлежат обычным source owners репозитория.

ILSpy engine поставляется внутри `.tmod` как обычная managed DLL; отдельная программа, процесс или скачивание при запуске не нужны. Полные graphs остаются в diagnostic packet. Fingerprint исключает только распознанное читаемое source view, поэтому его текст и настройки не меняют идентичность родителя.

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

# Полные canonical Prepare packets для проверки model-facing проекции и размера.
dotnet tools/native/bin/Debug/net8.0/EngineRuntimeChecks.dll \
  --capture-parent-context /path/to/capture-output
```

Этот harness не запускает Terraria.Main, мир или графику. CPU-проверка, игровой smoke и проверка качества генерации моделью — разные уровни результата.

Capture сохраняет восемь representative пар и `report.json` с hashes, native pin и scope. Это явная диагностическая команда; она пишет только в переданную output directory и не отправляет запросов модели. Полный native packet не равен Author dossier: размер последнего проверяется через настоящий Python request builder без увеличения лимитов.

## Как читать исторические материалы

`ORIGINAL_*`, старые отчёты, logs и `*-provenance.json` сохраняют результаты прежних workspace snapshots. Их counts, пути и утверждения «unpublished» относятся к этим snapshots. Manifest связывает patch с исходными и конечными SHA256; patch не применяется автоматически при сборке. Старые counts нельзя складывать или переносить на новое сочетание изменений.

Сохранены авторские harness sources и summaries. Внешние DLL, большие generated IL/CFG captures и часть исходных frozen inputs отсутствуют. Поэтому диагностические scripts внутри архива могут ссылаться на отсутствующие workspace inputs; они не являются готовыми командами проверки текущего checkout.
