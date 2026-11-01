# Gameplay vocabulary wire baseline

The compressed JSON contains all 69 visible capability witnesses captured at
`df29f5827429594c7969f22db63f66e0fa2a809b`, before the PR253 gameplay naming changes.
Every original Author source passed validation, compiled, and passed strict wire
validation before capture. `previousAuthor` and `wire` retain those literal
objects, including the historical v6 source and original receipt identifiers.
`author` selects exactly the same inputs and numeric values using the sole current
v7 canonical names. No native game execution or model inference produced this
fixture. Gzip is storage-only; it is never a model-input codec.

Coverage is fixed to this historical 69-capability cohort, with each original
identifier present exactly once. Later capabilities belong to the current
vertical-slice witnesses and their own behavioral tests; they have no original
pre-migration wire or receipts to add to this capture.

The regression independently compares the complete executable compiled DTO,
excluding only `runtimeContract` provenance (which must record the new source
names). It also validates untouched old wire/receipts, rejects old names as new
Author input, and sends old generated-parent data through actual next-craft
request assembly in both response formats. Other tests retain older archived
captures and their wrong-unit/forged-receipt rejection cases.

`combatCases` adds three independently captured pre-alignment examples on the
current v7 surface (default, held-refresh and event-selected effect groups).
Only the nested Author stat names then change; the captured wire still contains
`combat.attackSpeedPercent`, `critChancePoints` and `damagePercent`. Its
capture boundary is documented separately from the original v6 69-case corpus.
