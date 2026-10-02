# Visual Director: проекты и explicit presentation metadata

<a id="owners"></a>
## Visual ownership и authored surface

Visual Director выбирает внешний вид принятого gameplay, не mechanics/classifier outputs. Одна физическая вещь имеет один visual project; отдельный объект — отдельный. `item_body` всегда требует отдельный inventory PNG: единственный missing-mode Fix допускается только при уже непустых `prompt`, `silhouette`, `visualIdentity` и добавляет `baked_sprite` с audit. Без описания — Visual Repair/RED, не artwork из кода.

Источник ordinary/Repair schema и dispatch — [visual_generation_pipeline.py](../LocalGenerator/infini_local/pipelines/visual_generation_pipeline.py); projects/processing role — [visual_asset_plan.py](../LocalGenerator/infini_local/pipelines/visual_asset_plan.py). Director root: `schema`, `item`, одна `entities` запись на runtime entity, текстовый `animationPlan`; `equipOverlay` обязателен только для объявленной equipment потребности.

| Entity branch | Обязательная Visual запись |
|---|---|
| `baked_sprite` | `entityId`, `assetMode`, `visualProjectRef=item\|entity`, `prompt`, `silhouette`, `visualIdentity`, `scale`; item-body ссылается на item project, отдельный объект — на entity project |
| `reuse_item_icon` | `entityId`, `assetMode`, `visualProjectRef=item`, `scale`; exact item image без второго fake brief |
| `runtime_geometry`, `no_asset` | `entityId`, `assetMode`, `visualProjectRef=none`, `scale`; не authored sprite prompts |

`entityId` ссылается на уже принятый runtime entity. `scale` [.25,4] — visual multiplier, не hitbox, в том числе для `no_asset`. Из exact mode/identity может losslessly нормализоваться единственный `visualProjectRef`; это не разрешение угадать mode или дизайн. Impact PNG запрашивает только выбранный поздний VFX `impactSprite`, а не обязательный ранний Visual `impactPrompt` для каждой entity. VFX ingredients принадлежат VFX, не меняют основной Visual.

<a id="image-contract"></a>
## Изображение, canvas и художественная граница

Item требует `prompt`, `negativePrompt`, `silhouette`, `visualIdentity`, `palette`, `preferredCanvasSize`, `inventoryScale`, `worldScale`. Непустые authored descriptions обязательны; длины/число palette entries — schema transport bounds, не художественные units. Canvas item: 24/32/48/64/96/128 PNG px; overlay: 32/48/64/96 PNG px. Это side final square canvas, **не** мировой footprint, silhouette bbox или размер overlay на игроке. `inventoryScale` и `worldScale` [.25,4] — независимые draw multipliers после fit; нейтраль 1. Runtime hitbox — read-only gameplay context.

Processing role отделена от произвольного entity ID: identity вроде `entity_<id>` не является geometry role. Directional convention обязана соответствовать renderer: +X canonicalization нельзя применять поверх native +Y rotation; PCA/taper не semantic detector носа/рукояти. Authored design/palette/silhouette не переписываются name/category/regex heuristics.

Item/equipment сохраняют hard pixel alpha, impact/effect — soft alpha. Straight RGBA PNG premultiplies только при runtime upload, не вместо bake policy. Final PNG transparent; raw backend input может требовать solid chroma key по [sprite_contracts.py](../LocalGenerator/infini_local/pipelines/sprite_contracts.py). Prompt/keyer/retry используют один mapping (white/black/cyan и retained aliases); magenta-only spill не применяется к другому key, unknown key диагностируется. Нельзя путать raw solid-key background с непрозрачным final PNG или восстанавливать arbitrary alpha, уже сплющенную provider на opaque фон.

<a id="metadata"></a>
## Optional metadata

These are optional Visual Director choices, not Gameplay Author mechanics or classifier outputs. Existing definitions with absent fields retain historical presentation. No migration, atlas, skeleton, image analysis or name/category routing is introduced.

| Visual kit | Delivered C# wire | Contract |
|---|---|---|
| `item.grip` | `visual.grip` / `VisualSpec.Grip` | Atomic object: both `normalizedX` and `normalizedY` required; finite numbers in `[0,1]`; no extra keys. Coordinates refer to the **final item PNG canvas after crop/fit/padding**, before facing/gravity flips. `(0,0)` top-left, `(1,1)` bottom-right. |
| `equipOverlay.accessoryMount` | `visual.accessoryMount` / `VisualSpec.AccessoryMount` | Exact `chest`, `back`, `waist`, `shoulder`, `orbit`. Accessory-only presentation; armor keeps its existing part attachment. |
| `item.effectColor` | `visual.effectColor` / `VisualSpec.EffectColor` | Exact renderer token: `white`, `gray`, `brown`, `tan`, `red`, `orange`, `yellow`, `gold`, `green`, `cyan`, `blue`, `purple`, `pink`, `black`. Independent of rich art palette; no hex/prose parsing. |

<a id="draw"></a>
## Grip и accessory Draw contract

Explicit grip replaces the old artistic grip origin and role-forward translation. Its pixel origin is `(PNG width * normalizedX, PNG height * normalizedY)`, mirrored by facing/gravity. Engine item rotation and adjusted scale remain unchanged. Authored `HoldoutOffsetX/Y` retain the pre-existing screen-axis semantics: X is not facing-mirrored or rotated; Y is gravity-mirrored. Absent grip keeps old origin/translation behavior.

Accessory mounts all use the existing single overlay PNG, body position/pivot/rotation, dye, tint, visibility and 18px target fit. Offsets relative to the player's center in body-local player pixels:

- chest `(0,-2)`
- back `(-10,-4)`
- waist `(0,10)`
- shoulder `(8,-12)`
- orbit: the existing 16px accessory ring, including its existing ordinal/count policy

Fixed X offsets mirror with facing; Y mirrors with gravity. Vanilla owns the outer full-player rotation/scale. `back` selects a body-local offset, **not** guaranteed behind-body occlusion or a separate draw layer. Multiple fixed badges may overlap; there is no layout optimizer.

The Director is asked to choose grip/mount for new applicable designs and effectColor when VFX color is relevant. `normalize_asset_prompt` forwards the exact `visual.grip` object into the actual item image request as final-canvas placement guidance, without truncating its coordinates or applying it to separate entity sprites. A pre-image authored coordinate is not evidence that a generated bitmap's physical handle actually lands there; no physical-grip accuracy or GPU/game acceptance is claimed by DTO/DrawData tests.

<a id="repair"></a>
## Validation, Repair, transport

Present null/invalid types/ranges/tokens are rejected locally and by the C# boundary. Optional fields are independent; a grip cannot contain just one coordinate. Repair remains frozen-first and exact-leaf scoped, including missing/broken grip coordinates and forbidden nested keys. Valid sibling coordinates stay frozen. Unrelated Repair cannot add optional metadata. Only prompt/silhouette/visualIdentity mirror into item-project entity rows; grip/color do not authorize nonexistent entity fields.

Strict provider JSON Schema represents optional properties as required-plus-nullable. The existing provider projection/inverse is reused, gated by **actual** response-format metadata. Only declared optional-property nulls on an actual schema transport mean omission. json_object/off/downgraded transport does not gain that alias; required grip-coordinate nulls remain invalid. Repair object-or-null branches are selected by container type before inverse projection so invalid leaves are not erased by a validation-based branch guess.

Full/cache JSON and network JSON preserve present metadata. Python delivery's visual allowlist includes all three fields. C# optional properties have per-property `WhenWritingNull` omission so alternate snapshot serializers do not manufacture explicit nulls. Player saves and held-pose packets remain compact identity references; canonical registry hydration supplies presentation metadata, with no duplicated metadata in pose packets.

`RuntimeColorPolicy.RequireRenderingToken` validates against the existing renderer vocabulary without altering the narrower `NormalizeRequired` gameplay/light contract. Runtime effectColor consumption belongs to the VFX renderer owner.

Visual Repair root использует partial `itemPatch|null`, условно whole `equipOverlayPatch|null`, полные `entitiesUpsert`, `entityIdsDelete`, zero-based `entityIndicesDelete`, `animationPlan|null`, `note`. Exact frozen-first permissions, а не whole-kit reauthoring; пропуск означает no-change, кроме validator-diagnosed delete leaves. Gameplay не размораживается.

<a id="verification"></a>
## Источники и проверка

`test_visual_presentation_metadata.py`: strict values, all rendering colors, schema transport/downgrade behavior, Director dispatch/conditional Repair, frozen absences/siblings, delivery. `EngineRuntimeChecks.PresentationMetadata.cs` plus held/equip fixture extensions: real DTO full/cache/network/save/registry routes, facing/gravity grip DrawData and FNA CPU submission, all fixed mounts/orbit through real player transforms. Texture shells and intercepted GPU flushes are headless seams, not in-game rendering.

Условные проекты/actual packets/pixels защищают `test_vfx_packet_contracts.py`, `test_vfx_frozen_boundary_contracts.py`, `test_sprite_render_contracts.py`, `test_visual_vfx_prompt_prefix.py`. C# consumers — [VisualSpec](../ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs), [held layer](../ModSources/InfiniCrafterLocal/Common/Players/GeneratedHeldItemDrawLayer.cs), [equip layer](../ModSources/InfiniCrafterLocal/Common/Players/GeneratedEquipOverlayDrawLayer.cs). Результаты старых проходов — [history](VISUAL_AUDIT_HISTORY_RU.md#presentation); актуальные команды/границы — [test owners](TEST_CONTRACT_OWNERS_RU.md).
