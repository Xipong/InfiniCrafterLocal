# runtime_contract_history

Детерминированный replay-корпус executable runtime contracts без LLM и HTTP.

- `corpus.json` хранит исторические normalized plans, девять минимальных deterministic witnesses и ожидаемые fingerprints финального wire.
- Исторические строки v1 не содержат typed Author provenance. Для функций, которые lowerятся в другой executor, точное покрытие дают witnesses; selector не подменяет их всеми чужими `shoot_projectile` cases.
- Новые dumps могут сохранять `_authoredFn`/`_authoredParams`; builder выносит из них `authoredFunctions` и `authoredForms`, не оставляя internal keys в executable plan.
- `coverage.json` обязан покрывать все функции registry. Неизвестная или непокрытая function/form завершает affected replay ошибкой, а не пустым PASS.
- Пересборка выполняется только `tools/build_runtime_contract_replay_corpus.py`.
- Fixtures не должны содержать credentials, caches, media, prose envelopes или абсолютные machine paths.
