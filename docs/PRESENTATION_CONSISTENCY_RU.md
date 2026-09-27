# Presentation consistency: исправления и решения владельца

Исходная версия: `def9cefdad7492182d47f8f11359edf9c1bdf725`. Совместимость проверяется с установленным tModLoader **2026.6.3.6**, upstream tag `v2026.06.3.6`, commit `29bf9785f5f4de8cd305be002c4cc48aa1177b20`.

Это исправление существующих технических контрактов, **не** заявление о завершённой художественной переработке игры. Gameplay Author по-прежнему выбирает механику; новых оружейных presets, name/category routing, model passes или скрытых дизайнерских defaults нет.

## Исправлено

| Область | Нарушение и исправление |
|---|---|
| Руки | Конверсия itemRotation в composite-arm angle учитывает facing и gravity в том же порядке, что установленный vanilla Rapier. Убран повторный gravity flip самого held sprite. |
| Held scale/coordinates | Сохранён результат GetAdjustedItemScale без дополнительных художественных caps. Registry-only scale соответствует существующему ModifyItemScale. World/screen `(0,0)` больше не считается отсутствующим положением; невалидные packet coordinates отделены от нуля. |
| Inventory/world | Custom drawing, возвращавший false, подавлял второй vanilla tint-pass. Восстановлен Item.color overlay с правильным caller color, без повторного alpha. Центр inventory и существующий ground-anchor не переписаны: ошибку их исходной геометрии проверки не подтвердили. |
| Надетые overlays | Используются head/body/leg pivots, локальные rotations/offsets, prepared armor colors и dye. FullRotation применяется один раз downstream-рендерером. Минимальный texture scale больше не раздувает крупный PNG сверх target pixels. |
| Видимость экипировки | Учтены unlocked slots, отдельная social visibility, matching armor slot при vanity replacement. Functional hide не скрывает social overlay. При отсутствии dye storage не заимствуется chest dye. |
| VFX geometry | SpriteBatch scale переводится из требуемых world pixels в source-texel units; толщина линии центрирована. Runtime primitives, включая whip, отделены от sprite quarter-turn; реальное вращение boomerang/flail/yoyo сохранено. |
| VFX history | Число заполненных history samples хранится явно; мировой ноль допустим. Нулевые stationary-сегменты не тратят draw budget. Afterimages согласованы с rotation/flip/gfxOffY текущего тела. |
| VFX blend | Authored additive исполняется на активных и detached sprite путях через alpha-zero vertex color в существующем premultiplied AlphaBlend. RGB/opacity сохраняются; SpriteBatch не перезапускается ради каждого slot. |
| Item effects | Исполняются точный существующий particle selector и sound pitch mapping. Поздний relay от inactive player не создаёт эффект. Explicit particleSystemId=none не заменяется diamond dust; sprite/light/sound остаются независимыми. |
| PNG upload | Straight RGBA переводится в premultiplied RGB ровно при cache insertion, как у tML PNG reader. Alpha, PNG bytes и PCA-mask сохраняются; cache hits не преобразуются повторно; при ошибке upload/readback ресурс не публикуется. |
| Sprite canvas | Разрешённые 128 px проходят plan → generation dispatch → реальный Pillow bake без скрытого cap 96. Нормированные центры rectangular raw images вычисляются x/width, y/height. |
| Chroma transport | Prompt, keyer и retry используют один mapping. White/black/cyan и старые aliases согласованы; magenta-only spill heuristics не применяются к другому key. Unknown key даёт диагностическую ошибку. Model rules различают transparent final PNG и solid-key raw input; свободный authored текст не переписывается regex. |
| Item budget | Общий per-tick particle allowance для slots/events одного owner/item/entity. Не введён выдуманный бессрочный total-budget: он навсегда гасил бы повторно используемый предмет. Явный нулевой budget остаётся тишиной. World-clock cadence сохранён: StartTick документирован для возраста projectile, не item. |

## Проверки и границы доказательств

Регрессии подключены в оба canonical owners: `tools/EngineRuntimeChecks.csproj` и `tools/EngineRuntimeChecks.cs`. Реальные tML Item/Player/DrawData, FNA CPU vertex queues, Dust/light queues и socket-free packet decoder используются без запуска игры. GPU FlushBatch перехватывается только на границе отправки в graphics device.

- Held: baseline RED по rotation/scale/coordinates; контроли facing/gravity, scale endpoints, packet rejection и registry-only presentation.
- Inventory/world: baseline RED по отсутствующему tint-pass; полные UV, odd/non-square canvases, caller scales, rotation и ground anchor.
- Equip: baseline RED по double rotation и скрытому social overlay; реальные downstream transform/scale и unlock predicates.
- Active VFX: RED→GREEN для pixel units, history, blend, sprite pose, primitive forward и explicit none.
- Detached blend: RED vertex `{R:153 G:41 B:0 A:153}` вместо authored-additive `{R:153 G:41 B:0 A:0}`; после исправления проверяются alpha/additive на emission и mid-lifetime.
- Старые проверки не удалены: visibility fixture явно разблокирует семь slots, particle fixture явно выбирает dust и сбрасывает оба emitter cache между независимыми случаями. Static texture-routing assertion обновлён под cache overload без PCA; pose проверяется реальными FNA vertices.

Итоговая локальная проверка:

- **1421 Python tests passed**, Ruff clean, Pyright 0 errors / 0 warnings.
- **84 canonical C# checks passed**, включая новую cache-ingestion проверку.
- Обычная **Debug и Release DLL compilation: 0 errors / 0 warnings**.
- **12 contract/schema/hygiene gates** и **8 CI-classifier regressions** passed.
- `.tmod` собран SDK PackageMod из allowlisted staging. Установленный tML TmodFile прочитал **все 13 entries**; embedded DLL SHA256 совпал с новой Release DLL. В пакете нет launchSettings, source docs, PDB, локальных configs или dependency DLL. ParticleLibrary/Luminance остаются внешними зависимостями из build.txt.
- Пакет имеет внутреннюю версию `0.4.241`, tML `2026.6.3.6`; release tag отдельно идентифицирует presentation snapshot. Source commit и SHA256 публикуются рядом с артефактом.

Headless/DLL/package checks **не доказывают** качество GPU-картинки, texture upload, полноту game loop, реальный звук или two-client multiplayer. Cache test подставляет decoded pixels на FromStream boundary и перехватывает GPU readback/upload; это не end-to-end PNG decoder test. Новый Live20 не запускался; прежние captured results не переименованы в GREEN.

## Решения мейнтейнера — не реализованы молча

### 1. Хват, направленность и техническая роль изображения

Существующие held origins/forward offsets — фиксированные художественные допущения. Entity asset ID вида `entity_<id>` также не равен geometry role: неизвестная роль попадает в старый item processing contract.

**Рекомендация:** отдельный полный контракт asset metadata: grip/pivot, declared local-forward и crop transform; техническую processing role передавать отдельно от identity. Для directional assets можно согласовать +X generation convention. Не выводить острие из имени/класса, не считать PCA/taper семантическим детектором и не заменять хват универсальным bbox-center.

Нужно также определить, означает ли holdoutOffsetX screen-space translation текущего custom renderer или facing-dependent vanilla origin adjustment. Значения сохранённых предметов нельзя молча переинтерпретировать. Различия `overhead`/`forward` требуют явного pose-контракта.

### 2. Настоящая одежда или существующий overlay

Сейчас это корректно прикреплённый **один PNG**, не tML armor atlas. Accessory orbit сохранён, не заменён guessed shoulder/back/belt attachment.

**Рекомендация:** если нужна именно надеваемая броня — отдельные head/body/legs atlases, animation/frame layout и coverage flags; accessories получают явный mount/layer/pivot. Пока такого контракта нет, не скрывать vanilla кожу/руки. Sitting segmentation, modded accessory slots и head-only portraits не заявлены как поддержанные.

### 3. Полноценная библиотека VFX форм и anchors

Существующие имена не гарантируют разные реализации: `tipTrail=historyRibbon`, `wavyStrip=beamLine`, `fieldPulse/orbitingMotes/ghostArc` используют cross. У текущего vocabulary нет однозначных параметров частоты волны, aperture дуги, числа/скорости орбит и фазы пульса; scale prose описывает прежние beam/cross размеры.

**Рекомендация:** параметризованные renderer primitives с реальными consumers и понятными единицами, а не готовые sword/bow/staff presets. Согласовать geometry/anchor contract и сохранить authored свободу. Beam length сейчас не обещает совпадение с controller collision range. Item contact VFX получают player center; relay не переносит hit coordinates. Для hitPoint нужен сквозной event-position transport; для tip — определение геометрического tip. Не объявлять общий anchor selector уже исполненным.

### 4. Частицы, мягкая alpha и цветовая политика

Active manifest path использует direct Dust/FNA. Наличие зависимостей ParticleLibrary/Luminance не означает, что старый `VfxFoundation` исполняет эти slots.

**Рекомендация:** сначала сделать текущий backend честным и полным; подключать ParticleLibrary отдельным vertical slice, если нужны его возможности. Для изображений — hard-alpha item/equipment и soft-alpha impact/effects как отдельное согласованное изменение bake policy. GPU premultiplication и художественная hard/soft-alpha политика — разные задачи.

Нужно выбрать один явный color authority: item dust/light сейчас используют Visual palette, impact sprites — motif mapping. Массовое изменение saturation/gamma/intensity не является исправлением tML semantics.

### 5. Lifetime и event relay

У item-body нет канонического activation/lifetime ID для положительного MaxParticlesTotal. **Рекомендация:** определить activation scope и retirement отдельно; пока исполнять per-tick cap и explicit zero, а не total на всё время удержания предмета. Single per-player relay cooldown также может подавлять соседние on_use/on_hit/on_crit; изменение транспортного бюджета требует event-aware dedup/rate policy, а не отключения защиты.

## Закреплённые источники

Источники других модов — примеры решений, не ABI-гарантия и не разрешение копировать их параметры в generated content.

- [tML PlayerDrawLayers](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/patches/tModLoader/Terraria/DataStructures/PlayerDrawLayers.cs.patch), [PlayerDrawSet](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/patches/tModLoader/Terraria/DataStructures/PlayerDrawSet.cs.patch), [LegacyPlayerRenderer](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/patches/tModLoader/Terraria/Graphics/Renderers/LegacyPlayerRenderer.cs.patch): local/global transform ownership.
- [tML ItemSlot](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/patches/tModLoader/Terraria/UI/ItemSlot.cs.patch), [custom item drawing](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/ExampleMod/Content/Items/CustomItemDrawingShowcase.cs): inventory colors/position/scale.
- [ExampleGun](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/ExampleMod/Content/Items/Weapons/ExampleGun.cs), [ExampleCustomSwingProjectile](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/ExampleMod/Content/Projectiles/ExampleCustomSwingProjectile.cs): явный holdout и composite arms.
- [ExampleBullet](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/ExampleMod/Content/Projectiles/ExampleBullet.cs): trail history, rotation, gfxOffY.
- [tML PNG reader](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/patches/TerrariaNetCore/ReLogic/Content/Readers/PngReader.cs.patch): straight PNG → premultiplied upload.
- Calamity `1a8cebd27ec5615316b78f71973446b5528d2b78`: [laser geometry](https://github.com/CalamityTeam/CalamityModPublic/blob/1a8cebd27ec5615316b78f71973446b5528d2b78/Projectiles/BaseProjectiles/BaseLaserbeamProjectile.cs), [held glow layer](https://github.com/CalamityTeam/CalamityModPublic/blob/1a8cebd27ec5615316b78f71973446b5528d2b78/CalPlayer/DrawLayers/HeldItemGlowMaskLayer.cs), [Auric armor](https://github.com/CalamityTeam/CalamityModPublic/blob/1a8cebd27ec5615316b78f71973446b5528d2b78/Items/Armor/Auric/AuricTeslaBodyArmor.cs).
- Fargo Souls `226fadeadbe3422785a7708ba2cdf53bd8548c00`: [MutantArmorDrawLayer](https://github.com/Fargowilta/FargowiltasSouls/blob/226fadeadbe3422785a7708ba2cdf53bd8548c00/Content/PlayerDrawLayers/MutantArmorDrawLayer.cs), [TerraForce](https://github.com/Fargowilta/FargowiltasSouls/blob/226fadeadbe3422785a7708ba2cdf53bd8548c00/Content/Items/Accessories/Forces/TerraForce.cs): frame-local origin и отдельные equip assets.
