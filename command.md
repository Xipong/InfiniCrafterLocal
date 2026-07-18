# Команды InfiniCrafterLocal в Terraria

Все команды ниже вводятся в игровой чат Terraria/tModLoader.

## Быстрый список

```text
/infinicore
/infinidummy [count]
/getinfini
/infiniitem [trace [held|<1-58>]]
/infinicache [stats|warm|clear|resetbad] [held|inventory|registry] [limit]
/infinidump
/infinidumppicture [all|latest|id-or-name-filter]
/infinidumppicture source [held|active|baseline|item <id/name>|projectile <id/name>]
```

## Что делает каждая команда и куда попадает результат

Команды не складывают файлы в Steam-папку игры. Файловые результаты идут в пользовательский `Main.SavePath` tModLoader.

На текущей установке:

```text
Main.SavePath = C:\Users\Cosmi\OneDrive\Документы\My Games\Terraria\tModLoader
```

| Команда | Что делает | Куда попадает результат |
|---|---|---|
| `/infinicore` | Выдаёт один InfiniCore | В inventory игрока через Terraria quick-spawn; отдельных файлов нет |
| `/infinidummy [count]` | Выдаёт 1–99 Target Dummy | В inventory игрока через Terraria quick-spawn; отдельных файлов нет |
| `/getinfini` | Повторно запрашивает generated registry и недостающие assets | Definitions: `<Main.SavePath>\InfiniCrafterLocal\generated_items\<id>.json`; PNG/JSON assets: `<Main.SavePath>\InfiniCrafterLocal\asset_cache\`; retry state хранится в памяти |
| `/infiniitem ...` | Показывает authored/applied значения выбранного generated-предмета | Только сообщения в игровом чате; ничего не записывает |
| `/infinicache stats` | Показывает состояние sprite/asset cache | Только сообщение в игровом чате |
| `/infinicache clear` | Удаляет resident runtime textures и bad records | Только RAM/GPU cache; файлы в `asset_cache` остаются |
| `/infinicache resetbad` | Сбрасывает missing/bad backoff и asset retry state | Только память; файлов не создаёт и не удаляет |
| `/infinicache warm ...` | Загружает выбранные sprites и при необходимости запрашивает assets | PNG/JSON скачиваются в `asset_cache`; готовые textures держатся в RAM/GPU cache |
| `/infinidump` | Снимает числовые snapshots всех загруженных items/projectiles | `<Main.SavePath>\InfiniCrafterLocal\items_runtime_dump.jsonl` и `projectiles_runtime_dump.jsonl`; старые файлы перезаписываются |
| `/infinidumppicture ...` | Собирает generated sprites, JSON и HTML gallery | `<Main.SavePath>\InfiniCrafterLocal\picture_dumps\YYYYMMDD_HHMMSS\` |
| `/infinidumppicture source ...` | Экспортирует реально загруженные Terraria/mod item/projectile textures | `<Main.SavePath>\InfiniCrafterLocal\picture_dumps\source_YYYYMMDD_HHMMSS\` |

---

## `/infinicore`

```text
/infinicore
```

Выдаёт один `InfiniCore`. После этого открой инвентарь, чтобы использовать панель InfiniCraft station.

## `/infinidummy`

```text
/infinidummy [count]
```

Выдаёт vanilla Target Dummy для тестирования generated-оружия.

- без аргумента: 1;
- допустимый диапазон: 1–99;
- слишком маленькое или большое число зажимается;
- нечисловой аргумент даёт 1.

Примеры:

```text
/infinidummy
/infinidummy 10
/infinidummy 99
```

## `/getinfini`

```text
/getinfini
```

Повторно запрашивает generated-item registry и assets.

Использовать, если generated-предмет уже существует, но definition или sprite не загрузились.

Команда:

- сбрасывает asset retry state;
- повторяет загрузку отсутствующих PNG/JSON;
- в multiplayer запрашивает полный registry у сервера;
- не создаёт новый рецепт;
- не вызывает LLM повторно;
- не выдаёт предметы.

## `/infiniitem`

Source usage:

```text
/infiniitem [trace [held|<1-58>]]
```

Формы:

```text
/infiniitem
/infiniitem help
/infiniitem trace
/infiniitem trace held
/infiniitem trace <slot 1-58>
```

Показывает authored и фактически applied C# значения generated-предмета.

- без аргументов или с `help` показывает помощь;
- `trace` проверяет предмет в руке;
- `trace held` проверяет предмет в руке;
- `trace 1` ... `trace 58` проверяет inventory slot;
- неправильный slot возвращает выбор к предмету в руке;
- обычный предмет выводится как `not generated`;
- предмет не изменяется.

## `/infinicache`

Source usage:

```text
/infinicache [stats|warm|clear|resetbad] [held|inventory|registry] [limit]
```

### Статистика

```text
/infinicache
/infinicache stats
/infinicache status
```

Показывает:

- количество runtime textures;
- cache hits/misses/loads/evictions;
- missing/bad sprite records;
- примерный объём texture memory;
- generated registry count;
- asset files, активные downloads и missing assets.

### Очистка runtime cache

```text
/infinicache clear
```

Очищает resident runtime textures и missing/bad records из памяти.

PNG, JSON, recipes и picture dumps с диска не удаляются.

### Сброс ошибок и retry state

```text
/infinicache resetbad
/infinicache reset
```

Очищает missing/bad sprite backoff и сбрасывает asset retry state.

### Прогрев sprites

```text
/infinicache warm [held|inventory|registry|all] [limit]
/infinicache prefetch [held|inventory|registry|all] [limit]
```

Scopes:

- `held` — generated-предмет в руке;
- `inventory` — inventory, armor и misc equips; используется по умолчанию;
- `registry` или `all` — generated registry.

`limit` по умолчанию равен 64 и зажимается в диапазон 1–512.

Примеры:

```text
/infinicache warm held
/infinicache warm inventory 64
/infinicache warm registry 256
```

## `/infinidump`

```text
/infinidump
```

Создаёт числовые runtime dumps всех загруженных items и projectiles.

Файлы:

```text
<Main.SavePath>\InfiniCrafterLocal\items_runtime_dump.jsonl
<Main.SavePath>\InfiniCrafterLocal\projectiles_runtime_dump.jsonl
```

Каждый запуск перезаписывает оба JSONL.

Item dump содержит stats, use timing, damage class, rarity, tool/armor/accessory/ammo fields, `item.shoot`, projectile snapshot и texture metrics.

Projectile dump содержит hitbox, AI style, penetration, lifetime, collision, immunity, minion/sentry flags, frames, selected `ProjectileID.Sets` и texture metrics.

## `/infinidumppicture`: generated sprites

Source usage:

```text
/infinidumppicture [all|latest|id-or-name-filter] | /infinidumppicture source [held|active|baseline|item <id/name>|projectile <id/name>]
```

Формы:

```text
/infinidumppicture
/infinidumppicture latest
/infinidumppicture all
/infinidumppicture <id-or-name-filter>
```

- без аргумента используется `latest`;
- `latest` — до 12 последних generated items;
- `all` — весь текущий generated registry;
- filter ищется в id, name, parentA, parentB и recipeKey.

Выходная папка:

```text
<Main.SavePath>\InfiniCrafterLocal\picture_dumps\YYYYMMDD_HHMMSS\
```

Внутри создаются:

- копии item/projectile/impact/child/field sprites;
- full и network JSON;
- `picture_dump_manifest.json`;
- `index.html`;
- `README.txt`.

## `/infinidumppicture source`: Terraria/mod textures

Основная форма:

```text
/infinidumppicture source [held|active|baseline|item <id/name>|projectile <id/name>]
```

Aliases слова `source`:

```text
src
ref
reference
original
vanilla
mod
modded
```

### Предмет в руке

```text
/infinidumppicture source
/infinidumppicture source held
/infinidumppicture source current
/infinidumppicture source selected
```

Экспортирует texture предмета в руке. Если у предмета есть `item.shoot`, связанный projectile экспортируется в ту же папку.

### Активные projectiles

```text
/infinidumppicture source active
/infinidumppicture source nearby
/infinidumppicture source projectiles
```

Экспортирует уникальные активные projectile textures и предмет в руке.

### Starter baseline

```text
/infinidumppicture source baseline
/infinidumppicture source vanilla-baseline
/infinidumppicture source starter
```

Экспортирует встроенный набор starter vanilla weapons.

### Предмет по названию — иметь его в инвентаре не нужно

Самая простая форма:

```text
/infinidumppicture source <название предмета>
```

Например, при русской локализации:

```text
/infinidumppicture source Гарпун
```

Равнозначная явная форма:

```text
/infinidumppicture source item Гарпун
```

Команда ищет точное отображаемое название среди всех загруженных vanilla и modded item definitions. Предмет не обязан лежать в inventory, быть изучен, скрафчен или находиться рядом.

Для vanilla-предмета вводи название на текущем языке Terraria. Для modded-предмета также можно использовать его точное internal/full name:

```text
/infinidumppicture source item Copper Shortsword
/infinidumppicture source item SomeMod/InternalItemName
```

Numeric item id тоже поддерживается как запасной технический вариант, но для обычного использования знать его не требуется.

Если предмет уже находится в руке, название вообще не нужно:

```text
/infinidumppicture source held
```

В обоих вариантах команда:

1. экспортирует оригинальный `TextureAssets.Item` выбранного предмета;
2. читает его `item.shoot`;
3. если projectile есть, автоматически экспортирует связанный `TextureAssets.Projectile`;
4. создаёт HTML gallery и metadata.

После выполнения полный путь выводится в игровой чат. Bundle выбранного предмета выглядит так:

```text
source_YYYYMMDD_HHMMSS\
├─ index.html
├─ source_texture_manifest.json
├─ README.txt
└─ assets\
   └─ item_<type>_<отображаемое_название>\
      ├─ item.png
      ├─ projectile_shoot.png
      └─ bundle_meta.json
```

- `item.png` — оригинальный item/inventory texture;
- `projectile_shoot.png` — оригинальный texture связанного projectile, если у предмета есть `item.shoot`;
- `bundle_meta.json` — размеры, item/projectile types, use timing, `shoot`, `shootSpeed` и texture metrics;
- `index.html` — просмотр экспортированных textures на разных фонах.

Для Image Gen обычно используются два раздельных reference: `item.png` для предмета и `projectile_shoot.png` для тела projectile.

Ограничение: source dump экспортирует static `TextureAssets`, а не screenshot готового игрового кадра. Rotation, lighting, трос/цепь, dust, trail и другие runtime draw-эффекты в эти PNG не запекаются.

### Конкретный projectile

```text
/infinidumppicture source projectile <id-or-exact-name>
/infinidumppicture source proj <id-or-exact-name>
/infinidumppicture source p <id-or-exact-name>
```

Принимает numeric projectile id либо точное display/internal/full name.

Выходная папка source dump:

```text
<Main.SavePath>\InfiniCrafterLocal\picture_dumps\source_YYYYMMDD_HHMMSS\
```

Внутри создаются PNG, `bundle_meta.json`, `source_texture_manifest.json`, `index.html` и `README.txt`.

На dedicated server picture dump недоступен, потому что сервер не имеет локальных GPU textures для экспорта.
