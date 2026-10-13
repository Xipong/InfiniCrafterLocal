# Владельцы документации и миграция — 0.5.00

## Владельцы решений

| Решение читателя | Канонический doc owner | Source owner |
|---|---|---|
| Что это и как начать | root README, user/START | launchers и bootstrap |
| Настройки, config priority, безопасный запуск | user/SETTINGS, user/OPERATIONS | desktop settings_schema, trace_state, server_controls; core config_bootstrap |
| Ошибки, privacy и MP transport | user/DIAGNOSTICS, user/MULTIPLAYER, user/COMMANDS | web/services/storage + native host/asset consumers |
| Общая authority и поиск кода | development/ARCHITECTURE, CODE_MAP, OWNERS | canonical production owners по задаче |
| Контракт новой механики/Repair/lowering | development vertical slice, Repair/policy + reference manuals | registry, program_schema, validator/compiler/technical_lowering и C# consumers |
| Сборка/приёмка | development/BUILD, TESTING | csproj/runner/gates и behavioral suites |
| Полные canonical projections | reference/GENERATED → стабильные outputs | три Markdown producers, отдельно JSON exporter |
| Исторические verdicts/замеры | archive index и полный исходный отчёт | исходный commit/fixture/receipt; не current guarantee |
| Лицензия и вклад | LICENSE, LICENSE_RU, CONTRIBUTING | сопровождающий Xipong; LICENSE определяющий |

Это роли документации, не выдуманный список персональных maintainer-назначений. Автор изменения поддерживает docs рядом со своим canonical source; общий navigation/migration owner — этот документ. [Реестр исходников](OWNERS_RU.md).

## Политика сохранения

- Полные тематические руководства перенесены, их уникальные ограничения/история не сокращены. Англоязычный native craft lifecycle переведён на русский с сохранением facts, selectors, budgets и исторических пределов проверки. Относительные ссылки пересчитаны; contract facts, selectors, units, null/zero/absence и исторические RED/notRun остаются.
- Стабильные generated `lowery.md`, `TECHNICAL_LOWERING_AUDIT_RU.md`, три inventory/audit/parity в `docs/` **не перенесены**; после структурного C# переноса inventory обновлён своим producer только по новым owner paths. Author/wire/параметры не переавторствуются; freshness проверяется producer.
- Required root/LocalGenerator entrypoints сохранены полезными краткими маршрутами. Old-path docs, на которые ссылаются frozen generated/source/AGENTS consumers, сохраняют anchors и ведут к одному owner.
- README release-простыня перенесена в archive. Current README явно отделяет alpha-preparation tree от опубликованной поставки.
- LICENSE/перевод и исходные notices не изменяются. Полные исходные bytes baseline — Git `c546576`; архивные ссылки обновлены для чтения в новой структуре.

## Старый путь → канонический путь

| Старый путь | Новый владелец | Старый вход |
|---|---|---|
| `AGENT_INDEX_RU.md` | [docs/development/OWNERS_RU.md](OWNERS_RU.md) | маршрут сохранён |
| `BUILD_QOL_RU.md` | [docs/development/BUILD_RU.md](BUILD_RU.md) | маршрут сохранён |
| `PROJECT_ARCHITECTURE_RU.md` | [docs/development/ARCHITECTURE_RU.md](ARCHITECTURE_RU.md) | маршрут сохранён |
| `PROJECT_MAP_RU.md` | [docs/development/CODE_MAP_RU.md](CODE_MAP_RU.md) | маршрут сохранён |
| `QUICK_START_RU.md` | [docs/user/OPERATIONS_RU.md](../user/OPERATIONS_RU.md) | маршрут сохранён |
| `README_RU.md` | [docs/archive/README_BEFORE_ALPHA_RU.md](../archive/README_BEFORE_ALPHA_RU.md) | маршрут сохранён |
| `TODO_ROADMAP_VERY_LATER_RU.md` | [docs/development/ROADMAP_RU.md](ROADMAP_RU.md) | маршрут сохранён |
| `command.md` | [docs/user/COMMANDS_RU.md](../user/COMMANDS_RU.md) | маршрут сохранён |
| `docs/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md` | [docs/development/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md](ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md) | маршрут сохранён |
| `docs/AUDIT_PR_REVIEW_MAP_RU.md` | [docs/archive/AUDIT_PR_REVIEW_MAP_RU.md](../archive/AUDIT_PR_REVIEW_MAP_RU.md) | перенесён |
| `docs/AUTHOR_DIRECT_CONSTRUCTION_RU.md` | [docs/archive/AUTHOR_DIRECT_CONSTRUCTION_RU.md](../archive/AUTHOR_DIRECT_CONSTRUCTION_RU.md) | перенесён |
| `docs/AUTHOR_EVENT_DOMAINS_RU.md` | [docs/reference/AUTHOR_EVENT_DOMAINS_RU.md](../reference/AUTHOR_EVENT_DOMAINS_RU.md) | перенесён |
| `docs/AUTHOR_ITEM_ALIASES_RU.md` | [docs/reference/AUTHOR_ITEM_ALIASES_RU.md](../reference/AUTHOR_ITEM_ALIASES_RU.md) | перенесён |
| `docs/AUTHOR_PROMPT_CLARITY_RU.md` | [docs/archive/AUTHOR_PROMPT_CLARITY_RU.md](../archive/AUTHOR_PROMPT_CLARITY_RU.md) | перенесён |
| `docs/AUTHOR_REQUEST_COMPACTION_RU.md` | [docs/development/AUTHOR_REQUEST_COMPACTION_RU.md](AUTHOR_REQUEST_COMPACTION_RU.md) | перенесён |
| `docs/BALANCE_REFERENCE_VANILLA_PROGRESS_LIMITS_RU.md` | [docs/reference/BALANCE_REFERENCE_VANILLA_PROGRESS_LIMITS_RU.md](../reference/BALANCE_REFERENCE_VANILLA_PROGRESS_LIMITS_RU.md) | перенесён |
| `docs/BUGFIX_0_4_251_RU.md` | [docs/archive/BUGFIX_0_4_251_RU.md](../archive/BUGFIX_0_4_251_RU.md) | перенесён |
| `docs/CHANNEL_BEAM_SUSTAIN_GEOMETRY_RU.md` | [docs/reference/CHANNEL_BEAM_SUSTAIN_GEOMETRY_RU.md](../reference/CHANNEL_BEAM_SUSTAIN_GEOMETRY_RU.md) | перенесён |
| `docs/CHILD_COMBAT_INHERITANCE_RU.md` | [docs/reference/CHILD_COMBAT_INHERITANCE_RU.md](../reference/CHILD_COMBAT_INHERITANCE_RU.md) | перенесён |
| `docs/CODEX_IMAGE_OAUTH_RU.md` | [docs/user/CODEX_IMAGE_OAUTH_RU.md](../user/CODEX_IMAGE_OAUTH_RU.md) | перенесён |
| `docs/CURRENT_WORLD_TECHNICAL_FIXES_RU.md` | [docs/development/CURRENT_WORLD_TECHNICAL_FIXES_RU.md](CURRENT_WORLD_TECHNICAL_FIXES_RU.md) | маршрут сохранён |
| `docs/DECLARED_NEUTRAL_OMISSIONS_RU.md` | [docs/reference/DECLARED_NEUTRAL_OMISSIONS_RU.md](../reference/DECLARED_NEUTRAL_OMISSIONS_RU.md) | перенесён |
| `docs/ENGINE_RUNTIME_BOUNDARIES_RU.md` | [docs/development/ENGINE_RUNTIME_BOUNDARIES_RU.md](ENGINE_RUNTIME_BOUNDARIES_RU.md) | маршрут сохранён |
| `docs/FORGE_HEART_0_4_252_RU.md` | [docs/archive/FORGE_HEART_0_4_252_RU.md](../archive/FORGE_HEART_0_4_252_RU.md) | перенесён |
| `docs/HISTORICAL_RUNTIME_AUDIT_2026_10_RU.md` | [docs/archive/HISTORICAL_RUNTIME_AUDIT_2026_10_RU.md](../archive/HISTORICAL_RUNTIME_AUDIT_2026_10_RU.md) | маршрут сохранён |
| `docs/HISTORY_RU.md` | [docs/archive/HISTORY_RU.md](../archive/HISTORY_RU.md) | перенесён |
| `docs/IMAGE_ASSET_LIFECYCLE_RU.md` | [docs/development/IMAGE_ASSET_LIFECYCLE_RU.md](IMAGE_ASSET_LIFECYCLE_RU.md) | маршрут сохранён |
| `docs/INITIAL_NPC_EXCLUSION_RUNTIME_RU.md` | [docs/reference/INITIAL_NPC_EXCLUSION_RUNTIME_RU.md](../reference/INITIAL_NPC_EXCLUSION_RUNTIME_RU.md) | перенесён |
| `docs/ITEM_QUALITY_CONTEXT_RU.md` | [docs/reference/ITEM_QUALITY_CONTEXT_RU.md](../reference/ITEM_QUALITY_CONTEXT_RU.md) | перенесён |
| `docs/LLM_PROMPT_CACHE_AND_LATENCY_RU.md` | [docs/development/LLM_PROMPT_CACHE_AND_LATENCY_RU.md](LLM_PROMPT_CACHE_AND_LATENCY_RU.md) | перенесён |
| `docs/LLM_PROVIDER_ADMISSION_RU.md` | [docs/development/LLM_PROVIDER_ADMISSION_RU.md](LLM_PROVIDER_ADMISSION_RU.md) | маршрут сохранён |
| `docs/LLM_TRANSPORT_REQUEST_SHAPE_RU.md` | [docs/development/LLM_TRANSPORT_REQUEST_SHAPE_RU.md](LLM_TRANSPORT_REQUEST_SHAPE_RU.md) | перенесён |
| `docs/LOW_LEVEL_RUNTIME_AUTHORING_RU.md` | [docs/reference/LOW_LEVEL_RUNTIME_AUTHORING_RU.md](../reference/LOW_LEVEL_RUNTIME_AUTHORING_RU.md) | маршрут сохранён |
| `docs/LOW_LEVEL_RUNTIME_EXTERNAL_REFERENCES_RU.md` | [docs/reference/LOW_LEVEL_RUNTIME_EXTERNAL_REFERENCES_RU.md](../reference/LOW_LEVEL_RUNTIME_EXTERNAL_REFERENCES_RU.md) | перенесён |
| `docs/LUNA_MEDIUM_COMPREHENSION_RU.md` | [docs/archive/LUNA_MEDIUM_COMPREHENSION_RU.md](../archive/LUNA_MEDIUM_COMPREHENSION_RU.md) | перенесён |
| `docs/MODEL_FACING_UNITS_RU.md` | [docs/reference/MODEL_FACING_UNITS_RU.md](../reference/MODEL_FACING_UNITS_RU.md) | перенесён |
| `docs/NAMED_ITEM_EFFECT_GROUPS_RU.md` | [docs/reference/NAMED_ITEM_EFFECT_GROUPS_RU.md](../reference/NAMED_ITEM_EFFECT_GROUPS_RU.md) | перенесён |
| `docs/NATIVE_CRAFT_LIFECYCLE_QOL.md` | [docs/development/NATIVE_CRAFT_LIFECYCLE_QOL.md](NATIVE_CRAFT_LIFECYCLE_QOL.md) | перенесён |
| `docs/NATIVE_EQUIPMENT_UTILITIES_RU.md` | [docs/reference/NATIVE_EQUIPMENT_UTILITIES_RU.md](../reference/NATIVE_EQUIPMENT_UTILITIES_RU.md) | перенесён |
| `docs/OPENROUTER_ROUTING_RU.md` | [docs/user/OPENROUTER_ROUTING_RU.md](../user/OPENROUTER_ROUTING_RU.md) | перенесён |
| `docs/OWN_STACK_CHANCE_RU.md` | [docs/reference/OWN_STACK_CHANCE_RU.md](../reference/OWN_STACK_CHANCE_RU.md) | перенесён |
| `docs/PR18_CANONICAL_NOTATION_CHECKPOINT_RU.md` | [docs/archive/PR18_CANONICAL_NOTATION_CHECKPOINT_RU.md](../archive/PR18_CANONICAL_NOTATION_CHECKPOINT_RU.md) | перенесён |
| `docs/PRESENTATION_CONSISTENCY_RU.md` | [docs/reference/PRESENTATION_CONSISTENCY_RU.md](../reference/PRESENTATION_CONSISTENCY_RU.md) | перенесён |
| `docs/PRESENT_PLACED_ITEM_SPRITE_RU.md` | [docs/reference/PRESENT_PLACED_ITEM_SPRITE_RU.md](../reference/PRESENT_PLACED_ITEM_SPRITE_RU.md) | перенесён |
| `docs/PROJECTILE_AUTHOR_API_RU.md` | [docs/reference/PROJECTILE_AUTHOR_API_RU.md](../reference/PROJECTILE_AUTHOR_API_RU.md) | маршрут сохранён |
| `docs/PROJECTILE_HITBOX_CURVE_RU.md` | [docs/reference/PROJECTILE_HITBOX_CURVE_RU.md](../reference/PROJECTILE_HITBOX_CURVE_RU.md) | перенесён |
| `docs/PROJECTILE_PHASE_MODIFIERS_RU.md` | [docs/reference/PROJECTILE_PHASE_MODIFIERS_RU.md](../reference/PROJECTILE_PHASE_MODIFIERS_RU.md) | перенесён |
| `docs/PROJECTILE_TARGET_EMISSION_RU.md` | [docs/reference/PROJECTILE_TARGET_EMISSION_RU.md](../reference/PROJECTILE_TARGET_EMISSION_RU.md) | перенесён |
| `docs/RECIPE_HEALTH_AND_CONTRACTS_RU.md` | [docs/reference/RECIPE_HEALTH_AND_CONTRACTS_RU.md](../reference/RECIPE_HEALTH_AND_CONTRACTS_RU.md) | перенесён |
| `docs/REFERENCED_ENTITY_REQUIREMENTS_RU.md` | [docs/reference/REFERENCED_ENTITY_REQUIREMENTS_RU.md](../reference/REFERENCED_ENTITY_REQUIREMENTS_RU.md) | перенесён |
| `docs/REPAIR_REQUEST_COMPACTION_RU.md` | [docs/development/REPAIR_REQUEST_COMPACTION_RU.md](REPAIR_REQUEST_COMPACTION_RU.md) | перенесён |
| `docs/SENTRY_LIFECYCLE_BUDGET_RU.md` | [docs/reference/SENTRY_LIFECYCLE_BUDGET_RU.md](../reference/SENTRY_LIFECYCLE_BUDGET_RU.md) | перенесён |
| `docs/SENTRY_TARGETING_VOLLEY_RU.md` | [docs/reference/SENTRY_TARGETING_VOLLEY_RU.md](../reference/SENTRY_TARGETING_VOLLEY_RU.md) | перенесён |
| `docs/SIGNED_VERTICAL_ACCELERATION_RU.md` | [docs/reference/SIGNED_VERTICAL_ACCELERATION_RU.md](../reference/SIGNED_VERTICAL_ACCELERATION_RU.md) | перенесён |
| `docs/SPAWN_DISTRIBUTIONS_AND_TARGET_GEOMETRY_RU.md` | [docs/reference/SPAWN_DISTRIBUTIONS_AND_TARGET_GEOMETRY_RU.md](../reference/SPAWN_DISTRIBUTIONS_AND_TARGET_GEOMETRY_RU.md) | перенесён |
| `docs/TARGETED_REPAIR_PROTOCOL_RU.md` | [docs/development/TARGETED_REPAIR_PROTOCOL_RU.md](TARGETED_REPAIR_PROTOCOL_RU.md) | перенесён |
| `docs/TECHNICAL_LOWERING_POLICY_RU.md` | [docs/development/TECHNICAL_LOWERING_POLICY_RU.md](TECHNICAL_LOWERING_POLICY_RU.md) | маршрут сохранён |
| `docs/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md` | [docs/reference/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md](../reference/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md) | маршрут сохранён |
| `docs/TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md` | [docs/reference/TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md](../reference/TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md) | перенесён |
| `docs/TEST_CONTRACT_OWNERS_RU.md` | [docs/development/TESTING_RU.md](TESTING_RU.md) | маршрут сохранён |
| `docs/THREE_STAGE_LLM_PIPELINE_RU.md` | [docs/development/THREE_STAGE_LLM_PIPELINE_RU.md](THREE_STAGE_LLM_PIPELINE_RU.md) | маршрут сохранён |
| `docs/TYPED_AUTHOR_PARAMETER_PROJECTIONS_RU.md` | [docs/reference/TYPED_AUTHOR_PARAMETER_PROJECTIONS_RU.md](../reference/TYPED_AUTHOR_PARAMETER_PROJECTIONS_RU.md) | перенесён |
| `docs/VFX_MATERIAL_ELEMENTS_RU.md` | [docs/reference/VFX_MATERIAL_ELEMENTS_RU.md](../reference/VFX_MATERIAL_ELEMENTS_RU.md) | маршрут сохранён |
| `docs/VFX_SOUND_PALETTE_RU.md` | [docs/reference/VFX_SOUND_PALETTE_RU.md](../reference/VFX_SOUND_PALETTE_RU.md) | маршрут сохранён |
| `docs/VISUAL_AUDIT_HISTORY_RU.md` | [docs/archive/VISUAL_AUDIT_HISTORY_RU.md](../archive/VISUAL_AUDIT_HISTORY_RU.md) | перенесён |
| `docs/VISUAL_PRESENTATION_METADATA.md` | [docs/reference/VISUAL_PRESENTATION_METADATA.md](../reference/VISUAL_PRESENTATION_METADATA.md) | перенесён |
| `docs/WEAPON_AMMO_CONSUMPTION_RU.md` | [docs/reference/WEAPON_AMMO_CONSUMPTION_RU.md](../reference/WEAPON_AMMO_CONSUMPTION_RU.md) | перенесён |

`LocalGenerator/README_RU.md`, `PROJECT_*.md`, `QUICK_START_RU.md` остаются локальными routing guides к этим owners. `docs/README_RU.md` — центральный индекс. Healthy локальные `FOLDER_DOCS_RU.md` и тестовый portfolio остаются у своих каталогов.

## Проверка изменений

Проверяй local Markdown paths/anchors и rendered table widths, не только regex ссылок. Команды сверяй с launcher/producer/runner; live/game/paid команды не выполняются автоматически ради документации. [Freshness](../reference/GENERATED_RU.md), [offline gates](README_RU.md#быстрый-offline-проход).

После параллельного переноса исходников пересчитай source paths в `CODE_MAP` и тематических docs; не возвращай старые shims ради green ссылок. Исторические source paths/commit anchors сохраняются как provenance. Финальный integrated gate принадлежит завершённому дереву, не промежуточной writer-фазе.
