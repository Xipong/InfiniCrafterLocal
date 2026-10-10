# Common/Models

`RawJsonNumericDomain.cs` owns property-bound original-decimal numeric admission before float32 storage. Explicit field converters keep omissions and reject invalid presence; the writer uses an exact declared endpoint representative only when needed to preserve identical stored endpoint bits.

`RuntimeProgramSpec.cs` is the only gameplay runtime DTO. It accepts only `infini.runtime-program.v5` and `infini.runtime-program.wire.v3`, validates exact entity/binding/component/event relations and normalizes hard bounds.

`GeneratedItemData*` wraps metadata, explicit gameplay item fields, runtime program and VFX/visual contracts. There is no compatibility `AttackSpec`, `runtimeFamily` or weapon profile.

`RawJsonNumericDomain.cs` is property-local numeric admission, not normalization. Explicit converter subclasses declare decimal bounds and optionally a neutral; the original JSON lexeme is compared before float32 storage. Nullable omission stays absent, present null/type/range errors fail closed. Ordinary in-domain rounding is allowed; only a declared neutral permits nonneutral-collapse refusal. No process-wide converter, semantic routing, fallback or new token/exponent cap. If the shortest binary32 endpoint text lies outside its decimal domain, the writer emits the exact declared bound only for identical stored endpoint bits; this is a serialization equivalence, never outside-source admission.
