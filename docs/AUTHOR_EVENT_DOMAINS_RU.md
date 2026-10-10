# Точное имя nearest damage и разделение fresh/wire domain

Категории аудита **B15.2–B15.3** уточняют низкоуровневый Author API. Они не добавляют новый combat algorithm и не меняют native DTO/consumer.

## Damage nearest: один центр, несколько ближайших целей

```json
{
  "id": "nearby_damage",
  "fn": "damage_nearest_on_event",
  "target": "bolt",
  "params": {
    "when": "on_hit",
    "maxTargets": 3,
    "rangeTiles": 8,
    "damageMultiplier": 0.5,
    "delayTicks": 0
  }
}
```

| Fresh Author | Прежний wire / исполняемый смысл |
|---|---|
| `damage_nearest_on_event` | `action="chain_damage_on_event"`, `actionCode=4` |
| `maxTargets: 1…12` | `count`: максимум дополнительных NPC |
| `rangeTiles: 1…60` | Та же физическая область вокруг одного recorded event center; граница включена |
| `when: "on_hit" / "on_crit"` | Прежний event; нужен действительный item-body или projectile producer |
| `damageMultiplier: 0.05…2` | Один multiplier authored base damage для каждой выбранной цели |
| `delayTicks: 0…600`, optional | Прежняя задержка действия; существующие scheduler и authority правила |

`RuntimeProgramExecutor.ChainDamage` собирает chaseable NPC внутри одного радиуса, исключает directTarget, сортирует по расстоянию от того же центра и применяет урон первым `count`. Центр не переносится на следующую цель. Damage не уменьшается с расстоянием или порядком выбора. Результирующая потеря HP может различаться из-за native defense и других действующих правил Terraria. Порядок NPC на совершенно одинаковом расстоянии не получает нового обещания tie-break.

Поэтому слово `chain` убрано из свежего имени и model-facing пояснения количества. Технический discriminator остаётся прежним. Это **Alias Lowering**: `fn` выбирает одну точную action/opcode пару, `maxTargets` дословно передаёт `count`; контекст, название предмета и family не участвуют. Fn-selected literal receipts продолжают использовать общий статус `technical_projection`, scalar count receipt — `delivered` с источником `params.maxTargets`.

Старое `chain_damage_on_event` остаётся internal registry entry только для wire provenance. Оно отсутствует в свежих provider variants, Author catalog, диагностических предложениях для inert stationary entity и Repair create API. Все предложения диагностики используют ту же exposed-only registry границу. Старые Author calls не принимаются как новая альтернативная грамматика; сохранённые compiled wire не переименовываются. Ни последовательные hops, ни falloff, ни geometry/VFX chain этим PR не добавляются. Реальные on_hit/on_crit сохраняют owner authority и общий native damage consumer.

## Same-target bias: диапазон различимых Author choices

Свежий `target_and_fire.sameTargetBias` принимает **0…0.9**. Значение определяет distance score предыдущей цели:

`score = distance × (1 − bias)`

Для остальных NPC score равен distance. При `hardRange=false` native selector выбирает минимальный score строго меньше `rangeTiles × 16`. Поэтому soft range для предыдущей цели является score threshold: предыдущая NPC на расстоянии 100 px с bias 0.9 может выиграть у NPC на 15 px при range 20 px. При явно выбранном `hardRange=true` геометрическая граница проверяется до discount; `requireLineOfSight` и `targetPolicy` остаются независимыми решениями Author. Это не вероятность повторного попадания. Текущий firing caller использует `FindFiringTarget`; retained `FindNearestNpc` сохраняет прежний soft-score consumer для других movement paths.

В сохранённом wire допустим прежний **0…1**. Native selector использует `min(bias, 0.9)`, так что старые 0.9, 0.95 и 1 дают одинаковый discount. DTO сохраняет исходное число 0.95/1, а C# execution применяет прежнюю saturation; loader и compiler не переписывают сохранённый документ. Новое значение 0.95 от Author отвергается, а не clamp-ится в 0.9 и не выдаётся за старую запись.

Обе границы объявлены в единственном registry owner:

- `params.sameTargetBias.maximum=0.9` управляет fresh schema, cards, validation и Repair.
- `retained_receipt_params.sameTargetBias.maximum=1` описывает только предыдущий scalar projection/domain без исходного Author.
- Audit inventory отдельно показывает `retainedWireProvenance`. Эта информация не превращается в параметры, доступные Author.

## Wire/source и Repair граница

Scalar receipt с исходным Author проверяется по текущему ParamSpec и должен совпадать с его точной проекцией. Отсутствие Author не создаёт source evidence: проверяются declared paths, тип/диапазон значения, fixed literals и согласованность с wire. При явно объявленном prior domain wire-only audit использует его; прочие scalar значения проверяет по current projection. Проверка не восстанавливает и не выдумывает отсутствующий Author.

Для wire без provenance присутствующий targeting bias отдельно проверяется по retained 0…1. Bool, null, строки, нечисла, отрицательные и >1 отвергаются без записи нового значения. Absent field сохраняет прежнюю DTO семантику.

Расширение точного scalar audit выявило одну необходимую совместимость уже существующего #14 alias: старый `pull_on_event.mode="owner_to_target"` теперь выбирается отдельной fresh `pull_owner_to_event_target`. Его прежний enum добавлен **только** в retained provenance metadata. Fresh NPC-pull enum остаётся `target_to_owner / target_to_entity`. Frozen prior fixture сохранён без правок.

Repair открывает только ошибочный leaf: invalid `maxTargets` или `sameTargetBias`. Попытки переписать валидный range одновременно с полезной поправкой игнорируются и попадают в audit. Неверное значение на разрешённом leaf остаётся RED. Никакого fallback выбора числа или преобразования вероятности в discount нет.

## Доказательства и пределы проверки

`test_author_event_domains.py` проходит registry→provider/cards→validator→compiler receipts→strict wire. Матрицы включают оба event и item/projectile producers, 1/3/12 targets, явные delay/radius/damage значения, forged/missing/duplicate literals, неверный count source/path/domain, malformed fresh inputs, wire с/без receipts и frozen leaf Repair.

`fixtures/event_domain_retained_wire.json` содержит пять неизменённых записей original compiler на `c0a8450`: два radial event и bias 0.9/0.95/1. Каждый wire имеет SHA-256; alias сравнивается с прежними gameplay/runtime payload дословно. Старый bias=0.9 Author остаётся валидным, но его архивные receipts не содержат пяти новых targeting-neutral omission rows: source-aware audit точно отклоняет эти пять отсутствий. Fresh compile проходит полный audit; test-only projection удаляет лишь объявленные neutral leaves и их receipts, сохраняя архивный wire без изменений. Общие historical seed/retained-wire fixtures продолжают проверяться и не переписаны.

`EngineRuntimeChecks.EventDomains.cs` подготовлен для native проверки двух фактов. Radial check вызывает настоящий `ExecuteAction`/`ApplyDamageToNPC`, сравнивает с native damage control, проверяет исключённый directTarget, сортировку, count, inclusive boundary и NPC вне исходного радиуса, находящуюся рядом с выбранной целью. Bias check читает реальный строгий JSON DTO, вызывает actual `FindNearestNpc` при четырёх ролях, проверяет сохранение 0.95/1, одинаковую saturation и previous target вне физического range. Source gate связывает эти methods с реальными callers, включая текущий `ApplyTargetAndFire → FindFiringTarget`; восемь isolated native-source mutations обязаны его нарушить.

Это method-level checks, не эмуляция полного world/network loop. В среде подготовки **C# build, запуск EngineRuntimeChecks и игровые SP/MP smoke = notRun** из-за отсутствия .NET 8, tModLoader, ParticleLibrary/Luminance. Portable/source проверки не заявляются native execution.

## Канонические владельцы

- [`capability_registry.py`](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py): fresh параметры, exact wire alias и prior domains.
- [`technical_lowering.py`](../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py): scalar projection и source/wire receipt checks.
- [`wire_validator.py`](../LocalGenerator/infini_local/core/runtime_authoring/wire_validator.py): present saved targeting domain без provenance.
- [`RuntimeProgramExecutor.cs`](../ModSources/InfiniCrafterLocal/Common/Runtime/RuntimeProgramExecutor.cs): прежний `ChainDamage` и authority.
- [`GeneratedProjectile.Executors.cs`](../ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Executors.cs): current `ApplyTargetAndFire`/`FindFiringTarget` и retained `FindNearestNpc`.
- [`RuntimeProgramSpec.cs`](../ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs): прежние action 4 и обе DTO границы bias 0…1.
