#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

from infini_local.core.runtime_authoring.capability_registry import (  # noqa: E402
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    RUNTIME_WIRE_SCHEMA,
)
from infini_local.core.runtime_authoring.technical_lowering import (  # noqa: E402
    GLOBAL_TECHNICAL_LOWERINGS,
    technical_lowering_manifest,
)
from infini_local.qa.capability_library_audit import capability_library_audit  # noqa: E402


EXTERNAL_REFERENCES = {
    "item": "tML ModItem: SetDefaults/CanUseItem/UseItem/AltFunctionUse",
    "item_combat": "tML ModItem: UseItemHitbox/OnHitNPC",
    "item_utility": "tML ModItem + Player hooks",
    "item_tool": "tML Item pick/axe/hammer fields",
    "item_placeable": "tML Item.createTile/createWall/placeStyle",
    "equipment": "tML ModItem.UpdateAccessory/UpdateEquip/UpdateArmorSet",
    "entity_spawn": "ExampleMod projectile spawning + owner authority",
    "entity_combat": "tML ModProjectile damage/ownerHitCheck",
    "entity_lifecycle": "tML Projectile.timeLeft/Kill",
    "entity_collision": "tML ModProjectile.Colliding/OnTileCollide",
    "movement": "ExampleMod flail/yoyo/whip and project custom AI",
    "controller": "ExampleMod held projectile/Last Prism; Calamity holdout/beam",
    "event": "tML ModProjectile hooks + SendExtraAI/ReceiveExtraAI",
    "entity_utility": "tML Lighting.AddLight",
}


def esc(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def params_cell(cap: Any) -> str:
    rows: list[str] = []
    for name, spec in cap.params.items():
        shape = spec.kind
        if spec.enum:
            shape += "{" + ",".join(map(str, spec.enum)) + "}"
        elif spec.minimum is not None or spec.maximum is not None:
            shape += f"[{spec.minimum}..{spec.maximum}]"
        if spec.units:
            shape += f" {spec.units}"
        if spec.reference is not None:
            shape += " -> entity:" + ",".join(spec.reference.target_kinds)
        rows.append(f"`{name}`: {shape}")
    return "<br>".join(rows) if rows else "—"


def event_input_cell(cap: Any) -> str:
    values: list[str] = []
    if cap.allowed_events:
        values.append("events: " + ", ".join(f"`{x}`" for x in cap.allowed_events))
    if cap.emitted_events:
        values.append("emits: " + ", ".join(f"`{x}`" for x in cap.emitted_events))
    if cap.target_kinds == ("item_body",):
        values.append("through authored item binding/equipment state")
    return "<br>".join(values) if values else "entity lifecycle/input binding"


def inventory_markdown() -> str:
    audit = capability_library_audit()
    lines = [
        "# Низкоуровневый capability inventory InfiniCrafterLocal",
        "",
        "> Этот файл генерируется `python tools/generate_low_level_runtime_docs.py`. Не редактировать таблицы вручную.",
        "",
        f"Контракты: `{RUNTIME_PROGRAM_API_VERSION}` / `{RUNTIME_PROGRAM_SCHEMA}` / `{RUNTIME_WIRE_SCHEMA}`.",
        "",
        f"Inventory: **{len(CAPABILITY_REGISTRY)} capabilities**, **{len(ENTITY_KIND_REGISTRY)} entity kinds**, "
        f"**{len(INPUT_KIND_REGISTRY)} inputs**, **{len(BINDING_ACTION_REGISTRY)} binding actions**, "
        f"**{len(EVENT_KIND_REGISTRY)} events**. Machine audit: **{audit['score']}/{audit['scoreMax']}**, "
        f"errors={audit['errorCount']}, warnings={audit['warningCount']}.",
        "",
        "## Классификация",
        "",
        "- **expose** — Gameplay Author видит capability и сам выбирает её.",
        "- **internal** — техническая реализация одной точной capability, не отдельное дизайнерское решение.",
        "- **split** — механика извлечена из старого high-level macro и доступна отдельно.",
        "- **delete** — мёртвое/дублирующее поведение удалено.",
        "",
        "## Entity kinds",
        "",
        "| kind | назначение | spawn binding | позиция | обязательные компоненты | базовые события | visual role |",
        "|---|---|---:|---|---|---|---|",
    ]
    for row in ENTITY_KIND_REGISTRY.values():
        lines.append(
            f"| `{row.name}` | {esc(row.summary)} | {'да' if row.spawnable_by_binding else 'нет'} | "
            f"{esc(row.position_requirement)} | {esc(', '.join(row.required_components) or '—')} | "
            f"{esc(', '.join(row.base_events) or '—')} | `{row.visual_role}` |"
        )
    lines += [
        "",
        "## Inputs и binding actions",
        "",
        "| input | exclusive | actions | requires item capability any of | смысл |",
        "|---|---:|---|---|---|",
    ]
    for row in INPUT_KIND_REGISTRY.values():
        lines.append(f"| `{row.name}` | {'да' if row.exclusive else 'нет'} | {esc(', '.join(row.allowed_actions))} | {esc(', '.join(row.required_item_capabilities_any_of) or '—')} | {esc(row.summary)} |")
    lines += ["", "| action | target kinds | inputs | requires item capability any of | смысл |", "|---|---|---|---|---|"]
    for row in BINDING_ACTION_REGISTRY.values():
        lines.append(f"| `{row.name}` | {esc(', '.join(row.target_kinds))} | {esc(', '.join(row.allowed_inputs))} | {esc(', '.join(row.required_item_capabilities_any_of) or '—')} | {esc(row.summary)} |")
    lines += ["", "## Events", "", "| event | source kinds | producer capabilities | base projectile event | смысл |", "|---|---|---|---:|---|"]
    for row in EVENT_KIND_REGISTRY.values():
        lines.append(
            f"| `{row.name}` | {esc(', '.join(row.source_kinds))} | {esc(', '.join(row.producer_capabilities) or '—')} | "
            f"{'да' if row.always_available_on_projectile else 'нет'} | {esc(row.summary)} |"
        )
    lines += [
        "",
        "## Capability catalog",
        "",
        "| capability | назначение | параметры и единицы | target/entity kinds | events/inputs | C# owner | Python owner | authority | safety/multiplicity | prompt | status | external reference | решение |",
        "|---|---|---|---|---|---|---|---|---|---:|---|---|---|",
    ]
    for cap in CAPABILITY_REGISTRY.values():
        safety = f"{cap.multiplicity}; {cap.performance_budget}; slot={cap.component_slot}"
        if cap.exclusive_group:
            safety += f"; exclusive={cap.exclusive_group}"
        lines.append(
            "| " + " | ".join([
                f"`{esc(cap.name)}`",
                esc(cap.summary),
                esc(params_cell(cap)),
                esc(", ".join(cap.target_kinds)),
                esc(event_input_cell(cap)),
                f"`{esc(cap.csharp_owner)}`",
                f"`{esc(cap.compiler_owner)}`",
                f"`{esc(cap.network_authority)}`",
                esc(safety),
                "да" if cap.prompt_visible else "нет",
                esc(cap.implementation_status),
                esc(EXTERNAL_REFERENCES.get(cap.category, "InfiniCrafterLocal source")),
                esc(cap.decision),
            ]) + " |"
        )
    lines += [
        "",
        "## Что стало internal/delete",
        "",
        "Старые whole-weapon macros, family route tables, `AttackSpec`, `runtimeFamily`, hidden repair API и cache migration удалены. "
        "Внутренними остались только: numeric opcode dispatch, DTO field projection, entity-kind → visual-role и технические tModLoader adapters. "
        "Они не выбирают movement, attachment, delivery, input, lifecycle или topology.",
        "",
        "## Полнота",
        "",
        "Каждая public capability имеет Python compiler callable, конкретные C# method symbols, exact final-wire paths и автоматически исполняемый vertical witness. "
        "Структурная полнота registry не означает поддержку всего Terraria API: каталог намеренно конечный и включает только реализованные bounded executors.",
        "",
    ]
    return "\n".join(lines)


def audit_markdown() -> str:
    audit = capability_library_audit()
    m = audit["metrics"]
    lines = [
        "# Аудит машиночитаемости библиотеки компонентов",
        "",
        "> Генерируется `python tools/generate_low_level_runtime_docs.py` из live registry и audit-кода.",
        "",
        f"## Вердикт: {audit['score']}/{audit['scoreMax']}",
        "",
        "Это **структурная оценка контракта**, а не заявление, что реализован весь Terraria runtime.",
        "",
        "| критерий | вес | результат |",
        "|---|---:|---:|",
    ]
    weights = {
        "registryIdentity": 10, "typedParameters": 15, "compositionMetadata": 15, "exactDelivery": 15,
        "runtimeOwnership": 15, "rangeParity": 10, "projectionParity": 10, "verticalSlices": 10,
    }
    for key, weight in weights.items():
        lines.append(f"| `{key}` | {weight} | {'PASS' if audit['criteria'][key] else 'FAIL'} |")
    lines += [
        "",
        "## Измеренные свойства",
        "",
        f"- capabilities: **{m['capabilities']}**; parameters: **{m['parameters']}**; numeric: **{m['numericParameters']}/{m['boundedNumericParameters']} bounded**;",
        f"- entity kinds: **{m['entityKinds']}**; inputs: **{m['inputs']}**; actions: **{m['bindingActions']}**; events: **{m['events']}**;",
        f"- typed entity references: **{m['typedEntityReferences']}**; requirements: **{m['requirements']}**; binding dependency edges: **{m['bindingDependencyEdges']}**;",
        f"- exact wire paths: **{m['exactWirePaths']}**; global technical lowerer outputs: **{m['globalTechnicalLowererOutputs']}**;",
        f"- Python↔C# range parity rows: **{m['rangeParityRows']}**; vertical witnesses: **{m['verticalSliceCount']}**;",
        f"- errors: **{audit['errorCount']}**; warnings: **{audit['warningCount']}**.",
        "",
        "## Почему библиотека действительно машиночитаема",
        "",
        "1. `CAPABILITY_REGISTRY` — единый явный immutable registry; schema, prompt cards, manifest и compiler dispatch выводятся из него.",
        "2. Каждый parameter объявляет JSON type, semantic type, description, enum/range/units; entity references имеют namespace и допустимые target kinds.",
        "3. Entity kinds, inputs, binding actions и events имеют отдельные registries, а validator использует их, а не дублирующий набор `if`-маршрутов.",
        "4. Capability указывает component slot, exclusivity, position ownership, requirements, emitted/accepted events и authority.",
        "5. Delivery перечисляет точные wire-path; wildcard-output запрещён audit-gate.",
        "6. Owner — не просто имя файла: audit импортирует Python callable и ищет конкретные C# method symbols.",
        "7. Для каждой capability исполняется author→validate→compile→strict-wire witness; неизвестные поля/refs/opcodes fail closed.",
        "",
        "## Честные ограничения",
        "",
        "- На entity допускается один movement slot и один controller slot. Это намеренная bounded-композиция, не arbitrary ECS/VM.",
        "- Cross-entity references доступны только там, где runtime реально их исполняет (`target_and_fire`, event child spawn).",
        "- Authority metadata проверяется статическими контрактами, но реальный host/client smoke требует tModLoader runtime.",
        "- Статический vertical witness доказывает доставку Python→C# contract surface, но не заменяет успешный C# build и игровой smoke.",
        "- Prompt catalog крупный, но self-contained: около 71k символов на обычных parents и до 83k на rich generated-parent fixture при hard limit 96k; retrieval/tool loop не используется.",
        f"- Каталог покрывает реализованные {len(CAPABILITY_REGISTRY)} primitive/controller/effect, а не всю потенциальную семантику Terraria/mod ecosystem.",
        "",
        "## Практическая оценка",
        "",
        "- **Структура и проверяемость: 10/10** — все объявленные проекции замкнуты и проверяются машиной.",
        "- **Однозначность для LLM: 9/10** — API не содержит weapon families и semantic defaults; некоторые item-body calls длинные из-за широких typed DTO.",
        "- **Выразительность текущего runtime: 8/10** — странные multi-entity композиции поддерживаются, но controller layering и произвольная world interaction намеренно ограничены.",
        "- **Доказанность в игре: неполная** до C# build/tModLoader singleplayer/host-client smoke.",
        "",
    ]
    if audit["issues"]:
        lines += ["## Issues", "", "```json", json.dumps(audit["issues"], ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def lowering_markdown() -> str:
    manifest = technical_lowering_manifest()
    lines = [
        "# TECHNICAL LOWERING AUDIT",
        "",
        f"Schema: `{manifest['schema']}`.",
        "",
        "Lowering разрешён только как семантически без потерь технический перевод. Ни один lowerer не выбирает entity kind, movement, attachment, delivery, input, lifecycle, targeting или visual topology.",
        "",
        "## Global lowerers",
        "",
        "| id | inputs | exact outputs | equivalence | preserves |",
        "|---|---|---:|---|---|",
    ]
    for row in GLOBAL_TECHNICAL_LOWERINGS:
        lines.append(
            f"| `{row['id']}` | {esc(', '.join(row['inputs']))} | {len(row['outputs'])} | {esc(row['equivalence'])} | {esc(', '.join(row['preserves']))} |"
        )
    lines += [
        "",
        "`item_fields_to_tml_projection` имеет конечный автоматически выведенный список output-path; broad `gameplay.*`/`accessory.*`/`armor.*` запрещены.",
        "",
        "## Capability-level proof",
        "",
        "Каждая compiler receipt содержит `callId`, `fn`, `finalPath`. `audit_compiler_receipts` принимает запись только когда `finalPath` объявлен в exact outputs соответствующей capability. "
        "Mutation test добавляет недекларированный output и обязан получить отказ.",
        "",
        "## Решение по старому lowering",
        "",
        "Удалены family/root reducers и whole-weapon route tables. Извлечённые movement/controller/event helpers вызываются только по явно authored capability name. "
        "Никакой путь `family → held/thrust/straight/retract` не существует.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = {
        ROOT / "docs" / "LOW_LEVEL_CAPABILITY_INVENTORY_RU.md": inventory_markdown(),
        ROOT / "docs" / "CAPABILITY_LIBRARY_MACHINE_READABILITY_AUDIT_RU.md": audit_markdown(),
        ROOT / "TECHNICAL_LOWERING_AUDIT_RU.md": lowering_markdown(),
    }
    stale: list[str] = []
    for path, text in outputs.items():
        normalized = text.rstrip() + "\n"
        if args.check:
            if not path.is_file() or path.read_text("utf-8") != normalized:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(normalized, encoding="utf-8")
    if stale:
        print(json.dumps({"ok": False, "stale": stale}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "files": [str(p.relative_to(ROOT)) for p in outputs]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
