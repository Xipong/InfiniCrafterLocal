# runtime_authoring

Единственный активный Gameplay runtime contract. Canonical edit-routing и frozen boundary генерируются в корневой `lowery.md`.

- `capability_registry.py`: единственный owner entity/input/action/event/capability facts и event producer alternatives.
- `terraria_vocabulary.py`: finite canonical stable-tModLoader tokens; никаких loose gameplay aliases или open mod lookups.
- `program_schema.py`: единственный owner strict Author/Repair patch JSON shape и primaryEntity fields; `additionalProperties=false`.
- `repair_scope.py`: exact mutable IDs/indices, missing-dependency create policy, immutable context and scope rejection.
- `validator.py`: deterministic checks, no authorship.
- `compiler.py`: explicit component projection, numeric opcode and receipts.
- `technical_lowering.py`: единственный owner exact lossless adapters, receipts и minimum exact-repetition compression threshold = 5.
- `wire_validator.py`: strict final wire.

Нельзя возвращать deleted `root_lowering`, family macros, semantic reducers или compatibility importer.
