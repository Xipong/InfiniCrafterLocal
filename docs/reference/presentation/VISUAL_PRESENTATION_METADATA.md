# Visual Director: проекты и explicit presentation metadata

<a id="owners"></a>
## Visual ownership и authored surface

Visual Director выбирает внешний вид принятого gameplay, не mechanics/classifier outputs. Одна физическая вещь имеет один visual project; отдельный объект — отдельный. `item_body` всегда требует отдельный inventory PNG: единственный missing-mode Fix допускается только при уже непустых `prompt`, `silhouette`, `visualIdentity` и добавляет `baked_sprite` с audit. Без описания — Visual Repair/RED, не artwork из кода.

Источник ordinary/Repair schema и dispatch — [Visual contract](../../../LocalGenerator/infini_local/pipelines/visual/contract.py); projects/processing role — [visual_asset_plan.py](../../../LocalGenerator/infini_local/pipelines/visual/assets.py). Director root: `schema`, `item`, одна `entities` запись на runtime entity, optional advisory текст `animationPlan` (не основание для Repair); `equipOverlay` обязателен только для объявленной equipment потребности. Root `item` — единственный автор внешности тела предмета: его `prompt`, `silhouette`, `visualIdentity` не дублируются в `entities`. Существующий projector выбирает этот root по `visualProjectRef=item`, не восстанавливает копии в `visualKit`. Поэтому Repair root-текста не открывает permissions на entity rows. Отдельный baked entity по-прежнему обязан полностью описать собственный проект; missing/invalid root-дизайн остаётся RED. Сохранённые delivered DTO и их presentation не мигрируются.

| Entity branch | Обязательная Visual запись |
|---|---|
| item-body `baked_sprite` | `entityId`, `assetMode`, `visualProjectRef=item`, `scale`; дизайн, размер/canvas/ось принадлежат только root item; повторные `prompt`/`silhouette`/`visualIdentity` запрещены |
| distinct `baked_sprite` | `entityId`, `assetMode`, `visualProjectRef=entity`, `prompt`, `silhouette`, `visualIdentity`, `scale`, собственные `renderSizePx`, `preferredCanvasSize`, `forwardAngleDegrees` |
| `reuse_item_icon` | `entityId`, `assetMode`, `visualProjectRef=item`, `scale`; exact root PNG, base size, canvas и ось; свои prompt/size/canvas/axis запрещены |
| `runtime_geometry`, `no_asset` | `entityId`, `assetMode`, `visualProjectRef=none`, `scale`; не authored sprite prompts |

`entityId` ссылается на уже принятый runtime entity. `scale` [.25,4] — visual multiplier, не hitbox, в том числе для `no_asset`. Из exact mode/identity может losslessly нормализоваться единственный `visualProjectRef`; это не разрешение угадать mode или дизайн. Impact PNG запрашивает только выбранный поздний VFX `impactSprite`, а не обязательный ранний Visual `impactPrompt` для каждой entity. VFX ingredients принадлежат VFX, не меняют основной Visual.

<a id="image-contract"></a>
## Изображение, canvas и художественная граница

Fresh Visual v2 item требует `prompt`, `negativePrompt`, `silhouette`, `visualIdentity`, `palette`, `preferredCanvasSize`, `renderSizePx`, `forwardAngleDegrees`, `inventoryScale`, `worldScale`. Непустые authored descriptions обязательны; длины/число palette entries — schema transport bounds, не художественные units. Canvas item: 24/32/48/64/96/128 PNG px; overlay: 32/48/64/96 PNG px. Это side final square canvas, **не** мировой footprint, silhouette bbox или размер overlay на игроке. `inventoryScale` и `worldScale` [.25,4] — независимые draw multipliers после fit; нейтраль 1. Runtime hitbox — read-only gameplay context.

Processing role отделена от произвольного entity ID: identity вроде `entity_<id>` не является geometry role. Directional convention обязана соответствовать renderer: +X canonicalization нельзя применять поверх native +Y rotation; PCA/taper не semantic detector носа/рукояти. Authored design/palette/silhouette не переписываются name/category/regex heuristics.

Item/equipment сохраняют hard pixel alpha, impact/effect — soft alpha. Straight RGBA PNG premultiplies только при runtime upload, не вместо bake policy. Final PNG transparent; raw backend input может требовать solid chroma key по [sprite_contracts.py](../../../LocalGenerator/infini_local/core/images/contracts.py). Prompt/keyer/retry используют один mapping (white/black/cyan и retained aliases); magenta-only spill не применяется к другому key, unknown key диагностируется. Нельзя путать raw solid-key background с непрозрачным final PNG или восстанавливать arbitrary alpha, уже сплющенную provider на opaque фон.

<a id="size-axis"></a>
## Base world size, final-PNG axis и независимый canvas

Authoring schemas: `infini.visual-kit.runtime-entities.v2` и `infini.visual-kit-repair-patch.runtime-entities.v2`. Новый full Author не принимает v1/missing choices. Delivered runtime wire не меняет version: отсутствие всех новых полей в сохранённом DTO остаётся допустимым и не мигрируется; explicit null, bool/string, неверный тип, NaN/infinity и out-of-bounds отвергаются, не округляются/clamp-ятся.

- `renderSizePx` — integer `1..512`, большая сторона **полного final PNG frame** в base world pixels до rotation/camera/independent multipliers. Не alpha-bbox, hitbox, физическая длина древка или inventory slot. Если `C=max(actual final frame width,height)`, техническая конверсия `q=R/C`. Requested canvas не используется вместо реального C.
- `forwardAngleDegrees` — finite number `[-180,180]`, local forward-axis final PNG после crop/fit/padding, до facing/gravity flips: `0=+X`, positive clockwise в y-down. Это выбор Visual о нарисованных пикселях, не AI/movement/controller angle. Describe the same pose in authored prompt; не выводить ось из имени, прозы, PCA или image inspection. Runtime axis correction не меняет gameplay movement.
- Root item owns size/canvas/axis для exact `kind=item_body` независимо от spelling ID и для explicit `reuse_item_icon`. Никаких дополнительных authoritative копий в entity DTO. Distinct baked non-item owns свои три поля; enum canvas `24/32/48/64/96/128`. `runtime_geometry/no_asset` не имеют этих полей. `scale` каждого entity остаётся independent multiplier.
- Main-body `_canvas_for` требует explicit current `preferredCanvasSize` для item/distinct entity project; отсутствие или неверное значение даёт отказ, не hitbox-derived canvas; dedicated impact PNG получает explicit VFX `spriteCanvasSize` → `entity.visual.impactCanvasSize`, не hitbox-derived policy. Overlay и VFX ingredients сохраняют своих owners. Plan/manifest presentation values — diagnostics выбранного owner, не повторный Author.

### Draw factors (не gameplay scale)

`I=inventoryScale`, `W=worldScale`, `G=gameplay.itemScale`, `D=hitbox.drawScale`, `E=entity.visual.scale`, `P=current Projectile.scale` (initial `D*E`).

| Consumer | Declared-size factor | Legacy absence |
|---|---|---|
| Inventory | unchanged `s_inventory * min(1, caller frame max-side / C) * I`, **без q** | exact old fit |
| Dropped item | `q_item * s_world * W`; same finalScale bottom alignment | `s_world * W` |
| Held generated root | `q_item * player.GetAdjustedItemScale(held)`; G already included once | existing adjusted scale |
| Registry-only held root | `q_item * baseScale * clamp(G,.25,4)` | existing registry branch |
| Baked/reused body | `q_selected * P` при accepted `hitboxCurve.mirrorToSprite=true`; иначе `q_selected * clamp(P,.1,8)` | та же body policy без q |
| Live body copies | `q_selected * clamp(P,.1,8) * slot.Scale` | exact old `max(.05,P*slot.Scale)` |
| Detached body copies | selected q after actual texture load, existing dimensionless pose/slot multiplier | exact existing branch |

Snapshot/network `Pose.Scale`, Item.scale, Projectile.scale, collision, hitbox/tip anchors и growth остаются механическими/dimensionless. Size/path выбираются у одного texture owner; dedicated impact/overlay/material world widths/textured paths не получают body q. Existing tip anchors не являются измеренным PNG наконечником. Один scalar max-side не гарантирует равную физическую длину разных поз или точный grip/tip.

Reuse гарантирует одинаковые pixels и **base** frame extent, не принудительное равенство final held/world/body: с нейтральными caller hooks equality held/body требует `G == clamp(D*E,.1,8)` либо `G == D*E*curveScale(active age)` при явном mirror. W не переносится на held, G не дописывается в projectile. Accepted G/D/gameplay не менять ради арта. Mirror относится к базовому body; VFX body copies сохраняют собственные опубликованные scale rules.

### Projectile body-forward и native angle boundary

`SpritePresentation.ProjectileNativeRotation/ProjectileBodyAngle` — единственный
владелец преобразования угла между native storage и смысловым body-forward.
Обычные generated movement drivers сохраняют native `body + π/2`; explicit
`rotation` и legacy spin 14/16/17 хранят body-forward непосредственно. Для любого
main PNG, включая spin/whip, renderer вычитает declared PNG forward axis с учётом
flip. Эта ось описывает пиксели, не меняет полёт, aim или collider.

Новый initial contract: body-forward каждого нового physical source равен world
angle 0 (вправо), до первого AI/callback. Дальше его меняет принятый driver или
явный rotation component; неподвижность не означает автоматическое слежение за
aim. Native entity state инициализируется один раз, в том числе при первой remote
hydration. Повторная metadata hydration того же source не сбрасывает угол или
потраченный pierce; новый source token снова получает initial pose.

Это намеренное изменение presentation, не обещание pixel-совместимости старых
предметов. В частности, stationary main PNG больше не получает скрытые −90°.
Dedicated impact/asset stamps и `body_segment.axis=rotation` сохраняют свой
**literal raw native angle** contract: у обычного source начальный raw angle теперь
π/2, поэтому их начальная поза тоже меняется. У движущегося ordinary body после AI
raw convention прежняя; explicit spin также не переопределён. `body_segment` —
только draw geometry: gameplay collision по-прежнему читает AABB либо реальные
beam/lash points, а направления event-spawn — gameplay aim/velocity/initial axis.

Native SyncProjectile и текущий ExtraAI не передают rotation. First stationary
remote pose теперь инициализируется правильно; это **не** доставка произвольного
исторического угла late-joining peer: например, последний угол уже остановившегося
body из payload восстановить нельзя. Сетевой формат не менялся; полноценная
multiplayer-сессия и произвольные сторонние GlobalProjectile hooks здесь не доказаны.

### Read-only Director/Repair context и visibility

Оба actual packets передают exact accepted `gameplay.itemScale/width/height`, `itemUse`, `itemContact` when present, bindings, item/primary IDs/owner и полные movement/controller params, hitbox D/hitboxScale. Formulas и bake-fill/padding берутся в том же packet; fill facts проецируются из `sprite_contract_for` для eligible canvas/processing roles, не выбирают world size и не меняют image pipeline.

Held-root visibility имеет одного владельца: accepted `itemUse.hideUseGraphic` проецируется в native `Item.noUseGraphic`. Никакого отдельного custom-root visibility override или второго held renderer нет. Hidden projectile/floating bodies сохраняют собственные accepted visual/motion owners.

<a id="metadata"></a>
## Optional metadata

These are optional Visual Director choices, not Gameplay Author mechanics or classifier outputs. Existing definitions with absent fields retain historical presentation. No migration, atlas, skeleton, image analysis or name/category routing is introduced.

| Visual kit | Delivered C# wire | Contract |
|---|---|---|
| `item.grip` | `visual.grip` / `VisualSpec.Grip` | Atomic object: both `normalizedX` and `normalizedY` required; finite numbers in `[0,1]`; no extra keys. Coordinates refer to the **final item PNG canvas after crop/fit/padding**, before facing/gravity flips. `(0,0)` top-left, `(1,1)` bottom-right. |
| `equipOverlay.accessoryMount` | `visual.accessoryMount` / `VisualSpec.AccessoryMount` | Exact `chest`, `back`, `waist`, `shoulder`, `orbit`. Accessory-only presentation; armor keeps its existing part attachment. |

<a id="draw"></a>
## Grip и accessory Draw contract

Explicit grip replaces the old artistic grip origin and role-forward translation. Its pixel origin is `(PNG width * normalizedX, PNG height * normalizedY)`, mirrored by facing/gravity. Engine item rotation and adjusted scale remain unchanged. Authored `HoldoutOffsetX/Y` retain the pre-existing screen-axis semantics: X is not facing-mirrored or rotated; Y is gravity-mirrored. Absent grip keeps old origin/translation behavior.

Accessory mounts all use the existing single overlay PNG, body position/pivot/rotation, dye, tint, visibility and 18px target fit. Offsets relative to the player's center in body-local player pixels:

- chest `(0,-2)`
- back `(-10,-4)`
- waist `(0,10)`
- shoulder `(8,-12)`
- orbit: the existing 16px accessory ring, including its existing ordinal/count policy

Fixed X offsets mirror with facing; Y mirrors with gravity. Vanilla owns the outer full-player rotation/scale. `back` uses the rear accessory layer after Wings and before Skin/Leggings/Torso; `chest`, `waist`, `shoulder` and explicit `orbit` use a front layer after Torso and the generated body badge, before OffhandAcc. An absent mount retains the historical rear layer. Explicit `orbit` deliberately changes depth to avoid its first ring badge being fully hidden by the native legs; its ring geometry, fit, dye and transforms are unchanged. This is a presentation-depth change for existing explicit-orbit records, not a migration of absent metadata. These are the same single PNG and existing mount choices; see [equipment rendering](EQUIPMENT_OVERLAY_RENDERING.md) for the native layer/carrier contract. Multiple fixed badges may overlap; there is no layout optimizer.

The Director is asked to choose grip/mount for new applicable designs. Runtime VFX colors belong to the VFX Director’s local RGB fields, not Visual metadata. `normalize_asset_prompt` forwards the exact `visual.grip` object into the actual item image request as final-canvas placement guidance, without truncating its coordinates or applying it to separate entity sprites. A pre-image authored coordinate is not evidence that a generated bitmap's physical handle actually lands there; no physical-grip accuracy or GPU/game acceptance is claimed by DTO/DrawData tests.

For a required equipment overlay, the image request also retains the accepted `equipOverlay.silhouette` and `visualIdentity`, alongside its existing prompt. A protected read-only tail carries the explicit armor/accessory slot, accessory-only authored mount when present, and the renderer's maximum **whole-texture** fit: head 25px, body 31px, legs 27px, accessory 18px. Transparent padding makes the visible silhouette smaller; these values are neither authored silhouette dimensions nor native armor-frame support. Existing alpha-crop, centered fit and padding remain unchanged. The same tail survives technical retry compaction and prompt-only diagnostics, without borrowing the inventory design, inventing absent metadata, adding required fields, or changing frozen-first Repair. `test_equipment_image_prompt_facts.py` captures real adapter HTTP payloads with offline image responses; it proves fact transport, not image-model fidelity or in-game fit.

<a id="repair"></a>
## Validation, Repair, transport

Present null/invalid types/ranges/tokens are rejected locally and by the C# boundary. Optional fields are independent; a grip cannot contain just one coordinate. Repair remains frozen-first and exact-leaf scoped, including missing/broken grip coordinates and forbidden nested keys. Valid sibling coordinates stay frozen. Unrelated Repair cannot add optional metadata. Only prompt/silhouette/visualIdentity mirror into item-project entity rows; grip/size/axis do not authorize nonexistent alias fields. Missing R/axis and distinct canvas grant only their exact leaves. Branch-forbidden presentation is deleted only at diagnosed leaves of a uniquely selected literal mode/ref branch; unknown/ambiguous discriminators remain fail-closed. Typed numeric corrections survive frozen merge (true ≠ 1 ≠ 1.0).

При точной известной ownership-ошибке `baked_sprite` diagnostics проверяют неизменённую запись против единственной формы, заданной принятыми identity/kind: исправление root `entity → item` разрешает удалить только ставшие запрещёнными size/canvas/axis; обратное non-item `item → entity` разрешает явно создать только недостающие обязательные поля. Уже валидные значения целевой формы остаются frozen. Неверный `visualProjectRef` должен исправить Repair — код его не подставляет. Unknown/missing/ambiguous discriminators не получают такого разрешения. Эффективная deletion branch выбирается после frozen merge. ID-upsert принадлежит первой исходной записи; дубликаты удаляются только по разрешённым исходным индексам, no-op не схлопывает их.

C# `forwardAngleDegrees` проверяется property-local converter до сужения JSON number в `float32`, в том числе по исходному decimal literal около ±180, когда даже `double` округляет число к границе. `180.000001` и `180.000000000000000000000000000001` отвергаются; точные ±180 и допустимые fractions остаются разрешёнными. Nullable-float storage и omission/null distinction не меняются.

Strict provider JSON Schema represents optional properties as required-plus-nullable. The existing provider projection/inverse is reused, gated by **actual** response-format metadata. Only declared optional-property nulls on an actual schema transport mean omission. json_object/off/downgraded transport does not gain that alias; required grip-coordinate nulls remain invalid. Repair object-or-null branches are selected by container type before inverse projection so invalid leaves are not erased by a validation-based branch guess.

Full/cache JSON and network JSON preserve present metadata. Python delivery's canonical visual allowlist includes grip/mount and root renderSizePx/forwardAngleDegrees; distinct entity presentation remains in runtimeProgram. Metadata absence stays absent. C# optional properties have per-property `WhenWritingNull` omission so alternate snapshot serializers do not manufacture explicit nulls. Player saves and held-pose packets remain compact identity references; canonical registry hydration supplies presentation metadata, with no duplicated metadata in pose packets.

VFX uses strict `RuntimeRgbSpec` local RGB objects at its own slots/profile knots/endpoints. Visual palette text is not a renderer color selector; gameplay/light token validation remains separate.

Visual Repair root использует partial `itemPatch|null`, условно whole `equipOverlayPatch|null`, полные `entitiesUpsert`, `entityIdsDelete`, zero-based `entityIndicesDelete`, `note`. `animationPlan` не входит в mutable Repair surface; useful art context остаётся read-only. Exact frozen-first permissions, а не whole-kit reauthoring; пропуск означает no-change, кроме validator-diagnosed delete leaves. Gameplay не размораживается.

<a id="verification"></a>
## Источники и проверка

`test_visual_presentation_metadata.py`: strict values, refusal of foreign color metadata, schema transport/downgrade behavior, Director dispatch/conditional Repair, frozen absences/siblings, delivery. Existing held/equipment fixture extensions in `EngineRuntimeChecks`: real DTO full/cache/network/save/registry routes, facing/gravity grip DrawData and FNA CPU submission, all fixed mounts/orbit through real player transforms. Texture shells and intercepted GPU flushes are headless seams, not in-game rendering.

Условные проекты/actual packets/pixels защищают `test_vfx_packet_contracts.py`, `test_vfx_frozen_boundary_contracts.py`, `test_sprite_render_contracts.py`, `test_visual_vfx_prompt_prefix.py`. C# consumers — [VisualSpec](../../../ModSources/InfiniCrafterLocal/Common/Models/Contracts/GeneratedItemData.Model.cs), [held layer](../../../ModSources/InfiniCrafterLocal/Common/Players/GeneratedHeldItemPresentation.cs), [equip layer](../../../ModSources/InfiniCrafterLocal/Common/Players/GeneratedEquipOverlayDrawLayer.cs). Результаты старых проходов — [history](../../archive/VISUAL_AUDIT_HISTORY_RU.md#presentation); актуальные команды/границы — [test owners](../../development/TESTING_RU.md).

### Single native held owner

Ordinary visible `item_body` is rendered by Terraria `HeldItem` through the existing
`GeneratedItem.ModifyItemDraw` hook. The hook replaces only per-instance artwork
and its centered canvas calibration. Native position, rotation, facing/gravity,
arm pose, draw ordering and `noUseGraphic` gate remain authoritative. There is no
separate grip-contact renderer, `heldAlignment` choice or visibility alias.

For native frame F and actual artwork A, let k=max(A)/max(F). The artwork origin is
`(nativeOrigin - F/2)*k + A/2`; its scale is the native scale times
`renderSizePx/max(A)`. Source rectangles identify frame-local coordinates; their
atlas offset is not an additional origin. This uniform mapping does not stretch
non-square artwork or infer its handle. Draw the art for the accepted native pose:
PNG `grip` and `forwardAngleDegrees` remain truthful metadata for composable
projectile/reuse adapters, not an instruction to reposition this ordinary body.
No hidden axis rotation, per-weapon table or anatomical contact guarantee exists.

`hideUseGraphic` is the only authored item-body visibility flag. Hidden spear,
rapier and independently posed projectile bodies are not resurrected by a second
layer. Explicit arm gestures remain native gameplay intent. The discarded
`customHeldSprite`/`releaseTiming` and `heldAlignment` choices are not accepted by
the new strict contract; old item migration is not provided by this API reset.

Held history observes an unambiguous actual native body entry before coordinate
transforms and samples that entry after native transforms. A missing or duplicate
witness is skipped, never replaced with a guessed hand point. Image readiness and
canonical definition identity still fail closed. Native player use-state, not a
custom pose cache, owns local and remote animation.

### Dropped support

Dropped sprites retain their complete PNG, declared frame size, caller rotation and
scale, native collider and authored draw offsets. The selected texture cache measures
an alpha-positive pixel-edge convex hull once alongside its existing alpha bounds.
After rotation/scale, that visible hull is horizontally centered on `Item.Bottom`
and its lowest edge touches the native bottom (before explicit draw offsets). This
presentation normalization removes transparent padding without identifying feet,
decorations or materials. Alpha=1 participates just as in existing bounds; sparse or
rotated silhouettes do not acquire fictitious bounding-box corners. No item art,
placed-body pivot or physics is rewritten. Alpha-empty images remain empty; unknown
geometry exists only for borrowed/headless fixtures and retains old frame placement.
