# Добавление runtime capability

Новая capability существует только после полного vertical slice.

1. Добавь `CapabilitySpec` в `capability_registry.py`: точный смысл, target kinds, typed params, **единицу, neutral, Author range, one-to-one wire projection и execution phase**, slot/exclusivity, requirements/events, authority, budget, exact wire paths, Python callable и C# method symbols. Проценты, percentage points и multiplier не синонимы; runtime safety envelope может быть шире Author ради старых DTO, но не уже.
2. Используй registry-generated provider schema/prompt; не добавляй ручной alias.
3. Реализуй validator rule только через декларативные metadata или общий точный rule. Не выбирай design default.
4. Добавь compiler projection и receipts; каждый `finalPath` должен быть declared.
5. Расширь strict wire schema/validator.
6. Добавь C# DTO field/normalize и bounded executor. Unknown opcode должен оставаться fail closed.
7. Добавь authority/net sync только для реально нужного state.
8. Добавь capability witness и acceptance fixture, если это новый композиционный класс.
9. Перегенерируй schemas/docs:

```bash
PYTHONPATH=LocalGenerator python tools/export_contract_schemas.py
PYTHONPATH=LocalGenerator python tools/generate_low_level_runtime_docs.py
PYTHONPATH=LocalGenerator python tools/generate_equipment_bounds.py
PYTHONPATH=LocalGenerator python tools/generate_primitive_parity.py
PYTHONPATH=LocalGenerator python -m infini_local.qa.primitive_loss_audit
```

10. Добавь RED→GREEN test: новый C# executable field без Author primitive должен ломать AST loss audit; если поле deliberately internal, укажи проверяемую причину в `primitive_loss_audit.py`. Запусти parity/mutation/full tests и C# build/runtime smoke. Аудит wire-only не доказывает полноту C#.

## Запрещённый shortcut

Нельзя добавить `create_<weapon>` и внутри выбрать entity kind, movement, delivery и lifecycle. Если API-вызов tModLoader требует несколько технических полей для одного точного действия, это допустимый adapter; перечисли exact outputs и докажи эквивалентность в `TECHNICAL_LOWERING_AUDIT_RU.md`.
