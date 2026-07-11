# contracts

Машинно-читаемые межъязыковые контракты и lifecycle manifests.

- `field_lifecycle.json` перечисляет критические поля `AttackSpec` и обязательные стадии Python/C#/network/runtime.
- `schemas/` содержит детерминированные JSON Schema, экспортируемые из strict Pydantic boundary-моделей.

Эти файлы не генерируют gameplay и не заменяют явные Python/C# owners. Они используются только для валидации drift.
