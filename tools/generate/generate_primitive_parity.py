#!/usr/bin/env python3
"""Render implementation-facing primitive parity from the canonical registry."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "LocalGenerator"))
from infini_local.core.runtime_authoring.capability_registry import (  # noqa: E402
    CAPABILITY_REGISTRY, EQUIPMENT_DAMAGE_CLASSES, equipment_damage_wire_path,
)
from infini_local.qa.primitive_loss_audit import (  # noqa: E402
    equipment_surface_audit, event_surface_audit,
    runtime_component_surface_audit, item_gameplay_surface_audit,
    structural_surface_audit,
)

OUTPUT = ROOT / "docs/reference/generated/PRIMITIVE_PARITY_RU.md"


def _cell(value: object) -> str:
    return (str(value).replace("\r\n", "\n").replace("\r", "\n")
            .replace("|", r"\|").replace("\n", "<br>"))


def render() -> str:
    sections = ["# Parity примитивов Author ↔ Terraria/tModLoader",
        "", "> Generated: [`tools/generate/generate_primitive_parity.py`](../../../tools/generate/generate_primitive_parity.py). Не редактировать вручную; [refresh/check](#refresh).",
        "> Sources: [capability_registry.py](../../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py) — имена, единицы, диапазоны, wire и фазы; "
        "[primitive_loss_audit.py](../../../LocalGenerator/infini_local/qa/primitive_loss_audit.py) — C# executable-поля из AST. "
        "[Lowery](LOWERY_RU.md) — boundary/owners; [inventory](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) — полный каталог.",
        "", "**Навигация:** [источник](#history) · [machine audit](#audit) · [equipment](#equipment) · "
        "[events/runtime](#events) · [граница расширения](#unsupported) · [extraUpdates units](#units) · "
        "[границы проверки](#limits) · [обновление](#refresh).",
        "", '<a id="history"></a>',
        "", "## Текущий источник истины",
        "", "Один registry выдаёт Author JSON schema, компактные карточки, validator-параметры, exact wire paths, технические receipts, C# safety bounds и таблицы ниже. DTO — цель проекции, не второе описание механики. Semantic aliases/weapon-family routers и compatibility importer не входят в текущий контракт.",
        "", '<a id="audit"></a>',
        "", "## Результат machine loss audit",
        "", "Для каждой поверхности ниже C# DTO/исполняемые поля классифицированы. Исключения с причинами поддерживаются в `primitive_loss_audit.py`, не в LLM prompt.",
        ""]
    for label, fn in (("equipment", equipment_surface_audit), ("events", event_surface_audit),
                      ("runtime components", runtime_component_surface_audit),
                      ("item gameplay", item_gameplay_surface_audit),
                      ("structural runtime/visual", structural_surface_audit)):
        result = fn()
        if not result["ok"]:
            raise RuntimeError(f"primitive-loss audit failed: {label}: {result}")
        sections.append(f"- `{label}`: **PASS**.")
    sections.extend(["", '<a id="equipment"></a>', "", "## Equipment — значения, phase и authority", "",
        "`additive_percent` — авторский процент прибавки к additive компоненте StatModifier (15 → +0.15), не итоговый множитель урона. `percentage_points` — сдвиг шанса в п.п.; `probability_percent` — вероятность/100. `defense_points`, `life_points` и `slots` не масштабируются. Author-скорости в блоках/с переводятся в native pixels/world tick через ×16/60, регенерация HP/s — в lifeRegen через ×2. Отрицательные значения разрешены только там, где указан отрицательный минимум. Ноль/false/пустая строка — нейтральны, если не оговорено иначе. Item.defense проектируется в `ApplyToItem`: Terraria сама применяет защиту, equip-hook не удваивает её.",
        "", "Author schema ограничивает значения всех примитивов; C# Normalize применяет только объявленные **runtime safety clamps** из `runtime_minimum`/`runtime_maximum` registry и `GeneratedEquipmentBounds.g.cs`. В таблицах они обозначены `runtime clamp`; отсутствие пометки не разрешает подставлять новые ограничения. Это не разрешение Author выбирать значения вне своей схемы и не повод удалять действующие caps как устаревшие metadata.", ""])
    for cap_name in ("accessory", "armor"):
        cap = CAPABILITY_REGISTRY[cap_name]
        sections += [f"### `{cap_name}`", "", "| Author | Действие / engine semantics | Единица | Neutral | Author range | Wire DTO | Фаза |", "|---|---|---|---|---|---|---|"]
        for name, spec in cap.params.items():
            wire = spec.wire_name or name
            conversion = ((f" ×{spec.wire_multiplier}" if spec.wire_multiplier != 1 else "")
                          + (f" /{spec.wire_divisor}" if spec.wire_divisor != 1 else ""))
            wire_expression = f"{cap_name.removeprefix('configure_')}.{wire}"
            if conversion:
                wire_expression += f" = Author{conversion}"
            value_range = (f"{spec.minimum}…{spec.maximum}" if spec.minimum is not None else
                           "/".join(map(str, spec.enum)) if spec.enum else
                           spec.pattern if spec.pattern else spec.kind)
            if spec.runtime_minimum is not None or spec.runtime_maximum is not None:
                value_range += f"<br>runtime clamp: {spec.runtime_minimum}…{spec.runtime_maximum}"
            row = [name, spec.description, spec.units or spec.semantic_type or spec.kind,
                   spec.neutral, value_range, wire_expression,
                   spec.execution_phase or "C# normalized item projection"]
            sections.append("| " + " | ".join(_cell(x) for x in row) + " |")
        sections += ["", f"Authority: `{cap.network_authority}`; техническая фаза/сетевая роль выбираются runtime, не LLM.", ""]
    modifier = CAPABILITY_REGISTRY["equipment_damage_bonus"]
    bonus = modifier.params["bonusPercent"]
    sections += ["### `equipment_damage_bonus` — параметризованная операция", "",
        "Один call выбирает `phase`, `damageClass` и `bonusPercent`. Shared type `equipment_damage_class` содержит ровно классы, для которых текущий C# вызывает `GetDamage(DamageClass)`: "
        + ", ".join(f"`{name}`" for name in EQUIPMENT_DAMAGE_CLASSES)
        + ". Другие item/projectile DamageClass здесь не исполняются и отклоняются; crit, attack speed, knockback и armor penetration пока исполняются только для `generic` и не маскируются выдуманной поддержкой других классов.",
        f"`bonusPercent`: `{bonus.minimum}…{bonus.maximum}` {bonus.units}, neutral `{bonus.neutral}`; wire = percent / {bonus.wire_divisor}. Указанные в `phase` `equipped` и `matching_armor_set` — выбор модели. Последняя фаза требует `armor(slot=head, setKey=<непустой exact ключ>)`; C# применяет её только при совпадении head/body/legs. Повтор пары `(phase, damageClass)` отклоняется, а не неявно складывается.",
        "", "| Phase | DamageClass | Wire DTO | tModLoader hook |", "|---|---|---|---|"]
    for armor, phase in ((False, "equipped"), (True, "equipped"), (True, "matching_armor_set")):
        for damage_class in EQUIPMENT_DAMAGE_CLASSES:
            path = equipment_damage_wire_path(phase, damage_class, armor=armor)
            hook = "UpdateAccessory" if not armor else "UpdateEquip" if phase == "equipped" else "UpdateArmorSet"
            sections.append(f"| {phase} ({'armor' if armor else 'accessory'}) | {damage_class} | `{path}` | `{hook}` |")
    sections += ["", "C# DTO и runtime safety bounds проецируются из текущих typed primitives; Author выбирает phase/damageClass в одной параметризованной capability. Runtime wire загружается без повторной компиляции Author.", ""]
    sections += ['<a id="events"></a>', "", "## Event/runtime и намеренно скрытое", "",
        "- Все `RuntimeEventActionSpec` поля, включая `DelayTicks`, сверяются с exact wire paths. Каждый event action допускает `delayTicks=0…600`; C# scheduler проверяет spawn budget/authority и переносит действие, не создавая новый дизайн.",
        "- `move_owner_on_event` телепортирует только к **сохранённой позиции события** (ограничение `rangeTiles`, проверка safe tile, общий cooldown с `blink_on_use`). Wire `Mode=blink_to_event_position` — фиксированный технический discriminator; старое `blink_to_entity` исполнялось той же веткой и больше не предлагается модели.",
        "- `oreSenseEnabled` — булево включение Terraria `Player.findTreasure`; `GeneratedBuffSpec.OreSenseRadiusTiles` хранит только 0/1, **не радиус**. В prompt нет ложных тайлов.",
        "- `target_and_fire` использует только typed `Targeting.ShotEntityId`/`IntervalTicks`/`SameTargetBias`; typed interval обязателен и положителен, executor сохраняет floor 6 world ticks и перевод при extraUpdates. Старые `RuntimeParamsSpec.ShotEntity`/`IntervalTicks`/`SameTargetBias` удалены; старые Params-поля в saved wire отвергаются, fallback cadence отсутствует.",
        "- `refresh_held_effect` явно выбирает `runtimeProgram.heldEffectGroupId`: только named generated-buff group. `GeneratedItem.HoldItem -> RefreshHeldEffectGroup -> ApplyGeneratedUtilityBuff` пытается refresh раз за world tick для exact held item; duration управляет lingering после release, exhaustion остаётся отдельной политикой. Healing, mobility и native buffs не выводятся из held light/mining-speed или prose.",
        "- Single-slot `GameplaySpec.BuffCode`/`BuffTime` удалены; старые gameplay-поля отвергаются. Default и named effect groups используют явный многобафовый `ExtraBuffs[]` с `BuffEntrySpec.BuffCode`/`BuffTime`; `GeneratedItem.ApplyItemEffects` вызывает native `Player.AddBuff` для каждой записи. `ApplyUseEffectFields` очищает `Item.buffType`/`buffTime` до0, не восстанавливает single slot.",
        "- `Enabled`, opcodes, роли, `UseStyle` и DTO IDs выводятся из явно авторских calls. Display/advisory prose не выбирает механические поля.",
        "", '<a id="unsupported"></a>', "", "## Граница расширения executable surface", "",
        "Текущий AST audit проверяет текущих consumers, не историческую полноту или native/game acceptance. Новая поддержка требует explicit bounded primitive и полного vertical slice без whole-weapon macros. Исторический snapshot отдельно: [архивный аудит](../../archive/HISTORICAL_RUNTIME_AUDIT_2026_10_RU.md), не текущий capability catalog.",
        "", '<a id="units"></a>', "", "## Единицы при extraUpdates > 0", "",
        "Author явно задаёт `projectile_collision.updatesPerTick=N` — число AI/physics-обновлений снаряда за мировой тик; wire хранит `extraUpdates=N−1`. Игровые расстояния Author задаёт в блоках, длительности — в секундах, скорости — в блоках/с, физические ускорения — в блоках/с² и объявленные угловые скорости — в радианах/с. Registry-lowering учитывает N именно затронутой сущности: дочерний снаряд использует собственный clock. Длительности округляются до ближайшего world tick, половина тика вверх; C# сохраняет прежний перевод через `AuthoredTicksToProjectileUpdates`. Dimensionless retention/lerp/multiplier и технические update-счётчики сохраняют явно объявленный per-update смысл. Engine wire и сохранённые рецепты не пересчитываются; параметры не обещают конечную скорость нелинейного движения.",
        "", '<a id="limits"></a>', "", "## Границы проверки", "",
        "AST audit анализирует нынешние DTO и названные C# executor seams. Удалённое вместе с consumer поле исчезает из этого множества: текущий PASS не доказывает исторический паритет. Audit не заменяет полноценный compiler/semantic analysis всех tML API. Headless C# тесты покрывают projection/equip и cooldown, но не Terraria world loop, GPU или multiplayer. Live20 проверяет Author pipeline на внешней модели, а не выполнение в игре.",
        "", '<a id="refresh"></a>', "", "## Обновление и проверка", "",
        "Из корня репозитория, с Python окружения проекта. Без `--check` generator записывает **только этот Markdown**, не JSON, DTO или bounds:", "",
        "```bash",
        "PYTHONPATH=LocalGenerator python tools/generate/generate_primitive_parity.py",
        "PYTHONPATH=LocalGenerator python tools/generate/generate_primitive_parity.py --check",
        "```", "",
        "Generation/check исполняют все пять surface audits выше и завершаются ошибкой при loss; freshness доказывает совпадение projection с owners, а не игровой smoke. "
        "Affected regressions: [test_registry_vertical_contract.py](../../../LocalGenerator/tests/test_registry_vertical_contract.py), "
        "[test_registry_author_packet.py](../../../LocalGenerator/tests/test_registry_author_packet.py).", ""]
    return "\n".join(sections)


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--check", action="store_true")
    opts = args.parse_args()
    text = render()
    if opts.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != text:
            print(f"stale primitive parity documentation: {OUTPUT}", file=sys.stderr)
            return 1
    else:
        OUTPUT.write_text(text, encoding="utf-8")
        print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
