#!/usr/bin/env python3
from __future__ import annotations

"""Generate the root lowery.md technical-mapping and alias inventory."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

from infini_local.core.runtime_authoring.capability_registry import (  # noqa: E402
    CONTROLLER_OPCODE,
    EVENT_ACTION_OPCODE,
    MOVEMENT_OPCODE,
    VISUAL_ROLE_BY_ENTITY_KIND,
)
from infini_local.core.runtime_authoring.terraria_vocabulary import (  # noqa: E402
    AMMO_CATEGORY_TMODLOADER_NAMES,
    DAMAGE_CLASS_TMODLOADER_NAMES,
    ITEM_USE_STYLE_TMODLOADER_NAMES,
)

OUTPUT = ROOT / "lowery.md"


def table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out.extend("| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |" for row in rows)
    return out


def render() -> str:
    lines: list[str] = [
        "# lowery.md — canonical lowering и aliases",
        "",
        "Версия проекта: **0.4.241**.",
        "",
        "## Неподвижное правило",
        "",
        "> Lowering разрешён только как семантически без потерь технический перевод. Он может скрывать неудобство API, но не сжимать пространство дизайна. По имени, категории, family, tooltip или prose нельзя выбирать movement, attachment, delivery, entity kind, input binding, lifecycle, targeting, hitbox topology или root executor.",
        "",
        "Gameplay Author-visible semantic aliases: **нет**. У каждой механической операции и каждого enum-значения один канонический токен. Старые `passive`, `drink`, `eat`, plural ammo spellings и `rogue` не принимаются. Старый effect/weapon catalog с aliases `spear → spear_thrust`, `beam → laser_beam`, `slash → slash_holdout` физически удалён и не является reference. `throwing` сохранён только как точное каноническое отображение stable `DamageClass.Throwing`, а не как алиас. `damageClass` имеет одну identity-форму: built-in token либо точный tModLoader `ModName/ClassName`, скопированный из loaded parent facts; псевдотокены `none`/`modded` и параллельное `damageClassFullName` запрещены.",
        "",
        "## Канонические технические отображения — это не semantic aliases",
        "",
        "Эти таблицы являются one-to-one переводом JSON-токена в точное поле/константу stable tModLoader. Они не добавляют решений за Author.",
        "",
        "### DamageClass",
        "",
    ]
    lines += table(("runtime token", "tModLoader"), [(k, v) for k, v in DAMAGE_CLASS_TMODLOADER_NAMES.items()])
    lines += ["", "### ItemUseStyleID", ""]
    lines += table(("runtime token", "tModLoader"), [(k, v) for k, v in ITEM_USE_STYLE_TMODLOADER_NAMES.items()])
    lines += ["", "### Vanilla ammo item", ""]
    lines += table(("runtime token", "tModLoader field"), [(k, v) for k, v in AMMO_CATEGORY_TMODLOADER_NAMES.items()])
    lines += [
        "",
        "`configure_vanilla_ammo_item` отдельно принимает `projectileId` и `shootSpeedPxPerTick`, напрямую записывая `Item.shoot` и ammo-вклад `Item.shootSpeed`. Категория не выбирает projectile автоматически. `Item.ammo` означает «этот предмет является боеприпасом»; `Item.useAmmo` означал бы «это оружие расходует боеприпас» и данным adapter-ом не выставляется. Нельзя добавить `useAmmo` одним полем: стандартный `PickAmmo` также меняет projectile type, скорость, урон и knockback, поэтому нужен отдельный полный vertical slice.",
        "",
        "### Loaded content IDs",
        "",
        "`rarity`, `buffId`, `tileId` и `wallId` не имеют aliases и не угадываются по имени. Сейчас это точные IDs текущего loaded content set, прошедшие `RarityLoader`/`BuffLoader`/`TileLoader`/`WallLoader`; их можно только копировать из parent facts. Modded `DamageClass` является исключением: он хранится устойчивой exact content identity `ModName/ClassName` и разрешается через `ModContent.TryFind`.",
        "",
        "### Поля с неочевидными Terraria units",
        "",
        "- `valueCopper` напрямую пишет `Item.value`; это base/shop value в copper, а не обещание конкретной суммы resale игроком.",
        "- `axePower` напрямую пишет внутренний `Item.axe`; Terraria показывает в tooltip `Item.axe × 5`. Допустимый Author range 0..100 совпадает с C# boundary.",
        "",
        "### Runtime opcodes",
        "",
        "Movement:",
        "",
    ]
    lines += table(("capability", "opcode"), [(k, v) for k, v in MOVEMENT_OPCODE.items()])
    lines += ["", "Controllers:", ""]
    lines += table(("capability", "opcode"), [(k, v) for k, v in CONTROLLER_OPCODE.items()])
    lines += ["", "Event actions:", ""]
    lines += table(("capability", "opcode"), [(k, v) for k, v in EVENT_ACTION_OPCODE.items()])
    lines += ["", "### Entity kind → visual role", ""]
    lines += table(("entity kind", "visual role"), [(k, v) for k, v in VISUAL_ROLE_BY_ENTITY_KIND.items()])
    lines += [
        "",
        "Visual role — renderer handoff, а не gameplay-классификатор.",
        "",
        "## Удалённые gameplay aliases и archetype routers",
        "",
        "Физически удалены `effect_catalog.py` и `effect_archetypes.json`, включая `basic/projectile/bolt → thrown_simple`, `spear/lance/pike → spear_thrust`, `slash/held/swing → slash_holdout`, `beam/laser/ray → laser_beam` и другие whole-pattern aliases. Они не являются compatibility API и не должны восстанавливаться.",
        "",
        "## Сохранившиеся aliases вне gameplay",
        "",
        "Эти aliases не попадают в runtimeProgram и не могут выбирать механику предмета.",
        "",
        "### LLM provider config",
        "",
    ]
    lines += table(("accepted config spelling", "canonical provider"), [
        ("openrouter, or", "openrouter"),
        ("openai, openai_compat, api, remote", "openai_compat"),
        ("local, lmstudio, lm_studio, ollama, empty", "local"),
    ])
    lines += ["", "### Image backend config", ""]
    lines += table(("accepted config spelling", "canonical image backend"), [
        ("stablediffusioncpp, stable-diffusion.cpp, stable_diffusion_cpp", "sdcpp"),
        ("api_image, openai_image, openai_images, openai_compat_image", "image_api"),
        ("none, disabled", "off"),
    ])
    lines += [
        "",
        "Это только config migration для выбора уже существующего image backend; visual topology и gameplay от spelling не зависят.",
        "",
        "### Result identity/UI category normalization",
        "",
    ]
    lines += table(("incoming UI/category spelling", "canonical UI category"), [
        ("placeable", "furniture"),
        ("station, crafting_station", "placeable_station"),
        ("device", "technology"),
        ("trinket, acc", "accessory"),
        ("consumable_item, stack_consumable, thrown_stack", "consumable"),
    ])
    lines += [
        "",
        "Эта нормализация используется только для identity/UI/parent summary. Она не выбирает runtime capability, movement или delivery.",
        "",
        "### VFX fallback palette",
        "",
    ]
    lines += table(("visual motif spellings", "fallback color family"), [
        ("fire, heat", "fire/orange"),
        ("ice, water", "ice/cyan"),
        ("poison, nature", "poison/green"),
        ("shadow, void", "shadow/purple"),
        ("electric, lightning", "electric/yellow"),
        ("blood", "blood/crimson"),
    ])
    lines += [
        "",
        "Это только цветовой fallback VFX; gameplay и damage type от motif не зависят.",
        "",
        "## Где намеренно остаётся наш runtime",
        "",
        "1. **`GeneratedItem` и `GeneratedProjectile` — proxy-типы.** tModLoader регистрирует `ModItem`/`ModProjectile` и глобальные type IDs во время загрузки мода, а предметы UnlimitedCraft создаются уже во время игры. Поэтому каждый authored entity получает локальный `entityId`, а не новый глобальный `ProjectileID`.",
        "2. **Per-entity capabilities и opcodes.** Movement/controller/event composition динамична и хранится в typed runtimeProgram. Она не переводится в `aiStyle` или weapon family, если это потеряло бы authored комбинацию.",
        "3. **Per-instance visuals/assets.** Один proxy type не может иметь разные type-wide texture/static sets; PNG/VFX выбираются по generated item ID + entity ID.",
        "4. **Type-wide Terraria sets не подделываются.** `ItemID.Sets`, `ProjectileID.Sets` и ID-static NPC immunity общие для proxy type. Их нельзя безопасно менять на один generated item/entity. Поэтому sand ammo не выставляется: полная sandgun-семантика требует type-wide `ItemID.Sets.SandgunAmmoProjectileData`.",
        "5. **Local NPC immunity.** Поддерживаются явные режимы `owner` и `local`. ID-static immunity не exposed, потому что все generated projectiles имеют один global type и разделили бы cooldown между несвязанными предметами.",
        "6. **Custom hydration/network identity.** `entityId` и generated item ID синхронизируют параметры proxy projectile. `Projectile.identity/whoAmI` остаются Terraria-идентификаторами конкретного экземпляра, но не заменяют authored subtype ID.",
        "7. **Сложные held/beam/field controllers.** Используются обычные ModProjectile hooks и Terraria collision/network fields, но orchestration остаётся bounded custom runtime, потому что она составляется LLM после загрузки контента.",
        "",
        "## Запрет на добавление alias",
        "",
        "Новый gameplay alias допустим только если два входа обозначают одно и то же точное действие и один из них не показывается Author. Любое новое имя должно быть либо единственным canonical token, либо внутренней migration/config нормализацией вне gameplay. Добавление alias в Author schema требует обновить этот файл и пройти `tools/audit_terraria_standardization.py`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            print("[FAIL] stale lowery.md")
            return 1
        print("[OK] lowery.md matches canonical runtime mappings")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
