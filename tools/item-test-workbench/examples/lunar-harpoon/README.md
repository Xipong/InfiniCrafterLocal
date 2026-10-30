# Returning lunar trident: reproducible assistant-authored demo

This is a newly authored example, not a captured user item. The three source JSON
files are current Author v7, Visual Director and VFX Director inputs. The Author
vocabulary update preserves the executable gameplay wire; rebuilding regenerates
receipts against the current source paths. `build.py` invokes
the repository's actual validators, compiler, receipt auditor and delivery
sanitizer. It does not call an LLM/image API or edit compiled gameplay wire.

The exact imagegen PNG is bundled under `assets/` and selected by default:
`infini_asset_png_4a753935d470fa15fe74d5b8b4e87f63a8ef56060e8844a89b30e766fa0c8c2e.png`.
The builder verifies both its byte hash and canonical publication identity.
The raw original image is not accepted: it has not undergone the recorded canonical
normalization/publication. `--out` must be a new directory; existing evidence is
never overwritten.

The sanitized imagegen prompt, pixel hashes and canonical processing provenance
are in `assets/provenance.json`. No Terraria assets are bundled. Historical
wire IDs remain `assistant_lunar_harpoon`; the item has no anchor/pull mechanic.

From the repository root, after installing the existing LocalGenerator Python
dependencies and configuring the workbench's native dependencies:

```sh
python tools/item-test-workbench/fetch_player_assets.py --help
# Fetch the pinned player assets with --include-dummy as described by that tool.
python tools/item-test-workbench/examples/lunar-harpoon/build.py \
  --player-assets /path/to/terraria-player-assets --out artifacts/lunar-harpoon
python tools/item-test-workbench/workbench.py run \
  --item artifacts/lunar-harpoon/item.json --scenario artifacts/lunar-harpoon/scenario.json \
  --out artifacts/lunar-harpoon-run
```

The supplied final item JSON can also be run directly; rebuilding is optional.
The scenario template's empty asset fields are filled by the explicit arguments.
They are not playable defaults or asset fallbacks.

## Authored behavior and test scope

- Hold primary: full charge in 30 world ticks, automatic release at 60 active
  updates; manual early release is weaker. Native runtime timing is recorded.
- One use pays 8 mana. The same physical harpoon flies out, can strike again on
  return after native local immunity, then dies within its authored owner-arrival
  radius. The reusable inventory item is not consumed.
- Timed return starts at 72 active updates **from spawn**, not from release.
- A wall intercept latches return. The existing seek window requires both the
  released phase and a valid `since_return` clock, so homing starts on the next
  native AI update. It does not continue outward through the wall. Arrival at
  the owner kills the projectile and emits kill VFX.
- The v1 wall test exposed an incorrectly delayed seek window. A wall-kill v2
  alternative was tested but not selected. Final v3 preserves the original
  wall-return intent using the existing Author API; no runtime fix or bypass.
- Collision center is authored 48 pixels forward of the measured grip. The
  original sprite-anchor kernel compensates that base offset; no hand pose or
  artwork was patched in the testbench.

The native charge status is telemetry, not a claim that Terraria's original
charge HUD/font or ready sound was rendered. Existing world-render, community
asset provenance and training-dummy animation compatibility limits still apply.
`nativeRender.capture=false` with native dust enabled executes native drawing
but omits PNG export, because native dust drawing can change dust state.
