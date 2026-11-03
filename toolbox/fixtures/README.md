# Исторические пакеты запросов

Пакет — это исходные пары **в прежнем порядке**, ориентация A/B и отдельный snapshot
родительских объектов. Никаких заново придуманных характеристик или ответов моделей.
JSON в `panels/` — канонический список cases; JSONL в `parents/` / `items.jsonl` —
фактические входные parent rows. Архивные пути в metadata — provenance, не зависимости:
всё необходимое для выбора и сборки запросов уже находится в этом checkout.

| Команда / preset | Cases | Родители | Происхождение |
|---|---:|---:|---|
| `live10` / `live10-midgame` | 10 | 20 | Наш исторический midgame, преимущественно early Hardmode |
| `live20` / `live20-classic` | 20 | 39 | Классический преимущественно pre-Hardmode набор, включая поздний pre-Hardmode |
| `live20 --preset live20-classic-sprites` | те же 20 | те же 39 | Реальный вариант paired Sol/Luna с исходными `spriteReferenceRaw` |
| `live10 --preset live10-starter` | 10 | из classic20 | Новый subset из PR141, **не** прежний midgame |

```bash
python -m toolbox panels
python -m toolbox live10
python -m toolbox live20
python -m toolbox live20 --preset live20-classic-sprites
```

Это preflight без сети. Для фактической генерации остаётся явный `--run` и выбранные
настройки из [инструкции запуска](../live/README.md). Исполняется актуальный настоящий
pipeline проекта; старые model/provider настройки и старые результаты не переносятся.

## Live10 midgame

[Пары](panels/live10-midgame.json) · [20 исходных родителей](parents/live10-midgame.jsonl).
Восстановлено из `live10-luna6-high-midgame-20261011-0335`: `cases.json`,
`frozen-parent-inputs.json` и исходных строк `items_runtime_dump.jsonl`. Порядок
подтверждён `caseIndex` запросов, а не алфавитным списком snapshots из позднего review.

| Case | Родитель A | Родитель B |
|---|---|---|
| `night_missile` | `NightsEdge` | `MagicMissile` |
| `crystal_repeater` | `AdamantiteRepeater` | `CrystalShard` |
| `shadow_frost` | `ShadowFlameKnife` | `Frostbrand` |
| `rain_spiders` | `SpiderStaff` | `NimbusRod` |
| `ichor_spider_queen` | `QueenSpiderStaff` | `GoldenShower` |
| `holy_storm` | `DaedalusStormbow` | `HolyArrow` |
| `precision_titanium` | `TitaniumPickaxe` | `MechanicalLens` |
| `frost_obsidian_guard` | `FrostsparkBoots` | `ObsidianShield` |
| `radiant_forge` | `OrichalcumAnvil` | `SoulofLight` |
| `meteor_star_cannon` | `StarCannon` | `MeteorStaff` |

## Live20 classic

[Пары](panels/live20-classic.json) · [39 исходных родителей](items.jsonl).
Точный roster прежнего harness независимо подтверждён сохранённым
`live20-sol-luna-comparison-20261005/cache-audit/fixed20_cases.json`.
Это **не строго начало игры**: `QueenSpiderStaff` + `SpiderFang` относится к early Hardmode.

| Case | Родитель A | Родитель B |
|---|---|---|
| `woodwork_blade` | `WoodenSword` | `WorkBench` |
| `astral_mirror` | `MagicMirror` | `FallenStar` |
| `bee_boomstick` | `Boomstick` | `BeeWax` |
| `swift_boots` | `HermesBoots` | `Aglet` |
| `ropebound_spear` | `Spear` | `Rope` |
| `infernal_boomerang` | `EnchantedBoomerang` | `HellstoneBar` |
| `meteor_spacegun` | `SpaceGun` | `MeteoriteBar` |
| `astral_minishark` | `Minishark` | `FallenStar` |
| `chained_ball` | `BallOHurt` | `Chain` |
| `corrupt_yoyo` | `CorruptYoyo` | `DemoniteBar` |
| `jungle_whip` | `ThornWhip` | `JungleSpores` |
| `lens_finch_staff` | `BabyBirdStaff` | `Lens` |
| `spider_sentry` | `QueenSpiderStaff` | `SpiderFang` |
| `gel_grenade` | `Grenade` | `Gel` |
| `jester_bow` | `WoodenBow` | `JestersArrow` |
| `obsidian_pickaxe` | `MoltenPickaxe` | `Obsidian` |
| `vital_regen_band` | `BandofRegeneration` | `LifeCrystal` |
| `torch_mining_helmet` | `MiningHelmet` | `Torch` |
| `glowing_healing_potion` | `HealingPotion` | `GlowingMushroom` |
| `silt_extractinator` | `Extractinator` | `SiltBlock` |

## Варианты входов и проверка источников

- [Sprite-вариант](panels/live20-classic-sprites.json) использует те же 20 пар и
  [отдельный исходный JSONL](parents/live20-classic-sprites.jsonl). Он побайтно взят из
  `live20-sol-luna-comparison-20261005/parent-native/items-with-sprite-references.jsonl`.
  По сравнению с classic39 меняется только добавление `spriteReferenceRaw` каждому родителю;
  это не третья панель рецептов и не вызов image backend.
- `QueenSpiderStaff` встречается и в Live10, и в Live20. Scalar gameplay stats совпадают,
  но tooltip/texture/projectile context различается. Не сливай fixtures одним словарём
  `internalName`: loader всегда выбирает собственный snapshot пакета.
- [classic_provenance.json](classic_provenance.json) хранит source paths/hashes и byte identity.
  Все три JSONL сохраняют исходные строки, включая lexemes и line endings. Повторные
  исторические прогоны не размножены в отдельные presets; продолжение из 9 cases не
  объявлено новой панелью. SHA и ordered case list защищены offline regression tests.
- Старые ответы, prompts/traces, credentials и частные конфиги в пакет не входят.
  Восстановление входов не означает новую quality/latency/art/game приёмку.

```bash
python -m pytest -q toolbox/tests/test_builtin_panels.py toolbox/tests/test_campaign.py
```

## Частная панель из 40 случаев

В checkout включены только перечисленные выше исторические пакеты. Частная
панель Live40, её свежие snapshots 76 родителей и provenance не поставляются.
Собственные входы можно передать через существующий custom-selection маршрут:

```bash
python -m toolbox live20 --cases-file /path/to/cases.json --runtime-dump /path/to/parents.jsonl --expected-case-count 40
```

Здесь `live20` выбирает общий runner, а не ограничивает число custom cases.
`cases.json` содержит список `{ "case", "itemA", "itemB" }` либо объект с таким
списком в `cases`; `parents.jsonl` содержит соответствующие объекты родителей с
`internalName`. Файлы предоставляет оператор. Это preflight без вызовов моделей;
для фактического запуска нужны отдельные настройки и явный `--run` по
[инструкции](../live/README.md). Не называйте custom selection историческим Live20
и не смешивайте разные snapshots под видом одного неизменного входного cohort.
