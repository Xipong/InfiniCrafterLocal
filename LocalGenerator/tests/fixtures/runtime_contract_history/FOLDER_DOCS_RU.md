# runtime_contract_history

Deterministic replay corpus extracted from historical accepted runtime-plan artifacts.

- `corpus.json` stores normalized executable cases and expected final-wire fingerprints.
- The committed v1 snapshot predates preserved `_rawFn` inventories, so its coverage
  explicitly reports `authoredFunctionInventoryAvailable=false`; specialized typed
  changes are conservatively mapped to their normalized lowerer target.
- A rebuilt corpus records `authoredFunctions` separately and dedupes by normalized
  plan plus that authored inventory. Missing function coverage must fail closed.
- Rebuild only with `tools/build_runtime_contract_replay_corpus.py`.
- Tests must not call an LLM or image backend; they compile through the production runtime authoring path.
- This directory contains fixtures only, never live credentials, caches, generated media, or per-machine absolute paths.
