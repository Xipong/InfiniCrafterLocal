# Локальный откат VFX 0.4.243–0.4.244

> Исторический этап перед новым направлением 0.4.245. Описанные здесь эксперименты остаются отменёнными; индивидуальные material elements имеют отдельный контракт в `VFX_MATERIAL_ELEMENTS_RU.md` и не являются восстановлением четырёх масок .244.

Рабочий visual/VFX contract возвращён к `0.4.242`, commit `4271b0bf996cf4152614fa389ad7f6a525f579b4`. Это не откат самого опубликованного `0.4.242` и не новый GitHub release.

## Убрано из активного проекта

- `spriteEmitter` / `texturedRibbon`, их DTO, очередь, mesh/material integration;
- `sharpSpark`, `starFlare`, optional `colorProfile` и связанные профили нового контракта;
- composition guidance, schema branches, compiler/storage integration;
- экспериментальные тесты/документация и bump на `0.4.243` / `0.4.244`.

Существующие до эксперимента renderers, Visual/grip/mount/effectColor, geometry/collision и immutable v3 event snapshots не отменяются. Экспериментальные поля не преобразуются автоматически в старые эффекты; предметы/fixtures, использующие только отменённый контракт, нельзя считать совместимыми с rollback-сборкой. Пользовательские saves/configuration не меняются.

## Независимые исправления, оставленные в рабочем коде

- Один eligible periodic item VFX slot на owner/item/entity/slot/world tick: пересечение held/equipment/visible hooks не удваивает эффект. Разные events и снимки разных ticks остаются независимыми.
- Projectile VFX cadence не дублируется через независимый gameplay periodic event; gameplay actions, delays, authority и порядок событий сохранены.
- Очистка legacy detached queues/budgets через клиентский `PostUpdateEverything`, а не SP/server-only `PostUpdateWorld`; dedicated server не исполняет presentation cleanup.
- Type-aware frozen Repair различает `true`, `1` и `1.0`. Историческое atomic-array поведение сохранено; экспериментальный indexed-array merge убран.

Эти изменения не задают новый художественный стиль и не расширяют model-facing renderer vocabulary.

## Где сохранено переиспользуемое

Во внешнем исследовательском архиве рядом с checkout:
`../artifacts/vfx-rollback-to-0242/README_RU.md` (путь от корня checkout).
Там находятся точный source delta/patch с SHA-256 и отменённые полные локальные поставки. Это архив, не второй активный проект. Native FNA host, pixel blend oracle, ribbon continuity tooling, references и curated captures сохранены в соседних исследовательских папках, перечисленных в его README.

Архив не нужен для сборки/работы данного проекта. Самостоятельный source-generator ZIP содержит текущие исходники и обычные dependency/config examples, но не архив эксперимента, модели или внешние mod DLL.

## Границы проверки

Offline Python/contract gates, сборка против установленного tModLoader и CPU/headless checks проверяют откат и сохранённые технические исправления. Они не означают художественный acceptance, Terraria game-loop или сетевой матч. Ни live-модель, ни игра не запускаются для этого отката. Локальная упаковка не устанавливает мод, не меняет `enabled.json` и не публикует GitHub release.
