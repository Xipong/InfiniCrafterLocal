# Original lineage map artwork

These assets are original artwork produced for InfiniCrafterLocal from the user-approved single-map prototype in this task. The parchment and leather textures were generated deterministically from random grain, smooth tonal variation and short fiber strokes. Frame, stitching, page edges, brass corners, node wells, wax seal, bookmark and page fold were independently authored geometric shapes.

No sprites, screenshots, textures, traced artwork or drawing code from Calamity, Calamity Overhaul, Stars Above, Wrath of the Gods or Recipe Browser are included. Chronicle Quest Book was a visual reference for the general material language only.

The production PNGs contain no demonstration item icons, text, graph layout or gameplay data. They are intended for inclusion under the repository's existing licensing terms; this file records their original provenance rather than introducing a third-party asset license.

## Native drawing

- `BookFrame.png`: 640×450, transparent outside. Nine-slice source borders L/R=32 (48 also supported to retain whole metal corners), top=56, bottom=48. Use white tint. Suggested content inset left/right32, top62, bottom42 or larger. The centre is continuous parchment, with no gutter. Background includes leather, fibers, stitching, brass corner pieces and fore-edge layers.
- `NodeWell.png`: 64×64, transparent. Draw58–64px; draw actual item icon above it, maximum38px, full color. Never use prototype icons for actual items.
- `WaxSeal.png`: 64×64, transparent. Draw68–72px for selected root; actual item icon remains38px. This gives selected identity without changing graph semantics.
- `Bookmark.png`:28×104. Draw behind frame, centered at bottom; only final25–30px should extend past visible leather bottom. The frame includes transparent outer margins, so position relative to visible bottom (~height−24px), not raw image bottom.
- `PaperFold.png`:40×38. Optional fixed-size fold above the lower-right parchment corner (approximately right32,bottom42 within the frame destination). It is separate so nine-slice scaling does not distort it.
- Edges: #806947, hover #8b3429. Text #3c2e22. Brass controls #b99a64. Hover/card paper #e6d3aa, border #aa8f61. Leave actual gaps in edges around item labels.

Only five compact PNGs need to ship. Combined compressed size is approximately274KiB. Optional seamless `ParchmentTile.png` and `LeatherTile.png` are not required by the nine-slice renderer and were not copied into production.
