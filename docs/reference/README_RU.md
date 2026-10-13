# Техническая справка

Здесь ищут точные правила реализации после знакомства с [архитектурой](../development/ARCHITECTURE_RU.md). Для установки генератора используй [пользовательское руководство](../user/START_RU.md).

## Формат ответа модели

- [Авторство механики и построение предмета](LOW_LEVEL_RUNTIME_AUTHORING_RU.md).
- [Формы предмета и их точная проекция](AUTHOR_ITEM_ALIASES_RU.md), [типизированные параметры](TYPED_AUTHOR_PARAMETER_PROJECTIONS_RU.md).
- [Единицы измерения](MODEL_FACING_UNITS_RU.md), [нейтральные пропуски](DECLARED_NEUTRAL_OMISSIONS_RU.md), [ссылки между сущностями](REFERENCED_ENTITY_REQUIREMENTS_RU.md).
- [Контекст исходных предметов и качество описания](ITEM_QUALITY_CONTEXT_RU.md), [числовые ориентиры баланса](BALANCE_REFERENCE_VANILLA_PROGRESS_LIMITS_RU.md).

## Использование предмета и экипировка

- [Основное, альтернативное и удерживаемое действие](NAMED_ITEM_EFFECT_GROUPS_RU.md).
- [Эффекты экипировки](NATIVE_EQUIPMENT_UTILITIES_RU.md).
- [Вероятность расхода собственного стека](OWN_STACK_CHANCE_RU.md) и [расход боеприпасов](WEAPON_AMMO_CONSUMPTION_RU.md).
- [Готовность сохранённых рецептов и health](RECIPE_HEALTH_AND_CONTRACTS_RU.md).

## Снаряды, события и цели

- [Формат снаряда: позиция, иммунитет и условия](PROJECTILE_AUTHOR_API_RU.md), [события и область урона](AUTHOR_EVENT_DOMAINS_RU.md).
- [Начальная скорость и распределение дочерних снарядов](SPAWN_DISTRIBUTIONS_AND_TARGET_GEOMETRY_RU.md).
- [Наследование боевых характеристик](CHILD_COMBAT_INHERITANCE_RU.md), [исключение исходной цели](INITIAL_NPC_EXCLUSION_RUNTIME_RU.md), [последовательность целей](PROJECTILE_TARGET_EMISSION_RU.md).
- [Вертикальное ускорение](SIGNED_VERTICAL_ACCELERATION_RU.md), [модификаторы и фазы](PROJECTILE_PHASE_MODIFIERS_RU.md), [рост области столкновения](PROJECTILE_HITBOX_CURVE_RU.md).
- [Удерживаемый луч: рост и геометрия](CHANNEL_BEAM_SUSTAIN_GEOMETRY_RU.md).
- [Турель: залп и выбор цели](SENTRY_TARGETING_VOLLEY_RU.md), [время жизни и бюджет потомков](SENTRY_LIFECYCLE_BUDGET_RU.md).

## Изображение, размещение и эффекты

- [Описание внешности Visual Director](VISUAL_PRESENTATION_METADATA.md), [согласованность отображения](PRESENTATION_CONSISTENCY_RU.md).
- [Размещённый предмет из его PNG](PRESENT_PLACED_ITEM_SPRITE_RU.md).
- [Материалы визуальных эффектов](VFX_MATERIAL_ELEMENTS_RU.md), [звуки и параметры воспроизведения](VFX_SOUND_PALETTE_RU.md).

## Соответствие Terraria и полные каталоги

- [Границы использования Terraria/tModLoader API](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md).
- [Внешние примеры реализации](LOW_LEVEL_RUNTIME_EXTERNAL_REFERENCES_RU.md), [справочник оружия и прогрессии Terraria](TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md).
- [Автоматически собранные каталоги и их обновление](GENERATED_RU.md): полный набор возможностей, точные параметры, преобразования и сравнение с C#.

Смысловые решения принадлежат модели, технические правила — исходному коду. Эти главы объясняют существующий контракт; новый пункт документации сам по себе не добавляет игровую возможность. Прежние замеры и проверки читаются с указанными в них ограничениями.
