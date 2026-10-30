# Native Wooden Arrow parent capture

`native_wooden_arrow_parent_capture.json` is the complete `itemB` object from a
real `GeneratorClient.Prepare` request captured on 2026-10-30. Compact UTF-8 JSON
retains the original fingerprint, ammo and direct/effective projectile envelopes;
it is not a hand-authored graph or a fixture reconstructed from prompt output.
Only itemB is stored, not another copy of the complete Excalibur/Arrow pair.

- Pair capture SHA256: `7e7b5d02d231431e1c422b25932586985381bb4c132d7ef273ba115a35d50624`
- This compact itemB file SHA256: `c4f702c86c055b336499121ff70f53169c19c2909cf8ff1c40730308586382e7`
- Source base: `04f961a31995ada8892dac28a9186d9a26a3cdf3`, **plus uncommitted current producer changes**, not the unchanged base release.
- `GeneratorClient.AttackIdentitySelection.cs` SHA256: `70cc88f90c8e09553a9b1a31ee2e6a8e81be5f22d1f26267f071ab65025eb89f`
- `GeneratorClient.ProjectileAttackFacts.cs` SHA256: `3c8e4da506102a472e88f89a97262da0f4509bd4e0b85a6205609820acd9e267`
- Native module MVID: `033e87cd-cefe-4dc6-a1fb-e14aa938bbb2`
- `Terraria.Projectile.AI_001` IL SHA256: `cf0488832f92e43e699ae307df6f73d90f88f17194250f0a39ca5715a9e0631b`
- tModLoader.dll SHA256: `fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5`
- CPU native host: .NET SDK 8.0.427, net8 reference assemblies, actual tModLoader module.

The bounded selected Arrow motion slice has seven observations, three dependencies
and seven predicates. Its unspecialized sibling reports the exact refusal
`connected_source_dependency_count_bound:193>192`; selection success must not erase
that refusal or the separate unresolved collision/draw coverage. Dynamic conditions
remain symbolic. Source extraction is not execution of the complete AI/world/GPU.

`test_parent_stage_briefs.py` takes this item through the actual Author request in
both JSON modes and checks clock, conditional component acceleration, velocity
limits and rotation expressions, their predicates, and the refusal metadata.
The independent CPU execution oracle is
`ParentNativeArrowMotionMatchesSelectedSource` in
`tools/native/EngineRuntimeChecks.NativeAttackGeometryOracle.cs`; the Python test
does not claim to rerun that native oracle.

The adjacent Excalibur fixture is an earlier separate capture and is not replaced
or represented as this new capture. Final whole-request before/after size measurements
used both parents from the complete current pair above; this Arrow regression does
not impose that pair's size as a universal prompt budget.
