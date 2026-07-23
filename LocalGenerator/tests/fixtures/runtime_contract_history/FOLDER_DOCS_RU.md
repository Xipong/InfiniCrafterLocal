# runtime_contract_history

Deterministic replay corpus extracted from historical accepted runtime-plan artifacts.

- `corpus.json` stores normalized authored cases and expected final-wire fingerprints.
- Rebuild only with `tools/build_runtime_contract_replay_corpus.py`.
- Tests must not call an LLM or image backend; they compile through the production runtime authoring path.
- This directory contains fixtures only, never live credentials, caches, generated media, or per-machine absolute paths.
