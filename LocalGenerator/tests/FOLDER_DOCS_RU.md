# LocalGenerator/tests

Contract/regression tests for Python authoring, C# surface assumptions, MP craft, assets, VFX/audio, runtime repair, hygiene and replay paths.

`conftest.py` prepares an offline deterministic sandbox before collection: it ignores the operator `config.env`, disables live LLM/sd.cpp startup, preserves shipped backend/fallback defaults, and gives tests an isolated cache. Tests that mutate environment must use pytest `monkeypatch`. Set `INFINI_TEST_USE_PROJECT_CONFIG=1` only for an explicitly requested configuration experiment; that is not the release gate.

`run_pytest_shards.py` isolates only subprocess/server/tooling smoke files with reproduced process-boundary risk and bounds each child pytest command. Live LLM/image generation is exercised by the external workspace toolbox, not by the default repository test suite.

In a dependency-poor ChatGPT/web sandbox, do not collect this suite first. Run `python tools/validate_sandbox.py` from the repository root and only use full pytest when its JSON reports `fullSuiteAvailable=true`.

Do not trust test names as architecture proof; read the tested source path and assertions. When changing runtime fields, add/update tests that fail on old ad-hoc/prose/router behavior.

For dirty-tree agent feedback, `tools/run_focused_pytests.py` sets
`INFINI_FOCUSED_PYTEST=1`: only the explicitly selected modules are collected, so an
unrelated missing optional property-test dependency does not block local contract
checks. The ordinary/full pytest entry point keeps the complete dependency gate.
