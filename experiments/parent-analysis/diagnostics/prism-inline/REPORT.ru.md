# Реальный aiStyle84: audit extraction и bounded diagnostics

## Вывод

Нужен upstream проход по выбранной ветке, эффектам и связям акторов, а не ещё один LLM pass или упаковка уже неполных facts. Универсальный путь возможен без списка weapon IDs, но простой подъём лимита недостаточен. В этом эксперименте production и Git не менялись. Использованы неизменённый helper-final EngineRuntimeChecks.dll и реальный tML 1.4.4.9, MVID 033e87cd-cefe-4dc6-a1fb-e14aa938bbb2. Хэши в summary.json.

## Точные причины потери Last Prism

1. VanillaAI содержит 75 776 нормализованных IL instructions. Общая style84 ветка: 3 013 raw, 2 357 meaningful. ProjectileIdentityWindows допускает 4 096 raw, но только 1 024 meaningful. Поэтому отказывает именно meaningful bound. Отдельные совпадения type632 дают четыре маленьких неполных окна (23/13/8/19 raw instructions), а не полную механику лазера.
2. После window extractor ищет parameterless Projectile helper methods. style84 реализован inline, поэтому наличие motionDispatch не обеспечивает motion. Frozen packet реально не имеет motion у child632.
3. Даже при диагностическом допуске полного окна IsRoot не выбирает friendly и set_Opacity; роль motion также не выбирает damage. LaserScan имеет side effect в массиве samples, возвращает void, и его связь с последующим чтением массива не представлена. Значит pass лимита не равен покрытию механики.
4. AttackIdentitySelection сертифицирует всего 7 edges для 632 и перестаёт сужать identity после трёх вызовов set_Opacity. Этот setter фактически записывает alpha через MathHelper.Clamp, но не имеет доказанного callee summary, поэтому сохраняются соседние типы style84. У 455/461/537/642 тот же существующий selector сертифицирует 24 edges. Нельзя обобщать это на разрешение выкинуть late branches AI_075: GetProjectileSource_FromThis и Kill действительно могут передать actor в hooks.
5. Draw имеет независимое ограничение: текущий путь ищет отдельные Main helper calls из DrawProj_DrawSpecialProjs; настоящий 632 draw inline в другой общей области Main. Исправление motion не закроет draw автоматически.

## Что измерено без изменения analyzer

Внешний harness вручную передаёт полное syntax window существующим приватным типам analyzer, обходя только window admission для диагностики. Это не production-ready patch и не доказательство корректной slicing entry. Все source_slice_entry_and_external_CFG_targets_unresolved сохраняются.

- Полный raw dispatch: 90 591 знак.
- Existing selected dispatch: 44 101 знак, 36 observations, 51 dependencies, 46 predicates.
- Existing selected motion: 40 278 знаков, 27 observations. Отдельный motion не заменяет dispatch.
- Generic дополнительные roots: все Projectile/Entity field stores, property setters и calls с array/byref params, плюс прежние dispatch roots. Никаких проверок item/type constants в этой политике нет.
- Для 632 получены ровно 6 дополнительных observations: три set_Opacity, friendly > 30, LaserScan(samples), GetLastPrismHue(ref...). Итого 52 113 знаков, 42 observations, 64 dependencies, 48 predicates. Это размер до явного переноса старых unresolved warnings; итоговый preserved artifact сохраняет все старые warnings и дополнительную границу памяти/эффектов.
- Все прежние observations/dependencies/predicates/symbols сохранены точно. Generic root capture проверен также на реальных 455, 461, 537, 642: каждый получил LaserScan, прежние facts сохранены.

Числа выше относятся к standalone source JSON, не к полному dossier, токенам или provider input. Нельзя сложить их со старым dossier как будто native sharing/packing не меняется. Старый source-listing давал лишь 598 знаков запаса (4 641 с table packing), причём child632 motion тогда отсутствовал. Следовательно, прошлое прохождение размера не подтверждает admission после исправления покрытия.

## Конкретная техническая экономия: sparse locals

ParentSourceMethod.LinkLocals создаёт local-entry и копирует reaching-definition HashSet для всех 1 774 locals VanillaAI даже в style84 slice. В выбранном исходном окне реально используются только 97 slot IDs (ldloc/stloc/ldloca). Это source-scope анализ, не удаление условно достижимой игровой механики.

Независимый solver повторил ту же fixed-point transfer/merge логику для всех locals и только 97 используемых. Incoming и outgoing каждого достижимого блока сравнены с существующим analyzer на всех используемых slots, включая unknown entry definitions. Полное существующее тело analyzer не мутировалось.

Для 632:
- raw: 578 324 → 31 622 ячейки карт; managed allocation 444 386 760 → 28 763 720 bytes.
- selected: 514 460 → 28 130 ячеек; 391 128 376 → 25 312 472 bytes.
- Сокращение allocations примерно 93,5% на этом solver+harness. Все варианты сходятся за 3 прохода.
- 2 376 sparse incoming/outgoing map comparisons на пяти реальных типах прошли; dense control проверен отдельно тем же числом сравнений. Повторение raw style84 для разных типов является тем же исходным окном, не пятью независимыми алгоритмами.

Это cumulative managed allocations solver+harness, не peak/RSS/retained cache и не общая Prepare latency. Wall times сохранены в logs, но несколько процессов/GC/JIT и внешняя нагрузка не позволяют обещать production speedup. Первое фактическое построение existing raw+selected source body выделило около 891 MB ещё до observation rendering. Sparse solver показывает конкретный устранимый источник этого расхода, но не заменяет integrated patch benchmark.

## Рекомендуемый порядок работ

1. **Техническая база:** sparse local-domain по реально встречающимся slot IDs; immutable CFG/value DAG один раз на method/module hash; reuse root closures и per-site budgets. Сначала exact packet regression и allocation profile, без расширения семантики.
2. **Inline source regions:** общий dispatcher CFG и selector по доказанным type/aiStyle, а не требование отдельного AI_NNN method. Приём по scoped CFG/dependency work и явные per-region gaps; не удалять данные по text length и не поднимать один глобальный лимит.
3. **Эффекты вместо неполного списка motion fields:** actor field writes, setters, mutable arguments и вызовы с контролируемыми side-effect summaries. set_Opacity можно доказать как alpha-write/no identity escape, отдельно сохранив alpha equation. LaserScan требует связи call→samples[]→average→localAI[1], а не просто названия вызова. Unknown summaries остаются unknown.
4. **Связи акторов:** из spawn argument ai1 = parent.whoAmI и child чтения Main.projectile[(int)ai[1]] с active/type guards вывести source relation. Поле ai1 не именуется «parent» по convention; связь доказывается expression binding и argument mapping. Сохранять handle reuse, guards, nullable/invalid cases и отсутствие доказательства исполнения/ownership. ai0 — индекс луча в spawn, но root.ai0 — live charge; нельзя смешивать clocks двух акторов.
5. **Model-facing source:** одна последовательность source statements/blocks с локальными binds, exact predicates и attached unknowns, вместо повторного inline expansion одной формулы. Для справки полная декомпилированная style84 область занимает 404 строки / 15 234 символа; это не equivalence/LLM-comprehension доказательство и не готовый заменитель packet. Сначала upstream completeness, затем замер полного dossier одним Author response.

## Проверки и границы

Выполнено: five-type capture; 575 Python preservation/coverage assertions; 2 376 sparse local-map comparisons плюс dense controls; повторная стабильность 632 selected source/identity output; provenance manifest; отсутствие runtime AI/hook/gameplay вызовов. Ни модель, ни capability catalog не затронуты.

Не выполнено: безопасный production window selector; callee effect summaries; memory SSA; packet integration; provider budget after expanded coverage; full repo tests/CI; native visual/hit/DPS/workbench validation; model A/B. Generic effect prototype извлекает исходные calls, но не доказывает их эффекты. Не объявлять его готовым.

При реализации нужны negatives для direct identity write, actor escape в callback, unknown virtual callee, switch repeated targets, joins/loops, exception regions, local address aliases и внешний entry. Regressions Last Prism: t30/31, t119/120, t179/180; invalid/inactive parent; charge damage multiplier; blocked LaserScan при tileCollide=false; shared owner immunity; реальные mana cadence и draw paths проверяются отдельными слоями.

## Файлы и повторение

- MeasureSlice.cs, compile.rsp, native/MeasureSlice.dll: отдельный source-only harness, не репозиторий.
- 632-sparse/ и другие *-sparse/: IL, identity receipt, original observations, generic effect diagnostic, preserved warnings.
- *.log: allocations, times, failures и local-map evidence.
- validate.py, summary.json: assertions и provenance.

Запуск из workspace: source ifc-toolchain-20261105/env.sh; dotnet ifc-prism-slice-audit-20261105/native/MeasureSlice.dll OUTPUT TYPE 84. Затем python ifc-prism-slice-audit-20261105/validate.py.
