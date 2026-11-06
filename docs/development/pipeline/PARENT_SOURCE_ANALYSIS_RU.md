# Исходный контекст родителей: анализ, проекция и транспорт

Интеграция source analysis сохраняет контракт ammo main/#332: live inventory и fallback observations остаются отдельными от статических native source facts. Root использует Player, fingerprint — независимое player-free наблюдение. Source-профиль не означает исполненный выстрел.

## Анализ и проекция

Native IL/CFG collector сохраняет guards, неизвестные эффекты, ограниченные helper spawns и inline effects. Sparse locals не меняют условия statements. Подтверждённые identity predicates исключают лишь доказанно недостижимые source-ветви. Неизвестные значения, unsupported instructions, escapes и hooks сохраняют неопределённость; read-only observation не становится gameplay router.

Conditional arithmetic shot variants содержат provenance, исходную вероятность и зависимости значений, но не обещают final-shot identity/damage/speed после последующих native writes/hooks. Pinned ILSpy 8.2.0.7535 поставляется с модом. Readable C# records проходят source-identity/mapping checks; при неполноте используется исходный IL view и diagnostic. Readable-source metadata исключена из стабильных fingerprints.

Author получает исходники с guards, alias scopes, child-profile links и unknowns. Reversible shared-source/identifier/diagnostic notation сокращает повторения; literal tooltips и generated parents не переинтерпретируются. Inventory/fallback projectile profiles проходят тот же source-selection путь, что direct/effective/replacement profiles. Main source-projection cache сохраняет complete-method isolation, immutable values и cancellation перед warm hit.

## Размеры

300000 символов compact Author dossier — development/test цель, не runtime admission. Craft не отвергается и данные не обрезаются лишь из-за её превышения. При размере сериализованного dossier **от 350000 символов включительно** existing logger записывает warning с размером, порогом и stage, без prompt/recipe/parent данных. Настройка отключения диагностических логов сохраняется.

Размер относится к символам dossier JSON, не токенам или полному provider request. Provider/response/transport ограничения остаются. Ваншотный Author, Author → Visual → VFX и frozen-first Repair не меняются.

## HTTP

GeneratorClient gzip-кодирует UTF-8 craft JSON только свыше прежних 2 MiB и если gzip короче. Прежние допустимые запросы остаются identity JSON. Server принимает один complete gzip member лишь на `/combine`: wire cap 2 MiB, decoded cap 32 MiB. Bounded decoding и strict JSON идут до cache lookup/Author. Prepared JSON, arrays, null/zero и несовпадающие root/fingerprint значения сохраняются. Для oversized requests нужны обновлённые обе стороны.

## Проверка и границы

`tools/checks/check_planner_prompt_usability.py --parent-captures <directory> --all-pairs` проверяет полные Prepare packets, ordered pairs и полный каталог Author capabilities. Превышение 300000 делает dev report отрицательным, но не блокирует production craft.

Python tests проверяют reversible notation, mappings/unknowns, source order, ammo observations и CFG alternatives. `test_author_payload_headroom.py` проверяет warning boundary и полный HTTP Chat/Responses request без truncation. Native checks отдельно проверяют identity, helper/inline effects, fingerprints, inventory/fallback, cache/cancellation, gzip и managed dependency packaging.

Размеры должны относиться к итоговому main-based DLL и свежим captures; старые weapon-only measurements не являются результатом main integration. Full C# completeness, произвольные modded hooks/detours, graphics/game-loop/MP и качество генерации не следуют из offline tests. Dependency-count bound профиля 635 остаётся explicit unknown, не доказательством отсутствия поведения.
