# Политика technical lowering

Lowering может скрывать неудобство Terraria/tModLoader API, но не сжимать пространство дизайна.

## Допустимо

- seconds → ticks;
- exact capability name → finite opcode;
- explicit entity kind → renderer role;
- одно authored value → несколько обязательных DTO fields;
- sentinel normalization, не меняющая смысл.

## Недопустимо

- family/category/name/prose → movement, attachment, delivery, entity kind, input, lifecycle, targeting или topology;
- несколько независимых механик из одного high-level слова;
- fallback к whole-weapon executor;
- broad undeclared output paths.

Каждый lowerer обязан объявить inputs, конечные outputs, equivalence и preserved decisions. `audit_compiler_receipts` отклоняет writer недекларированного поля; mutation gate проверяет это автоматически. Текущий machine audit: `TECHNICAL_LOWERING_AUDIT_RU.md`.
