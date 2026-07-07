# Terraria 1.4.5+: полный гайд в одном документе

> **Формат:** вики-простыня / единый справочник для прохождения, моддинга, генерации прогрессии и LLM-пайплайна.  
> **База:** Desktop / Console / Mobile 1.4.5.x, Bigger and Boulder и новее.  
> **Дата ревизии:** 2026-07-05.  
> **Основные источники для сверки:** Official Terraria Wiki на wiki.gg: `Weapons`, `Guide:Class setups`, `Guide:Game progression`, `Guide:Walkthrough`, `Bosses`, `Armor`, `Accessories`, `Potions`, `Shimmer`, `Pylons`, `NPC Happiness`, `Zenith`, страницы отдельных предметов/боссов.  
> **Важно:** этот документ не пытается заменить сортируемые таблицы Wiki по всем 6000+ предметам. Он собирает прохождение, ключевые предметы, классы, боссов, биомы, события, крафты и правила прогрессии в один файл. Для точного урона каждого редкого предмета всегда можно сверить конкретную страницу предмета.

---

## 0. Что изменено относительно исходного документа

Документ оставлен в стиле большого справочника, но расширен из “оружие + прогрессия” в **единый фулл-гайд**.

### 0.1. Исправлены критичные ошибки фактов

| Было / риск | Исправлено |
|---|---|
| Лунные оружия Solar / Vortex / Nebula / Stardust могли выглядеть как дропы Moon Lord | Они **крафтятся из Lunar Fragments** после столпов. Moon Lord дропает Luminite и собственный пул оружия/предметов. |
| Lunatic Cultist указан как этап “после Plantera” | Реальный обычный порядок: **Plantera → Golem → Lunatic Cultist → Celestial Pillars → Moon Lord**. |
| Spider Staff попал в Pre-Hardmode | Spider Staff — **early Hardmode summon**, делается из Spider Fangs. |
| Vampire Knives указаны как Crimson Mimic | Vampire Knives — **Crimson Chest в Dungeon post-Plantera**, нужен Crimson Key. Crimson Mimic даёт другой пул. |
| Ice Rod в Pre-Hardmode | Ice Rod — **Hardmode**, продаётся Wizard. |
| Flower of Fire как дроп Lava Slimes | Flower of Fire — Shadow Chest / Obsidian Lock Box в Underworld. |
| Phaseblade через Crystal Shards | Phaseblade = Meteorite Bars + gems. Crystal Shards нужны для Phasesaber. |
| Flamarang через Molten Fury | Flamarang = Enchanted Boomerang + Hellstone Bars. |
| Ball O' Hurt как Hellstone | Ball O' Hurt — Shadow Orb / Corrupt crates. |
| Uzi / Chain Gun от Arms Dealer | Uzi — Angry Trapper; Chain Gun — Santa-NK1 в Frost Moon. |
| “Storm Staff” в summoner HM | В ваниле ключевой предмет — **Tempest Staff** от Duke Fishron. |
| Meteor armor как ranged-прогрессия | Meteor armor — в первую очередь magic/Space Gun сетап, не ranged-сет. |

### 0.2. Добавлено

- Полная дорожная карта прохождения от спавна до Moon Lord / Zenith.
- Разделы по миру, сложности, биомам, NPC, pylons, happiness, housing.
- Разделы по баффам, аренам, алхимии, еде, фласкам, станциям.
- Оружие не просто списком, а по **стадиям доступности**.
- Сводки по классам: Melee / Ranged / Magic / Summoner.
- Чеклисты перед каждым major gate: Skeletron, Wall of Flesh, Mechs, Plantera, Golem, Cultist, Moon Lord.
- Раздел “LLM-safe rules”: что нельзя придумывать при генерации предметов/прогрессии.
- ToDo-лист для будущего расширения документа, если нужен прям реально “Wiki mirror”.

---

## 1. Базовая модель Terraria

Terraria — это не линейная RPG, а progression sandbox. У игры есть мягкая свобода маршрута, но есть жёсткие ворота:

```text
Старт мира
  ↓
Pre-Hardmode exploration
  ↓
Evil boss / Queen Bee / Skeletron
  ↓
Wall of Flesh
  ↓
Hardmode
  ↓
Hardmode ores + mechanical bosses
  ↓
Plantera
  ↓
Golem
  ↓
Lunatic Cultist
  ↓
Celestial Pillars
  ↓
Moon Lord
  ↓
Endgame farming / Zenith / completion
```

### 1.1. Формальных классов нет

В Terraria нет выбора класса на старте. “Класс” — это сборка вокруг типа урона:

| Класс | Тип урона | Главная логика | Слабое место |
|---|---:|---|---|
| Melee | melee | высокая защита, ближний бой, мечи/йо-йо/копья/флэйлы/псевдо-дальние мечи | на ранних этапах приходится подходить близко |
| Ranged | ranged | луки, пушки, ammo, стабильный урон на дистанции | зависимость от патронов/стрел и ammo-management |
| Magic | magic | высокий burst/utility, книги/жезлы/пушки маны | зависимость от маны и potion sickness по mana potion |
| Summoner | summon | миньоны + whips, активное позиционирование | мало защиты, слабый старт без нужных дропов |
| Hybrid | смешанный | берёт лучшее из нескольких классов | хуже скейлится от class-specific брони |

### 1.2. Сложности

| Сложность | Что меняет | Практический смысл |
|---|---|---|
| Classic | базовая сложность мира | нормальный режим для прохождения и тестов |
| Expert | сильнее враги/боссы, expert loot | другой баланс, важнее арены и баффы |
| Master | ещё выше урон/HP, больше vanity/mount/pet-наград | челлендж, не лучший baseline для баланса модов |
| Journey | настройки мира, duplication/research | sandbox/тесты/строительство |

### 1.3. Персонаж и мир

Персонаж и мир существуют отдельно. Один персонаж может ходить по разным мирам и переносить вещи. Поэтому “честная прогрессия” — это не только наличие предмета, но и вопрос: **мог ли игрок легально получить его в этом мире на этой стадии?**

Для LLM/мода это критично:

- не выдавать post-Plantera предмет как pre-Hardmode;
- не путать evil-locked предметы Crimson/Corruption;
- учитывать, что некоторые вещи можно получить рыбалкой/ящиками раньше прямого крафта;
- учитывать, что игрок может принести предмет из другого мира, но это уже не vanilla progression baseline.

---

## 2. Создание мира и ранние решения

### 2.1. Размер мира

| Размер | Плюсы | Минусы | Кому подходит |
|---|---|---|---|
| Small | быстро бегать, быстро найти биомы | меньше ресурсов, теснее биомы | быстрые прохождения, тесты |
| Medium | лучший баланс | иногда долго искать редкости | стандартный выбор |
| Large | много ресурсов и мест | длинные перемещения до pylons/boots | кооп, строительство, долгий мир |

### 2.2. Evil biome: Corruption vs Crimson

| Мир | Босс | Ключевые предметы | Стиль |
|---|---|---|---|
| Corruption | Eater of Worlds | Shadow armor, Musket, Vilethorn, Ball O' Hurt, Cursed Flames, Scourge of the Corruptor | сегментный босс, проще фармить Demonite/Scales |
| Crimson | Brain of Cthulhu | Crimson armor, The Undertaker, Crimson Rod, The Rotted Fork, Ichor, Vampire Knives | burst-опасность, Ichor сильнейший debuff |

**Важно:** Ichor из Crimson обычно сильнее для урона, Cursed Flames даёт DoT и отдельные крафты. Для моддинга не стоит считать Corruption и Crimson полными синонимами.

### 2.3. Seed и special seeds

Terraria поддерживает secret/special seeds. Они меняют мир, прогрессию и иногда боссов. Для обычного гайда baseline — **обычный seed**.

| Seed category | Что делает | Для баланса |
|---|---|---|
| Drunk world | смешивает evil, меняет генерацию | нельзя считать стандартом |
| For the worthy | сильно усложняет мир | отдельная балансировка |
| Get fixed boi / Zenith seed | комбинирует много special rules | не baseline вообще |
| Skyblock 1.4.5 | особый limited-resource сценарий | отдельная экономика прогрессии |

---

## 3. Главная дорожная карта прохождения

### 3.1. Макро-этапы

| Этап | Ворота | Главная цель | Типичный результат |
|---|---|---|---|
| Spawn / Day 1 | нет | дом, верстак, факелы, базовая шахта | выживание ночью |
| Early Pre-HM | металл, сундуки | life crystals, movement, первые аксессуары | 200+ HP, boots/hook по возможности |
| Evil / Jungle / Desert | доступ к биомам | первые сильные оружия | подготовка к боссам |
| Dungeon gate | Skeletron | открыть Dungeon | Muramasa, Handgun, Cobalt Shield, books |
| Underworld gate | Hellstone + Wall of Flesh | Molten gear, hellbridge | Hardmode |
| Early HM | алтари/ящики/ores | Cobalt/Palladium → Mythril/Orichalcum → Adamantite/Titanium | HM броня/оружие |
| Mech gate | 3 mechanical bosses | Hallowed Bars + Souls | Pickaxe Axe/Drax, Hallowed gear |
| Jungle gate | Plantera | Temple Key, post-Plantera Dungeon | Chlorophyte, Spectre, Turtle, Terra Blade path |
| Temple gate | Golem | открыть cultist progression | Beetle, event farming |
| Lunar gate | Lunatic Cultist + Pillars | fragments | pillar weapons/armor |
| Endgame | Moon Lord | Luminite + ML drops | endgame sets, Zenith |

### 3.2. Мини-чеклист ранней игры

- Сделать Work Bench, Furnace, Anvil.
- Накопать ore-tier до хотя бы Silver/Tungsten/Gold/Platinum, если не повезло с loot.
- Найти Life Crystals: цель 200 HP перед Eye of Cthulhu, 400 HP перед Wall of Flesh.
- Найти Hermes/Flurry/Sailfish/Dunerider Boots или их апгрейд.
- Найти Cloud in a Bottle / Sandstorm / Blizzard / Fart / Tsunami in a Bottle.
- Сделать Grappling Hook.
- Построить арену: platforms, campfire, heart lantern later, sunflowers.
- Получить первые utility potions: Ironskin, Regeneration, Swiftness, Hunter/Spelunker.

---

## 4. Workstations, руды, инструменты

### 4.1. Базовые станции

| Станция | Когда | Зачем |
|---|---|---|
| Work Bench | день 1 | базовый крафт, мебель |
| Furnace | early | слитки из руды |
| Iron/Lead Anvil | early | оружие, инструменты, armor |
| Sawmill | early | мебель, loom |
| Loom | early | silk, beds, robes |
| Cooking Pot / Cauldron | early | еда |
| Placed Bottle / Alchemy Table | early / Dungeon | potions |
| Tinkerer's Workshop | после Goblin Army | аксессуарные крафты |
| Hellforge | Underworld | Hellstone Bars |
| Mythril/Orichalcum Anvil | Hardmode tier 2 ore | advanced HM craft |
| Adamantite/Titanium Forge | Hardmode tier 3 ore | tier 3 bars, Chlorophyte later |
| Ancient Manipulator | после Lunatic Cultist | Lunar Fragment craft |

### 4.2. Рудная прогрессия

| Этап | Руда / материал | Альтернатива | Требование | Что открывает |
|---|---|---|---|---|
| Early | Copper | Tin | старт | базовые tools/weapons |
| Early | Iron | Lead | старт | Anvil, chains, buckets |
| Early | Silver | Tungsten | старт | нормальный pre-boss металл |
| Early | Gold | Platinum | старт | сильные pre-boss tools/armor |
| Evil | Demonite | Crimtane | evil boss / spheres/hearts | evil weapons, pickaxe path |
| Underworld | Hellstone | — | Obsidian + Hellforge | Molten armor/tools/weapons |
| HM 1 | Cobalt | Palladium | Molten Pickaxe / Reaver Shark context | первая HM руда |
| HM 2 | Mythril | Orichalcum | Cobalt/Palladium pick | HM anvil |
| HM 3 | Adamantite | Titanium | Mythril/Orichalcum pick | HM forge, strong armor |
| Post-mechs | Hallowed Bars | — | mechanical bosses | Hallowed gear, Excalibur, Drax/Pickaxe Axe |
| Post-mechs | Chlorophyte | — | Drax/Pickaxe Axe | Chlorophyte/Turtle/Spectre/Shroomite path |
| Lunar | Fragments | Solar/Vortex/Nebula/Stardust | Celestial Pillars | pillar weapons/armor |
| Endgame | Luminite | — | Moon Lord | final armor/tools |

### 4.3. Алтари в Hardmode

После Wall of Flesh падает Pwnhammer. Им можно разбивать Demon/Crimson Altars, чтобы мир получил Hardmode ore tiers.

Обычная последовательность:

```text
1-й тип алтаря → Cobalt / Palladium
2-й тип алтаря → Mythril / Orichalcum
3-й тип алтаря → Adamantite / Titanium
```

**Практика:** не обязательно ломать все алтари. Достаточно 6–12, чтобы не превращать мир в хаос. Альтернатива — fishing crates, если хочется меньше трогать world evil spread.

---

## 5. Боссы: порядок, ворота, награды

### 5.1. Pre-Hardmode bosses

| Босс | Когда обычно | Summon / trigger | Что проверяет | Главные награды |
|---|---|---|---|---|
| King Slime | optional early | Slime Rain / Slime Crown | мобильность, базовый урон | Slimy Saddle, Ninja pieces, Hook |
| Eye of Cthulhu | 200+ HP / ночь | Suspicious Looking Eye / auto-spawn | арена, mobility | Demonite/Crimtane, Shield of Cthulhu в Expert |
| Eater of Worlds | Corruption | Worm Food / 3 Shadow Orbs | piercing/AoE | Demonite, Shadow Scales |
| Brain of Cthulhu | Crimson | Bloody Spine / 3 Crimson Hearts | burst, target switching | Crimtane, Tissue Samples |
| Queen Bee | Jungle | Larva / Abeemination | dodge, poison, adds | Beenades, Bee Keeper, Bee's Knees, Bee Wax |
| Skeletron | Dungeon gate | Old Man ночью | арена, endurance | Dungeon access |
| Deerclops | optional crossover | Snow biome summon | area control | Don't Starve-themed loot |
| Wall of Flesh | final Pre-HM gate | Guide Voodoo Doll в лаву | длинная арена, DPS check | Hardmode, Pwnhammer, emblems |

### 5.2. Hardmode bosses

| Босс | Когда обычно | Summon / trigger | Что открывает |
|---|---|---|---|
| Queen Slime | early HM optional | Gelatin Crystal в Hallow | early HM mobility/summon gear |
| The Destroyer | mech | Mechanical Worm | Soul of Might, Hallowed Bars |
| The Twins | mech | Mechanical Eye | Soul of Sight, Hallowed Bars |
| Skeletron Prime | mech | Mechanical Skull | Soul of Fright, Hallowed Bars |
| Plantera | после всех 3 mechs | Plantera's Bulb | Temple Key, post-Plantera Dungeon, biome chests |
| Golem | после Plantera | Lihzahrd Power Cell | cultists unlock, Beetle path |
| Duke Fishron | optional HM | Truffle Worm в Ocean | топовое pre/post-Golem оружие |
| Empress of Light | после Plantera | Prismatic Lacewing ночью/днём | сильные wings, Kaleidoscope, Terraprisma |
| Lunatic Cultist | после Golem | cultists у Dungeon | Lunar Events |
| Moon Lord | после Pillars / Celestial Sigil | automatic / summon | Luminite, final drops |

### 5.3. Событийные боссы

| Событие | Боссы/мини-боссы | Стадия | Важные дропы |
|---|---|---|---|
| Goblin Army | Goblin Summoner в HM | early / HM | Goblin Tinkerer unlock |
| Pirate Invasion | Flying Dutchman | HM | Coin Gun, Discount Card, Pirate Staff |
| Solar Eclipse | Mothron, etc. | после mech/Plantera для части дропов | Broken Hero Sword, Death Sickle, Deadly Sphere Staff |
| Pumpkin Moon | Mourning Wood, Pumpking | post-Plantera | Horseman's Blade, Raven Staff, Dark Harvest |
| Frost Moon | Everscream, Santa-NK1, Ice Queen | post-Plantera | Chain Gun, Blizzard Staff, Razorpine |
| Martian Madness | Martian Saucer | post-Golem | Influx Waver, Xenopopper, Xeno Staff, Laser Machinegun |
| Old One's Army | Dark Mage, Ogre, Betsy | stage-based | sentries, Defender Medal gear, Betsy's Wrath/Wings |

---

## 6. Арены и подготовка к боссам

### 6.1. Базовая арена

Минимум:

- 2–4 ряда platforms.
- Campfire.
- Heart Lantern.
- Sunflowers на поверхности.
- Bast Statue, если есть.
- Honey pool для некоторых боёв.
- Star in a Bottle для mage.
- Ammo Box для ranged.
- Bewitching Table для summoner.
- Sharpening Station для melee/whips.
- Slice of Cake, если доступен.

### 6.2. Универсальные баффы

| Бафф | Эффект | Когда важен |
|---|---|---|
| Ironskin | +defense | почти всегда |
| Regeneration | regen | почти всегда |
| Swiftness | speed | до wings особенно |
| Endurance | damage reduction | Expert/Master и поздние боссы |
| Lifeforce | +max life % | hard fights |
| Wrath | +damage | Corruption world / fishing |
| Rage | +crit | Crimson world / fishing |
| Heartreach | сбор hearts | арены с adds |
| Inferno | AoE вокруг игрока | events/add-heavy fights |
| Summoning | +1 minion | summoner/hybrid |
| Magic Power | magic damage | mage |
| Mana Regeneration | mana regen | mage |
| Archery | arrow speed/damage | bows |
| Ammo Reservation | шанс не тратить ammo | guns/bows |
| Flask of Ichor / Cursed Flames | debuff на melee/whips | melee/summoner |

### 6.3. Еда

Любой food buff лучше, чем никакой. Для прохождения достаточно держать стабильный `Well Fed / Plenty Satisfied / Exquisitely Stuffed`.

---

## 7. Классовая прогрессия: быстрые сетапы

### 7.1. Melee progression snapshot

| Стадия | Оружие | Броня | Аксессуары |
|---|---|---|---|
| Early Pre-HM | Cactus Sword, Enchanted Sword, Starfury, Amazon, Ice Blade | Gold/Platinum, Cactus situational | boots, cloud bottle, hook |
| Evil/Jungle | Blade of Grass, Bee Keeper, Volcano, Night's Edge path | Shadow/Crimson/Molten | Feral Claws, Shield, mobility |
| Pre-WoF | Night's Edge, Cascade, Sunfury, Flamarang | Molten | Obsidian Shield, Terraspark path |
| Early HM | Amarok, Shadowflame Knife, Dao of Pow, Fetid Baghnakhs, Drippler Crippler | Adamantite/Titanium/Frost | Warrior Emblem, wings |
| Mechs | Excalibur, Light Disc, Bananarang, Ice Sickle | Hallowed | Mechanical Glove path |
| Post-Plantera | Terra Blade path, Death Sickle, Vampire Knives, Seedler | Turtle/Chlorophyte | Fire Gauntlet, Ankh Shield |
| Post-Golem | Possessed Hatchet, Flairon, Influx Waver, Horseman's Blade | Beetle | Celestial Shell, Master Ninja Gear |
| Lunar | Solar Eruption, Daybreak | Solar Flare | endgame accessories |
| Post-ML | Meowmere, Star Wrath, Zenith | Solar Flare | final reforges |

### 7.2. Ranged progression snapshot

| Стадия | Оружие | Броня | Ammo |
|---|---|---|---|
| Early Pre-HM | Gold/Platinum Bow, Boomstick, Minishark | Fossil / metal | Frostburn/Jester arrows, basic bullets |
| Evil/Jungle | Demon/Tendon Bow, Bee's Knees, Musket/Undertaker | Fossil / Necro later | Jester, Hellfire, Meteor Shot |
| Pre-WoF | Phoenix Blaster, Hellwing Bow, Star Cannon | Necro | Hellfire/Jester, Meteor Shot, Stars |
| Early HM | Daedalus Stormbow, Onyx Blaster, Clockwork Assault Rifle, Dart Rifle/Pistol | Adamantite/Titanium/Frost | Holy Arrows, Crystal/Ichor/Cursed bullets/darts |
| Mechs | Megashark, Hallowed Repeater | Hallowed | Crystal/Ichor/Chlorophyte later |
| Post-Plantera | Chlorophyte Shotbow, Tactical Shotgun, Rocket Launcher, Sniper Rifle | Shroomite | Chlorophyte bullets, Ichor bullets |
| Post-Golem | Tsunami, Xenopopper, Electrosphere Launcher, Chain Gun | Shroomite | Chlorophyte/Luminite later |
| Lunar | Phantasm, Vortex Beater | Vortex | endgame ammo |
| Post-ML | S.D.M.G., Celebration Mk2 | Vortex | Luminite bullets/arrows/rockets |

### 7.3. Magic progression snapshot

| Стадия | Оружие | Броня | Особенности |
|---|---|---|---|
| Early Pre-HM | Wand of Sparking, gem staves, Vilethorn/Crimson Rod | Jungle / gem robes | mana stars important |
| Dungeon/Underworld | Water Bolt, Demon Scythe, Flower of Fire, Space Gun | Meteor / Jungle | Space Gun + Meteor = no mana cost |
| Early HM | Crystal Serpent, Sky Fracture, Meteor Staff, Cursed Flames/Golden Shower | Adamantite/Titanium/Forbidden | Golden Shower/Ichor очень силён |
| Mechs | Rainbow Rod, Magical Harp, Crystal Storm | Hallowed | mana sustain |
| Post-Plantera | Spectre Staff, Shadowbeam Staff, Inferno Fork, Rainbow Gun, Magnet Sphere | Spectre | Hood = sustain, Mask = damage |
| Post-Golem | Razorpine, Blizzard Staff, Laser Machinegun, Razorblade Typhoon | Spectre | Fishron/Moon events |
| Lunar | Nebula Blaze, Nebula Arcanum | Nebula | топовый damage/support |
| Post-ML | Last Prism, Lunar Flare | Nebula | mana management |

### 7.4. Summoner progression snapshot

| Стадия | Minions | Whips | Броня |
|---|---|---|---|
| Early Pre-HM | Finch Staff, Flinx Staff, Abigail's Flower, Slime Staff | Leather Whip | Flinx Fur Coat + mixed |
| Jungle/Dungeon | Hornet Staff, Imp Staff, Vampire Frog Staff | Snapthorn, Spinal Tap | Bee armor / Obsidian armor |
| Early HM | Spider Staff, Blade Staff, Sanguine Staff, Queen Spider Staff | Firecracker, Cool Whip | Spider armor |
| Mechs | Optic Staff, Pirate Staff situational | Durendal | Hallowed / Forbidden |
| Post-Plantera | Deadly Sphere Staff, Desert Tiger Staff, Pygmy Staff | Dark Harvest, Morning Star | Tiki / Spooky |
| Post-Golem | Xeno Staff, Tempest Staff | Kaleidoscope | Spooky/Tiki |
| Lunar | Stardust Dragon Staff, Stardust Cell Staff | Kaleidoscope | Stardust |
| Post-ML | Terraprisma still top-tier, Stardust Dragon/Cell | Kaleidoscope | Stardust |

---

## 8. Pre-Hardmode weapon encyclopedia

Раздел не дублирует вообще все декоративные/слабые варианты, но закрывает основную progression-матрицу и важные исключения.

### 8.1. Pre-HM Melee: swords / yoyos / spears / boomerangs / flails

| Оружие | Стадия | Источник | Почему важно |
|---|---|---|---|
| Cactus Sword | day 1 desert | Cactus craft | дешёвый early sword |
| Enchanted Sword | early/mid | shrine / crates | projectile sword, Zenith component |
| Starfury | sky islands | Skyware Chest / crates | falling star projectile, Zenith component |
| Ice Blade | snow | Frozen Chest/crates | projectile + light |
| Blade of Grass | jungle | Jungle materials | Night's Edge component |
| Light's Bane | Corruption | Demonite Bars | Night's Edge component |
| Blood Butcherer | Crimson | Crimtane Bars | Night's Edge component |
| Muramasa | Dungeon | Locked Gold Chest / Lock Box | Night's Edge component |
| Volcano | Underworld | Hellstone Bars | Night's Edge component |
| Night's Edge | pre-WoF | 4 sword components | лучший классический pre-HM sword path |
| Bee Keeper | Queen Bee | boss drop | bees + Zenith component |
| Purple Clubberfish | Corruption fishing | fishing | высокий base damage для early/mid |
| Wooden Yoyo | early | craft | старт йо-йо |
| Amazon | jungle | craft | хороший pre-boss yoyo |
| Code 1 | merchant | Traveling Merchant | быстрый yoyo option |
| Valor | Dungeon | chest | strong pre-HM yoyo |
| Cascade | Underworld | enemy drop | сильный pre-WoF yoyo |
| Spear | early | chests | безопасная дистанция |
| Trident | ocean | Water Chest/Ocean crates | early spear |
| The Rotted Fork | Crimson | Crimson Heart/crates | сильный Crimson spear |
| Dark Lance | Underworld | Shadow Chest | strong spear, pre-WoF |
| Enchanted Boomerang | early | chest / upgrade | ranged melee utility |
| Flamarang | Underworld | Enchanted Boomerang + Hellstone | сильный boomerang |
| Ball O' Hurt | Corruption | Shadow Orb/crates | early flail |
| Blue Moon | Dungeon | Dungeon chest | strong flail |
| Sunfury | Underworld | Shadow Chest | strong pre-WoF flail |

### 8.2. Pre-HM Ranged

| Оружие | Стадия | Источник | Ammo / notes |
|---|---|---|---|
| Wooden/metal bows | early | craft | Frostburn/Jester arrows решают |
| Gold/Platinum Bow | pre-boss | craft | нормальный baseline |
| Demon Bow | Corruption | Demonite Bars | strong pre-HM bow |
| Tendon Bow | Crimson | Crimtane Bars | strong pre-HM bow |
| Blood Rain Bow | Blood Moon fishing | Wandering Eye Fish / Zombie Merman | вертикальный дождь стрел |
| The Bee's Knees | Queen Bee | boss drop | стрелы превращаются в пчёл |
| Hellwing Bow | Underworld | Shadow Chest | летучие projectiles |
| Molten Fury | Underworld | Hellstone Bars | огненный bow |
| Flintlock Pistol | early | Arms Dealer | старт gun route |
| Musket | Corruption | Shadow Orb/crates | открывает Arms Dealer |
| The Undertaker | Crimson | Crimson Heart/crates | Crimson gun route |
| Minishark | early | Arms Dealer | скорость, Star Cannon/Megashark path |
| Boomstick | Jungle | Ivy Chest/Jungle crates | сильный shotgun early |
| Handgun | Dungeon | Locked Gold Chest | Phoenix Blaster component |
| Phoenix Blaster | Underworld/Dungeon | Handgun + Hellstone Bars | топ pre-WoF gun |
| Star Cannon | mid/pre-WoF | Minishark + Fallen Stars + Lens | высокий DPS, дорогие звёзды |
| Sandgun | Desert | craft | situational, ammo = sand |
| Beenade | Queen Bee | boss/craft | один из самых сильных WoF tools |

### 8.3. Pre-HM Magic

| Оружие | Стадия | Источник | Notes |
|---|---|---|---|
| Wand of Sparking | very early | surface chests | starter magic |
| Gem staves | early | gems + bars | стабильный early mage |
| Vilethorn | Corruption | Shadow Orb/crates | pierce through blocks |
| Crimson Rod | Crimson | Crimson Heart/crates | cloud damage zone |
| Space Gun | Meteor | Meteorite Bars | с Meteor armor не тратит mana |
| Water Bolt | Dungeon | bookshelves | сильные отскоки, обычно после Skeletron |
| Demon Scythe | Underworld | Demons | slow high damage projectile |
| Flower of Fire | Underworld | Shadow Chest/Obsidian Lock Box | bouncing fireball |
| Flamelash | Underworld | Shadow Chest/Obsidian Lock Box | управляемый projectile |
| Weather Pain | Deerclops | boss drop | storm cloud projectile |
| Magic Missile | Dungeon | Locked Gold Chest | controllable projectile |
| Aqua Scepter | Dungeon | Dungeon chest | continuous stream |

### 8.4. Pre-HM Summoner + Whips

| Предмет | Стадия | Источник | Notes |
|---|---|---|---|
| Finch Staff | early | Living Wood Chest | starter minion |
| Slime Staff | rare | slimes | крайне редкий |
| Flinx Staff | snow | Flinx Fur craft | хороший гарантированный summon старт |
| Abigail's Flower | graveyard | grows near tombstones | scaling minion, удобный старт |
| Vampire Frog Staff | Blood Moon fishing | Zombie Merman / Wandering Eye Fish | сильный pre-HM summon |
| Hornet Staff | Jungle/Queen Bee path | Bee Wax | стабильный minion |
| Imp Staff | Underworld | Hellstone Bars | сильный pre-WoF minion |
| Leather Whip | Zoologist | purchase | starter whip |
| Snapthorn | Jungle | craft | poison + speed buff |
| Spinal Tap | Dungeon | bones + cobweb | strong pre-WoF whip |
| Bee Armor | Queen Bee | Bee Wax | pre-HM summoner armor |
| Obsidian Armor | Underworld materials | craft | whip-focused pre-HM set |

---

## 9. Hardmode weapon encyclopedia

### 9.1. Early Hardmode weapons

| Класс | Оружие | Источник | Почему важно |
|---|---|---|---|
| Melee | Amarok | Snow enemies | yoyo, easy farm |
| Melee | Shadowflame Knife | Goblin Summoner | safe ranged melee |
| Melee | Dao of Pow | Souls + shards | flail |
| Melee | Fetid Baghnakhs | Crimson Mimic | огромный close-range DPS |
| Melee | Drippler Crippler | Blood Moon fishing HM | flail/blood projectile |
| Ranged | Daedalus Stormbow | Hallowed Mimic | mech killer with arrows |
| Ranged | Dart Rifle / Dart Pistol | Corrupt/Crimson Mimic | strong with cursed/ichor darts |
| Ranged | Onyx Blaster | Shotgun upgrade | мощный early HM gun |
| Ranged | Clockwork Assault Rifle | Wall of Flesh | early HM gun |
| Magic | Crystal Serpent | Hallow fishing | strong magic projectile |
| Magic | Sky Fracture | Magic Missile path | accurate burst |
| Magic | Meteor Staff | Meteorite + Souls | falling meteors |
| Magic | Golden Shower | Crimson craft | Ichor debuff, support/damage |
| Magic | Cursed Flames | Corruption craft | DoT magic |
| Summon | Spider Staff | Spider Fangs | first HM summon baseline |
| Summon | Queen Spider Staff | Spider Fangs | sentry |
| Summon | Blade Staff | Queen Slime / enchanted sword enemies context | fast low damage minions, scales with tag damage |
| Summon | Sanguine Staff | Dreadnautilus | excellent tracking |
| Whip | Firecracker | Wall of Flesh | explosion synergy |
| Whip | Cool Whip | Frost Core craft | snowflake minion |

### 9.2. Mechanical boss tier

| Класс | Оружие | Источник | Notes |
|---|---|---|---|
| Melee | Excalibur | Hallowed Bars | Terra Blade path |
| Melee | Light Disc | Hallowed Bars + Souls | stackable projectile melee |
| Melee | Bananarang | Clowns | strong boomerang |
| Melee | Ice Sickle | ice enemies | safe projectile melee |
| Ranged | Megashark | Minishark + Illegal Gun Parts + Souls + Shark Fin | iconic gun |
| Ranged | Hallowed Repeater | Hallowed Bars | bow route |
| Ranged | Flamethrower | Souls + Illegal Gun Parts | crowd control |
| Magic | Magical Harp | Hallowed Bars + Souls + Crystal Shards | wide control |
| Magic | Rainbow Rod | Hallowed + souls + crystals | controlled projectile |
| Summon | Optic Staff | Souls from Twins | twin minions |
| Whip | Durendal | Hallowed Bars | summon tag + speed |

### 9.3. Post-Plantera / Dungeon tier

| Класс | Оружие | Источник | Notes |
|---|---|---|---|
| Melee | Terra Blade | True swords + Broken Hero Sword | core melee milestone |
| Melee | Death Sickle | Reapers, Solar Eclipse | projectile through walls |
| Melee | Vampire Knives | Crimson Chest, Dungeon | sustain, Crimson world/key |
| Melee | Scourge of the Corruptor | Corruption Chest, Dungeon | homing split projectiles |
| Melee | Seedler | Plantera | Zenith component |
| Ranged | Chlorophyte Shotbow | Chlorophyte Bars | multiple arrows |
| Ranged | Tactical Shotgun | Tactical Skeleton | shotgun route |
| Ranged | Sniper Rifle | Skeleton Sniper | high damage slow gun |
| Ranged | Rocket Launcher | Skeleton Commando | rocket route |
| Magic | Spectre Staff | Ragged Caster | homing |
| Magic | Shadowbeam Staff | Necromancer | beam bounces |
| Magic | Inferno Fork | Diabolist | AoE explosion |
| Magic | Magnet Sphere | Dungeon casters | autonomous damage |
| Magic | Rainbow Gun | Hallowed Chest | persistent rainbow |
| Summon | Pygmy Staff | Plantera | unlocks Witch Doctor summoner gear |
| Summon | Deadly Sphere Staff | Deadly Sphere, Solar Eclipse | strong summon |
| Summon | Desert Tiger Staff | Desert Chest, Dungeon | scaling single tiger |
| Whip | Dark Harvest | Pumpkin Moon | tag + dark energy |
| Whip | Morning Star | post-Plantera Dungeon | high tag damage |

### 9.4. Post-Golem / events / Fishron

| Класс | Оружие | Источник | Notes |
|---|---|---|---|
| Melee | Possessed Hatchet | Golem | homing hatchet |
| Melee | Flairon | Duke Fishron | bubbles, very strong |
| Melee | Influx Waver | Martian Saucer | Zenith component |
| Melee | The Horseman's Blade | Pumpking | Zenith component, pumpkins |
| Ranged | Tsunami | Duke Fishron | 5 arrows per shot |
| Ranged | Xenopopper | Martian Saucer | bubble bullets |
| Ranged | Electrosphere Launcher | Martian Saucer | electric spheres |
| Ranged | Chain Gun | Santa-NK1, Frost Moon | extreme fire rate |
| Magic | Razorblade Typhoon | Duke Fishron | homing bouncing projectiles |
| Magic | Laser Machinegun | Martian Saucer | ramping laser |
| Magic | Blizzard Staff | Ice Queen | falling icicles |
| Magic | Razorpine | Everscream | rapid pine needles |
| Summon | Xeno Staff | Martian Saucer | reliable UFOs |
| Summon | Tempest Staff | Duke Fishron | sharknado minion |
| Whip | Kaleidoscope | Empress of Light | top whip |
| Summon | Terraprisma | daytime Empress of Light | top-tier summon challenge reward |

### 9.5. Lunar / post-Moon Lord

| Класс | Weapon | Источник | Notes |
|---|---|---|---|
| Melee | Solar Eruption | Solar Fragments | whipsword through blocks |
| Melee | Daybreak | Solar Fragments | spear projectiles + DoT |
| Ranged | Phantasm | Vortex Fragments | bow, ramping arrows |
| Ranged | Vortex Beater | Vortex Fragments | gun + rockets |
| Magic | Nebula Blaze | Nebula Fragments | high damage projectile |
| Magic | Nebula Arcanum | Nebula Fragments | slow homing AoE |
| Summon | Stardust Dragon Staff | Stardust Fragments | long dragon minion |
| Summon | Stardust Cell Staff | Stardust Fragments | cell minions |
| Melee | Meowmere | Moon Lord | bouncing cat projectile |
| Melee | Star Wrath | Moon Lord | falling stars |
| Ranged | S.D.M.G. | Moon Lord | final gun |
| Ranged | Celebration Mk2 | Moon Lord | final launcher |
| Magic | Last Prism | Moon Lord | channel beam, huge mana cost |
| Magic | Lunar Flare | Moon Lord | strikes from sky |
| Summon/Sentry | Lunar Portal Staff | Moon Lord | sentry |
| Summon/Sentry | Rainbow Crystal Staff | Moon Lord | sentry |
| Melee | Zenith | craft | final sword |

---

## 10. Armor progression

### 10.1. Universal / early armor

| Armor | Stage | Notes |
|---|---|---|
| Wood / Cactus | day 1 | лучше, чем голым |
| Mining set | rare | utility, not combat |
| Copper/Tin/Iron/Lead | early | если не повезло с сундуками |
| Silver/Tungsten | early | нормальная pre-boss защита |
| Gold/Platinum | pre-boss | сильный generic pre-boss сет |
| Fossil | Desert | ranged bonuses |
| Jungle | Jungle | magic bonuses |
| Meteor | Meteor | Space Gun synergy |
| Shadow | Corruption | melee speed / movement style |
| Crimson | Crimson | regen + balanced stats |
| Bee | Queen Bee | summoner pre-HM |
| Obsidian | Underworld materials | whip-focused summoner |
| Molten | Underworld | highest classic pre-HM defense, melee |
| Necro | Dungeon | ranged pre-HM |

### 10.2. Early Hardmode armor

| Armor | Class / role | Notes |
|---|---|---|
| Cobalt / Palladium | generic/class helmets | first HM tier |
| Mythril / Orichalcum | generic/class helmets | second HM tier |
| Adamantite / Titanium | class helmets | strong pre-mech |
| Frost | melee/ranged hybrid | Frost Core from Ice Golem |
| Forbidden | magic/summon hybrid | Forbidden Fragment from Sand Elemental |
| Spider | summoner | Spider Fangs, early HM summon |
| Crystal Assassin | hybrid mobility | Queen Slime |

### 10.3. Mid/Late Hardmode armor

| Armor | Stage | Class |
|---|---|---|
| Hallowed | post-mech | all classes via helmets |
| Chlorophyte | post-mech jungle | all classes via helmets |
| Turtle | post-mech | melee tank, Beetle path |
| Spectre | post-Plantera | magic: Hood sustain / Mask damage |
| Shroomite | post-Plantera | ranged helmets by ammo style |
| Tiki | post-Plantera | summoner, bought after Pygmy Staff |
| Spooky | Pumpkin Moon | summoner damage |
| Beetle | post-Golem | melee shell/scalemail variants |

### 10.4. Endgame armor

| Armor | Class | Материалы |
|---|---|---|
| Solar Flare | melee | Solar Fragments + Luminite |
| Vortex | ranged | Vortex Fragments + Luminite |
| Nebula | magic | Nebula Fragments + Luminite |
| Stardust | summoner | Stardust Fragments + Luminite |

---

## 11. Accessories progression

### 11.1. Movement

| Аксессуар | Stage | Effect / value |
|---|---|---|
| Hermes/Flurry/Sailfish/Dunerider Boots | early | horizontal speed |
| Rocket Boots | Goblin Tinkerer | flight boost |
| Spectre/Lightning/Frostspark Boots | pre-HM/HM | boots upgrade chain |
| Terraspark Boots | long craft | lava/water/ice mobility package |
| Cloud/Blizzard/Sandstorm/Tsunami in a Bottle | early | double jump variants |
| Bundle of Balloons | pre-HM | multiple jumps |
| Lucky Horseshoe | sky | fall damage immunity |
| Fledgling Wings | sky/Journey variants | early wings-like mobility |
| Wings | HM | flight; tier depends on source |
| Master Ninja Gear | post-Plantera Dungeon | dash + dodge + climb |
| Shield of Cthulhu | Expert Eye | dash, very strong early |

### 11.2. Defense / survival

| Аксессуар | Stage | Notes |
|---|---|---|
| Band of Regeneration | early | regen |
| Cobalt Shield | Dungeon | knockback immunity path |
| Obsidian Shield | pre-HM | knockback + fire block immunity |
| Ankh Shield | HM/post-Plantera realistic | many debuff immunities |
| Worm Scarf | Expert Corruption | damage reduction |
| Brain of Confusion | Expert Crimson | dodge/confusion/crit synergy |
| Charm of Myths | HM | regen + potion cooldown reduction |
| Star Veil | HM | more invincibility frames + stars |
| Frozen Shield | HM | tank accessory |
| Hero Shield | HM | aggro/tank |

### 11.3. Damage accessories by class

| Класс | Аксессуары |
|---|---|
| Melee | Feral Claws → Power Glove → Mechanical Glove → Fire Gauntlet; Warrior Emblem; Berserker's Glove; Yoyo Bag |
| Ranged | Ranger Emblem; Magic Quiver chain; Sniper Scope; Recon Scope; Molten/ Stalker's Quiver |
| Magic | Sorcerer Emblem; Mana Flower; Celestial Cuffs; Celestial Emblem; Magnet Flower; Arcane Flower |
| Summoner | Summoner Emblem; Pygmy Necklace; Papyrus Scarab; Necromantic Scroll; Hercules Beetle; Feral Claws line for whips |
| Universal | Avenger Emblem, Destroyer Emblem, Celestial Shell, Celestial Stone |

### 11.4. Informational accessories

Информационные аксессуары полезны не как combat stats, а как качество игры и крафт PDA/Cell Phone/Shellphone:

- Compass.
- Depth Meter.
- DPS Meter.
- Stopwatch.
- Lifeform Analyzer.
- Metal Detector.
- Radar.
- Tally Counter.
- Fisherman's Pocket Guide.
- Weather Radio.
- Sextant.
- Goblin Tech.
- R.E.K. 3000.
- PDA.
- Cell Phone / Shellphone.

---

## 12. Ammo, arrows, bullets, rockets, darts

### 12.1. Arrows

| Ammo | Stage | Effect |
|---|---|---|
| Wooden Arrow | start | baseline |
| Flaming Arrow | early | fire |
| Frostburn Arrow | early snow | better DoT |
| Jester's Arrow | early stars | pierce, great early |
| Hellfire Arrow | Underworld | explosion |
| Unholy Arrow | Corruption | pierce |
| Holy Arrow | HM | falling stars, Daedalus synergy |
| Ichor Arrow | HM Crimson | defense debuff |
| Cursed Arrow | HM Corruption | cursed flames |
| Chlorophyte Arrow | post-mechs | ricochet/homing style depending behavior |
| Venom Arrow | post-Plantera | venom debuff |
| Luminite Arrow | post-ML | endgame pierce |

### 12.2. Bullets

| Ammo | Stage | Effect |
|---|---|---|
| Musket Ball | basic | baseline |
| Silver/Tungsten Bullet | early | higher damage |
| Meteor Shot | meteor | bounce + pierce |
| Crystal Bullet | HM | shards, strong DPS |
| Ichor Bullet | HM Crimson | defense debuff |
| Cursed Bullet | HM Corruption | cursed flames |
| Chlorophyte Bullet | post-mechs | homing, very easy aim |
| Venom Bullet | post-Plantera | venom |
| Nano Bullet | post-Plantera | confuse |
| High Velocity Bullet | HM | speed/pierce style |
| Luminite Bullet | post-ML | endgame |

### 12.3. Darts / rockets / special ammo

| Ammo | Weapon family | Notes |
|---|---|---|
| Poison Dart | Dart Rifle/Pistol | baseline dart |
| Cursed Dart | Dart Rifle/Pistol | Corruption, flame rain |
| Ichor Dart | Dart Rifle/Pistol | Crimson, debuff |
| Crystal Dart | Dart Rifle/Pistol | bouncing projectile |
| Rockets I-IV | launchers | explosion/tile damage variants |
| Stakes | Stake Launcher | Pumpkin Moon route |
| Gel | Flamethrower/Elf Melter | fuel |
| Fallen Stars | Star Cannon/Super Star Shooter | high cost high damage |
| Sand | Sandgun | consumes sand variants |

---

## 13. Potions, flasks, food, stations

### 13.1. Combat potion pack by class

| Класс | Must-have | Optional |
|---|---|---|
| All | Ironskin, Regeneration, Swiftness, Endurance, Lifeforce, food | Heartreach, Inferno, Wrath/Rage |
| Melee | Flask, Sharpening Station | Titan, Thorns |
| Ranged | Archery if bow, Ammo Reservation, Ammo Box | Hunter |
| Magic | Magic Power, Mana Regeneration, Crystal Ball | Mana Regen furniture, Star in a Bottle |
| Summoner | Summoning Potion, Bewitching Table, Flask for whip | War Table for sentries |
| Fishing | Fishing, Sonar, Crate | Chum Bucket, Angler gear |
| Mining | Spelunker, Mining, Shine, Night Owl, Obsidian Skin | Dangersense |

### 13.2. Flask logic

Flasks apply to melee attacks and whips. For summoner this matters because whips are summon damage but can apply flask debuffs.

| Flask | World | Use |
|---|---|---|
| Flask of Ichor | Crimson | defense reduction, usually best damage support |
| Flask of Cursed Flames | Corruption | DoT |
| Flask of Fire | generic | early DoT |
| Flask of Venom | post-Plantera | stronger DoT |

### 13.3. Potion crafting infrastructure

- Herb farm: Daybloom, Blinkroot, Moonglow, Deathweed, Waterleaf, Fireblossom, Shiverthorn.
- Clay Pots / Planter Boxes.
- Bottled Water stock.
- Fishing biome pools for fish ingredients.
- Alchemy Table from Dungeon экономит ингредиенты по сравнению с обычной placed bottle станцией.

---

## 14. NPCs, housing, pylons

### 14.1. Housing минимум

Комната считается жильём, если в ней есть:

- достаточно закрытого пространства;
- player-placed background walls;
- light source;
- flat surface item;
- comfort item;
- entrance/door/platform access;
- нет corruption/crimson/hallow-overload рядом, который ломает валидность.

### 14.2. Ранние NPC unlocks

| NPC | Условие | Почему важен |
|---|---|---|
| Guide | старт | crafting hints, Wall of Flesh trigger |
| Merchant | достаточно денег | basic supplies, piggy bank |
| Nurse | повысить max HP | лечение |
| Demolitionist | explosive в инвентаре | bombs/dynamite |
| Dye Trader | dye item | dyes |
| Angler | Ocean | quests, fishing rewards |
| Dryad | победить boss | seeds, evil/hallow status |
| Arms Dealer | gun/bullet | guns/ammo |
| Goblin Tinkerer | после Goblin Army, found underground | reforging, Tinkerer's Workshop |
| Mechanic | Dungeon | wires/mechanisms |
| Wizard | Hardmode cavern | magic items |
| Steampunker | mechanical boss | Clentaminator, solutions |
| Truffle | surface Glowing Mushroom HM | Autohammer, Shroomite |
| Witch Doctor | Queen Bee | summoner items, imbuing station |
| Cyborg | Plantera | rockets, proximity mine launcher |
| Princess | почти все town NPC | vanity/social |

### 14.3. Pylon network

Pylons — телепорт-сеть между биомами. Удобная базовая сеть:

| Pylon | Биом | Кого селить примерно |
|---|---|---|
| Forest | Forest | Merchant + Guide/Zoologist/Golfer |
| Desert | Desert | Dye Trader + Arms Dealer/Steampunker |
| Jungle | Jungle | Dryad + Witch Doctor/Painter |
| Snow | Snow | Mechanic + Goblin Tinkerer |
| Ocean | Ocean | Angler + Pirate/Stylist |
| Cavern | Cavern | Demolitionist + Tavernkeep/Clothier |
| Hallow | Hallow | Wizard + Party Girl/Nurse |
| Mushroom | Mushroom | Truffle + chosen neighbor |
| Universal | any | rare/universal pylon, late utility |

**Важно для 1.4.5.x:** условия продажи/работы pylons и happiness нужно сверять по актуальной Wiki, потому что эти правила менялись патчами. Для практического гайда достаточно помнить: pylon требует правильный биом и живых NPC рядом, а happiness влияет на цены/доступность и часть наград.

---

## 15. Biomes: что где искать

### 15.1. Surface / Forest

- Wood, mushrooms, basic chests.
- Fallen Stars ночью.
- NPC housing hub.
- Early arena.

### 15.2. Underground / Cavern

- Life Crystals.
- Gems.
- Skeletons, Crawdads, Salamanders, Tim.
- Gold/Platinum chests.
- Extractinator, Hermes Boots variants, Cloud in a Bottle variants.

### 15.3. Desert

- Cactus gear early.
- Underground Desert: fossils, sturdy fossils, Bast Statue, desert loot.
- Antlion materials.
- Sandstorm in a Bottle / Magic Conch / shell items via chests/crates depending loot.

### 15.4. Snow

- Ice chests.
- Ice Blade, Ice Skates, Blizzard in a Bottle, Flurry Boots.
- Flinx Fur for summoner.
- Hardmode Ice Golem: Frost Core.

### 15.5. Jungle

- Jungle Spores, Stingers, Vines.
- Boomstick, Feral Claws, Staff of Regrowth, Anklet of the Wind.
- Queen Bee arena.
- Plantera bulbs later.
- Chlorophyte after mechanical bosses.

### 15.6. Ocean

- Angler.
- Water Chests.
- Fishing.
- Duke Fishron summon with Truffle Worm in Hardmode.

### 15.7. Dungeon

До Skeletron вход глубоко опасен из-за Dungeon Guardian. После Skeletron:

- Golden Keys.
- Muramasa.
- Cobalt Shield.
- Handgun.
- Magic Missile.
- Aqua Scepter.
- Water Bolt.
- Mechanic NPC.

Post-Plantera Dungeon меняет enemy pool и даёт:

- Ectoplasm.
- Spectre gear path.
- Tactical Shotgun, Sniper Rifle, Rocket Launcher.
- Biome Chests.
- Paladin items.
- Strong magic staves.

### 15.8. Underworld

- Hellstone.
- Hellforge.
- Shadow Chests.
- Obsidian Lock Boxes via crates.
- Guide Voodoo Demon.
- Wall of Flesh arena.

### 15.9. Hallow

Hardmode biome:

- Crystal Shards.
- Pixie Dust, Unicorn Horns.
- Souls of Light underground.
- Hallowed Mimics.
- Queen Slime summon via Gelatin Crystal.

### 15.10. Evil spread

Corruption/Crimson/Hallow spread ускоряется в Hardmode. Практические решения:

- Не паниковать в первые минуты HM.
- Защитить NPC базы тоннелями/Clentaminator позже.
- Steampunker после mech boss продаёт Clentaminator.
- До Hardmode можно подготовить hellevators вокруг базы/джунглей, если хочется clean world.

---

## 16. Fishing, crates, Angler

Fishing — альтернативная прогрессия, особенно если не хочется ломать много алтарей.

### 16.1. Зачем рыбачить

| Причина | Что даёт |
|---|---|
| Crates | ore/bars/accessories/biome loot |
| Potion fish | ингредиенты сильных зелий |
| Quest fish | Angler rewards |
| Biome loot | unique items через crates/fishing enemies |
| Hardmode ores | через crates после HM |

### 16.2. Fishing power

Влияют:

- fishing rod power;
- bait power;
- размер водоёма;
- weather/time/moon;
- fishing potion;
- chum buckets;
- Angler gear/accessories;
- luck.

### 16.3. Crate правило

Pre-HM crates, открытые в Hardmode, historically were abused for HM ores; текущие правила нужно сверять под версию, но общий safe-rule для гайда:

- хочешь pre-HM loot — рыбачь и открывай pre-HM;
- хочешь HM ресурсы — рыбачь уже в Hardmode;
- biome crates полезны для альтернативного получения части biome chest loot.

---

## 17. Shimmer / Aether

Shimmer — особая жидкость из mini-biome Aether, генерируется один раз на мир.

### 17.1. Что делает Shimmer

- Transmutation предметов.
- Decrafting некоторых crafted items.
- Превращение critters/enemies/NPC sprites.
- Получение permanent upgrades из некоторых предметов.
- Обратные evil-пары/альтернативы для части предметов после 1.4.5.x expanded transmutations.

### 17.2. Практические применения

| Use-case | Пример |
|---|---|
| Альтернативные evil items | часть Corruption/Crimson counterparts через transmutation |
| Decraft | возврат компонентов у ряда вещей |
| Permanent upgrades | специальные consumables |
| Cosmetic/utility | NPC shimmer variants, critter transforms |
| Zenith joke/transform | некоторые endgame transforms существуют как easter egg/utility |

**LLM-safe правило:** не придумывать Shimmer-рецепты. Если конкретная transmutation не подтверждена Wiki или кодом — считать неизвестной.

---

## 18. Events: подробная карта

### 18.1. Blood Moon

| Stage | Что важно |
|---|---|
| Pre-HM | Blood Rain Bow, Vampire Frog Staff через fishing enemies |
| HM | Dreadnautilus → Sanguine Staff, Blood Eel/Hemogoblin Shark |
| General | повышенный spawn, NPC danger, fishing enemies |

### 18.2. Goblin Army

- Открывает Goblin Tinkerer после события.
- Goblin Tinkerer = reforging + Tinkerer's Workshop.
- В Hardmode появляется Goblin Summoner, даёт Shadowflame weapons.

### 18.3. Pirate Invasion

- HM event.
- Pirate NPC после победы.
- Coin Gun / Discount Card / Lucky Coin / Pirate Staff.
- Flying Dutchman как мини-босс.

### 18.4. Solar Eclipse

- Hardmode daytime event.
- После progression gates открываются новые враги/дропы.
- Mothron даёт Broken Hero Sword для Terra Blade path.
- Deadly Sphere даёт Deadly Sphere Staff.
- Death Sickle от Reapers.

### 18.5. Pumpkin Moon

- Post-Plantera event.
- Wave-based.
- Pumpking: Horseman's Blade, Raven Staff, Dark Harvest, trophies.
- Mourning Wood: spooky wood, stake launcher route.

### 18.6. Frost Moon

- Post-Plantera event.
- Santa-NK1 → Chain Gun.
- Everscream → Razorpine.
- Ice Queen → Blizzard Staff, Snowman Cannon, North Pole.

### 18.7. Martian Madness

- Post-Golem event.
- Trigger: Martian Probe notices player and escapes.
- Martian Saucer: Influx Waver, Xeno Staff, Xenopopper, Laser Machinegun, Cosmic Car Key.

### 18.8. Old One's Army

- Tavernkeep event.
- Sentries + Defender Medals.
- Multiple tiers tied to progression.
- Betsy late-tier drops: Betsy's Wrath, Aerial Bane, Flying Dragon, Betsy Wings.

---

## 19. Crafting trees

### 19.1. Night's Edge

```text
Night's Edge
├── Light's Bane OR Blood Butcherer
├── Muramasa
├── Blade of Grass
└── Volcano
```

Где брать:

| Component | Source |
|---|---|
| Light's Bane | Demonite Bars, Corruption |
| Blood Butcherer | Crimtane Bars, Crimson |
| Muramasa | Dungeon Locked Gold Chest / Golden Lock Box |
| Blade of Grass | Jungle materials |
| Volcano | Hellstone Bars |

### 19.2. Terra Blade

```text
Terra Blade
├── True Night's Edge
│   └── Night's Edge + Hardmode materials
├── True Excalibur
│   └── Excalibur + Hardmode materials
└── Broken Hero Sword
    └── Mothron, Solar Eclipse
```

**Note:** рецепты менялись в 1.4.x. Если нужен 100% точный material count для мод-кода — сверить по wiki/item recipe или через tModLoader data.

### 19.3. Megashark

```text
Megashark
├── Minishark
├── Illegal Gun Parts
├── Shark Fin
└── Souls of Might
```

### 19.4. Ankh Shield

```text
Ankh Shield
├── Obsidian Shield
│   ├── Cobalt Shield
│   └── Obsidian Skull
└── Ankh Charm
    ├── Armor Bracing
    ├── Medicated Bandage
    ├── The Plan
    ├── Countercurse Mantra
    └── Blindfold
```

### 19.5. Terraspark Boots

```text
Terraspark Boots
├── Frostspark Boots
│   ├── Lightning Boots
│   │   ├── Spectre Boots
│   │   │   ├── Hermes/Flurry/Sailfish/Dunerider Boots
│   │   │   └── Rocket Boots
│   │   ├── Aglet
│   │   └── Anklet of the Wind
│   └── Ice Skates
└── Lava Waders
    ├── Water Walking Boots
    ├── Lava Charm
    ├── Obsidian Rose
    └── Molten Charm / Obsidian Water Walking Boots chain
```

### 19.6. Cell Phone / Shellphone route

```text
Cell Phone
├── PDA
│   ├── GPS
│   ├── Goblin Tech
│   ├── R.E.K. 3000
│   └── Fish Finder
└── Magic/Ice/Magic Conch path for Shellphone variants
```

---

## 20. Zenith

Zenith — post-Moon Lord melee weapon и финальный символ sword progression.

### 20.1. Компоненты Zenith

| Component | Stage | Source |
|---|---|---|
| Copper Shortsword | start | craft |
| Enchanted Sword | pre-HM | shrine/crates |
| Starfury | pre-HM | sky chests/crates |
| Bee Keeper | pre-HM | Queen Bee |
| Seedler | post-Plantera | Plantera |
| The Horseman's Blade | post-Plantera event | Pumpking |
| Influx Waver | post-Golem event | Martian Saucer |
| Star Wrath | post-Moon Lord | Moon Lord |
| Meowmere | post-Moon Lord | Moon Lord |
| Terra Blade | post-Plantera/Solar Eclipse path | craft |

### 20.2. Zenith tree summary

```text
Zenith
├── Copper Shortsword
├── Enchanted Sword
├── Starfury
├── Bee Keeper
├── Seedler
├── The Horseman's Blade
├── Influx Waver
├── Star Wrath
├── Meowmere
└── Terra Blade
    ├── True Excalibur
    │   └── Excalibur
    └── True Night's Edge
        └── Night's Edge
            ├── Evil sword
            ├── Muramasa
            ├── Blade of Grass
            └── Volcano
```

### 20.3. Практическая проблема Zenith

Самые раздражающие компоненты:

- Enchanted Sword, если не повезло с shrine/crates.
- Seedler, если Plantera не даёт дроп.
- Horseman's Blade из Pumpkin Moon.
- Influx Waver из Martian Saucer.
- Star Wrath / Meowmere из Moon Lord.

---

## 21. Moon Lord и Lunar progression

### 21.1. Правильный порядок

```text
Golem defeated
  ↓
Cultists spawn near Dungeon
  ↓
Kill cultists → Lunatic Cultist
  ↓
Kill Lunatic Cultist → Celestial Pillars
  ↓
Destroy Solar / Vortex / Nebula / Stardust Pillars
  ↓
Moon Lord spawns
```

### 21.2. Celestial Pillars

| Pillar | Class theme | Fragments craft |
|---|---|---|
| Solar | Melee | Solar Eruption, Daybreak, Solar armor |
| Vortex | Ranged | Phantasm, Vortex Beater, Vortex armor |
| Nebula | Magic | Nebula Blaze, Nebula Arcanum, Nebula armor |
| Stardust | Summoner | Stardust Dragon, Stardust Cell, Stardust armor |

### 21.3. Moon Lord drops

Moon Lord даёт:

- Luminite.
- Meowmere.
- Star Wrath.
- S.D.M.G.
- Celebration Mk2.
- Last Prism.
- Lunar Flare.
- Lunar Portal Staff.
- Rainbow Crystal Staff.
- Meowmere Minecart / portal gun / vanity / expert loot depending version and mode.

**Не путать:** Solar Eruption, Daybreak, Phantasm, Vortex Beater, Nebula Blaze, Nebula Arcanum, Stardust Dragon и Stardust Cell — это **не Moon Lord drops**, а fragment craft.

---

## 22. Подробная progression-памятка по этапам

### 22.1. Day 1–2

Цели:

- shelter;
- wood armor or cactus armor;
- basic bow/sword;
- torches;
- rope/platforms;
- first cave trip.

Не тратить время на:

- идеальную базу;
- полный сет copper/tin;
- бессмысленное копание без Spelunker/целей.

### 22.2. До первого босса

Цели:

- 200+ HP;
- 8–12 defense;
- mobility accessory;
- hook;
- 2–3 ряда platforms;
- Ironskin/Regeneration/Swiftness.

Кандидаты на первого босса:

- Eye of Cthulhu;
- King Slime;
- evil boss, если оружие уже хорошее.

### 22.3. До Skeletron

Цели:

- 300–400 HP;
- evil boss beaten;
- decent weapon: Bee's Knees / Phoenix Blaster / Night's Edge path / Space Gun / Imp Staff;
- arena at Dungeon entrance.

После победы:

- loot Dungeon;
- find Mechanic;
- Cobalt Shield;
- Muramasa;
- Handgun;
- Water Bolt / Magic Missile / Aqua Scepter.

### 22.4. До Wall of Flesh

Цели:

- 400 HP;
- Hellstone gear or class equivalent;
- long Underworld bridge / arena;
- Obsidian Skin for mining Hellstone;
- Beenades if ranged/hybrid cheese route;
- class emblem target после WoF.

WoF важен не только как босс, а как **переключатель мира**.

### 22.5. Первые 30 минут Hardmode

Цели:

- не умереть от новых врагов;
- разбить ограниченное число алтарей или выбрать fishing route;
- добыть first HM ore tier;
- сделать wings ASAP;
- получить weapon spike: Daedalus / Onyx / Spider / Crystal Serpent / Shadowflame.

Опасности:

- world evil spread;
- Wyverns;
- Mimics;
- ночные mech boss spawns.

### 22.6. До mechanical bosses

Цели:

- Adamantite/Titanium/Frost/Forbidden/Spider armor;
- wings;
- reforges хотя бы на weapons;
- potions;
- arena с Heart Lantern/Campfire/Bast.

Самый частый первый mech:

- Destroyer, если есть Daedalus Stormbow / piercing / Nimbus Rod / good arena.
- Twins, если хорошая mobility и single target DPS.
- Prime, если есть endurance и контроль дистанции.

### 22.7. После mechanical bosses

Цели:

- Hallowed gear;
- Drax/Pickaxe Axe;
- Chlorophyte mining;
- Plantera arena;
- upgrade class accessories.

### 22.8. До Plantera

Цели:

- arena в Underground Jungle;
- не ломать bulb случайно без подготовки;
- movement по арене;
- Chlorophyte/Hallowed/Turtle/Summon gear.

После Plantera:

- Temple Key;
- Dungeon upgrade;
- Biome Chests;
- Spectre/Shroomite/Tiki/Turtle progression.

### 22.9. До Golem

Цели:

- Lihzahrd Temple clear;
- traps осторожно;
- Power Cells;
- Golem arena адаптировать, если возможно.

Golem часто проще Plantera, но это gate к Cultist/Martians.

### 22.10. Post-Golem до Moon Lord

Цели:

- Martian Madness farm;
- Duke Fishron / Empress if needed;
- Pumpkin/Frost Moon farm;
- Beetle/Spectre/Shroomite/Spooky/Tiki optimization;
- Cultist fight;
- Pillar weapons craft;
- Moon Lord arena/strategy.

---

## 23. Биомные сундуки Dungeon

Post-Plantera можно открыть biome chests, если есть соответствующий key.

| Chest | Key | Item | Class |
|---|---|---|---|
| Crimson Chest | Crimson Key | Vampire Knives | melee sustain |
| Corruption Chest | Corruption Key | Scourge of the Corruptor | melee projectile |
| Hallowed Chest | Hallowed Key | Rainbow Gun | magic |
| Jungle Chest | Jungle Key | Piranha Gun | ranged |
| Frozen Chest | Frozen Key | Staff of the Frost Hydra | sentry |
| Desert Chest | Desert Key | Desert Tiger Staff | summon |

Keys редкие и фармятся с врагов соответствующего biome. Для искусственных биомов key farming работает при достаточном biome condition.

---

## 24. Reforging и модификаторы

### 24.1. Общая логика

Goblin Tinkerer позволяет reforging. Это денежная яма, но сильный источник DPS/survival.

| Категория | Частые лучшие modifiers |
|---|---|
| Swords / melee | Legendary, Godly/Demonic for some projectile weapons |
| Yoyos | Godly/Demonic/Legendary depending item rules |
| Guns | Unreal |
| Bows | Unreal |
| Magic | Mythical, иногда Demonic/Masterful depending mana/knockback |
| Summon weapons | Ruthless часто лучший DPS, Mythical если нужен knockback/utility |
| Whips | Legendary |
| Accessories | Warding / Menacing / Lucky / Violent / Quick |

### 24.2. Практический выбор accessory modifiers

| Ситуация | Modifier |
|---|---|
| умираешь | Warding |
| уверенно живёшь | Menacing / Lucky |
| summoner whip speed | Violent situational |
| speedrun/mobility | Quick situational |

---

## 25. Деньги, фарм, экономика

### 25.1. Early money

- sell duplicate accessories;
- gems;
- statue farms later;
- boss farming;
- fishing crates;
- events.

### 25.2. Hardmode money

- Pirate Invasion;
- Pumpkin/Frost Moon;
- boss farming;
- biome key farms;
- Mimic farms;
- sell bars/extra drops.

### 25.3. На что тратить

| Покупка | Почему важно |
|---|---|
| Piggy Bank / Safe / Defender's Forge / Void Bag | storage |
| Minishark / Illegal Gun Parts | ranged progression |
| Rocket Boots / Tinkerer's Workshop reforging | mobility + crafting |
| Clentaminator | biome control |
| Ammo / solutions | quality of life |
| Reforging | combat scaling |

---

## 26. Building / QoL / база

### 26.1. Базовая структура

Хорошая база:

- storage room;
- crafting hall;
- potion/herb farm;
- NPC housing separated by pylons;
- arena nearby;
- hellevator;
- fishing ponds;
- shimmer access route;
- boss/event arena.

### 26.2. Storage naming

Пример категорий:

- Ores / Bars.
- Gems / Crystals.
- Potions / Herbs.
- Fish / Bait.
- Weapons.
- Armor.
- Accessories.
- Blocks.
- Furniture.
- Boss Summons.
- Souls / Fragments / Endgame.

### 26.3. Useful permanent stations

- Crystal Ball.
- Ammo Box.
- Bewitching Table.
- Sharpening Station.
- War Table.
- Slice of Cake.
- Bast Statue.
- Campfire / Heart Lantern / Star in a Bottle.

---

## 27. Completion checklist

### 27.1. Main completion

- Defeat all main bosses.
- Defeat event bosses.
- Craft Zenith.
- Build endgame armor for all classes.
- Complete Bestiary.
- Get all NPCs.
- Build pylon network.
- Obtain Cell Phone / Shellphone.
- Obtain Ankh Shield.
- Obtain Terraspark Boots.
- Clear Old One's Army tier 3.
- Farm Moon Lord drops.

### 27.2. Collection goals

- All armor sets.
- All boss masks/trophies/relics.
- All biome chest weapons.
- All paintings / banners.
- All town slimes/pets.
- All music boxes.
- All mounts.
- All wings.

---

## 28. LLM-safe rules для генерации предметов/прогрессии

Этот раздел нужен, если документ скармливается модели для Terraria-мода, генерации оружия или автопроверки прогрессии.

### 28.1. Нельзя нарушать progression gates

| Gate | Что запрещено до него |
|---|---|
| до Skeletron | Dungeon locked loot как гарантированный обычный предмет |
| до WoF | Hardmode ores, Souls, mechanical boss drops |
| до 3 mechs | Chlorophyte mining, Plantera, Temple |
| до Plantera | post-Plantera Dungeon loot, biome chests |
| до Golem | Cultist, Martian Madness normal trigger, Lunar |
| до Cultist | Lunar Fragments |
| до Moon Lord | Luminite, Moon Lord drops |

### 28.2. Не путать source types

| Тип | Пример | Ошибка модели |
|---|---|---|
| Boss drop | Bee Keeper from Queen Bee | выдать как craft |
| Chest loot | Muramasa from Dungeon chest | выдать как boss drop |
| Biome chest | Vampire Knives | выдать Crimson Mimic |
| Mimic drop | Daedalus Stormbow | выдать Hallowed Chest |
| Fragment craft | Solar Eruption | выдать Moon Lord drop |
| Fishing | Crystal Serpent | выдать enemy drop |
| NPC purchase | Ice Rod | выдать Snow chest |
| Event drop | Chain Gun | выдать Arms Dealer |

### 28.3. Для генератора оружия

Каждый сгенерированный предмет должен иметь:

- stage: `pre_boss`, `pre_skeletron`, `pre_wof`, `early_hm`, `post_mech`, `post_plantera`, `post_golem`, `lunar`, `post_moon_lord`;
- class: `melee`, `ranged`, `magic`, `summon`, `hybrid`, `tool`;
- acquisition: `craft`, `drop`, `chest`, `fishing`, `npc`, `event`, `shimmer`, `quest`;
- gating boss/event;
- rough DPS budget;
- ammo/mana/minion-slot cost if applicable;
- special effect budget;
- validation note.

### 28.4. Балансные эвристики

- Early weapons can have utility, but not endgame homing + pierce + high base damage all at once.
- Defense debuff is stronger than raw DoT.
- Homing greatly increases real DPS vs mobile bosses.
- Piercing is overpowered vs segmented bosses.
- Summoner tag damage changes value of fast minions.
- Ammo economy matters: “does not consume ammo” is a DPS/economy stat.
- Mana cost is not enough to balance extreme burst if Mana Flower exists.
- Lifesteal is dangerous and should be heavily gated.
- Infinite range through blocks is dangerous for cheesing.

---

## 29. ToDo для будущего расширения

Если нужно довести документ до прям “локальной копии Wiki”, расширять так:

1. Добавить полный sortable-like список всех melee weapons с exact damage/use time/knockback/crit/source.
2. Добавить полный список всех ranged weapons и ammo interaction.
3. Добавить полный список magic weapons с mana cost/use time/projectile notes.
4. Добавить полный список summon weapons, sentries и whips с tag damage.
5. Добавить exact HP всех боссов по Classic/Expert/Master, включая части/сегменты.
6. Добавить exact drop rates для каждого boss/event enemy.
7. Добавить full NPC happiness matrix.
8. Добавить все Shimmer transmutations из 1.4.5.x.
9. Добавить все potion recipes и food tiers.
10. Добавить все armor set bonuses exact.
11. Добавить all accessories exact effects и crafting trees.
12. Добавить секцию mod-balancing budgets по стадиям.
13. Добавить JSON/YAML schema для машинной валидации предметов.

---

## 30. Быстрый one-page route

```text
1. Build shelter → mine → 200 HP → mobility + hook.
2. Kill Eye / evil boss → craft evil gear.
3. Jungle / Queen Bee → Bee gear / Beenades / Blade of Grass.
4. Kill Skeletron → loot Dungeon.
5. Mine Hellstone → build hellbridge → kill Wall of Flesh.
6. Enter Hardmode → ores/fishing → wings → early HM weapon spike.
7. Kill mechanical bosses → Hallowed Bars + Souls → Drax/Pickaxe Axe.
8. Mine Chlorophyte → prepare Jungle arena → kill Plantera.
9. Loot post-Plantera Dungeon / biome chests → kill Golem.
10. Farm Fishron/Empress/events/Martians if needed.
11. Kill Lunatic Cultist → pillars → craft Lunar weapons.
12. Kill Moon Lord → Luminite/endgame drops → craft final armor/Zenith.
```

---

## 31. Короткие “не забыть”

- Guide can show crafting recipes from materials.
- Reforge weapons before hard bosses.
- Arena and buffs often matter more than +1 tier weapon.
- Do not open Dungeon before Skeletron unless you know what you are doing.
- Do not accidentally summon Wall of Flesh before base/world prep.
- Do not fight Plantera in tiny natural tunnels.
- Do not confuse biome Mimics with biome Dungeon Chests.
- Do not confuse Lunar Fragment weapons with Moon Lord drops.
- For exact item stats, source-of-truth is current wiki/code, not memory.

