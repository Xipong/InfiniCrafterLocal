# InfiniCrafterLocal v0.4.241 — Terraria/tModLoader standardization report

## Результат

Runtime сохранён low-level и LLM-authored, но технические представления приведены ближе к stable tModLoader там, где это не сокращает пространство дизайна. Собственный proxy/component runtime оставлен только для динамических сущностей, per-instance assets и authored entity/event graph.

## Основные изменения

- добавлен единый finite vocabulary Python/C# для `DamageClass`, `ItemUseStyleID` и `AmmoID`;
- удалены gameplay aliases `passive`, `drink`, `eat`, plural ammo spellings и `rogue`; `throwing` оставлен как точное stable `DamageClass.Throwing`;
- loose/alias lookup modded DamageClass заменён единственной строгой tModLoader content identity `ModName/ClassName` без fallback в `Generic`; псевдотокены `none`/`modded` и дублирующее `damageClassFullName` удалены;
- `configure_consumption` отделён от новой `configure_vanilla_ammo_item`;
- `Item.ammo` больше не смешивается с `Item.useAmmo`; ammo `Item.shootSpeed` отделён от скорости runtime entity; finite ammo vocabulary расширен до всех безопасных stable AmmoID-категорий, а vanilla projectile ID ограничен `1..1021`;
- `Item.notAmmo` и `Item.potion` стали явными authored полями вместо скрытых выводов;
- `valueCopper` документирован как точное `Item.value`, а `axePower` — как внутреннее `Item.axe` с tooltip ×5; диапазон Python 0..100 выровнен с C#;
- удалены мёртвые `effect_catalog.py`/`effect_archetypes.json` и их whole-pattern aliases, чтобы старый archetype router нельзя было случайно восстановить;
- rarity/buff/tile/wall IDs проверяются по live tModLoader loader counts вместо произвольных clamp-диапазонов;
- parent facts получили canonical use-style/ammo names и один точный registered damage-class token/full name;
- projectile defaults возвращены к Terraria semantics и затем переопределяются только authored fields;
- collision/NPC immunity стали явными и typed;
- projectile spawn переведён на `NewProjectileDirect`;
- owner vector sync ограничен meaningful-change + interval;
- добавлен корневой `lowery.md` и machine gate `audit_terraria_standardization.py`;
- agent metadata заставляет будущую модель читать standardization/alias policy и запускать gate.

## Не стандартизировалось намеренно

- runtime `entityId` не заменён глобальными ProjectileID;
- generated entity не превращается в отдельный ModProjectile class;
- movement/controller/event opcodes не сведены к `aiStyle`/weapon family;
- sand ammo и ID-static immunity не exposed из-за shared proxy type;
- Visual/VFX остаются per-instance, а не type-wide static content.

## Остаточные границы

- `Item.useAmmo` намеренно не exposed: честный vanilla weapon-ammo vertical slice должен провести `PickAmmo`-результат через authored entity selection, projectile type, скорость, урон, knockback и расход стека. Один флаг создал бы ложную совместимость.
- Sand ammo и ID-static projectile immunity не exposed из-за shared generated `Item.type`/`Projectile.type`.
- Modded `DamageClass` хранится как стабильный `ModName/ClassName`, но rarity/buff/tile/wall пока сериализуются numeric loaded-content IDs. Они строго проверяются в текущей сессии, однако для долговременной переносимости между разными load orders нужен отдельный full-name content-reference vertical slice.
- Dynamic `entityId`, component opcodes, event graph и per-instance assets остаются собственным bounded runtime: статические `ModProjectile`/`ProjectileID` здесь потребовали бы регистрации до загрузки мира и сократили бы функции.

## Проверка

- Python suite: **85 passed**;
- capability library: **100/100**, 52/52 vertical slices;
- Terraria standardization: **87/87**;
- Author prompt: **52/52** capabilities; обычный probe 70 729 / 96 000, rich generated-parent fixture 82 532 / 96 000 символов;
- mutation gate: **5/5**;
- non-archetypal fixtures: **8/8**;
- C# Debug и Release: **0 warnings, 0 errors** с `ParticleLibrary.dll`/`Luminance.dll` из внешнего dependency root;
- C# static contract, delivery/parity, generated docs/schema, config, Ruff, Pyright, hygiene и portable sandbox: passed.

Реальный tModLoader runtime self-test и host/client игровой smoke не выполнялись. Они остаются `notRun`, а не объявляются успехом; сборка DLL и deterministic/source gates их не заменяют.

## Проверка упакованного deliverable

Финальный Git ZIP должен собираться только из clean tracked tree, содержать `.git`, повторно распаковываться в отдельную директорию и проходить `git fsck`, проверку HEAD/manifest и ключевые Python/C# gates. Результат конкретной упаковки фиксируется во внешнем integration report вместе с SHA-256 архива, а не заранее в этом source-документе.
