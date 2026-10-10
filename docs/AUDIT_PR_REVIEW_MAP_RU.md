# Карта PR по аудиту — финальное техническое ревью

Пакет #7–#27 в `Xipong/InfiniCrafterLocal`: ниже сначала финальные решения, затем исходный исторический proposal snapshot. Текущие canonical owners — [AGENT_INDEX_RU.md](../AGENT_INDEX_RU.md) и [PROJECT_MAP_RU.md](../PROJECT_MAP_RU.md). Исторические выводы сохранены в `HISTORICAL_RUNTIME_AUDIT_2026_10_RU.md`.

## Итог интеграции

Все **21 PR (#7–#27) приняты** после технического и архитектурного ревью; подтверждённые дефекты исправлены на соответствующих ветках. Это результат current main, а не утверждение о первоначальных proposal heads. Исходный параллельный compact API #18 не сохранён: его заменяет единственная fresh grammar `authoring.v5`, без legacy admission. Persisted gameplay wire, readers и старые recipes сохранены.

| PR | Итог и существенная граница |
|---|---|
| #7/#8/#9/#10 | Аудит, контекст Author/Repair и typed основание приняты; Repair остаётся exact-scope и frozen-first |
| #11/#12/#13/#15/#16/#17 | Stack RNG, item aliases, sentry choices, named effect groups, один reservation/refund owner и native ammo приняты |
| #18 | Переработан и принят как единственный Author v5; прежние v4/compact source отказываются, wire-only provenance не выдаётся за проверку Author |
| #14/#24/#26 | Projected reference requirements, typed projectile aliases, signed gravity −2…2, nearest radial damage и fresh bias 0…0.9 совместимы с v5; retained wire bias 0…1 не расширяет fresh admission |
| #19/#20/#21/#22/#23 | Beam/curves/sound/child combat/movement приняты; raw numeric admission проверяет original decimal до float32, native combat basis сохраняется |
| #25/#27 | Physical projectile emission, exact dyadic target geometry, sampled launch и hit-relative snapshot приняты; не добавляют semantic router или whole-weapon presets |

Final combined canonical Python suite — **9173 PASS / 0 FAIL, 109 test files, все четыре shards**; **16 portable gates PASS**, source-bound native harness **333 PASS / 0 FAIL** и реальный private SDK compile **0 warnings / 0 errors** проверены отдельно; точные результаты, scopes и merge commits доступны в PR reviews/CI. SDK pin включает 141 source/resource/project input, из них 107 файлов C#; headless harness pin — 186 inputs, 333 исполненных checks. Это разные единицы измерения, их нельзя складывать. World/GPU/MP/live и качество новой LLM-генерации не проверялись. Installed Windows mods/config/saves не менялись, опубликованный v0.4.254 не переиздавался.

## Дополнение: пакет #29/#30/#32–#36

Все семь предложений прошли техническое и архитектурное ревью и приняты; #36 доработан перед принятием. #31 уже был в исходном main и не входит в этот roster. Проверка выполнена поверх `274d4c38849bff5b8f7ecde1c61d6276a4803712`, а не поверх прежнего итогового пакета #7–#27.

| PR | Итог и canonical граница |
|---|---|
| [#29](https://github.com/Xipong/InfiniCrafterLocal/pull/29) | Приоритеты LLM-first и single-shot Author закреплены в AGENTS; creative/gameplay choices не переходят к host |
| [#30](https://github.com/Xipong/InfiniCrafterLocal/pull/30) | Diagnosed `realization.selfEvaluation.planVsProgram` — advisory, без автозаполнения/лишнего Repair; runtime, containers, description, `programVsReport`, чужие siblings и resource guards остаются strict |
| [#32](https://github.com/Xipong/InfiniCrafterLocal/pull/32) | Реальный Repair требует non-null `realizationReplacement` через единственный request-local schema owner; generic sparse patch сохраняет omission-as-no-change |
| [#33](https://github.com/Xipong/InfiniCrafterLocal/pull/33) | Radial/disk child учитывает только declared/context-valid neutral omission spread; source и frozen absences не дописываются, present-invalid/root omissions остаются RED |
| [#34](https://github.com/Xipong/InfiniCrafterLocal/pull/34) | Fresh scalar names `accelY`, `radiusTiles`, `speed`, `miningSpeedMultiplier` имеют exact прежнюю wire projection; старые имена только retained receipt provenance, не Author aliases |
| [#35](https://github.com/Xipong/InfiniCrafterLocal/pull/35) | Actual Author/Repair cards построены из canonical shapes; Repair показывает только scope-visible `callsUpsert`, empty union даёт empty examples; формы не объявлены defaults или weapon presets |
| [#36](https://github.com/Xipong/InfiniCrafterLocal/pull/36) | `moveSpeedBonusPercent / 100` с прежним wire factor lifecycle; исправлены exact signed-zero omission provenance и standalone float-type/consumer-domain audit, без inverse equality/quantization/fallback |

Проверенный общий executable snapshot — tree `ae09cbd346747314d35f03e43fc32e33684978df`, executed head `e427b451eb568a1fb990f78c4766180d979c354d`: **9506 Python PASS / 0 FAIL**, **111 test files**, четыре canonical shards и **33 actual commands**, **16 portable gates PASS**; 672 input hashes не менялись во время исполнения, same-scope duplicate observers отсутствуют. Финальные ancestry-only successors имеют тот же tree; navigation commit меняет только три Markdown-файла. Counts отдельных ревью не складываются с full-suite total. Ранний full на доработанном precursor имел три timing FAIL в healthy image sibling controls; same-byte shard retry прошёл, исходный RED сохранён. Финальный 9506-case run прошёл целиком без retry.

На совместной композиции повторены actual Author/Repair readers в обоих formats: 14 report/gameplay/frozen/resource controls, 68 public witnesses и 12 frozen Repair controls. Final independent fix36 review: 26 regressions + 4 historical controls PASS. Архивные 4 scalar и 8 buff wires аутентифицированы исполнением первоначального producer `274d4c3`; fixture hashes не обновлялись под candidate.

Native **333 checks PASS** и private SDK **0 warnings / 0 errors** здесь — source-bound reuse прежнего реального исполнения по точным 186/141 compile-input hashes и фактическим DLL, **не новый native run**. SDK pin содержит 107 C# файлов внутри 141 inputs. Hosted Windows source scan не выдаётся за compilation. World/GPU/MP/live и качество новых генераций не проверялись; установленный Windows runtime, configs/saves и опубликованный v0.4.254 не менялись.

Ubuntu MOTD `GEN_EMAIL` traceback диагностирован отдельно как system OpenSSL/Hermes cryptography search-path contamination; clean-env control прошёл. Он не подменяет реальные project exit codes, глобальные packages/config не менялись.

## Исходный proposal snapshot — исторический, не current status

Следующие таблицы фиксируют первоначальные ветки, их counts и ограничения на момент подготовки. Их «Открыт»/«Draft», отсутствие .NET и opt-in compact mode **устарели** и не описывают принятый main. Первоначальная база — `62762da1831771b376eb83efbab80530411ff3f1`. Исходные pytest totals нельзя складывать или приписывать финальной композиции.

## Как выбирать

В колонке «База» указан фактический base branch PR. `main` означает отдельный кандидат от общей исходной версии, а не обещание бесконфликтного совместного merge всех соседних PR. Ссылки в этой колонке обозначают необходимые родительские PR; после принятия основания дочернюю ветку нужно перенести/перенацелить на выбранную обновлённую базу.

**Draft** у runtime-категорий означает, что код, контракты, portable tests и подготовленные native scenarios доступны для ревью, но C# build/EngineRuntimeChecks и Terraria SP/MP ещё не выполнены. В окружении нет .NET/tModLoader/ParticleLibrary/Luminance. У компактного output отдельный Draft нужен для проверки качества реальной LLM-генерации; новый режим остаётся opt-in.

Число pytest относится к собственной ветке. Эти числа нельзя складывать как независимое общее покрытие: suite в основном общий. Для каждого code PR выполнены также остальные обязательные portable gates; native notRun не включён в PASS. Artifact-only и formatting-only follow-ups отдельно отмечены в описаниях соответствующих PR с точными проверенными ревизиями.

## Карта и доказательства

| PR | Категория и результат | База | Статус | pytest |
|---|---|---|---|---|
| [#7](https://github.com/Xipong/InfiniCrafterLocal/pull/7) | **История и границы аудита**. Проверенные потери, сохранённые композиции и случаи без доказанного working path. | `main` | Открыт | docs |

## Запросы к моделям и Repair

| PR | Категория и результат | База | Статус | pytest |
|---|---|---|---|---|
| [#8](https://github.com/Xipong/InfiniCrafterLocal/pull/8) | **Контекст Gameplay Author**. Меньше повторяющихся schema/prose/annotations; реальные единицы и устойчивый prefix. | `main` | Открыт | 7156 |
| [#9](https://github.com/Xipong/InfiniCrafterLocal/pull/9) | **Контекст Repair**. Scope-specific schema и компактный Format Repair с сохранением frozen-first прав. | `main` | Открыт | 7108 |
| [#18](https://github.com/Xipong/InfiniCrafterLocal/pull/18) | **Компактный Author output**. Opt-in API для сокращённого source; точная проекция, receipts и обратный Repair. | [#10](https://github.com/Xipong/InfiniCrafterLocal/pull/10) | Draft | 7294 |

## Author API

| PR | Категория и результат | База | Статус | pytest |
|---|---|---|---|---|
| [#10](https://github.com/Xipong/InfiniCrafterLocal/pull/10) | **Типизированное основание Author API**. Общие objects/unions/leaves, canonical aliases, strict provider disjointness и scoped structural Repair. | `main` | Открыт | 7156 |
| [#12](https://github.com/Xipong/InfiniCrafterLocal/pull/12) | **Author API предметов**. Размещение tile/wall, held sprite choice, utility/equipment и typed predicates. | [#10](https://github.com/Xipong/InfiniCrafterLocal/pull/10) | Открыт | 7202 |
| [#14](https://github.com/Xipong/InfiniCrafterLocal/pull/14) | **Author API снарядов**. Immunity, spawn position, hit/periodic choices, единицы скорости/обновлений и точные bounce/pull aliases. | [#10](https://github.com/Xipong/InfiniCrafterLocal/pull/10) | Открыт | 7276 |
| [#26](https://github.com/Xipong/InfiniCrafterLocal/pull/26) | **Точные названия и диапазоны событий**. Nearest radial damage с maxTargets, fresh bias 0…0.9 и сохранённый wire 0…1; internal alias не раскрывается в диагностике или Repair. | [#14](https://github.com/Xipong/InfiniCrafterLocal/pull/14) | Draft | 7356 |

## Предметы и ammo

| PR | Категория и результат | База | Статус | pytest |
|---|---|---|---|---|
| [#11](https://github.com/Xipong/InfiniCrafterLocal/pull/11) | **Вероятность расхода собственного стека**. Один RNG receipt после принятого действия; не подменяет ammo saving. | `main` | Draft | 7131 |
| [#15](https://github.com/Xipong/InfiniCrafterLocal/pull/15) | **Отдельные группы item effects и held refresh**. Явные primary/alternate effect groups, held utility refresh и существующий общий mobility cooldown. | `main` | Draft | 7130 |
| [#17](https://github.com/Xipong/InfiniCrafterLocal/pull/17) | **Потребление ammo оружием**. Native выбор/расход ammo и отдельная authored/native speed basis. | `main` | Draft | 7158 |

## Sentry

| PR | Категория и результат | База | Статус | pytest |
|---|---|---|---|---|
| [#13](https://github.com/Xipong/InfiniCrafterLocal/pull/13) | **Выбор целей и залп sentry**. Count/spread, assigned-target policy, LOS и hard range как отдельные choices. | `main` | Draft | 7182 |
| [#16](https://github.com/Xipong/InfiniCrafterLocal/pull/16) | **Native lifecycle и live budget sentry**. Размещение и turret slots, ancestor/live-child accounting, корректный возврат отказанных reservations. | `main` | Draft | 7159 |

## Снаряды и геометрия

| PR | Категория и результат | База | Статус | pytest |
|---|---|---|---|---|
| [#19](https://github.com/Xipong/InfiniCrafterLocal/pull/19) | **Поддержание и геометрия луча**. Повторный расход маны, ramp ширины/урона и clip длины по стенам. | `main` | Draft | 7233 |
| [#20](https://github.com/Xipong/InfiniCrafterLocal/pull/20) | **Кривая игровой области урона**. Независимая damage rectangle curve и явный mirror на sprite, включая конечную отрисовку. | `main` | Draft | 7175 |
| [#22](https://github.com/Xipong/InfiniCrafterLocal/pull/22) | **Источники combat stats дочерних снарядов**. Явный authored-child/live-parent basis без повторного player/class multiplier; snapshot при задержке. | [#10](https://github.com/Xipong/InfiniCrafterLocal/pull/10) | Draft | 7268 |
| [#23](https://github.com/Xipong/InfiniCrafterLocal/pull/23) | **Фазы движения и независимое притяжение**. Отдельные turn/speed/homing/pull, visual curve и whip gravity. | [#20](https://github.com/Xipong/InfiniCrafterLocal/pull/20) | Draft | 7420 |
| [#24](https://github.com/Xipong/InfiniCrafterLocal/pull/24) | **Знаковое вертикальное ускорение**. Явный диапазон −2…2 на каждый projectile update; прежний opcode и сохранённый wire. | [#14](https://github.com/Xipong/InfiniCrafterLocal/pull/14) | Draft | 7322 |
| [#25](https://github.com/Xipong/InfiniCrafterLocal/pull/25) | **Поиск целей и физические projectile links**. Явные anchor, repeats, radius и LOS; один child на шаг, обычные collision и damage. | `main` | Draft | 7233 |
| [#27](https://github.com/Xipong/InfiniCrafterLocal/pull/27) | **Распределения начальной скорости и hit-relative split**. Constant/fan/radial/disk/cone, явная геометрия рождения вокруг поражённого NPC, snapshot при admission и точный initial target exclusion. | [#22](https://github.com/Xipong/InfiniCrafterLocal/pull/22) | Draft | 7407 |

## Звук и VFX

| PR | Категория и результат | База | Статус | pytest |
|---|---|---|---|---|
| [#21](https://github.com/Xipong/InfiniCrafterLocal/pull/21) | **Палитра звуков и pitch variation**. Восстановленные native sound cues и отдельные volume/pitch/variance choices. | `main` | Draft | 7287 |

## Общие основания и пересечения

- **#10 → #12 / #14 / #18 / #22.** Типизированное основание общее. Предметные и projectile aliases, компактный output и parent-combat inheritance остаются отдельными решениями.
- **#14 → #24 / #26.** Знаковое ускорение и API polish используют финальные projectile aliases; они не требуют друг друга.
- **#22 → #27.** Random velocity / target-relative split использует явные combat bases, введённые A9. В базе #27 учтён актуальный generated-contract follow-up #22.
- **#20 → #23.** Общие curve constraints и полный renderer product сначала вводятся в A12; отдельные motion/visual modifiers используют их поверх него.
- **#8 + #9.** В `author_item_provider_repair_response_schema` нужно сохранить обе части: локальный scope schema из Repair PR и `omit_annotations=True` из Author-context PR. Выбор одного whole-file варианта потеряет вторую оптимизацию.
- **#25 (A10) + #27 (A11).** Оба используют общий spawn transform/exact-NPC-exclusion helper. При объединении сетевой writer остаётся v4 из A11, reader принимает v2/v3/v4; общий v3 exclusion segment и owner replay guard сохраняются вместе с v4 launch state. Opcode 8 A10 и alias opcode 1 A11 различны. Общий exception/refund boundary нельзя дублировать.
- **#16 + #25/#27.** Общий обработчик ошибки создания снаряда нужно совместить с резервированием и учётом живых descendants из #16. Вызванная операция отвечает за попытку создания, вызывающая — за ещё не начатые попытки; один и тот же reservation нельзя возвращать дважды.
- **#13 + #27.** Новый sentry spread из #13 тоже должен соблюдать ограничение radial/disk velocity: такой child допускает только нулевой spread. Runtime A11 уже отклоняет несовместимый actual override; в объединённом Author registry нужно применить тот же reference constraint к `target_and_fire.shotEntity` и `spreadRadians`, учитывая объявленный neutral 0 для пропущенного optional spread.
- **#19 + #20/#23.** Общая `DrawLine` signature с `preserveWidth` и её native invocation sites должны сохраниться согласованно. Финальный exact-scale consumer A12 сохраняет finite/positive guards и принимает subpixel geometry; beam consumer использует собственную явную ширину.
- **Runtime categories.** Spawn, event scheduler, DTO и capability registry являются общими файлами. Их пересечения требуют осмысленного объединения выбранных changes и повторного общего запуска gates после объединения. Individual branch PASS не доказывает произвольную комбинацию веток.

Generated schemas/manifests/docs следует перегенерировать из объединённого canonical registry, а не вручную выбирать фрагменты конфликтующих JSON. В публикациях #14 и #22 добавлены отдельные artifact-only follow-ups; конечные экспорты сверены с генераторами.

## Существенные смысловые границы

Историческая реставрация возвращает доказанные низкоуровневые возможности через явные choices. Старые weapon-family bundles и скрытые формулы целиком не возвращаются. В частности, hop/split geometry не обещает точного re-hit, принудительного урона выбранной цели или скрытого наследования parent speed.

У A10 задержка откладывает поиск: требуются активный исходный NPC с прежней incarnation и его dispatch-time geometry. У A11 hit-relative split геометрия и seed фиксируются при admission. Это разные явные контракты; их нельзя сворачивать в один универсальный «отложенный split».

Архивные fixtures не переписаны под новые ожидания. При сравнении A11 со старым полным отчётом отдельно учитывается объявленное изменение диагностических счётчиков registry; это не обещание идентичности всего нового JSON-отчёта. Исполняемые поля и provenance проверяются отдельно. A10 сохраняет прежние диагностические counts для документов, которые не выбирают новую операцию.

Collision rectangle, sprite curve и VFX body-copy scale имеют разные owners. #20/#23 исправляют основной PNG и generic geometry; отдельные VFX copies сохраняют свои опубликованные формулы. Выбор визуального размера не меняет gameplay collision автоматически.

Ammo saving, собственный item stack RNG и live projectile cap — разные механизмы. Родительский total activation budget не пополняется от смерти дочернего projectile; отдельный sentry live cap учитывает живых descendants.

Компактный output #18 сокращает синтаксический payload в тестовых fixtures. Это измерение символов/JSON, а не доказанное снижение token billing или повышение качества LLM. Paid live model/image calls при подготовке не запускались.

## Почему отдельные идеи не получили restoration PR

У per-instance Extractinator найден дефект передачи instance data в неинстансный native hook; возврат старого proxy не доказал бы working path. У native minion lifecycle и state meters/triggers рабочая старая generated вертикаль не найдена. Старый timed-yoyo return имел lifetime defect. Эти случаи отмечены в историческом аудите как границы доказательства и не выданы за восстановленные функции.

Широкий defensive envelope C# DTO сам по себе не разрешает свежему Author все числа. Signed acceleration вынесен как отдельное обоснованное расширение диапазона; диапазоны shrink/maxScale/return-speed этим пакетом не расширяются.

## Проверенные версии PR с кодом

Полные commit-ссылки позволяют сопоставить описания с конкретным snapshot. Последующие изменения автора репозитория могут изменить head и результаты. Сам PR #7 содержит эту карту и исторический аудит; его собственный меняющийся head в таблицу не включён.

| PR | Head commit | База ветки |
|---|---|---|
| [#8](https://github.com/Xipong/InfiniCrafterLocal/pull/8) | [cdf19ca031ec](https://github.com/Xipong/InfiniCrafterLocal/commit/cdf19ca031ecb676d22b31dd5b5811c6eecd246d) | `main` |
| [#9](https://github.com/Xipong/InfiniCrafterLocal/pull/9) | [ac7da5846de5](https://github.com/Xipong/InfiniCrafterLocal/commit/ac7da5846de5476537b08d48f9d016dcd75f2d94) | `main` |
| [#10](https://github.com/Xipong/InfiniCrafterLocal/pull/10) | [a3dae152a142](https://github.com/Xipong/InfiniCrafterLocal/commit/a3dae152a142f225e0c72bcb2a72cb05aff2210f) | `main` |
| [#11](https://github.com/Xipong/InfiniCrafterLocal/pull/11) | [818b3e8f961a](https://github.com/Xipong/InfiniCrafterLocal/commit/818b3e8f961ae785f1b9d49b3a6a8e9d4d3ff38f) | `main` |
| [#12](https://github.com/Xipong/InfiniCrafterLocal/pull/12) | [9271543324c6](https://github.com/Xipong/InfiniCrafterLocal/commit/9271543324c698dc66ee7f10226d419a17bec073) | `audit/typed-author-foundation` |
| [#13](https://github.com/Xipong/InfiniCrafterLocal/pull/13) | [edf2f567b624](https://github.com/Xipong/InfiniCrafterLocal/commit/edf2f567b624850c31fc235484f004d09bf29807) | `main` |
| [#14](https://github.com/Xipong/InfiniCrafterLocal/pull/14) | [fc2b07826980](https://github.com/Xipong/InfiniCrafterLocal/commit/fc2b07826980d7eb4b4db97e181a260d923eb05b) | `audit/typed-author-foundation` |
| [#15](https://github.com/Xipong/InfiniCrafterLocal/pull/15) | [291e12202aae](https://github.com/Xipong/InfiniCrafterLocal/commit/291e12202aae252689b1b2c5f517e637503c0ac4) | `main` |
| [#16](https://github.com/Xipong/InfiniCrafterLocal/pull/16) | [475fa24556f5](https://github.com/Xipong/InfiniCrafterLocal/commit/475fa24556f50ab0d9c3e62e8816a6fe3a3abb03) | `main` |
| [#17](https://github.com/Xipong/InfiniCrafterLocal/pull/17) | [c3d0d3d81640](https://github.com/Xipong/InfiniCrafterLocal/commit/c3d0d3d81640eccce6ab7ae893ca9a4f5943ea27) | `main` |
| [#18](https://github.com/Xipong/InfiniCrafterLocal/pull/18) | [901325611758](https://github.com/Xipong/InfiniCrafterLocal/commit/9013256117587d0d30ae271a1fbe6b6cb8242367) | `audit/typed-author-foundation` |
| [#19](https://github.com/Xipong/InfiniCrafterLocal/pull/19) | [972953cb0cf7](https://github.com/Xipong/InfiniCrafterLocal/commit/972953cb0cf7ebc68173baf866ad1f8de4d436b2) | `main` |
| [#20](https://github.com/Xipong/InfiniCrafterLocal/pull/20) | [9cf415024bf9](https://github.com/Xipong/InfiniCrafterLocal/commit/9cf415024bf97e34404fb1efde389fa900b2915c) | `main` |
| [#21](https://github.com/Xipong/InfiniCrafterLocal/pull/21) | [5fb7651746c0](https://github.com/Xipong/InfiniCrafterLocal/commit/5fb7651746c0f9844b52c14eaee553ecef304217) | `main` |
| [#22](https://github.com/Xipong/InfiniCrafterLocal/pull/22) | [4d15f0dd5485](https://github.com/Xipong/InfiniCrafterLocal/commit/4d15f0dd548517c026398302e33fcc92a6644b5b) | `audit/typed-author-foundation` |
| [#23](https://github.com/Xipong/InfiniCrafterLocal/pull/23) | [e3b33a786c69](https://github.com/Xipong/InfiniCrafterLocal/commit/e3b33a786c693017a6437eeeee7770033e0e4880) | `audit/runtime-hitbox-curve` |
| [#24](https://github.com/Xipong/InfiniCrafterLocal/pull/24) | [24f76ffc31275](https://github.com/Xipong/InfiniCrafterLocal/commit/24f76ffc312750a6702c3b38b3a454bcd60ac162) | `audit/author-projectiles` |
| [#25](https://github.com/Xipong/InfiniCrafterLocal/pull/25) | [16bdf428c54b4](https://github.com/Xipong/InfiniCrafterLocal/commit/16bdf428c54b42398c728c58c612bc19a71b84d2) | `main` |
| [#26](https://github.com/Xipong/InfiniCrafterLocal/pull/26) | [9134fa9d8884](https://github.com/Xipong/InfiniCrafterLocal/commit/9134fa9d8884acd5e28028f5548f3a7c54d00fb2) | `audit/author-projectiles` |
| [#27](https://github.com/Xipong/InfiniCrafterLocal/pull/27) | [ed4ae1fde559](https://github.com/Xipong/InfiniCrafterLocal/commit/ed4ae1fde55958e0f3c9c76648e596adfd11068f) | `audit/runtime-parent-inheritance` |
