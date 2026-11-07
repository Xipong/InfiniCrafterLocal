# Сохранённые отчёты

Это исторические receipts прежних проверок, не инструкции запуска и не проверка текущего архива. Исходные байты сохранены. `SHA256SUMS_SOURCE.txt` относится к прежнему source snapshot: не используй его для проверки нынешней поставки. Актуальные checksums должны поставляться вместе с конкретным архивом релиза.

Некоторые прежние orphaned `*.generated.json` без действующего producer сохранены здесь как `contract_parity_report.historical.json`, `runtime_impact_report.historical.json`, `sandbox_validation.historical.json`. Их counts/schema/вердикты относятся только к исходному snapshot; current projections находятся в `contracts/schemas/` и у действующих audit tools.

Пользовательские инструкции — [установка](../../docs/user/START_RU.md); текущие команды проверки — [тестирование](../../docs/development/TESTING_RU.md).

`parent_source_performance_20261107.json` — отдельный receipt локального сравнения с `3c092e3`, уже содержащим supplied patch поверх PR #333. В нём записаны исходники, DLL fingerprints, все 16 native-фаз с побайтной проверкой packets, отдельные Python-замеры и результаты проверок. Методология, воспроизведение и ограничения — в [отчёте](../../docs/development/pipeline/PARENT_SOURCE_PERFORMANCE_20261107_RU.md). Этот receipt относится к указанному source snapshot и не подтверждает последующие revisions или game/GPU/MP.
