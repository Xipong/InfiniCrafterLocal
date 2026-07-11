# Предлайфтестовый ручной трейс v12

Дата: 2026-07-10
Baseline: maintainable runtime v11 + prompt/image contract patch v12.

Это не прогон кода и не утверждение, что локальная LLM уже дала именно такие ответы. Ниже вручную проиграна цепочка:

`parent facts → Author LLM JSON → normalization/compile → AttackSpec/gameplay → Visual Director → Image backend`.

Цель — найти места, где формально валидный ответ модели создаёт другой предмет, чем она обещала. Трейсы не используют name/tooltip/material как источник gameplay.

## 1. Дробовик с шестью пеллетами

**Ожидаемый authoring:** `fire_ranged_weapon(family=shotgun, ammoFor=bullet, shotCount=6, spreadRadians≈0.3)`.

**Runtime:** шесть `GeneratedProjectile` создаются одновременно; `shotCount` не является временной очередью.

**Image:** projectile slot описывает одну пеллету. Шесть тел создаёт runtime, а не PNG.

**Найденный риск:** Visual Director мог написать `six pellets in a fan`, после чего runtime ещё раз создавал шесть копий текстуры.

**v12:** explicit `shotCount/splitCount` включает single-body sanitizer. Исключение остаётся только для явно authored `projectileFamily=bundle|cluster|swarm|fan|volley`.

**Остаточный риск:** настоящий timed burst всё ещё не поддерживается и не должен обещаться.

## 2. Магическая сфера, раскалывающаяся при попадании

**Ожидаемый authoring:** один `cast_magic_weapon` плюс `spawn_secondary_projectiles(trigger=on_hit,count=3,projectileShape=...)`.

**Runtime:** primary orb получает один secondary lifecycle; child spec обнуляет `SplitCount`, child depth и дальнейшие secondary triggers, поэтому рекурсивного дерева нет.

**Image:** primary projectile и child projectile — разные роли. `projectileSpritePrompt` описывает одну сферу, `childSpritePrompt` — один осколок.

**Найденный риск:** Visual Director мог запечь три осколка в один child PNG.

**v12:** child-role прямо говорит «one child body; runtime spawns copies».

**Остаточный риск:** одновременное использование child-producing `apply_on_hit_effect` и отдельного secondary call может дать две разные группы детей; planner должен выбирать одну понятную механику.

## 3. Ракета, распадающаяся при завершении полёта

**Ожидаемый authoring:** launcher/rocket primary плюс `spawn_secondary_projectiles(trigger=on_expire,count=4)`.

**Runtime:** `on_expire` означает любой `Projectile.Kill`: timeout, tile collision, исчерпание penetrate или explicit kill. Child spec не наследует `on_expire`, поэтому рекурсии нет.

**Найденный риск:** модель могла понимать `on_expire` как «только закончился lifetime» и обещать таймерный фейерверк, хотя ракета распадётся и при раннем столкновении.

**v12:** это значение явно объяснено в API card.

**Остаточный риск:** отдельного `on_timeout_only` сейчас нет; его нельзя обещать через prose.

## 4. Копьё/рапира с held-thrust

**Ожидаемый authoring:** `perform_melee_attack(family=spear|rapier, projectileShape=...)`.

**Runtime:** один held projectile, owner arm pose, line collision, item melee hitbox выключен; это не свободно летящее копьё.

**Image:** item sprite переиспользуется как held projection, если отдельная transformed projectile form не authored.

**Найденный риск:** `heldSpritePrompt` создавал иллюзию отдельного ассета, хотя отдельный held PNG pipeline не генерирует.

**v12:** поле не рекламируется и удаляется на visual boundary. Один canonical item/projectile decision остаётся в `bakedAssets`.

**Остаточный риск:** очень короткий/широкий authored предмет может выглядеть странно при thrust rotation; live test нужен для draw origin.

## 5. Item-bodied формы: boomerang, yoyo, flail и whip

**Ожидаемый authoring:** exact finite family через `perform_melee_attack`.

**Runtime:**

- returning — тот же предмет летит и возвращается;
- yoyo — held/channel hover и возврат;
- flail — projectile head плюс runtime tether;
- whip — runtime line/lash, а не длинная картинка хлыста.

**Image:** boomerang/yoyo обычно reuse item sprite. Flail projectile — одна головка с коротким chain nub. Whip asset — tip/short segment или particle VFX, не растянутый трос на весь canvas.

**Найденный риск:** Image Gen мог запечь полную цепь/хлыст, а runtime дополнительно рисовал tether.

**v12:** role contracts оставляют только локальный attachment/tip. Gameplay family не определяется по тексту цепи.

**Остаточный риск:** текущие flail/yoyo executors упрощённее ванильных state machines; предметы играбельны, но не повторяют все состояния Terraria один в один.

## 6. Временный орбитальный помощник

**Ожидаемый authoring:** `spawn_temporary_helper_projectile(family=orbiter|drone|wisp|temporary_turret|pet_attack, lifetimeTicks=...)`.

**Runtime:** короткоживущий обычный generated projectile с bounded movement.

**Найденный риск:** старое имя `summon_combat_entity` и families `minion/sentry` почти неизбежно заставляли LLM обещать buff lifecycle, slots, persistence и resummon, которых нет.

**Текущее состояние:** active API называется `spawn_temporary_helper_projectile`; старое имя отклоняется. Persistent minion/sentry не рекламируются.

**Остаточный риск:** настоящий summon class пока не готов. Его надо делать отдельным vertical slice с buff/slot/target/persistence lifecycle.

## 7. Generated ammo и самостоятельный метательный дротик

### Обычная стрела/пуля как ammo stack

`resultKind=ammo + ammoFor=arrow|bullet` создаёт vanilla ammo identity. У такого ammo нет собственного generated `AttackSpec` projectile.

### Самостоятельный ядовитый дротик

Должен быть `resultKind=consumable_weapon` или `weapon`, `ammoFor=empty`, плюс `shoot_projectile` с explicit effect/onHit.

**Найденный риск:** LLM могла сделать `resultKind=ammo, ammoFor=bullet` и пообещать уникальную generated bullet механику, которая не исполняется.

**v12:** различие прописано в semantic rules и function cards.

**Остаточный риск:** оружие, потребляющее vanilla arrows/bullets, всё равно создаёт `GeneratedProjectile` и сохраняет authored weapon AttackSpec; ограничение относится именно к generated ammo item.

## 8. Броня и аксессуар

**Ожидаемый authoring:** `set_item_stats(resultKind=armor|accessory)` плюс ровно один `armor_effect`/`accessory_effect`.

**Runtime:** item damage/attack выключены; equip stats применяются из explicit fields.

**Image:** одна конкретная часть брони по `armorSlot` или один компактный аксессуар.

**Найденный риск:** Image Gen мог нарисовать персонажа в полном комплекте вместо inventory icon одной вещи.

**v12:** final item-role guard использует explicit resultKind/armorSlot и запрещает character/mannequin/full set. Это visual framing, не gameplay routing.

**Остаточный риск:** отдельные equip textures на теле игрока не генерируются; это inventory item sprite, не полноценный vanity set.

## 9. Зелье, инструмент, мебель и материал

**Ожидаемый authoring:** отдельные result kinds и конечные calls (`apply_player_effect_on_use`, `tool_capability`, placeable facts, `extractinator_output`).

**Image:** один bottle/tool/furniture object/material stack как Terraria inventory icon.

**Найденный риск:** сцена питья, шахта, комната с мебелью или landscape вместо объекта.

**v12:** explicit resultKind visual guard запрещает action/environment scenes и задаёт один объект.

**Остаточный риск:** runtime поддержка произвольной новой furniture tile сущности ограничена; модель не должна обещать неизвестную tile logic только по картинке.

## 10. Неизвестный modded parent без визуальных фактов

**Author LLM:** получает raw gameplay/projectile facts, source mod/internal name и authored merge task, но не гарантированно знает исходный внешний вид предмета.

**Visual Director:** должен создать coherent child из authored concept, mechanical facts, palette и anchors, но не утверждать exact parent fidelity.

**Image backend:** технический validator проверяет фон, alpha, fill, края и читаемость, но не доказывает семантическое сходство с неизвестным modded parent.

**Найденный риск:** красивый технически правильный sprite может быть визуально «не тем предметом».

**v12:** prompt запрещает выдумывать точную fidelity при отсутствии evidence. Item/projectile/impact роли жёстко разделены; emitted projectile не рисуется рядом с item icon.

**Остаточный риск перед live test:** семантический image judge отсутствует. Это осознанный риск; добавлять ещё один тяжёлый LLM-call до A/B теста не следует.

# Итоговый предлайфтестовый статус

Теоретически готовы к честному лайфтесту:

- swing/thrust/returning/flail/yoyo/whip;
- ranged and magic multishot;
- channel beam;
- overhead barrage с независимой темой Daedalus/Starfury;
- on-hit/on-expire children;
- temporary helper projectile;
- equipment, potion, tool, ammo/material visual roles.

Не считать готовыми и не обещать:

- timed burst fire;
- timeout-only secondary trigger;
- persistent minion/sentry lifecycle;
- произвольную новую furniture/tile logic;
- точную визуальную fidelity неизвестного modded parent без visual evidence;
- семантическую правильность PNG только на основании технического sprite score.
