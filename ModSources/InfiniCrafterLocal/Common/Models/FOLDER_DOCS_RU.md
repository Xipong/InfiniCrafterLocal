# Common/Models

`RuntimeProgramSpec.cs` is the only gameplay runtime DTO. It accepts only `infini.runtime-program.v5` and `infini.runtime-program.wire.v3`, validates exact entity/binding/component/event relations and normalizes hard bounds.

`GeneratedItemData*` wraps metadata, explicit gameplay item fields, runtime program and VFX/visual contracts. There is no compatibility `AttackSpec`, `runtimeFamily` or weapon profile.
