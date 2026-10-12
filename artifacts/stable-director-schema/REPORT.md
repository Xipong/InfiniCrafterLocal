# Stable Director schema data boundary

Base: `28621ad`; branch: `fix/stable-director-schema`.

## Result

Visual and VFX Director/Repair builders now send complete SYSTEM / DEVELOPER / static USER schemaDefinitions / case USER. Explicitly selected existing owner nodes use standard `$defs`/`$ref`, not a second grammar or an invariant-discovery engine. VFX definitions are element/path/screenShake/particle/sound; Visual definitions are item or the existing partial itemPatch. Exact runtime enums, conditional body/texture/history clauses, configured limits, equipment branches and frozen Repair data remain case USER. Full provider response_format schemas stay inline and unchanged.

The declared static USER endpoint participates in cache identity. Changed parents/errors/runtime enum constraints preserve routing identity; canonical definition revisions invalidate it. Only this new framing omits the case-specific response-format schema from affinity hashing (not from HTTP constraints). Native Author, Gameplay Repair and Format Repair wire/key bytes remain identical.

## Verification

- RED: four boundary tests failed because production emitted only SYSTEM/DEVELOPER/USER; GREEN: all four passed after implementation.
- RED: changed runtime enums plus json_schema changed the cache key; GREEN: five actual sender families × all three formats preserve key while retaining full outgoing schema.
- RED: staticData declaration without instructionMessageIndex reached the stopped HTTP seam; GREEN: it is rejected before sender.
- 1848 affected tests passed in 109.08s (18 modules), including frozen Repair, sound controls, all provider contracts and production three-stage pipeline. Subsequent final strengthened schema assertions: 201/201 passed in 30.76s. Full repository suite intentionally deferred until parent integration.
- 42 actual builder packets against immutable base, all seven stages × json_object/json_schema/off × two changed tails; exact literal original-dossier reconstruction, unchanged system/options.
- 210 actual candidate wire packets at the stopped production sender seam: Nous Chat, OpenAI Chat, OpenRouter Chat, native Codex Responses, OpenAI Responses. No credentials resolved or physical requests sent; offline placeholder credential handles only.
- Author/Gameplay Repair/Format Repair wire hashes and keys match base for every family/format/case.
- Standard Draft202012Validator and the real strict validator agree across inline vs reference schemas on valid/boolean/missing/foreign/null controls for all five VFX payloads; Visual normal/partial and nullable provider shapes covered.
- Strict declaration negatives cover nested/escaped duplicates, NaN/Infinity/1e999, overlaps, unknown keys, wrong roles, bad/null/boolean/out-of-bounds endpoints and missing instruction declarations.
- Runtime domains tested: workbench, door, returning potion, beam, whip. Existing frozen permission/merge/optional absence gates unchanged.
- All seven gates pass: generate_lowery --check, generate_low_level_runtime_docs --check, contract_parity, audit_targeted_repair --check, mutation_contract_gate, check_delivery_contract, check_project_hygiene.

## Literal measurements

Workbench-shaped real builder fixture; json_object; compact text chars. Static block UTF-8 bytes equal chars in this fixture.

| Stage | Static USER definitions | Dynamic USER before → after | Full inline schema → case schema | Total text before → after |
|---|---:|---:|---:|---:|
| Visual | 2877 | 14025 → 11212 | 7367 → 4554 | 28763 → 29044 |
| Visual Repair | 2732 | 15724 → 13066 | 7745 → 5087 | 28466 → 28757 |
| VFX | 19663 | 47972 → 28527 | 42863 → 23418 | 66354 → 66789 |
| VFX Repair | 19663 | 49605 → 30160 | 43226 → 23781 | 65634 → 66069 |

No fields removed; total text increases by framing/refs (281/291/435/435 chars). This moves invariant text out of dynamic tails; it does not reduce whole-request text or assert token savings. Existing payload-node vs packaged-definition estimates overlap and are not additive. Under structured output the complete schema still transmits separately, so its provider processing remains case-dependent.

## Limitations / environment

Actual changed-tail KV hits at the new static USER endpoint, provider schema acceptance, fresh output quality, latency, game/MP/GPU behavior remain unmeasured. Parent owns combined authorized live acceptance. No models/probes, settings/mechanics changes or main publication performed. Full suite awaits combined parent integration.

Initial sandbox lacked pytest/Pydantic/Pillow/tree-sitter; isolated uv dependencies resolved these. First uv project run created .venv/uv.lock and tripped hygiene; both task-created files were removed and subsequent runs used uv --no-project. All final gates pass. Transport edits share llm_transport.py with the separate admission writer; parent must integrate that file carefully.

Reproduce offline parity with `PYTHONPATH=LocalGenerator uv run --no-project --python 3.12 --with pytest --with jsonschema --with pydantic --with pillow python artifacts/stable-director-schema/offline_parity.py`. `offline-parity.json` contains every stage/mode/case measurement; generated full packet snapshots remain local ignored artifacts.
