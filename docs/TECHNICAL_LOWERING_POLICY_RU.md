# Политика technical lowering — projection

> Канонический generated contract: [`../lowery.md`](../lowery.md). Machine projection: [`../TECHNICAL_LOWERING_AUDIT_RU.md`](../TECHNICAL_LOWERING_AUDIT_RU.md). Владелец executable policy — `LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py`.

Lowering может скрывать неудобство Terraria/tModLoader API, но не сжимать пространство дизайна.

## Два разных механизма

1. **Mandatory technical projection** сериализует уже authored identity/value: exact capability name → opcode, exact entity kind → visual role, exact primary id + binding target equality → wire role. Порог повторений тут неприменим: новых решений нет.
2. **Authoring compression** может заменить только буквально одинаковое low-level значение, повторённое минимум **5** раз. Требуются literal equality и `addsDesignChoice=false`. Текущие primary role/owner projections compression не являются.

## Допустимо

- exact capability name → finite opcode;
- explicit entity kind → renderer role;
- одно authored value → несколько обязательных DTO fields;
- exact authored identity/equality → требуемое wire поле;
- exact repetition compression при `count >= 5`.

## Недопустимо

- family/category/name/prose → movement, attachment, delivery, entity kind, input, lifecycle, targeting или topology;
- объединение нескольких независимых решений в один prefix;
- fallback к whole-weapon executor;
- broad undeclared output paths;
- unknown kind/value → permissive semantic default.

Каждый lowerer объявляет authored inputs, конечные outputs, equivalence, preserved decisions и `addsDesignChoice=false`. Global receipt содержит `lowererId + authoredPaths + finalPath`; capability receipt — `callId + fn + finalPath`. `audit_compiler_receipts` и mutation gate отклоняют undeclared input/output.
