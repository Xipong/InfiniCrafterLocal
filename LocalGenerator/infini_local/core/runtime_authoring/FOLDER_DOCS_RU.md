# runtime_authoring

Единственный активный Gameplay runtime contract.

- `capability_registry.py`: 7 entity kinds, 4 inputs, 5 actions, 10 events, 52 capabilities.
- `terraria_vocabulary.py`: finite canonical stable-tModLoader tokens; никаких loose gameplay aliases или open mod lookups.
- `program_schema.py`: strict Author/Repair patch JSON Schema; `additionalProperties=false`.
- `repair_scope.py`: exact mutable IDs/indices, missing-dependency create policy, immutable context and scope rejection.
- `validator.py`: deterministic checks, no authorship.
- `compiler.py`: explicit component projection, numeric opcode and receipts.
- `technical_lowering.py`: exact lossless adapters only.
- `wire_validator.py`: strict final wire.

Нельзя возвращать deleted `root_lowering`, family macros, semantic reducers или compatibility importer.
