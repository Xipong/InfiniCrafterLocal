# Equipment overlay: native carriers and draw order

Generated armor/accessories still use one per-instance `equip_overlay` PNG, fitted
as a badge. This is not an animated armor atlas and does not split an image into
limbs. [Visual ownership and metadata](VISUAL_PRESENTATION_METADATA.md) remain the
source of authored appearance and `accessoryMount`.

## Neutral native armor appearance

`GeneratedHeadArmor`, `GeneratedBodyArmor` and `GeneratedLegsArmor` keep their
static `AutoloadEquip` registrations and inventory equip slots. Their
`ModItem.EquipFrameEffects` hooks set only their currently displayed visual
`Player.head`, `Player.body` or `Player.legs` to native neutral slot `0`, guarded
by matching `EquipType` and carrier slot. tModLoader dispatches this hook through
`EquipLoader`/`EquipTexture` after the ordinary functional/vanity selection.

This uses native rendering for the player's hair, shirt/sleeves/hands and
pants/shoes below the badge. A transparent body sheet alone would still select
the armored-body branch and could hide hands/clothes. No per-definition
`ArmorIDs` mutation, player renderer, draw-time state swap or synthetic limb art
is involved. `PlayerFrame` rebuilds the visual slots from the actual inventory on
each frame, so changing/unequipping the item or using vanilla vanity needs no
saved-state restoration. Stats, actual inventory equip slots and armor dyes stay
unchanged. Foreign visual slot overrides are not reset by these hooks.

The packaged PNGs are deterministic transparent registration carriers:

- Head and legs: 40 × 1120, twenty 40 × 56 native frames
- Modern body: 360 × 224, the native 9 × 4 composite layout
- Retained legacy `FemaleBody` and `Arms` paths: transparent 40 × 1120 sheets;
  the current tML body route uses `ArmorBodyComposite`, not these paths

Regenerate/check with `python tools/generate/generate_equipment_carriers.py [--check]`.
These code-owned assets are not replacements for required generated artwork.
If a per-instance PNG has not arrived, the ordinary base player remains visible
and the existing asset catch-up path runs; no invented armor artwork is drawn.

## Accessory depth

- `back`, `orbit` and absent mount: existing rear layer after `Wings`, before
  native skin/leggings/torso
- `chest`, `waist`, `shoulder`: front layer immediately before `OffhandAcc`,
  after the torso and its generated armor badge, before hands/held items

The explicit mount token determines this finite rendering route. No name,
category or image analysis selects placement. The full visible accessory set
owns orbit count/ordinal before the rear/front split, so moving a badge forward
or waiting for another texture does not move an already visible orbit badge.
Functional and social accessories contribute independently, as native accessories
do; only the functional slot obeys its `hideVisibleAccessory[3..9]` flag. A social
item without a generated overlay cannot erase a functional badge. Each source
also obeys native visual-incompatibility checks and uses its paired slot dye.
Armor retains its matching-slot vanity replacement policy.

Rear badges apply native `TorsoGroup` once (their `Wings` parent has no such
transform); front badges inherit it from `OffhandAcc`. Both follow seated/mounted
torso displacement and obey `hideEntirePlayer`, invisibility/death/shadow,
gravity/facing and the native final full-rotation transform.

## Verification boundary

`EngineRuntimeChecks.EquipmentPresentation.cs` exercises actual tML setup,
`PlayerFrame`, `EquipLoader`/`EquipTexture` dispatch, `PlayerDrawSet.BoringSetup`,
native player-part `DrawData` production and native child-layer traversal using
known-size synthetic CPU textures. It covers functional/vanity priority, a
second player, changed equipment, inventory/stat/dye invariants, base clothes,
hair, hands, front/back order, orbit stability, flips and native full rotation.
The PNG test checks real file dimensions and every alpha value.

These are headless native-consumer checks. They do not start a graphics device,
load the full mod/game, judge generated art quality, or prove live-game visual
appearance with other mods. That visual smoke remains a separate check.
