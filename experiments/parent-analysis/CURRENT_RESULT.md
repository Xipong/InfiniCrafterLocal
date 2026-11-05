# Текущий результат эксперимента

Дата проверки: 2026-11-05. Начальный срез этой доработки: `be864d011d72cb9101fa02d76c9b19894b3a6eb1`.

## Проверенная основа

Активный код исходной ветки восстанавливает canonical replacement profiles и сохраняет условия native ammo sources. Inventory/fallback ammo для оружия не выбирается; самостоятельный ammo-parent сохраняет собственную идентичность и факты. Дальнейшие архивные commits до `be864d01` добавляли материалы исследований, а не включали CFG/helper/COW patches в runtime.

Один Author ответ по-прежнему должен содержать полный предмет. Эксперимент не добавляет запросов инструментов, обязательного classifier или LLM-прохода для разбора родителей.

## Что необходимо довести

1. Связать source observations, определения значений и guards в читаемую последовательность, сохранив порядок использования и происхождение фактов.
2. Дополнить извлечение доказанных дочерних снарядов из helper methods без weapon-ID routers и выдуманных outputs.
3. Проверить полный запрос со свежим capture в стандартном Author budget. Старые оптимизации на неполном Last Prism capture этого не доказывают.
4. Измерять source-analysis allocations отдельно от размера model-facing context. Copy-on-write не решает полноту извлечения или budget автоматически.

## Подтверждённые границы старых кандидатов

- Helper-spawn candidate находил child632, но сохранённый Author payload составлял 325379 знаков при стандартном лимите 300000. Это исторический RED, не admission текущего результата.
- Closed-call summary оставлял Last Prism packet побайтно тем же: реальные source/callback escapes сохраняли неизвестность. Этот кандидат не даёт обоснованного сокращения контекста.
- Удаление неиспользуемых dependencies/predicates и повторное применение существующих certified edges не устраняли ни одного source fact. Предположение о неизменной identity после callback нельзя использовать как доказательство pruning.
- Sparse-local/inline study не включал безопасный production selector, packet integration и model A/B.

## Воспроизводимая native-среда

Для нового linked-source build найдены .NET SDK 8.0.427 и существующие references tModLoader 2026.08.3.0 с ParticleLibrary/Luminance. SHA256 `tModLoader.dll`:

```text
fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5
```

Эта assembly SHA совпадает с текущими native catalogs; их source module MVID — `033e87cd-cefe-4dc6-a1fb-e14aa938bbb2`. Поведение на другой версии tML этим результатом не подтверждается.

Свежий baseline MSBuild `tools/native/EngineRuntimeChecks.csproj` прошёл: 0 warnings, 0 errors. Результаты выполнения CPU checks будут записаны после завершения прогона. Игра, графика, multiplayer, model/provider calls и `.tmod` packaging не запускались.
