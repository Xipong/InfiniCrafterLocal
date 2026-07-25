# infini_local/qa

Offline proof-слой для `runtimeProgram v5`. Он не выбирает механику и не участвует в игровом исполнении.

- `runtime_program_fixtures.py` хранит небольшие complete Author fixtures с явными entities/calls/bindings; names/categories не выводят gameplay.
- `capability_witnesses.py` строит bounded vertical-slice witness для каждой публичной capability и прогоняет production author/wire validators и compiler.
- `capability_library_audit.py` проверяет registry identity, provider schema, prompt catalog, compiler receipts, technical-lowering и C# ownership для каждой capability.
- `runtime_program_proof.py` компилирует non-archetypal fixtures через production owners и проверяет final wire, Visual entity roles и допустимые VFX entity/event pairs.
- `tools/replay_generation_case.py` — единственный saved-case replay owner: strict v5 final/delivery validation, canonical wire snapshot, drift comparison и явный saved-raw rerun.

Здесь запрещены LLM/HTTP/image calls, item-name rules, prose classifiers, runtime-family aliases и повторная компиляция смысла. Исторический `runtimePlan` corpus не мигрируется: v5 принимает только новый wire. Terraria/tModLoader smoke остаётся отдельным acceptance-слоем.
