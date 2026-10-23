# Техническая справка

Здесь ищут точные правила реализации после знакомства с [архитектурой](../development/architecture/ARCHITECTURE_RU.md). Для установки генератора используй [пользовательское руководство](../user/START_RU.md).

Файлы разложены по тем же темам, что и главы ниже: **`authoring/`**, **`items/`**, **`projectiles/`**, **`presentation/`**, **`terraria/`**. В **`generated/`** — воспроизводимые каталоги, а не ручные инструкции. В корне остаются только этот вход и [порядок обновления каталогов](GENERATED_RU.md).

## Формат ответа модели

- [Авторство механики и построение предмета](authoring/LOW_LEVEL_RUNTIME_AUTHORING_RU.md).
- [Формы предмета и их точная проекция](authoring/AUTHOR_ITEM_ALIASES_RU.md), [типизированные параметры](authoring/TYPED_AUTHOR_PARAMETER_PROJECTIONS_RU.md).
- [Единицы измерения](authoring/MODEL_FACING_UNITS_RU.md), [нейтральные пропуски](authoring/DECLARED_NEUTRAL_OMISSIONS_RU.md), [ссылки между сущностями](authoring/REFERENCED_ENTITY_REQUIREMENTS_RU.md).
- [Контекст исходных предметов и качество описания](authoring/ITEM_QUALITY_CONTEXT_RU.md), [числовые ориентиры баланса](terraria/BALANCE_REFERENCE_VANILLA_PROGRESS_LIMITS_RU.md).

## Использование предмета и экипировка

- [Основное, альтернативное и удерживаемое действие](items/NAMED_ITEM_EFFECT_GROUPS_RU.md).
- [Эффекты экипировки](items/NATIVE_EQUIPMENT_UTILITIES_RU.md).
- [Рыбалка, сбор, зрение, инструменты и восстановление](terraria/EXPLORATION_EQUIPMENT_RU.md).
- [Вероятность расхода собственного стека](items/OWN_STACK_CHANCE_RU.md) и [расход боеприпасов](items/WEAPON_AMMO_CONSUMPTION_RU.md).
- [Готовность сохранённых рецептов и health](items/RECIPE_HEALTH_AND_CONTRACTS_RU.md).

## Снаряды, события и цели

- [Формат снаряда: позиция, иммунитет и условия](projectiles/PROJECTILE_AUTHOR_API_RU.md), [события и область урона](authoring/AUTHOR_EVENT_DOMAINS_RU.md).
- [Начальная скорость и распределение дочерних снарядов](projectiles/SPAWN_DISTRIBUTIONS_AND_TARGET_GEOMETRY_RU.md).
- [Наследование боевых характеристик](projectiles/CHILD_COMBAT_INHERITANCE_RU.md), [исключение исходной цели](projectiles/INITIAL_NPC_EXCLUSION_RUNTIME_RU.md), [последовательность целей](projectiles/PROJECTILE_TARGET_EMISSION_RU.md).
- [Вертикальное ускорение](projectiles/SIGNED_VERTICAL_ACCELERATION_RU.md), [модификаторы и фазы](projectiles/PROJECTILE_PHASE_MODIFIERS_RU.md), [рост области столкновения](projectiles/PROJECTILE_HITBOX_CURVE_RU.md).
- [Удерживаемый луч: рост и геометрия](projectiles/CHANNEL_BEAM_SUSTAIN_GEOMETRY_RU.md).
- [Заряд, орбита и отскок](projectiles/PROJECTILE_CHARGE_ORBIT_BOUNCE_RU.md).
- [Турель: залп и выбор цели](projectiles/SENTRY_TARGETING_VOLLEY_RU.md), [время жизни и бюджет потомков](projectiles/SENTRY_LIFECYCLE_BUDGET_RU.md).

## Изображение, размещение и эффекты

- [Панель эффектов, таймеры и возвратное оружие](presentation/GENERATED_STATUS_HUD_RU.md).

- [Описание внешности Visual Director](presentation/VISUAL_PRESENTATION_METADATA.md), [согласованность отображения](presentation/PRESENTATION_CONSISTENCY_RU.md).
- [Отрисовка экипировки поверх персонажа](presentation/EQUIPMENT_OVERLAY_RENDERING.md).
- [Размещённый предмет из его PNG](presentation/PRESENT_PLACED_ITEM_SPRITE_RU.md).
- [Материалы визуальных эффектов](presentation/VFX_MATERIAL_ELEMENTS_RU.md), [звуки и параметры воспроизведения](presentation/VFX_SOUND_PALETTE_RU.md).

## Соответствие Terraria и полные каталоги

- [Границы использования Terraria/tModLoader API](terraria/TERRARIA_TMODLOADER_STANDARDIZATION_RU.md).
- [Внешние примеры реализации](terraria/LOW_LEVEL_RUNTIME_EXTERNAL_REFERENCES_RU.md), [справочник оружия и прогрессии Terraria](terraria/TERRARIA_WEAPONS_AND_PROGRESSION_FULL_GUIDE_RU.md).
- [Автоматически собранные каталоги и их обновление](GENERATED_RU.md): полный набор возможностей, точные параметры, преобразования и сравнение с C#.

Смысловые решения принадлежат модели, технические правила — исходному коду. Эти главы объясняют существующий контракт; новый пункт документации сам по себе не добавляет игровую возможность. Прежние замеры и проверки читаются с указанными в них ограничениями.

- [Книга открытий, условия ЛКМ/ПКМ и реакции экипировки](items/RECIPE_JOURNAL_AND_EQUIPMENT_REACTIONS_RU.md).
