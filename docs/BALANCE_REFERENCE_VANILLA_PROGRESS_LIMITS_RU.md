# Balance corridor — текущий owner и архив legacy policy

<a id="current"></a>
## Текущая архитектура

[combine_balance.stat_profile_for](../LocalGenerator/infini_local/pipelines/combine_balance.py#L60) вычисляет broad **numeric parent guidance**, а [llm_authoring_prompt._balance_corridor](../LocalGenerator/infini_local/pipelines/llm_authoring_prompt.py#L182) проецирует его в Author packet. Источники: damage/useTime, tool power, sustain/defense, rarity/value и explicit generated generationDepth. Names/tags/category/tooltip/knowledge не читаются для corridor. Формулы не копируются в prose или новые modules.

`authority=source_numeric_facts_only`, `gameplayRouter=false`: powerBudget и оставшийся broadEnvelope не разрешают коду выбрать mechanic/kind/input/asset или переписать design. Расчёт рекомендуемого урона и производный коридор damage удалены: packet сохраняет исходный parentDamage, но не превращает лечение, tool power, цену или rarity ID в suggested damage. Урон результата выбирает Author; schema/validator/runtime применяют hard contract/safety bounds, не «идеальный балансер». Current combine path не содержит post-Author `report|safety|normalize` mode policy. Terraria progression guide — human reference, не активный helper/prompt ontology.

Active flow: numeric parent facts → one Author packet → [strict compile/conditional Repair](THREE_STAGE_LLM_PIPELINE_RU.md#flow) → exact wire → C# hard safety. Sparse explicit zero/default сохраняет provenance; [declared omission](DECLARED_NEUTRAL_OMISSIONS_RU.md#contract) — отдельная семантика, не soft balance clamp. Limits/packet IDs принадлежат `InfiniRuntimeLimits.cs`/`InfiniNetPacketIds.cs` ([map](../PROJECT_MAP_RU.md#csharp)), не баланс-документу.

<a id="legacy"></a>
## Legacy v0.4.220–0.4.226 — не действующий contract

Старые `balance_mode.py/balance_policy.py/balance_report.py` отсутствуют в текущем дереве. Перечень ниже сохранён как объяснение исторических отчётов, **не команды включения и не обещание сохранённых knobs**:

- `INFINI_BALANCE_MODE=report|safety|normalize`: safety сохранял authored numbers от soft envelopes, применял Python technical corridor и писал suggestions `applied=false`; normalize применял weapon DPS/equipment envelopes + corridor с provenance; report оставлял advice без Python clamps. C# hard safety во всех случаях не отключался.
- Taxonomy: `balance/balanceClamp` — advice или soft normalization; `safety/safetyClamp/runtime compiler clamps` — FPS/network/runtime caps; `contract/contractClamp` — shape/unsupported/validation. `debug.balanceReport.balanceMode`, advice `applied=false`, mutation `applied=true` и explicit equipment `apply_clamps` относились к этому пути, не новой v5 гарантии.
- v0.4.220 narrow patch surface: runtimePlan/engineCalls, attack и explicit repairPatch.gameplay; name/tooltip/concept/visual/tags/parents/ids frozen, rejected rewrites шли в `debug.runtimePlanRepairPatchContract` / balanceReport.clamps.contract. Эти **legacy fields не принимаются** нынешним [leaf-local Repair](TARGETED_REPAIR_PROTOCOL_RU.md#frozen-first).
- v0.4.226 единые power bands/envelopes тогда принадлежали balance_policy; report/pipeline только использовали их. `accessoryBudgetReport/armorBudgetReport` и сравнение authored engineCalls с compiler defaults были legacy provenance, не reason to restore a parallel scorer.

Removed prompt fields `softDamageCapPerHit/softAoeTilesCap/softActiveProjectileCap/sourceEnvelope/terrariaProgressionReference` остаются неактивной историей. Не возвращать category routing, dynamic caps, progression ontology или второй judge под видом balance guidance.
