# infini_local/qa

Offline proof-слой для runtime contracts. Он не выбирает механику и не участвует в игровом исполнении.

- `golden_runtime_cases.py` хранит небольшой проверенный набор authored `runtimePlan` и ожидаемые gameplay envelopes.
- `runtime_proof.py` строит compiler/provenance и gameplay-seam отчёты через production owners.
- `runtime_contract_replay.py` хранит generated witnesses, historical replay, callable-level fingerprints и affected-case selector. Accepted cases проверяют exact final wire и finite-executor fingerprint; известные старые dead wires остаются ожидаемыми typed rejections.
- `executable_semantics.py` — proof-only DTO canonicalizer. Он десериализует уже готовые `gameplay/attack/accessory/armor` через strict boundary и нормализует только эквивалентные для конечного executor написания. Он не читает Author prose, не маршрутизирует функции и не создаёт gameplay defaults.
- `csharp_delivery_contract.py` выводит strict recursive `GeneratedItemData` JSON graph из текущих C# DTO и проверяет delivery payload.

Здесь запрещены LLM/HTTP/image calls, item-name rules, prose classifiers и повторная компиляция смысла. Terraria/tModLoader smoke остаётся отдельным acceptance-слоем.
