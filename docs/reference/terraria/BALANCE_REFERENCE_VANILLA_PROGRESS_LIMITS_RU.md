# Balance corridor — текущий owner и архив legacy policy

<a id="current"></a>
## Текущая архитектура

[combine_balance.stat_profile_for](../../../LocalGenerator/infini_local/pipelines/combine_balance.py#L60) вычисляет broad **numeric parent guidance**, а [llm_authoring_prompt._balance_corridor](../../../LocalGenerator/infini_local/pipelines/llm_authoring_prompt.py#L182) проецирует его в Author packet. Источники: damage/useTime, tool power, sustain/defense, rarity/value и explicit generated generationDepth. Names/tags/category/tooltip/knowledge не читаются для corridor. Формулы не копируются в prose или новые modules.

`authority=source_numeric_facts_only`, `gameplayRouter=false`: powerBudget и оставшийся broadEnvelope не разрешают коду выбрать mechanic/kind/input/asset или переписать design. Расчёт рекомендуемого урона и производный коридор damage удалены: packet сохраняет исходный parentDamage, но не превращает лечение, tool power, цену или rarity ID в suggested damage. Урон результата выбирает Author; schema/validator/runtime применяют hard contract/safety bounds, не «идеальный балансер». Current combine path не содержит post-Author `report|safety|normalize` mode policy. Terraria progression guide — human reference, не активный helper/prompt ontology.

Active flow: numeric parent facts → one Author packet → [strict compile/conditional Repair](../../development/pipeline/THREE_STAGE_LLM_PIPELINE_RU.md#flow) → exact wire → C# hard safety. Sparse explicit zero/default сохраняет provenance; [declared omission](../authoring/DECLARED_NEUTRAL_OMISSIONS_RU.md#contract) — отдельная семантика, не soft balance clamp. Limits/packet IDs принадлежат `InfiniRuntimeLimits.cs`/`InfiniNetPacketIds.cs` ([map](../../development/CODE_MAP_RU.md#csharp)), не баланс-документу.

<a id="legacy"></a>
## Граница ответственности

Balance guidance не вводит post-Author scorer/clamp mode, dynamic damage caps, category router или второй judge. Исторические policy knobs/IR не входят в текущий API; техническая validation/Repair работает только с current contract. Advisory сравнение ингредиентов не меняет уже принятую программу.
