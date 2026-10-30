# Runtime references — external patterns, не локальная authority

[Standardization boundary](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md) · [Source owners](../../development/CODE_MAP_RU.md) · [Current proof limits](../../development/architecture/ARCHITECTURE_RU.md#runtime-trust)

<a id="version"></a>
## Версионная граница

Проект объявляет stable tModLoader/.NET 8. Pattern references ниже — official stable docs и ExampleMod/Calamity `1.4.4`, не development/1.4.5. Точный patch/наличие DLL/build result определяются **конкретной проверкой и references**, не этим статическим обзором. Старое «локальной installation нет» было статусом исходного прохода; поздние [headless records](../../archive/HISTORY_RU.md#typed) нельзя переименовывать в current game/MP proof.

<a id="official"></a>
## Official API и ExampleMod

- [ModItem stable](https://docs.tmodloader.net/docs/stable/class_mod_item.html): AltFunctionUse/CanUseItem/ConsumeItem/UseItem/Shoot/HoldoutOffset — разные input/lifecycle hooks; CanUseItem не место для mutation.
- [ModProjectile stable](https://docs.tmodloader.net/docs/stable/class_mod_projectile.html): AI/Colliding/OnTileCollide/OnHitNPC/SendExtraAI/ReceiveExtraAI — movement, collision, events и необходимое instance net state отдельно.
- [Projectile API](https://docs.tmodloader.net/docs/stable/class_projectile.html): timeLeft/penetrate/tileCollide/immunity/extraUpdates; NewProjectileDirect для created-instance hydrate. Defaults не скрытые design choices.
- [ItemUseStyleID](https://docs.tmodloader.net/docs/stable/class_item_use_style_i_d.html), [DamageClass](https://docs.tmodloader.net/docs/stable/class_damage_class.html): exact finite mappings, не loose names. ModType.FullName + ModContent.TryFind<T> — exact registered content; AmmoID/PickAmmo и loader counts объясняют [ammo/loaded-ID exclusions](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md#ammo-healing).
- [Stable releases](https://github.com/tModLoader/tModLoader/releases?q=stable) задают release line, не pinned current patch.

Все ExampleMod paths ниже относительны [tModLoader/1.4.4/ExampleMod](https://github.com/tModLoader/tModLoader/tree/1.4.4/ExampleMod):

| Path / method | Pattern |
|---|---|
| `Common/GlobalProjectiles/ExampleProjectileNetSync.cs` SendExtraAI/ReceiveExtraAI | Только нужное instance state, симметричный wire shape |
| `Content/Projectiles/ExampleAdvancedFlailProjectile.cs` AI/collision | Reusable tether/return controller, не whole-weapon macro |
| `ExampleYoyoProjectile.cs`, `ExampleWhipProjectile.cs` в Content/Projectiles | Owner-relative hover/return; bounded lash points/collision |
| `Content/Items/Weapons/ExampleHeldProjectileWeapon.cs` + projectile | Explicit owner-attached entity, channel, one held instance и aim sync |
| `Content/Items/Weapons/ExampleLastPrism.cs` | Beam controller/holdout lifecycle отделён от item identity |
| ExampleHamaxe / item value examples | Internal Item.axe ×5 tooltip; buyPrice/sellPrice helpers задают copper Item.value, не resale guarantee |

<a id="calamity"></a>
## Calamity reference и capability routing

[CalamityModPublic/1.4.4](https://github.com/CalamityTeam/CalamityModPublic/tree/1.4.4): `Projectiles/BaseProjectiles/BaseGunHoldoutProjectile.cs` (ManageHoldout/KillHoldoutLogic) — owner mouse aim, peers consume sync; `Projectiles/Ranged/AdamAcceleratorBeam.cs` (Colliding/length/scale) — bounded line collision и visual length lifecycle. Assets, dependencies и крупные blocks не копировались; это patterns, не runtime requirement.

Item/use/alternate/tool/placeable/equipment → ModItem; attached/channel/beam → held-projectile/beam patterns; flail/yoyo/whip → bounded custom AI; child/events/net → hooks + extra AI; collision/AoE → exact collision/event consumers. Последняя группа **не** blanket server collision proof: owner-hit отдельно использует [vanilla owner trust](../../development/architecture/ARCHITECTURE_RU.md#runtime-trust).

Внешний пример не расширяет executable surface. Mapping/units/ranges/exclusions принадлежат [standardization](TERRARIA_TMODLOADER_STANDARDIZATION_RU.md#boundary), finite aliases/lowerings — [generated Lowery](../generated/LOWERY_RU.md), доказанный новый adapter — [vertical slice](../../development/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md#vertical-slice).

## Проверенные NPC-hit статусы родителей

`Item.buffType` описывает buff от использования предмета, а не дебафф попадания
снаряда. Нулевой `buffType` поэтому не доказывает отсутствие on-hit эффекта.
Native `Projectile.StatusNPC` вызывается из hit path отдельно от `SetDefaults`:
[официальный patch ветки 1.4.4](https://github.com/tModLoader/tModLoader/blob/1.4.4/patches/tModLoader/Terraria/Projectile.cs.patch).

`directProjectileRaw` / `effectiveProjectileRaw.onHitStatusReference` передают
узкую read-only справку, только если SHA256 IL метода и MVID модуля совпадают с проверенными.
Она сохраняется целиком в Author parent dossier, включая scope и certificate.
Тот же canonical capture используется для `/infinidump`: и внутри item projectile
snapshot, и в отдельном projectile roster. Старые dumps не дополняются догадками.
Это не автоматическое наследование эффекта и не маршрутизация generated AI.

### Систематическое извлечение, а не список двух предметов

`tools/generate/generate_native_hit_status.py` читает IL всей функции из
официальной сборки и анализирует **каждый vanilla ProjectileID**. Он не загружает
сборку как исполняемый код и не запускает игровые hooks. Bounded CFG-анализ
знает только конкретный `this.type`; неизвестное состояние игрока, мира, AI и
случайных условий рассматривается по обеим веткам. В справку попадают лишь
`NPC.AddBuff` на целевом NPC, доказанные на каждом достижимом выходе. Неизвестные
вызовы/opcodes, циклы и неверный control flow останавливают генератор, а не
порождают догадку. Ветвящиеся buff IDs/durations исключаются.

Результат: **64 типа снарядов, 65 запросов эффектов** из 1021 проанализированного
типа в обеих проверенных сборках; покрыта 51 из 100 call sites `AddBuff`.
Остальные sites и причины исключения доступны в
[`native_hit_status_sources.generated.json`](../../../contracts/reports/native_hit_status_sources.generated.json).
Это не означает, что у остальных снарядов нет эффектов: условные procs,
player/world/AI-зависимые случаи, item hooks, PvP, child AI и mod hooks **неизвестны**.
В частности, случайный шанс наложения не превращается в гарантированный эффект.

Каждая справка содержит массив `effects` (не теряет второй эффект), `buffId`,
`buffFullName`, точные inclusive min/max, **шаг** распределения и IL offset.
Например, `GoldenShowerFriendly` → Ichor 600 ticks; `ShadowFlameKnife` →
ShadowFlame равномерно 60–179 ticks; `PygmySpear` → Venom 300–600 ticks **шагом
60**, а не любое целое между границами. `fixed` означает фиксированный срок,
`uniform_integer_steps_inclusive` — равновероятные значения с указанным шагом.

### Источники и воспроизводимость

- [tML v2026.08.3.0](https://github.com/tModLoader/tModLoader/releases/tag/v2026.08.3.0):
  ZIP SHA256 `61e865f3702b12ce4a26c5a90b9de99a12c65ffc228455eb3390ce54af1eab15`;
  `StatusNPC` IL SHA256 `0409d6e8aeb6c41acc5454f7f818368639b041341d9eafff9dd1336cd42e2cf7`.
- [tML v2026.06.3.6](https://github.com/tModLoader/tModLoader/releases/tag/v2026.06.3.6):
  ZIP SHA256 `de501c82d25e8485a4c6174c64f8bcd6f4948e9fc4ee3d963745a7186e526674`;
  `StatusNPC` IL SHA256 `ea30212888353eea100edc863b651f8ee1555b4f39891eb2de442ba3339dcb79`.

Report также содержит SHA256 каждой DLL и MVID модуля (привязка metadata tokens
к проверенной сборке, а не только к байтам метода). `assemblyVersion: 1.4.4.9` — версия
Terraria из metadata, не номер релиза tML. Generated C# catalog и report
строятся одной командой (developer-only зависимости, не runtime dependency):

```bash
python -m pip install -r tools/generate/native-hit-status-requirements.txt
python tools/generate/generate_native_hit_status.py \
  --assembly <2026.08.3.0>/tModLoader.dll \
  --assembly <2026.06.3.6>/tModLoader.dll --check
```

Без `--check` команда обновляет оба generated файла. Передавать нужно обе
поддерживаемые сборки; analyzer tests не требуют DLL или этих dependencies.

IDs и имена берутся из metadata native constants. Имя предмета, tooltip и
`aiStyle` не выбирают статус. Runtime принимает только certificate из generated
catalog и совпадающий ModuleVersionId; другой IL/модуль, неизвестный тип или `ModProjectile` → справка отсутствует.
Это vanilla NPC-hit **запрос**, не гарантия фактического наложения: иммунитет
NPC и другие моды могут менять результат. Во время крафта hit hooks не
запускаются. Native regression отдельно вызывает настоящий `StatusNPC` на
изолированных NPC и проверяет fixed/integer/stepped durations; Python tests
проверяют условные/dynamic exclusions, ветвления и отсутствие потери multiplicity.

## Native attack source за пределами SetDefaults

`GeneratorClient.ProjectileAttackFacts.cs` извлекает `attackReference` из actual native source: выбор AI/helper по type/aiStyle guards, связанные clock/position/rotation/scale/lifetime expressions, collision calls и их аргументы/предикаты, выбранный draw helper с Frame/palette/fade/scale dependencies. Каждый использованный native метод имеет SHA256 IL и MVID; неизвестный native binary или mod projectile не заимствует vanilla-факт. AI, draw и hooks при capture не запускаются.

Это source observations, не автоматически унаследованное поведение. В частности, 16×16 из projectile defaults не описывает cone collision; `noMelee` отключает item contact damage, а не видимость held item. Сам held-item renderer, runtime detours, mod/world/player gates и итоговый урон остаются отдельной границей доказательства. Unsupported source shape и превышение bound обозначаются явно: отсутствие справки не доказывает отсутствие механики. Размер сериализованной роли не используется как предел извлечения. Ограничения считают работу графа, выражения и зависимости; отказ сохраняет точную причину вместо обрезания формулы. Подтверждённый срез конкретного actor строится до попытки полного аудиторского представления общего метода. Отказ полного метода не уничтожает пригодный подтверждённый срез.

`InfiniDumpCommand` использует тот же `ToWireItem` / `ProjectileRawSnapshot`, что live craft, и добавляет только dump-specific identity/texture diagnostics. Полный raw dump остаётся доказательством происхождения. Модель получает отдельную проекцию поведения, а не обязательную копию аудиторского протокола. Source observations не расширяют `fieldPermissions` и не являются новым generated opcode/controller или weapon-family router.

`native_attack_behavior_view.py` отделяет модельный контекст от provenance: исключает сертификаты методов/SHA/MVID и избыточные служебные сведения, сохраняет связанные выражения, условия, альтернативы, единицы и неизвестные зависимости. Вместо абсолютных instruction offsets используются локальные `step`, общие для observations, dependencies и predicates: порядок между коллекциями не теряется. Полный исходный capture не изменяется. Это явно metadata-lossy view, не обещание восстановить исходный dump из промпта.

Для общего native AI метода producer дополнительно строит `identitySelected`: выбирает только доказанные ветви по `type`/`aiStyle` конкретного получателя. Ветки по времени, ai/localAI, игроку и другим изменяемым условиям не выбираются. Запись identity, передача/утечка возможного alias и неподтверждённый получатель препятствуют специализации. Исходный граф либо явная диагностика отказа полного разбора остаётся в дампе; причины structural-budget отказов не скрываются общим сообщением о неподдержанном helper. Выбранный срез сохраняет свой сертификат и полноту собственных зависимостей. Ошибка специализации не уничтожает уже извлечённые факты. Python принимает selected view только при совпадении source identity/сертификата и известном формате; неизвестный формат сохраняет исходную справку.

`native_attack_expression_view.py` делает арифметику и чтение/запись полей понятнее, сохраняя порядок операций, группировку, числовые значения и casts. Python не исполняет выражения и не выбирает ветки; доказанная identity-специализация принадлежит native producer. Для подтверждённых XNA Color операций представление `rgba.white * scalar` сохраняет умножение всех RGBA каналов и исходный порядок, а не подменяет его изменением только alpha. `native_attack_tables.py` дополнительно устраняет повторные ключи там, где таблица действительно короче; необходимые обозначения находятся в самой справке. Размер 15–20 тысяч символов служит ориентиром для реального примера, не лимитом усечения. Значимые условия нельзя отбрасывать ради достижения числа.

Семантические представления не требуют декодировать служебные таблицы. `native_attack_geometry_view.py` заменяет тела известных engine helpers краткими правилами только при совпадении полного графа и native/transitive сертификатов. Для cone сохраняются включённые угловые и исключённая радиальная границы; rectangle helper остаётся именно проверкой пяти точек, а не объявляется точным пересечением фигур. Изменённый helper остаётся исходным графом. Нативная численная проверка сравнивает правила с реальными функциями на граничных и случайных входах.

`native_attack_draw_view.py` показывает упорядоченные sprite layers и native sparkle calls с frame/tint/rotation/scale и условиями, общими буквальными параметрами и определениями переменных. Исходные binding steps и изменения отдельных каналов цвета сохраняются; повторный вызов конструктора исключается только при соответствующем source use с теми же порядком/условиями и multiplicity. Нераспознанные операции сохраняют прежнее source-представление. Сигнатуры распознанных API и дублирующая упаковка ресурсов не являются частью нового дизайна; raw dump остаётся полным. Имена `fade` и `fadeInput` используются только для доказанной пары remap-up/remap-down, а не угадываются по имени оружия. Семантические слои остаются именованным JSON, не превращаются обратно в анонимные строки таблицы.

Родители представлены одинаковыми по структуре `parentBriefs` (identity/properties/behavior/appearance) и отдельными техническими `parents`. Brief содержит выбранные буквальные факты в исходных единицах, не придумывает роль ингредиента, tier, DPS или итоговую внешность. Нет квоты 50/50 по длине. Gameplay Author/Repair исключают только распознанный граф инструкций отрисовки, оставляя его source-мотивы в brief и все игровые зависимости в технической справке; неизвестная draw schema сохраняется целиком. Visual/VFX получают source-внешность родителей, но не их motion/collision implementation как шаблон нового поведения: принятую механику ребёнка они получают отдельно и не меняют её. `light` принятого ребёнка передаётся буквально, включая нулевые значения.

Контекст Repair соответствует разрешённой правке. Visual sizing/grip-only Repair получает размерные ссылки и принятую механику ребёнка, без полного исходного поведения родителей. VFX numeric/reference-only Repair использует принятые runtime/visual данные; контекст родителей остаётся для создания и художественного описания. Initial/design запросы сохраняют релевантную родительскую справку. Передача read-only данных сама по себе не делает их необходимыми для каждого запроса.

Лимит попаданий не равен числу уникальных целей. `ProjectileRawSnapshot` уже сохраняет `penetrate`, `maxPenetrate`, local/static NPC immunity и cooldown, `stopsDealingDamageAfterPenetrateHits`, lifetime и owner-hit ограничения. Эти поля следует читать вместе с motion/collision и spawn bindings; текущие нулевые ai defaults не заменяют выражения, устанавливаемые при создании снаряда. Нативные проверки сравнивают эти поля с настоящим объектом и отдельно исполняют AI/collision на изолированных CPU actors. Последнее не доказывает автоматически полноту всего извлечённого source graph.

Offline `generate_native_attack_facts.py` сохраняет exact typed constructor и `spawnInputs`, включая source position/velocity/ai0…2 и helper certificates; helper output не подменяется Item.scale. Существующие strict count/damage proofs сохраняют свою узкую область: multi-spawn branches не объявляются fixed1 или полностью распознанными. Native decoder читает полную объявленную длину method body, а не прежний prefix 100000 bytes.
