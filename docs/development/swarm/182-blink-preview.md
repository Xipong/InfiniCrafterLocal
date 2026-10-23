# Exact blink destination preview (#182)

Holding an item with a primary or alternate blink binding shows the actual player-sized destination footprint. The overlay reads the exact selected effect group, clips to authored range, distinguishes world boundary, solid-body overlap and lava overlap, and displays the shared mobility cooldown. Right mouse previews the alternate binding. It hides during menus, inventory, lost focus and pointer UI interaction.

Preview and direct-use execution call one geometric resolver. Inspection never moves the player, reserves cooldown, searches for a replacement landing tile or edits item data. Unsafe authored movement still respects finite coordinates/world boundaries and skips only the authored collision checks.

Native `QoL BlinkGeometry` checks real solid/actuated/lava geometry plus exact footprint, range clipping and mutation-free inspection. Existing blink execution checks retain actual native Teleport coverage. GPU rendering is not run locally.
