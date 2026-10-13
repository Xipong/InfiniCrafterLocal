# Организация документации

Вход — [общий индекс](../README_RU.md). Документ отвечает на решение читателя, а не создаётся потому, что появилась новая папка.

## Где искать и куда писать

| Раздел | Назначение |
|---|---|
| [user](../user/README_RU.md) | Установка, настройки, запуск/остановка, MP и диагностика. Один основной launcher: `OPEN_INFINICRAFT.bat`. |
| [development](README_RU.md) | Architecture → code map → task owners → modules, затем build/testing и тематические development контракты. |
| [reference](../reference/README_RU.md) | Полные Author/runtime/units/VFX/engine manuals. `generated/` — проверяемые проекции canonical sources. |
| [archive](../archive/README_RU.md) | Исторические решения, release notes, измерения и verdicts с их snapshot/fixture/пределами доказательства. |
| `contracts/schemas/`, `contracts/config_registry.json` | Generated machine-readable exports, не ручной registry. |
| `contracts/reports/` | Сохранённые audit/validation receipts, не пользовательские инструкции. |

Корень содержит короткий README, AGENTS/CONTRIBUTING, лицензии и рабочие config/launcher files. Старые redirect-only `PROJECT_*`, `QUICK_START`, локальные README shims и папочные `FOLDER_DOCS_RU.md` удалены: ссылки ведут прямо к каноническому guide, совместимость старой раскладки не поддерживается.

[MODULES](MODULES_RU.md) собран по границам состояния: Studio draft/queue/native controller, DTO numeric admission, station/placement claims, runtime/assets/presentation, VFX и QA/CI. Он сохраняет уникальные **действующие** ограничения, не 65 копий папочных заметок. CODE_MAP перечисляет реальные files, OWNERS направляет задачу к source owner; документация не назначает вымышленных персональных maintainers.

## Источники и обновление

- Canonical source/registry/schema и реальный consumer имеют приоритет над описанием. [OWNERS](OWNERS_RU.md) выбирает точку изменения; [AGENTS](../../AGENTS.md) определяет transformation/vertical-slice правила.
- Автор изменения обновляет соответствующий guide и прямые ссылки. Не дублируй инструкции запуска в architecture, exhaustive catalog — в overview, исторический PASS — в текущую гарантию.
- Generated Markdown живёт в `docs/reference/generated/`; JSON/schema — в `contracts/`. Изменяй producer, а не output вручную. Полный список source → output → refresh/check — [GENERATED](../reference/GENERATED_RU.md).
- Сохраняй selectors/units/type/zero/null/absence и пределы proof в тематическом контракте. Не превращай legacy proposal, stale metadata version или fixture prose в текущую механику. Лицензии и upstream notices не сокращаются и не заменяются лицензией проекта.

<a id="history"></a>
## История не является текущей инструкцией

Полные исходники удалённых заметок и прежние пути доступны в Git baseline `42955070e92fd3d5d1ccd867e7061401c1e07b5f`, например:

```bash
git show 42955070e92fd3d5d1ccd867e7061401c1e07b5f:LocalGenerator/infini_local/desktop/webui/FOLDER_DOCS_RU.md
```

Нынешняя навигация от этого пути не зависит. В активных guides остаются только полезные constraints и явные proof limits; historical UI observations свернуты в [MODULES](MODULES_RU.md#studio), подробные release/audit записи — в archive. Список «старый маршрут сохранён» не нужен: старые входы не сохраняются.

## Проверка docs-правки

1. Сверь paths/symbols/команды с source и actual consumer; новый файл/registration не равен исполненному тесту.
2. Проверь local links/anchors, code fences и **rendered table widths**: backticks не защищают неэкранированный pipe внутри ячейки.
3. Для generated changes выполни соответствующий freshness check; для поведения — affected regression по [TESTING](TESTING_RU.md). Не запускай live/game/paid действия ради docs.
4. После параллельной правки дождись законченных writer lanes, затем проверь финальные links/source paths. Не возвращай удалённые shims ради зелёного gate и не называй промежуточную проверку integrated PASS.
