# Explicit visual presentation metadata

These are optional Visual Director choices, not Gameplay Author mechanics or classifier outputs. Existing definitions with absent fields retain historical presentation. No migration, atlas, skeleton, image analysis or name/category routing is introduced.

| Visual kit | Delivered C# wire | Contract |
|---|---|---|
| `item.grip` | `visual.grip` / `VisualSpec.Grip` | Atomic object: both `normalizedX` and `normalizedY` required; finite numbers in `[0,1]`; no extra keys. Coordinates refer to the **final item PNG canvas after crop/fit/padding**, before facing/gravity flips. `(0,0)` top-left, `(1,1)` bottom-right. |
| `equipOverlay.accessoryMount` | `visual.accessoryMount` / `VisualSpec.AccessoryMount` | Exact `chest`, `back`, `waist`, `shoulder`, `orbit`. Accessory-only presentation; armor keeps its existing part attachment. |
| `item.effectColor` | `visual.effectColor` / `VisualSpec.EffectColor` | Exact renderer token: `white`, `gray`, `brown`, `tan`, `red`, `orange`, `yellow`, `gold`, `green`, `cyan`, `blue`, `purple`, `pink`, `black`. Independent of rich art palette; no hex/prose parsing. |

## Draw contract

Explicit grip replaces the old artistic grip origin and role-forward translation. Its pixel origin is `(PNG width * normalizedX, PNG height * normalizedY)`, mirrored by facing/gravity. Engine item rotation and adjusted scale remain unchanged. Authored `HoldoutOffsetX/Y` retain the pre-existing screen-axis semantics: X is not facing-mirrored or rotated; Y is gravity-mirrored. Absent grip keeps old origin/translation behavior.

Accessory mounts all use the existing single overlay PNG, body position/pivot/rotation, dye, tint, visibility and 18px target fit. Offsets relative to the player's center in body-local player pixels:

- chest `(0,-2)`
- back `(-10,-4)`
- waist `(0,10)`
- shoulder `(8,-12)`
- orbit: the existing 16px accessory ring, including its existing ordinal/count policy

Fixed X offsets mirror with facing; Y mirrors with gravity. Vanilla owns the outer full-player rotation/scale. `back` selects a body-local offset, **not** guaranteed behind-body occlusion or a separate draw layer. Multiple fixed badges may overlap; there is no layout optimizer.

The Director is asked to choose grip/mount for new applicable designs and effectColor when VFX color is relevant. `normalize_asset_prompt` forwards the exact `visual.grip` object into the actual item image request as final-canvas placement guidance, without truncating its coordinates or applying it to separate entity sprites. A pre-image authored coordinate is not evidence that a generated bitmap's physical handle actually lands there; no physical-grip accuracy or GPU/game acceptance is claimed by DTO/DrawData tests.

## Validation, Repair, transport

Present null/invalid types/ranges/tokens are rejected locally and by the C# boundary. Optional fields are independent; a grip cannot contain just one coordinate. Repair remains frozen-first and exact-leaf scoped, including missing/broken grip coordinates and forbidden nested keys. Valid sibling coordinates stay frozen. Unrelated Repair cannot add optional metadata. Only prompt/silhouette/visualIdentity mirror into item-project entity rows; grip/color do not authorize nonexistent entity fields.

Strict provider JSON Schema represents optional properties as required-plus-nullable. The existing provider projection/inverse is reused, gated by **actual** response-format metadata. Only declared optional-property nulls on an actual schema transport mean omission. json_object/off/downgraded transport does not gain that alias; required grip-coordinate nulls remain invalid. Repair object-or-null branches are selected by container type before inverse projection so invalid leaves are not erased by a validation-based branch guess.

Full/cache JSON and network JSON preserve present metadata. Python delivery's visual allowlist includes all three fields. C# optional properties have per-property `WhenWritingNull` omission so alternate snapshot serializers do not manufacture explicit nulls. Player saves and held-pose packets remain compact identity references; canonical registry hydration supplies presentation metadata, with no duplicated metadata in pose packets.

`RuntimeColorPolicy.RequireRenderingToken` validates against the existing renderer vocabulary without altering the narrower `NormalizeRequired` gameplay/light contract. Runtime effectColor consumption belongs to the VFX renderer owner.

## Evidence

`test_visual_presentation_metadata.py`: strict values, all rendering colors, schema transport/downgrade behavior, Director dispatch/conditional Repair, frozen absences/siblings, delivery. `EngineRuntimeChecks.PresentationMetadata.cs` plus held/equip fixture extensions: real DTO full/cache/network/save/registry routes, facing/gravity grip DrawData and FNA CPU submission, all fixed mounts/orbit through real player transforms. Texture shells and intercepted GPU flushes are headless seams, not in-game rendering.
