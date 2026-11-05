# Исследование upstream relevance AI_075

## Результат

Семантическое выкидывание «чужих ветвей» **не обосновано при нынешнем строгом baseline**. Это не доказательство невозможности любого будущего оптимизатора. Проверенные два дешёвых кандидата на сокращение дают ноль:

- Backward closure от всех observations на 13 parent cards (41 программа) не нашёл ни одной неиспользуемой dependency или predicate. Для AI_075: все 216 dependencies и 142 predicates достижимы из 63 observations. В closure включены receiver/arguments, orderedSourceUses, guards и embedded alternatives/source_block.
- Проверка фактического source CFG AI_075 под уже сертифицированными identity edges не нашла ни одной недостижимой observation, scalar definition, alias use или predicate. Нельзя получить выигрыш обычной garbage collection или повторной фильтрацией теми же известными ветками.

Исходный model-facing program в unpacked виде: 96 885 знаков; raw identitySelected с audit metadata: 103 535. Это **не** отдельный более выгодный baseline и не токены. Строго принятое semantic-pruning сокращение равно **0**. Предыдущие 325 379 / 319 119 относятся к целому shared dossier и иному encoding, их нельзя вычитать из размера этой программы.

## Откуда берутся лишние на вид ветви

Реальный native source module: `033e87cd-cefe-4dc6-a1fb-e14aa938bbb2`, тот же, что в frozen capture. Reflection прочитал source analyzer и IL, не вызывал AI, игровые hooks или методы поведения.

- AI_075 имеет 538 basic blocks, 5 196 decoded values.
- Четыре доказанных selector edges оставляют 355 blocks достижимыми.
- В них 12 identity hazards: 2 GetProjectileSource_FromThis и 10 Kill.
- На первом позднем чтении Projectile.type, IL offset 5604 / block 5603, могут предшествовать GetProjectileSource_FromThis на 5504 и Kill на 5598. Поэтому исходная captured identity больше не является доказанным значением для этого чтения. Проверка b5614 уже сравнивает живое значение, а не сохранённый snapshot.

Это реальная неизвестность в проверяемом коде, не только искусственная осторожность анализатора:

1. GetProjectileSource_FromThis → Entity.GetSource_FromThis → new EntitySource_Parent(this, context). Constructor сохраняет родителя в Entity backing field.
2. NewProjectile передаёт этот source в ProjectileLoader.OnSpawn (offset 1808).
3. Kill вызывает ProjectileLoader.PreKill(this, timeLeft) на offset 110 и OnKill на 161215.

Hooks могут наблюдать родителя и имеют доступ к изменяемым полям. Здесь не доказано, что они реально меняют type в конкретной игре; доказано, что предположение об их неизменности не вытекает из текущего source evidence. Обычный single-tick oracle с шестью лазерами также не доказывает отсутствие альтернатив при других условиях и callbacks.

## Диагностический контрфакт, не оптимизация

Если **запретить hazards в рассуждении**, то generic literal/type branch selector без списка IDs уменьшает reachable blocks 355 → 65 и observations 63 → 10. Он выкидывает 53 observations. Эти числа показывают, где сосредоточен объём, но **не являются допустимой экономией** и не используются для packet rewrite. Вариант нарушает текущую unknown/side-effect границу и строгую фактологическую полноту; full equivalence не доказана.

Текущий кандидат не может отличить «модель выберет только устойчивую исходную механику» от «она может использовать условно доступные source facts после callback» без внешнего правила, выбирающего смысл за модель. Удалять unknown tail лишь потому, что он редко нужен, означало бы ввести такое правило.

## Что могло бы стать следующим корректным направлением

1. Сохранить всё в одном запросе, но показать отдельно исходно доказанную identity и последующее ослабление доказательства после конкретных escaped calls. Это помогает читать, однако само по себе не сокращает facts.
2. Усилить upstream анализ memory/effect summaries и path-sensitive identity state. Разрешать устранение ветви только при проверенном no-write/no-escape контракте всех возможных callbacks; unresolved callback сохраняет путь. На данном frozen source hooks не имеют такого доказательства, поэтому обещать крупную экономию нельзя.
3. Для addressed locals исследовать field-sensitive memory SSA/reaching stores, но не считать одинаковые `initobj` или expressions дубликатами: source point, reaching path, живые чтения, RNG и вызываемые эффекты различаются. Готовая строковая проекция и `alias_effects_and_reaching_value_unresolved` недостаточны для такого доказательства.

Не тронуты capability catalog, production, Git; вызовов модели и сети не было. Не выполнены full gameplay equivalence, production integration, model A/B, live-game smoke.

## Файлы и воспроизведение

- `InspectSource.cs`, `inspect.rsp`: read-only reflection source/CFG extractor; source method и identity взяты из packet, не hardcoded item IDs.
- `LastPrism.full-cfg.json`: фактические values/blocks, selected reachability, hazards и IL соответствующих calls.
- `analyze.py`: closure для 41 программы, CFG baseline reachability и явно недопустимый counterfactual только для диагностики.
- `summary.json`: результаты и SHA-256 источников.
- `LastPrism.baseline-program.json`: authoritative decoded model-facing input, без сокращения.

Для повторного расчёта: `python ifc-source-relevance-study-20261105/analyze.py`.
