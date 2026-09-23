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
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    EVENT_ACTION_OPCODE,
    MOVEMENT_OPCODE,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    RUNTIME_WIRE_SCHEMA,
    VISUAL_ROLE_BY_ENTITY_KIND,
)
from infini_local.core.runtime_authoring.program_schema import (  # noqa: E402
    PRIMARY_ENTITY_AUTHOR_PATH,
    PRIMARY_ENTITY_SELECTION_FIELD,
)
from infini_local.core.runtime_authoring.technical_lowering import (  # noqa: E402
    EXACT_REPETITION_COMPRESSION_POLICY,
    GLOBAL_TECHNICAL_LOWERINGS,
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
        "# Low-level authoring и Lowery — канонический контракт",
        "",
        "> Этот файл генерируется `python tools/generate_lowery.py`. Не редактировать вручную. "
        "Source of truth — перечисленные ниже Python owners; inventory/audit docs являются projections.",
        "",
        f"Schemas: `{RUNTIME_PROGRAM_API_VERSION}` / `{RUNTIME_PROGRAM_SCHEMA}` / `{RUNTIME_WIRE_SCHEMA}`.",
        "",
        "## READ THIS FIRST — замороженная граница",
        "",
        "1. Gameplay Author сам выбирает механику, entities, bindings, calls, params, events, references, metadata и финальный realization/selfEvaluation. "
        "Ни имя, tooltip, category, family, parent tag или capability prose не разрешают коду дописать дизайн.",
        "2. Deterministic Python имеет право только проверить exact authored graph, ограничить его, отфильтровать exact Repair scope и выполнить lossless technical lowering.",
        "3. Lowery не является вторым Author. Он не выбирает movement, attachment, delivery, lifecycle, input, target, entity kind, event, damage, visual topology или fallback mechanic.",
        "4. Authoring compression допустима только для буквально одинакового low-level значения, повторённого минимум "
        f"**{EXACT_REPETITION_COMPRESSION_POLICY['minimumRepeatedPlacements']}** раз. Она обязана сохранять literal equality и не может добавлять design choice.",
        "5. Обязательная wire projection из уже authored identity (например, exact entity kind → renderer role или exact primary id/target equality → binding role) не считается authoring compression: она сериализует одно решение, а не заменяет несколько решений модели.",
        "6. Repair получает конечные registry-derived alternatives и exact permissions. Модель выбирает и явно пишет полный вариант; код ничего не вставляет и после merge повторно запускает canonical validator.",
        "",
        "## Единственные owners",
        "",
    ]
    lines += table(("что меняется", "единственный owner", "derived consumers"), [
        ("Author JSON shape, primaryEntity fields, repair patch shape", "runtime_authoring/program_schema.py", "prompt schema, validator, Repair filter"),
        ("capabilities, entity/input/action/event facts and event producers", "runtime_authoring/capability_registry.py", "Author catalog, validator, Repair alternatives, docs"),
        ("lossless projections, exact outputs, receipts, repetition policy", "runtime_authoring/technical_lowering.py", "compiler, audits, this document"),
        ("Author/Repair model-facing prose", "pipelines/author_item_contract.py", "Author and Repair system prompts"),
        ("validation truth", "runtime_authoring/validator.py", "Repair requirements and final acceptance"),
        ("Repair permissions/filter", "runtime_authoring/repair_scope.py", "conditional Repair dossier and merge report"),
        ("wire materialization", "runtime_authoring/compiler.py", "RuntimeProgram wire + finalWireReceipts"),
        ("runtime execution", "ModSources/.../RuntimeProgramSpec.cs + executors", "tModLoader behavior"),
    ])
    lines += [
        "",
        "Правило меняется у owner-а. Нельзя создавать facade, shadow constant, prose-router или второй event/primary contract рядом. "
        "Generated projections обновляются командами в разделе «Проверка».",
        "",
        "## Authoring → wire boundary",
        "",
        f"- `{PRIMARY_ENTITY_AUTHOR_PATH}` — ровно один model-authored существующий entity id.",
        "- Author bindings/calls не содержат `role`. Compiler сравнивает exact `binding.target` с exact `primaryEntityId`: equality → wire `primary`, иначе wire `secondary`.",
        "- `primaryOwner` выводится только из exact kind выбранной entity через `ENTITY_KIND_REGISTRY.projectile`; неизвестный kind fail-closed валидатором, а не становится projectile default.",
        "- Каждая такая projection имеет manifest row и compiler receipt с authored paths, exact final path и value.",
        f"- Repair может менять primary identity только через `{PRIMARY_ENTITY_SELECTION_FIELD}` и только выбирая один id из transaction candidates.",
        "",
        "### Event producer contract",
        "",
        "`EventKindSpec` владеет producer calls, producer binding inputs и exact producer params; `EntityKindSpec.base_events` владеет producer-free availability для конкретного kind. "
        "Validator и Repair вызывают одну generic registry projection. Event-name `if/elif` вне registry запрещён.",
        "",
    ]
    event_rows: list[tuple[object, ...]] = []
    for event in EVENT_KIND_REGISTRY.values():
        base_kinds = [kind.name for kind in ENTITY_KIND_REGISTRY.values() if event.name in kind.base_events]
        exact = "; ".join(
            f"{capability}({','.join(f'{name}={value!r}' for name, value in params.items())})"
            for capability, params in event.producer_exact_params.items()
        ) or "—"
        event_rows.append((
            event.name,
            ", ".join(event.producer_capabilities) or "—",
            ", ".join(event.producer_binding_inputs) or "—",
            ", ".join(base_kinds) or "—",
            exact,
        ))
    lines += table(("event", "producer calls", "producer binding inputs", "producer-free kinds", "exact params"), event_rows)
    lines += [
        "",
        "## Lossless lowering manifest",
        "",
        f"Exact-repetition policy: `{EXACT_REPETITION_COMPRESSION_POLICY}`.",
        "",
    ]
    lines += table(("lowerer", "authored inputs", "wire outputs", "adds design"), [
        (
            row["id"],
            ", ".join(row["inputs"]),
            ", ".join(row["outputs"]),
            str(row["addsDesignChoice"]).lower(),
        )
        for row in GLOBAL_TECHNICAL_LOWERINGS
    ])
    lines += [
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
        "### Primary entity → binding role",
        "",
        "`runtimeProgram.primaryEntityId` выбирается Author как точный существующий `entityId`. Lowery сравнивает его только с точным `binding.target`: равный target materializes wire `role=primary`, остальные — `role=secondary`. Это one-to-one техническая проекция authored identity; она не выбирает entity, input, action, attachment, delivery или gameplay importance.",
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
        "## Проверка",
        "",
        "```bash",
        "python tools/generate_lowery.py --check",
        "python tools/generate_low_level_runtime_docs.py --check",
        "python tools/run_pyright.py --pythonpath /path/to/venv/bin/python",
        "python -m pytest -q LocalGenerator/tests/test_runtime_authoring_change_locality.py LocalGenerator/tests/test_low_level_runtime_contract_v5.py LocalGenerator/tests/test_low_level_three_stage_pipeline.py",
        "```",
        "",
        "Change-locality acceptance: изменить один canonical owner, обновить generated projections, пройти affected replay; не редактировать параллельные prose contracts и не запускать Live как замену локальному доказательству.",
        "",
        "## Запрет на добавление alias",
        "",
        "Новый gameplay alias допустим только если два входа обозначают одно и то же точное действие и один из них не показывается Author. Любое новое имя должно быть либо единственным canonical token, либо внутренней migration/config нормализацией вне gameplay. Добавление alias в Author schema требует изменить canonical vocabulary owner, перегенерировать этот файл и пройти `tools/audit_terraria_standardization.py`.",
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
