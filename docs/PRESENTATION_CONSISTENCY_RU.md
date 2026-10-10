# Presentation: активные render contracts и ограничения

Это описание существующего Dust/FNA runtime и принятых Visual/VFX choices, не заявление о завершённой художественной переработке, GPU/game-loop или MP-приёмке. Gameplay остаётся у Author; нет presets, name/category routing, дополнительных LLM passes, atlas/skeleton/shader framework.

<a id="draw"></a>
## Item/held/equipment consumers

| Граница | Сохраняемый контракт |
|---|---|
| Composite arms / facing / gravity | `itemRotation` переводится в arm angle в vanilla Rapier порядке; held sprite не получает второй gravity flip. Runtime primitive forward не наследует sprite quarter-turn; boomerang/flail/yoyo сохраняют реальное вращение. |
| Held scale/coordinates | `GetAdjustedItemScale` без художественного cap; registry-only scale совпадает с `ModifyItemScale`. World/screen `(0,0)` допустим; invalid/nonfinite packet coordinates отделены от нуля. |
| Inventory/world | Custom drawing исполняет caller color и `Item.color` tint-pass без повторного alpha; full UV, non-square/odd canvases, rotation/scale и существующий ground-anchor сохраняются. Центр inventory не переопределяется без доказанного дефекта. |
| Equipment transforms | Single PNG использует head/body/leg pivots, local rotations/offsets, prepared armor colors/dye. Downstream renderer применяет FullRotation один раз; minimum texture scale не раздувает PNG сверх target fit. |
| Visibility | Unlocked slots и social visibility отдельны; vanity replacement проверяет matching armor slot. Functional hide не скрывает social overlay; отсутствующий dye storage не заимствует chest dye. |
| Authored placement | Grip, mounts, effectColor, optional-null/Repair и HoldoutOffset semantics определены **только** в [Visual metadata](VISUAL_PRESENTATION_METADATA.md). `back` mount не гарантирует occlusion/layer. |
| Pixel processing | 128 px item canvas проходит actual bake без cap 96; rectangular normalized raw centers используют x/width,y/height. Image contracts — [Visual guide](VISUAL_PRESENTATION_METADATA.md#image-contract); upload/retirement — [lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md#bytes). |

Броня остаётся single-PNG overlay, не tML armor atlas. Accessory orbit не заменяется guessed shoulder/back/belt attachment. Полные head/body/legs atlases, animation/frame layout, coverage flags, sitting segmentation, modded accessory slots и head-only portraits не заявлены как поддержанные. Пока нет такого отдельного контракта, нельзя скрывать vanilla кожу/руки ради воображаемого atlas.

<a id="legacy-vfx"></a>
## Реальные VFX формы и companion requirements

Source of truth — [vfx_manifest.py](../LocalGenerator/infini_local/core/vfx_manifest.py): `_RENDERER_REQUIREMENTS`, `_RENDERER_SEMANTICS`, Director/Repair schemas и diagnostics; C# consumers — [InfiniVfxRuntime](../ModSources/InfiniCrafterLocal/Common/VFX/InfiniVfxRuntime.cs), [item runtime](../ModSources/InfiniCrafterLocal/Common/VFX/InfiniItemVfxRuntime.cs), [detached runtime](../ModSources/InfiniCrafterLocal/Common/VFX/InfiniDetachedVfxSystem.cs).

| Renderer | Исполняемый смысл |
|---|---|
| `projectileAfterimage`, `spriteStampTrail`, `actorAfterimage` | Projectile periodic: реальные textured history samples, не fabricated history. Projectile event: snapshot body rotation/scale/flip/gfxOffY; event scale = clamp(projectile.scale,.1,8) × slot.Scale. Item: направленный texture stamp, не player/held animation atlas. |
| `historyRibbon` | Связная center history, 20 world samples, fade к старому краю; `on_spawn` может начать live trail. |
| `tipTrail` | История geometric tip = center + forward × projectile.width × projectile.scale/2, не PNG/PCA nose. |
| `wavyStrip` | Одна animated sine wave: длина 48×scale px, amplitude 6×scale px, thickness max(1,2×scale), 8+round(16×density) segments. |
| `beamLine` | Decorative straight segment max(20,48×scale) px, thickness max(1,2×scale); не меняет collision range. |
| `fieldPulse` | Expanding ring: radius scale×(6+18×phase) px, 12+round(20×density) segments, opacity ×(1−phase). |
| `orbitingMotes` | 2+round(6×density) square motes, сторона 3×scale px, radius 18×scale px, оборот за procedural period. |
| `ghostArc` | Rotating open 120° arc, radius 24×scale px, 8+round(12×density) segments, fade head→tail. |
| `impactRing` | Expanding ring: radius scale×(4+28×phase) px, 12+round(20×density) segments. Выбранные particles независимы. |
| `impactSprite` | Dedicated generated impact PNG, duration world ticks + linear fade; `textureRole=impact` и непустой `spritePrompt`, не inventory/Dust substitute. |
| `childMotes` | Bounded выбранный Terraria Dust, не gameplay children. |
| `lightCue` | World Lighting, не drawn glow/trail: **channel=light, lane=cue**. |
| `soundCue` | Exact finite `soundId` на resolved anchor: **channel=sound, lane=cue**; fresh output требует `sound={volume,pitch,pitchVariance}`. [Sound contract](VFX_SOUND_PALETTE_RU.md) сохраняет прежний alpha/phase/native-variance путь только при отсутствии `sound` в saved wire. |
| `spriteElement`, `texturedPath` | Полный отдельный [material contract](VFX_MATERIAL_ELEMENTS_RU.md), не наследование legacy scale/density/lifetime semantics. |

Conditional dependencies обязаны присутствовать в actual runtimeSurface и outputSchema Director **и Repair**, в том числе при json_object transport: отдельные enum lists их не сообщают. `allOf`/semantic diagnostics дают точный leaf error, не whole-slot размораживание. Код не дописывает lane/channel/textureRole. Repair сначала проверяет patch structure, затем frozen merge и full final constraints; попытка изменить frozen lane не отменяет полезный разрешённый leaf fix. Если tuple после bounded Repair невалиден — manifest не создаётся. Selected PNG dependencies — [одна projection](IMAGE_ASSET_LIFECYCLE_RU.md#dependencies).

<a id="anchors"></a>
## Anchors, geometry и immutable events

- Primitive/cue/event `self|field` — bound entity center; `owner` — active owner center; `tip|tipHistory` — geometric projectile tip (item: engine itemLocation); `velocity` — center + motion axis; `hitPoint` — captured event point (item hit/crit: NPC center). Без item hitPoint/доступного owner — тишина, не guessed self.
- Event snapshots захватывают center/tip/forward/owner center/позицию цели и sprite pose **в момент события**. Перемещение/удаление источника и late relay не меняют этот снимок. Историческое сравнение .242 packet v3 с v2 — [provenance](VISUAL_AUDIT_HISTORY_RU.md#presentation); текущий transport проверяется у consumers, не определяется названием релиза.
- Center/tip history хранит число заполненных samples; мировой ноль допустим. Stationary нулевые segments не тратят draw budget; named history renderer не переносит trajectory к произвольному anchor.
- Pixel width переводится в source-texel SpriteBatch units, линия центрируется. `runtime_geometry` для уже выбранных ChannelBeam/whip использует canonical collision points/width; это не новая механика/дальность. Decorative `beamLine` и `texturedPath.widthPx` collision не меняют.

<a id="color-budget"></a>
## Цвет, alpha, particles, lifetime и budget

`effectColor` — один явный rendering token Visual для item/projectile/detached VFX. Rich art palette не парсится как hex/prose color; motif не перебивает explicit effectColor. Отсутствие сохраняет legacy paths (включая historical palette-color item primitives рядом с Dust), без migration. Mass saturation/gamma/intensity change — новое художественное решение, не tML bugfix.

Authored additive на active/detached sprite/primitive paths масштабирует RGB/opacity и выставляет vertex alpha=0 в существующем premultiplied AlphaBlend; не перезапускает SpriteBatch для каждого slot. Alpha-mode сохраняет alpha. Straight PNG upload и hard/soft bake различны; ноль не заменяется default opacity.

`particleSystemId` — exact Terraria selector: `dust=GemDiamond`, `pl:glow=TintableDustLighted`, `pl:shard=Glass`, `pl:smoke=Smoke`, `pl:spark=Electric`, `none` подавляет только particles. Название `pl:*` и установленные ParticleLibrary/Luminance не означают исполнения ParticleLibrary instances старым VfxFoundation; rendererKind выбирает Dust/FNA path, legacy backend — hint. Свет/sprite/звук независимы от particle selector/cap; item sound исполняет существующий pitch mapping.

Legacy common controls имеют renderer-specific units и inert metadata: [units guide](MODEL_FACING_UNITS_RU.md#vfx). Периодический procedural shape анимируется world clock; simulation/lifetime не живёт в Draw. Shared source/world-tick particle allowance охватывает slots/events одного owner/item/entity. Nonperiodic item event дополнительно имеет event-local total; periodic не получает бессрочный cap удержания или cap одной emission-группы. Explicit total=0 — запрет. Projectile lifetime ledger и draw/resource caps сохраняются.

Eligible periodic item slot исполняется один раз на owner/item/entity/slot/world tick даже при пересечении held/equipment/visibility hooks; projectile VFX cadence не дублируется gameplay periodic producer. Разные events и snapshot ticks самостоятельны; соседние use/hit/crit не гасят друг друга одним per-player cooldown. Transport rate/dedup защита остаётся. Поздний inactive-player relay не создаёт effects. Legacy queues/budgets очищает клиентский `PostUpdateEverything`, не SP/server-only `PostUpdateWorld`; dedicated server не исполняет presentation.

<a id="verification"></a>
## Проверка и scope доказательства

Python owners: `test_sprite_render_contracts.py`, `test_visual_presentation_metadata.py`, `test_visual_vfx_prompt_prefix.py`, `test_vfx_packet_contracts.py`, `test_vfx_frozen_boundary_contracts.py`; C# consumers исполняет existing `tools/EngineRuntimeChecks.csproj` с зарегистрированными presentation/VFX checks. Порядок и environment bounds — [test owners](TEST_CONTRACT_OWNERS_RU.md).

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

Эти pinned upstream/mod examples — provenance решений, не обещание текущего установленного tML ABI. Исторические verification counts, baseline RED→GREEN и package observations — [presentation record](VISUAL_AUDIT_HISTORY_RU.md#presentation), не current-green stamp.
