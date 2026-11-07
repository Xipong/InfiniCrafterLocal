# Presentation: активные render contracts и ограничения

Это описание существующего Dust/FNA runtime и принятых Visual/VFX choices, не заявление о завершённой художественной переработке, GPU/game-loop или MP-приёмке. Gameplay остаётся у Author; нет presets, name/category routing, дополнительных LLM passes, atlas/skeleton/shader framework.

<a id="draw"></a>
## Item/held/equipment consumers

| Граница | Сохраняемый контракт |
|---|---|
| Composite arms / facing / gravity | `itemRotation` переводится в arm angle в vanilla Rapier порядке; held sprite не получает второй gravity flip. Runtime primitive forward не наследует sprite quarter-turn; явный `rotate_sprite` задаёт реальное вращение. |
| Held scale/coordinates | `GetAdjustedItemScale` без художественного cap; registry-only scale совпадает с `ModifyItemScale`. World/screen `(0,0)` допустим; invalid/nonfinite packet coordinates отделены от нуля. |
| Inventory/world | Custom drawing исполняет caller color и `Item.color` tint-pass без повторного alpha; full UV, non-square/odd canvases, rotation/scale и существующий ground-anchor сохраняются. Центр inventory не переопределяется без доказанного дефекта. |
| Equipment transforms | Single PNG использует head/body/leg pivots, local rotations/offsets, prepared armor colors/dye. Downstream renderer применяет FullRotation один раз; minimum texture scale не раздувает PNG сверх target fit. |
| Visibility | Unlocked slots и social visibility отдельны; vanity replacement проверяет matching armor slot. Native `ModAccessorySlot` сохраняет functional/vanity gates, shared-loadout conflicts и paired dye владельца. Functional hide не скрывает social overlay; отсутствующий dye storage не заимствует chest dye. |
| Authored placement | Grip, mounts, optional-null/Repair и HoldoutOffset semantics определены **только** в [Visual metadata](VISUAL_PRESENTATION_METADATA.md). `back` mount не гарантирует occlusion/layer. |
| Pixel processing | 128 px item canvas проходит actual bake без cap 96; rectangular normalized raw centers используют x/width,y/height. Image contracts — [Visual guide](VISUAL_PRESENTATION_METADATA.md#image-contract); upload/retirement — [lifecycle](../../development/pipeline/IMAGE_ASSET_LIFECYCLE_RU.md#bytes). |

Броня остаётся single-PNG overlay, не tML armor atlas. Accessory orbit не заменяется guessed shoulder/back/belt attachment. Полные head/body/legs atlases, animation/frame layout, coverage flags, sitting segmentation и head-only portraits не заявлены как поддержанные. Пока нет такого отдельного контракта, нельзя скрывать vanilla кожу/руки ради воображаемого atlas.

<a id="renderers"></a>
## Текущие VFX формы

Source of truth — [renderer semantics](../../../generator/infini_local/core/vfx/contract.py), [schema](../../../generator/infini_local/core/vfx/schema.py), [validation](../../../generator/infini_local/core/vfx/validation.py) и C# `VfxRendererRegistry`. Director, Repair и persisted manifest используют одну текущую renderer grammar.

| Renderer | Исполняемый смысл и owner payload |
|---|---|
| `shape` | Явная geometry, dimensions, motion, opacity endpoints; не preset формы по имени предмета |
| `contour` | Авторская bounded полилиния/контур с явными точками и transforms |
| `historyTrail` | Действительная история источника и выбранный способ её отображения, без выдуманных samples |
| `nativeDust` | Явные native Dust selectors и controls; не ParticleLibrary substitute |
| `nativeLight` | `Lighting.AddLight` с явными цветом и интенсивностью, не drawn glow |
| `nativeEffect` | Явный finite native visual effect; gameplay не добавляется |
| `libraryParticle` | Реальные ParticleLibrary instances с выбранными texture/motion/color/lifetime |
| `soundCue` | Explicit `soundId` и `sound={volume,pitch,pitchVariance}`; [sound contract](VFX_SOUND_PALETTE_RU.md) |
| `screenShakeCue` | Explicit Luminance camera cue; strength/dissipation не выводятся из damage |
| `spriteElement`, `texturedPath` | [Материалы](VFX_MATERIAL_ELEMENTS_RU.md): texture, profiles, attachment/path и lifetime принадлежат nested payload |

Common поля не универсальны: schema запрещает controls, которые выбранный consumer не читает. Не дополняй slot нейтральными placeholders и не переноси параметры другой renderer ветви. Пустой `slots=[]` — допустимая тишина.

Conditional dependencies должны присутствовать в actual runtimeSurface и outputSchema Director/Repair, включая json_object transport. Диагностика даёт точный leaf; Repair сначала проверяет структуру patch, затем frozen merge и полный output. Frozen renderer не меняется ради починки соседнего числа. Если после bounded Repair контракт невалиден, manifest не создаётся.

PNG selector и обязательность asset выводятся только из принятого renderer payload: [одна dependency projection](../../development/pipeline/IMAGE_ASSET_LIFECYCLE_RU.md#dependencies). Missing PNG не заменяется inventory image, белым quad или Dust.

<a id="anchors"></a>
## Anchors, geometry и immutable events

- Primitive/cue/event `self|field` — bound entity center; `owner` — active owner center; `tip|tipHistory` — geometric projectile tip (item: engine itemLocation); `velocity` — center + motion axis; `hitPoint` — captured event point (item hit/crit: NPC center). Без item hitPoint/доступного owner — тишина, не guessed self.
- Event snapshots захватывают center/tip/forward/owner center/позицию цели и sprite pose **в момент события**. Перемещение/удаление источника и late relay не меняют этот снимок.
- Center/tip history хранит число заполненных samples; мировой ноль допустим. Stationary нулевые segments не тратят draw budget; named history renderer не переносит trajectory к произвольному anchor.
- Pixel width переводится в source-texel SpriteBatch units, линия центрируется. `runtime_geometry` для явно выбранных beam/lash components использует canonical collision points/width; это не новая механика/дальность. Decorative shape и `texturedPath.widthPx` collision не меняют.

<a id="color-budget"></a>
## Цвет, alpha, particles, lifetime и budget

Цвет VFX задаётся локально как `{r,g,b}`: каждый канал — integer 0..255, без alpha, названий, hex/prose parsing или global color reference. Native Dust/light используют собственный явный цвет; `spriteElement`/`texturedPath` требуют RGB knots собственного `colorProfile`, `libraryParticle` — `colorStart`/`colorEnd`. Sound/camera cues не принимают `color`. `{r:255,g:255,b:255}` сохраняет RGB текстуры; opacity задаётся отдельно. Visual `palette` описывает art для image generation, не выбирает runtime tint. Gameplay light tokens — отдельный capability contract.

Authored additive на active/detached sprite/primitive paths масштабирует RGB/opacity и выставляет vertex alpha=0 в существующем premultiplied AlphaBlend; не перезапускает SpriteBatch для каждого slot. Alpha-mode сохраняет alpha. Straight PNG upload и hard/soft bake различны; ноль не заменяется default opacity.

`nativeDust` испускает выбранный Dust независимо от library, light, sprite и sound lanes. `libraryParticle` принадлежит `InfiniDetachedVfxSystem.Library`. Отключённый backend подавляет свою lane без подстановки другой; звук использует только явные playback controls.

Сохраняемые common controls имеют renderer-specific units: [units guide](../authoring/MODEL_FACING_UNITS_RU.md#vfx). Периодический procedural shape анимируется world clock; simulation/lifetime не живёт в Draw. Shared source/world-tick particle allowance охватывает slots/events одного owner/item/entity. Nonperiodic item event дополнительно имеет event-local total; periodic не получает бессрочный cap удержания или cap одной emission-группы. Explicit total=0 — запрет. Projectile lifetime ledger и draw/resource caps сохраняются.

Eligible periodic item slot исполняется один раз на owner/item/entity/slot/world tick даже при пересечении held/equipment/visibility hooks; projectile VFX cadence не дублируется gameplay periodic producer. Разные events и snapshot ticks самостоятельны; соседние use/hit/crit не гасят друг друга одним per-player cooldown. Transport rate/dedup защита остаётся. Поздний inactive-player relay не создаёт effects. Queues/budgets очищает клиентский `PostUpdateEverything`, не SP/server-only `PostUpdateWorld`; dedicated server не исполняет presentation.

## Текстовые поля и границы длины

Имя результата принадлежит Gameplay Author, `visual.palette` — art context Visual Director. Исполняемый VFX определяется explicit `slots`; пустой `slots=[]` не создаёт частицы из prose. Optional advisory reports не становятся verdict router или причиной Repair.

| Текст | Fresh предел, Unicode code points | Смысл / сохранение |
|---|---:|---|
| Author `name` | 80 | Schema/Repair/final gate и native definition identity. |
| Visual `palette[]` | 256 на запись, до 8 записей | Свободные описания цвета/материала для image generation, не renderer tint. |
| Optional Author `description`, `playerExperience`, `selfEvaluation` | 4000 / 3000 / 4000 | Advisory text; parent summary сохраняет description/playerExperience, не structural verdicts. |
| Visual body/impact/VFX asset prompts | 1400 / negative 700 | Generation input; native считает Unicode scalars, не UTF-16 units. |

IDs/enums/schema/path/hash и численные resource bounds не расширяются вместе с human prose. MaxLength — потолок, не требуемый объём ответа.

<a id="verification"></a>
## Проверка и scope доказательства

Python owners: `test_sprite_render_contracts.py`, `test_visual_presentation_metadata.py`, `test_visual_vfx_prompt_prefix.py`, `test_vfx_packet_contracts.py`, `test_vfx_frozen_boundary_contracts.py`; C# consumers исполняет existing `tests/native/EngineRuntimeChecks.csproj` с зарегистрированными presentation/VFX checks. Порядок и environment bounds — [test owners](../../development/TESTING_RU.md).

Real tML Item/Player/DrawData, FNA CPU vertices, Dust/Lighting queues и socket-free decoder доказывают соответствующие seams. Texture shells/intercepted GPU flush/upload/readback не доказывают GPU PNG decoder/upload, реальный звук, Terraria game-loop, socket delivery или two-client MP. Hand-authored native fixtures не доказывают LLM/image artistic quality или физическое попадание authored grip в нарисованную рукоять. Новый live screen требует отдельного разрешения, не статус старого лога.

<a id="references"></a>
## Закреплённые references

Источники других модов — примеры решений, не ABI-гарантия и не разрешение копировать их параметры в generated content.

- [tML PlayerDrawLayers](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/patches/tModLoader/Terraria/DataStructures/PlayerDrawLayers.cs.patch), [PlayerDrawSet](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/patches/tModLoader/Terraria/DataStructures/PlayerDrawSet.cs.patch), [LegacyPlayerRenderer](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/patches/tModLoader/Terraria/Graphics/Renderers/LegacyPlayerRenderer.cs.patch): local/global transform ownership.
- [tML ItemSlot](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/patches/tModLoader/Terraria/UI/ItemSlot.cs.patch), [custom item drawing](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/ExampleMod/Content/Items/CustomItemDrawingShowcase.cs): inventory colors/position/scale.
- [ExampleGun](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/ExampleMod/Content/Items/Weapons/ExampleGun.cs), [ExampleCustomSwingProjectile](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/ExampleMod/Content/Projectiles/ExampleCustomSwingProjectile.cs): явный holdout и composite arms.
- [ExampleBullet](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/ExampleMod/Content/Projectiles/ExampleBullet.cs): trail history, rotation, gfxOffY.
- [tML PNG reader](https://github.com/tModLoader/tModLoader/blob/29bf9785f5f4de8cd305be002c4cc48aa1177b20/patches/TerrariaNetCore/ReLogic/Content/Readers/PngReader.cs.patch): straight PNG → premultiplied upload.
- Calamity `1a8cebd27ec5615316b78f71973446b5528d2b78`: [laser geometry](https://github.com/CalamityTeam/CalamityModPublic/blob/1a8cebd27ec5615316b78f71973446b5528d2b78/Projectiles/BaseProjectiles/BaseLaserbeamProjectile.cs), [held glow layer](https://github.com/CalamityTeam/CalamityModPublic/blob/1a8cebd27ec5615316b78f71973446b5528d2b78/CalPlayer/DrawLayers/HeldItemGlowMaskLayer.cs), [Auric armor](https://github.com/CalamityTeam/CalamityModPublic/blob/1a8cebd27ec5615316b78f71973446b5528d2b78/Items/Armor/Auric/AuricTeslaBodyArmor.cs).
- Fargo Souls `226fadeadbe3422785a7708ba2cdf53bd8548c00`: [MutantArmorDrawLayer](https://github.com/Fargowilta/FargowiltasSouls/blob/226fadeadbe3422785a7708ba2cdf53bd8548c00/Content/PlayerDrawLayers/MutantArmorDrawLayer.cs), [TerraForce](https://github.com/Fargowilta/FargowiltasSouls/blob/226fadeadbe3422785a7708ba2cdf53bd8548c00/Content/Items/Accessories/Forces/TerraForce.cs): frame-local origin и отдельные equip assets.

Эти pinned upstream/mod examples — provenance решений, не обещание текущего установленного tML ABI.
