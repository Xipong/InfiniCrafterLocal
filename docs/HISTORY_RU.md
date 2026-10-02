# История решений и проверок

Компактная provenance старых аудитов, а не текущий runtime verdict. Активные ограничения собраны в [ENGINE_RUNTIME_BOUNDARIES_RU](ENGINE_RUNTIME_BOUNDARIES_RU.md); authoring/Repair/visual guides владеют рабочими процедурами. Старые counts, prompt sizes, версии зависимостей и availability не переносятся на сегодняшнее дерево.

Навигация: [источники](#provenance) · [v5/Repair](#v5) · [engine audit](#engine-audit) · [typed primitives](#typed) · [Live20](#live) · [81509e2](#audit-81509e2) · [multi-lane](#lanes) · [проверки/справочник](#reference).

Отдельная [история Visual/image/VFX/units](VISUAL_AUDIT_HISTORY_RU.md) объединяет image flags, prompt/claims audit, единицы, presentation .241–.242, renderer Live20 и rollback .243–.244 перед material-направлением .245–.246. Её числа и предложения исторические; отсутствие старой Exact20 capture-папки не выдаётся за replay. Актуальные инструкции: [Visual](VISUAL_PRESENTATION_METADATA.md), [materials](VFX_MATERIAL_ELEMENTS_RU.md), [images](IMAGE_ASSET_LIFECYCLE_RU.md), [units](MODEL_FACING_UNITS_RU.md).

<a id="provenance"></a>
## Сохранённые источники

Полные исходные Markdown доступны как Git blobs на **`e715b34ab89ec41d2528417aff5ab8847ad15f62`**. При консолидации наличие и byte identity каждого из десяти исходников проверены локально через `git show`; это commit-provenance, не новый запуск исторических проверок. Portable reader может открыть ссылки ниже или использовать локальную историю:

```bash
git show e715b34ab89ec41d2528417aff5ab8847ad15f62:docs/ENGINE_RUNTIME_AUDIT_RU.md
```

| Прежний источник на зафиксированном commit | Что сохранено / текущий владелец |
|---|---|
| [LOW_LEVEL_RUNTIME_REFACTOR_REPORT_RU](https://github.com/Xipong/InfiniCrafterLocal/blob/e715b34ab89ec41d2528417aff5ab8847ad15f62/LOW_LEVEL_RUNTIME_REFACTOR_REPORT_RU.md) | Переход weapon-IR → finite v5, условный Repair, запрет family routers; [v5](#v5), [runtime contract](ENGINE_RUNTIME_BOUNDARIES_RU.md#contract). |
| [root TARGETED_REPAIR_AUDIT_RU](https://github.com/Xipong/InfiniCrafterLocal/blob/e715b34ab89ec41d2528417aff5ab8847ad15f62/TARGETED_REPAIR_AUDIT_RU.md), [docs copy](https://github.com/Xipong/InfiniCrafterLocal/blob/e715b34ab89ec41d2528417aff5ab8847ad15f62/docs/TARGETED_REPAIR_AUDIT_RU.md) | Одинаковая frozen-first policy, разные handoff/размеры snapshots; [Repair protocol](TARGETED_REPAIR_PROTOCOL_RU.md). Текущие measurements принадлежат generated JSON, не двум ручным таблицам. |
| [TERRARIA_TMODLOADER_STANDARDIZATION_REPORT_RU](https://github.com/Xipong/InfiniCrafterLocal/blob/e715b34ab89ec41d2528417aff5ab8847ad15f62/TERRARIA_TMODLOADER_STANDARDIZATION_REPORT_RU.md) | Exact vocabulary, собственный dynamic proxy, intentionally unexposed seams; [standardization](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md), [units](ENGINE_RUNTIME_BOUNDARIES_RU.md#units). |
| [TEST_SUITE_AND_TOOLBOX_AUDIT_RU](https://github.com/Xipong/InfiniCrafterLocal/blob/e715b34ab89ec41d2528417aff5ab8847ad15f62/TEST_SUITE_AND_TOOLBOX_AUDIT_RU.md) | Snapshot gate results/NotRun; [проверки](#reference), [test owners](TEST_CONTRACT_OWNERS_RU.md). |
| [MULTI_LANE_ARCH_REVIEW](https://github.com/Xipong/InfiniCrafterLocal/blob/e715b34ab89ec41d2528417aff5ab8847ad15f62/MULTI_LANE_ARCH_REVIEW.md) | Read-only proposal и его escrow/refund/packet traps, не описание нынешнего кода; [multi-lane](#lanes). |
| [ENGINE_RUNTIME_AUDIT_RU](https://github.com/Xipong/InfiniCrafterLocal/blob/e715b34ab89ec41d2528417aff5ab8847ad15f62/docs/ENGINE_RUNTIME_AUDIT_RU.md) | 28 поправок, scheduler/terminal controls и честные proof limits; [engine audit](#engine-audit), [active boundaries](ENGINE_RUNTIME_BOUNDARIES_RU.md). |
| [TYPED_PRIMITIVE_RUNTIME_AUDIT_RU](https://github.com/Xipong/InfiniCrafterLocal/blob/e715b34ab89ec41d2528417aff5ab8847ad15f62/docs/TYPED_PRIMITIVE_RUNTIME_AUDIT_RU.md) | Units, C# lifecycle, owner-hit trust, oneOf/Repair findings и RED Live20; [typed](#typed), [Live20](#live). |
| [AUDIT_81509E2_FIXES_RU](https://github.com/Xipong/InfiniCrafterLocal/blob/e715b34ab89ec41d2528417aff5ab8847ad15f62/docs/AUDIT_81509E2_FIXES_RU.md) | A1–A9 fixes, дополнительный frozen-first и unchanged captures; [81509e2](#audit-81509e2). |
| [Прежний Terraria guide](https://github.com/Xipong/InfiniCrafterLocal/blob/e715b34ab89ec41d2528417aff5ab8847ad15f62/docs/TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md) | Useful gameplay tables/recipes сохранены в [справочнике](TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md), но это не runtime schema и не текущий game-version audit. |

Внешний baseline archive и рабочие logs остаются evidence оператора. Active guides не требуют конкретного WSL `/tmp`/artifact path; исторические log paths внутри blobs — не обещание их нынешней доступности. Финальный source ZIP/hash, `.tmod`, DLL build и game acceptance всегда имеют отдельные receipts; старый clean-tracked ZIP рецепт не применяют к dirty delivery без проверки его фактического состава.

<a id="v5"></a>
## Первоначальный v5 и стандартизация

- Gameplay Author стал владельцем конечных entities/bindings/calls. Whole-weapon macros, legacy family/profile routing, old schema/cache replay/import и placeholder mandatory PNG paths были удалены; arbitrary ECS/VM не добавлялись. Успешный baseline — три стадии Author/Visual/VFX; Repair остаётся условным, не classifier/judge pass.
- Сохранялись typed item/projectile/equipment executors, explicit movement/controller/event composition и non-archetypal fixtures (workbench-blade, umbrella-grenade, chained door, returning potion, tool/placeable, shield+disc, alternate deployment, equipment+combat), а не whole-weapon presets.
- Terraria vocabulary отделил animation/DamageClass/ammo/consumption; modded class использует exact `ModName/ClassName`, не Generic fallback. Dynamic graph и per-instance assets остались custom из-за shared proxy types; weapon useAmmo, sand ammo/ID-static immunity и load-order переносимость numeric IDs не стали автоматически поддержаны.
- Repair reports описывали exact errors, blocker/support closure, read-only fragments, fieldPermissions и frozen merge. В root copy осталось 33 policies и старые sizes; toolbox snapshot уже сообщает 36, поздний typed snapshot — 43. **Эти числа относятся к разным проходам.** `tools/audit_targeted_repair.py` владеет текущим [`targeted_repair_audit.generated.json`](../contracts/targeted_repair_audit.generated.json); Markdown-копии генератором не владелись.
- Уточнённый handoff называет `readOnlySourceFragments` входом, а `requiredJsonShape` — только формой patch ответа. Malformed JSON, unresolved blocker после одного Repair и registry defects не скрываются deterministic догадкой. Рабочая инструкция — [TARGETED_REPAIR_PROTOCOL_RU](TARGETED_REPAIR_PROTOCOL_RU.md).

Первоначальный refactor report прямо писал об отсутствии toolchain/provider credentials; поздний standardization/toolbox report уже записал Debug/Release DLL builds 0w/0e. Это разные evidence points, не вечный blocker и не общий release-ready PASS.

<a id="engine-audit"></a>
## Широкий C# audit: исправления и пределы

Audit был остановлен по запросу пользователя после detached SpriteBatch fix. Его «65 файлов read» — карта чтения тогдашнего дерева, **не coverage percentage и не список текущих файлов**. Ни игра, ни GPU, ни live provider campaign в этом проходе не запускались.

| Старые пункты | Сохранённое решение | Активная граница |
|---|---|---|
| 1, 20 | Byte enum load validation; strict player-save kind/version/runtime markers | [Placement/storage](ENGINE_RUNTIME_BOUNDARIES_RU.md#persistence) |
| 2–4, 13, 16–17 | Единственный vanilla defense owner, signed authored projection, aggregate-before-cap, сохранённые equipment/blink endpoints | [Item/hooks](ENGINE_RUNTIME_BOUNDARIES_RU.md#items), [units](ENGINE_RUNTIME_BOUNDARIES_RU.md#units) |
| 5–9 | Armor hide index, InfiniCore consumption gate, rejected remote out-pose, client light control, int.MinValue seed safety | [Presentation](ENGINE_RUNTIME_BOUNDARIES_RU.md#presentation), [item](ENGINE_RUNTIME_BOUNDARIES_RU.md#items); exact regressions — original blob |
| 10–12 | JSON-object cacheOnly transform без numeric loss; blank identity rejection без random replacement; применение declared MaxEntityCount | [Contract](ENGINE_RUNTIME_BOUNDARIES_RU.md#contract) и canonical `GeneratorClient` / DTO |
| 14 | Dispose publication fence для verified file/retry state | [Assets](ENGINE_RUNTIME_BOUNDARIES_RU.md#assets); reads/callback cancellation этим не доказана |
| 15, 18–19, 21 | Pull mode без fallthrough, exact delayed owner/NPC identity, authored event-owning damage/class | [Authority](ENGINE_RUNTIME_BOUNDARIES_RU.md#authority), [delay](ENGINE_RUNTIME_BOUNDARIES_RU.md#delay) |
| 22–24 | Request-only prefix normalization, exact generated ammo instance facts, applied-vs-authored trace | [Item/context](ENGINE_RUNTIME_BOUNDARIES_RU.md#items); full registry/refund/command/performance proof не заявлен |
| 25–28 | Client particle/draw multiplier consumers, draw-vs-tick budget reset, owned lazy SpriteBatch Begin/finally-End | [Presentation](ENGINE_RUNTIME_BOUNDARIES_RU.md#presentation); CPU queues не GPU acceptance |

Дополнительные проверки **без production edits** сохранили same-instance NPC.Transform, bounded scheduler drain/reservation refunds и 54 terminal damage сценария, включая совместные on_expire/on_kill с разными due ticks. Это реальные mod-hook/API observers, но не vanilla Kill/collision/game loop. Поздние shared spawn ledger, generation/lineage, asset certification/retirement и all-client VFX cleanup учитываются по текущим source owners, а не выводятся из старой карты чтения.

Исторические доказательства — canonical-source `tools/EngineRuntimeChecks.csproj` против installed tML/FNA/внешних DLL, настоящие Item/Player/NPC hooks и CPU очереди. Прежний итог отчёта: 40 headless checks, 319 Python tests; эти counts не обновляют нынешний suite. Незавершённые placement/craft/asset/mobility/save/MP/GPU/mod-interaction границы перенесены в [limits](ENGINE_RUNTIME_BOUNDARIES_RU.md#limits), не названы новыми подтверждёнными bugs.

<a id="typed"></a>
## Typed primitives, prompt и runtime seams

Verified revision anchors: [units/lifecycle `aa51a486`](https://github.com/Xipong/InfiniCrafterLocal/commit/aa51a48654f6a697b855d8b51eabe6a9aec02b78), [oneOf/frozen repairs `3834acd5`](https://github.com/Xipong/InfiniCrafterLocal/commit/3834acd5faff483717568b94a365eb185205f4aa). Наличие этих commits проверено локально; phase outcomes ниже сообщает preserved audit, не новый run.

- AST parity расширили от известного списка capabilities до DTO declarations и executable reads. Equipment modifiers стали доступны Author; class damage представлен typed selector, generic-only consumers не превращены в вымышленные class-specific операции. Intentionally hidden/custom roster принадлежит [generated parity](PRIMITIVE_PARITY_RU.md).
- Axe tooltip percent `/5` и generated regen HP/s `×2` сохранили прежние integer wire domains; signed percent/points, raw coefficients и world/projectile clocks получили точные пояснения. Исторические replay bytes и frozen digest не переписаны ради GREEN.
- Исправлялись maxRunSpeed hook phase, ammo offset/direct-use projection, custom whip range/tag, proximity expiry/VFX, общий spawn ledger и captured delayed source lineage. Terminal generation reuse пока отменяет pending action; это не immutable terminal snapshot.
- Независимый cold reader получил **только фактически переданный packet**. Requiredness parity не доказала понятность: добавлены damage-source, clocks/sentinels, DamageClass/ItemUseStyle, placement zero/style, event source/target, suppression и exact mandatory fields. Механика не выбиралась host code.
- Serializer fixture с WordPiece proxy сначала показал user 89 655→80 263 chars, затем уточнения подняли его до 88 744; это не exact Gemini token count и не дополнительная compression victory. Local schema в `json_object` не передавалась. Изменение live first-pass quality этими замерами не измерено.
- MP owner-hit поправка сохранила native AddBuff/ApplyDamageToNPC sync и узкий server NPC-pull receipt с generation/sequence/identity. Vanilla owner trust не является server collision/anti-cheat proof; socket-match, remote VFX и custom-tag replication оставались отдельными acceptance seams.
- Runner discovery/selection включили toolbox, консервативно выбирали оба offline roots при shared changes, различали `not_selected` и непокрытые paths и отключали live/project-config для offline. Numeric parameterized cases не удаляли по одному collected count. Последний typed offline snapshot сообщил 780 Python и 65 headless checks, а не доказанный игровой loop.

<a id="live"></a>
## Live acceptance: RED не переписывается

| Snapshot / конфигурация | Исторический результат и граница |
|---|---|
| `aa51a486` → quota report [`6fbb51a1`](https://github.com/Xipong/InfiniCrafterLocal/commit/6fbb51a1ec0043b0bc75d65e485806f42e2c895d); `gemini-3.5-flash-lite`, no-image, json_object, parallel=3 | Preflight/availability отдельно от full panel. Direct API location rejection и proxy daily RPD quota=500 остановили кампанию; минутный retry не закрывал daily quota. 20-case panel на 3.5 не стартовал. Нынешняя availability неизвестна. |
| 3.1 pilot на `6fbb51a1`, затем medium/18000 по разрешению пользователя | oneOf выбирал чужую ветку вместо explicit discriminator и создавал ложные Repair permissions. Panel остановлен; partial attempts не суммируются в acceptance. Offline diagnostic replay после fix не является успешным live Repair. |
| Clean `3834acd5`, `gemini-3.1-flash-lite`, **все стадии medium/18000**, 20 cases, parallel=3, no images/fallback | **Pipeline 20/20 GREEN, acceptance RED (exit 1)**: firstAuthorSuccesses=2 при threshold ≥10. 18 final Gameplay Repairs; два first-Author cases тоже имели ранее оборванные transport attempts. |
| Отдельный no-image C# FromJson diagnostic replay того panel | 20 passed/0 failed на QA fixture; не image generation, game/MP loop и не изменение acceptance verdict. CI tML build был skipped из-за отсутствующих DLL; локальная DLL сборка — отдельное evidence. |
| Поздний [`cf503d4`](https://github.com/Xipong/InfiniCrafterLocal/commit/cf503d483baa87323bdab9c5d8871084391612c4) / `81509e2` captures | Исходный отчетный результат **18/20, RED** сохранён; принятый позднее offline `meteor_spacegun` replay его не меняет. Смысл нового neutral-omission контракта не применяется задним числом к кампании. |

Full `3834acd5` campaign сохранила все **23 craft attempts, 94 logical / 94 HTTP requests**, 3 case-level transport retries (после 60 s), без hidden low-level retries; с interrupted attempt было 19 scoped Repair requests. Final-case разбор: 17/18 repaired cases пропускали required params, 76 missing-field и 37 companion shape_one_of diagnostics; 11 случаев имели только omissions. Это не 37 независимых design failures и не доказательство единственной причины в модели/prompt.

Frozen `summary.json` digest в preserved report: `13a243ff28e19404dfaa1185bb3337d8faf4dc8de17ea17f0fbf71320a5791eb`. Campaign label: `typed-final-3834acd-flashlite31-all18k-medium-live20`; исходный summary не переписывался. Raw campaign artifacts не встроены в этот Markdown; доступность внешних logs здесь не заявлена. Для причинного улучшения нужен matched prompt-only эксперимент на отдельном snapshot, а не понижение порога, выбор удачного retry или host default.

<a id="audit-81509e2"></a>
## Поправки после аудита `81509e2`

Исходная neutral-omission revision: [`81509e22dec0f149b597ad36ec3377f0358e5cb4`](https://github.com/Xipong/InfiniCrafterLocal/commit/81509e22dec0f149b597ad36ec3377f0358e5cb4). Таблица фиксирует **решения**, не предлагает восстановить старые test filenames после их консолидации.

| Finding | Сохранённая поправка / владелец |
|---|---|
| A1 | Null→omission только объявленный фактически использованный strict transport; unknown keys/array indices/raw Repair не очищаются. [Contract](ENGINE_RUNTIME_BOUNDARIES_RU.md#contract). |
| A2 | Exact placementCallId permission допускает нужный binding/reference repair; frozen соседей не раскрывает. [Repair protocol](TARGETED_REPAIR_PROTOCOL_RU.md). |
| A3 | Каждое sprite diagnostic указывает свой negative-prompt leaf/permission. [Asset lifecycle](IMAGE_ASSET_LIFECYCLE_RU.md). |
| A4 | Item impactSprite идёт в dedicated detached sprite consumer, без dust/inventory downgrade. [Assets/presentation](ENGINE_RUNTIME_BOUNDARIES_RU.md#assets). |
| A5 | Убраны arbitrary generated-buff deadbands; float32 neutral collapse отвергается до compile без quantization. [Precision](ENGINE_RUNTIME_BOUNDARIES_RU.md#units). |
| A6 | Только preflight notRun semantics, не downstream compiler/parser failure или текст лога, определяют SKIP. [Verification](ENGINE_RUNTIME_BOUNDARIES_RU.md#verification). |
| A7 | Каждый present buff leaf проверяется независимо от активного companion; legacy absent leaves сохраняют объявленную семантику. [Contract/precision](ENGINE_RUNTIME_BOUNDARIES_RU.md#units). |
| A8 | Inert-buff Repair получает causal nonneutral effect leaves и нужные missing companions, не валидные duration/color. [Repair protocol](TARGETED_REPAIR_PROTOCOL_RU.md). |
| A9 | Malformed receipt rows/path/index дают structured RED, не exception или ложное source coverage. Exact authored path/value mapping не ослабляется self-reported receipt status. [Contract](ENGINE_RUNTIME_BOUNDARIES_RU.md#contract). |
| Дополнительный Gameplay frozen-first | Premerge проверяет structure/type/discriminator/unknown fields; numerical bounds — после frozen merge. Wrong frozen numeric sibling не отменяет полезный exact repair. [Repair protocol](TARGETED_REPAIR_PROTOCOL_RU.md). |

Preserved integrated report записал 1299 Python tests, 69 headless checks, обычную DLL-only сборку tML `2026.6.3.6` 0w/0e, CI exit-code regressions и unchanged 70 historical compiled documents/receipts + 18 VFX manifests. Это historical report-level evidence, **не выполненные в Markdown consolidation gates**. `.tmod`, providers, live game, GPU и MP sockets не запускались. Captured Author/Repair bytes и прежний Live20 RED сохранены; рабочие регрессии теперь ищутся по [contract owners](TEST_CONTRACT_OWNERS_RU.md).

<a id="lanes"></a>
## Multi-lane: старый proposal и актуальная граница

`MULTI_LANE_ARCH_REVIEW` был read-only планом превращения single-lane fields в массивы и добавления lane byte во все packets. Его estimate, старые line offsets и предложенный protocol layout — **не текущее API**. Реальный [`InfiniCraftPlayer.MultiDev.cs`](../ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.MultiDev.cs) оставляет lane 1 и два отдельных jobs/inputs; packet/state owners надо читать заново.

Полезные traps сохранены как review checklist: per-lane pending/start/clear/tick и exact A/B slot routing; escrow replies не применяются к другой операции; commit/cancel/server authority и requestId dedupe согласованы; world-exit backup не даёт double refund; audio/UI/profile routing не стирают состояние другой lane; save/load и скрытие заполненной/pending lane проверяются совместно. Global pending boolean или предположение «backend profile field означает готовый multi-lane» недостаточны. UI/core gate и старый порядок patching были proposal design choices, не принятой runtime policy. End-to-end ACK/reconnect/refund границы остаются в [runtime limits](ENGINE_RUNTIME_BOUNDARIES_RU.md#limits).

<a id="reference"></a>
## Проверки и внешний игровой справочник

Toolbox snapshot сообщил 85 Python tests, 52 vertical witnesses, 5 caught mutations, 87 standardization checks и DLL Debug/Release 0w/0e. Он отдельно оставил tML self-test, SP assets/VFX smoke, host/client, Calamity и real LLM craft как **NotRun**; `releaseReady=false` не скрывался deterministic GREEN. Числа и elapsed times не являются текущим coverage/performance benchmark. Рабочие команды/selection находятся у [test owners](TEST_CONTRACT_OWNERS_RU.md), а proof ladder — у [engine verification](ENGINE_RUNTIME_BOUNDARIES_RU.md#verification).

[Terraria weapons/progression](TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md) сохраняет предметные таблицы, gates, world/NPC/biome/event tips и crafting trees. Это внешний gameplay reference прежней редакции с Wiki-ссылками, **не runtime contract, не валидатор progression и не утверждение совместимости установленного tML с Terraria 1.4.5**. Optional stage/class/acquisition notes — пример анализа, не новые обязательные поля Author. Для authored balance используется [balance corridor](BALANCE_REFERENCE_VANILLA_PROGRESS_LIMITS_RU.md), для wire — registry/schema.
