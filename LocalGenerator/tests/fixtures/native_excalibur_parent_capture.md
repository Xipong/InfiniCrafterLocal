# Native Excalibur parent capture

`native_excalibur_parent_capture.json` is the `itemA` object from a real
`GeneratorClient.Prepare` request, captured by the current canonical native
checks. It includes the item/spawn-input source graph, direct/effective native
projectile snapshots, and their original provenance. Repeated fingerprint data
is deliberately retained: tests exercise the actual parent packet builders.

- tModLoader.dll SHA256: `fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5`
- Native module MVID: `033e87cd-cefe-4dc6-a1fb-e14aa938bbb2`
- Native check: `--check-filter 'projectile attack'`, with
  `INFINI_DUMP_ATTACK_PARENT` selecting the request output file.
- CPU host built from canonical mod/native-check sources with .NET SDK 8.0.427
  and net8 reference assemblies; real native tModLoader module, not a mock graph.

The capture observes source IL without executing AI, GPU drawing, a world/game
loop, or multiplayer. It is evidence of source extraction and request contents,
not proof of played gameplay. The distinct native growing-arc oracle executes
AI/collision on isolated CPU actors; that execution is not encoded by this JSON.

Model-view tests assert connected timing, collision/target arguments, rendering,
branch/dependency data and unchanged source capture. Size is measured against the
previous projection on this input, not imposed as a universal character budget.

The refreshed capture also includes per-program `identitySelected` graphs and
`identitySelection` edge receipts. These are native CFG projections using only
certified reads of the captured projectile's type/AI style. Original unspecialized
programs remain beside them in the raw capture; dynamic AI/localAI branches remain
symbolic. Python only consumes matching identity/method/module/hash receipts.
