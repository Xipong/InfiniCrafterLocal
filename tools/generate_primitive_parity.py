#!/usr/bin/env python3
"""Render implementation-facing primitive parity from the canonical registry."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))
from infini_local.core.runtime_authoring.capability_registry import (  # noqa: E402
    CAPABILITY_REGISTRY, EQUIPMENT_DAMAGE_CLASSES, equipment_damage_wire_path,
)
from infini_local.qa.primitive_loss_audit import (  # noqa: E402
    equipment_surface_audit, event_surface_audit,
    runtime_component_surface_audit, item_gameplay_surface_audit,
    structural_surface_audit,
)

OUTPUT = ROOT / "docs/PRIMITIVE_PARITY_RU.md"


def _cell(value: object) -> str:
    return (str(value).replace("\r\n", "\n").replace("\r", "\n")
            .replace("|", r"\|").replace("\n", "<br>"))


def render() -> str:
    sections = ["# Parity примитивов Author ↔ Terraria/tModLoader",
        "", "> Generated: [`tools/generate_primitive_parity.py`](../tools/generate_primitive_parity.py). Не редактировать вручную; [refresh/check](#refresh).",
        "> Sources: [capability_registry.py](../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py) — имена, единицы, диапазоны, wire и фазы; "
        "[primitive_loss_audit.py](../LocalGenerator/infini_local/qa/primitive_loss_audit.py) — C# executable-поля из AST. "
        "[Lowery](../lowery.md) — boundary/owners; [inventory](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md) — полный каталог.",
        "", "**Навигация:** [история](#history) · [machine audit](#audit) · [equipment](#equipment) · "
        "[events/runtime](#events) · [невосстановленное](#unsupported) · [extraUpdates units](#units) · "
        "[границы проверки](#limits) · [обновление](#refresh).",
        "", '<a id="history"></a>',
        "", "## Историческое сопоставление",
        "", "- `019ff01` (до low-level v5): `LocalGenerator/infini_local/core/runtime_authoring.py`, `effect_catalog.py`. `accessory_effect` и `armor_effect` допускали raw DTO-названия и смешивали десятичные доли (например `meleeDamage=0.15`), points и bool; существовали текстовые `archetype`/`setBonusText` и whole-weapon pattern cards. Это не целевой Author API.",
        "- `25caddf` (импорт v5): явные item/entity/binding/event calls вместо оружейных macros. Часть executable-полей `AccessorySpec`/`ArmorSpec` осталась в C#, но была потеряна из model-visible каталога.",
        "- Сейчас один registry выдаёт Author JSON schema, компактные карточки, validator-параметры, exact wire paths, технические receipts, C# safety bounds и таблицы ниже. Legacy C# DTO — цель проекции, а не второе описание механики.",
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
        "`additive_percent` — авторский процент прибавки к additive компоненте StatModifier (15 → +0.15), не итоговый множитель урона. `percentage_points` — сдвиг шанса в п.п.; `probability_percent` — вероятность/100. `defense_points`, `life_points`, `slots` и `pixels_per_tick` не масштабируются. Отрицательные значения разрешены только там, где указан отрицательный минимум. Ноль/false/пустая строка — нейтральны, если не оговорено иначе. Item.defense проектируется в `ApplyToItem`: Terraria сама применяет защиту, equip-hook не удваивает её.",
        "", "Author schema ограничивает новые значения всех примитивов; C# Normalize сохраняет **только исторические DTO clamps**, перечисленные в `runtime_minimum`/`runtime_maximum` registry и `GeneratedEquipmentBounds.g.cs`. В таблицах они обозначены `legacy clamp`; отсутствие этой пометки означает отсутствие такого исторического clamp. Поля без него не сужаются для уже сохранённых legacy recipes. Это не разрешение Author выбирать значения вне своей схемы.", ""])
    for cap_name in ("configure_accessory", "configure_armor"):
        cap = CAPABILITY_REGISTRY[cap_name]
        sections += [f"### `{cap_name}`", "", "| Author | Действие / engine semantics | Единица | Neutral | Author range | Wire DTO | Фаза |", "|---|---|---|---|---|---|---|"]
        for name, spec in cap.params.items():
            wire = spec.wire_name or name
            conversion = f" /{spec.wire_divisor}" if spec.wire_divisor != 1 else ""
            value_range = (f"{spec.minimum}…{spec.maximum}" if spec.minimum is not None else
                           "/".join(map(str, spec.enum)) if spec.enum else
                           spec.pattern if spec.pattern else spec.kind)
            if spec.runtime_minimum is not None or spec.runtime_maximum is not None:
                value_range += f"<br>legacy clamp: {spec.runtime_minimum}…{spec.runtime_maximum}"
            row = [name, spec.description, spec.units or spec.semantic_type or spec.kind,
                   spec.neutral, value_range, f"{cap_name.removeprefix('configure_')}.{wire}{conversion}",
                   spec.execution_phase or "C# normalized item projection"]
            sections.append("| " + " | ".join(_cell(x) for x in row) + " |")
        sections += ["", f"Authority: `{cap.network_authority}`; техническая фаза/сетевая роль выбираются runtime, не LLM.", ""]
    modifier = CAPABILITY_REGISTRY["add_equipment_damage_bonus"]
    bonus = modifier.params["bonusPercent"]
    sections += ["### `add_equipment_damage_bonus` — параметризованная операция", "",
        "Один call выбирает `phase`, `damageClass` и `bonusPercent`. Shared type `equipment_damage_class` содержит ровно классы, для которых текущий C# вызывает `GetDamage(DamageClass)`: "
        + ", ".join(f"`{name}`" for name in EQUIPMENT_DAMAGE_CLASSES)
        + ". Другие item/projectile DamageClass здесь не исполняются и отклоняются; crit, attack speed, knockback и armor penetration пока исполняются только для `generic` и не маскируются выдуманной поддержкой других классов.",
        f"`bonusPercent`: `{bonus.minimum}…{bonus.maximum}` {bonus.units}, neutral `{bonus.neutral}`; wire = percent / {bonus.wire_divisor}. Указанные в `phase` `equipped` и `matching_armor_set` — выбор модели. Последняя фаза требует `configure_armor(slot=head, setKey=<непустой exact ключ>)`; C# применяет её только при совпадении head/body/legs. Повтор пары `(phase, damageClass)` отклоняется, а не неявно складывается.",
        "", "| Phase | DamageClass | Wire DTO | tModLoader hook |", "|---|---|---|---|"]
    for armor, phase in ((False, "equipped"), (True, "equipped"), (True, "matching_armor_set")):
        for damage_class in EQUIPMENT_DAMAGE_CLASSES:
            path = equipment_damage_wire_path(phase, damage_class, armor=armor)
            hook = "UpdateAccessory" if not armor else "UpdateEquip" if phase == "equipped" else "UpdateArmorSet"
            sections.append(f"| {phase} ({'armor' if armor else 'accessory'}) | {damage_class} | `{path}` | `{hook}` |")
    sections += ["", "Legacy C# DTO/Normalize-поля и выборочные исторические clamps сохранены; Author больше не видит пять class-specific полей как независимые primitives. Сохранённый wire v5 загружается без повторной компиляции Author.", ""]
    sections += ['<a id="events"></a>', "", "## Event/runtime и намеренно скрытое", "",
        "- Все `RuntimeEventActionSpec` поля, включая `DelayTicks`, сверяются с exact wire paths. Каждый event action допускает `delayTicks=0…600`; C# scheduler проверяет spawn budget/authority и переносит действие, не создавая новый дизайн.",
        "- `move_owner_on_event` телепортирует только к **сохранённой позиции события** (ограничение `rangeTiles`, проверка safe tile, общий cooldown с `move_player_on_use`). Wire `Mode=blink_to_event_position` — фиксированный технический discriminator; старое `blink_to_entity` исполнялось той же веткой и больше не предлагается модели.",
        "- `oreSenseEnabled` — булево включение Terraria `Player.findTreasure`; legacy `GeneratedBuffSpec.OreSenseRadiusTiles` хранит только 0/1, **не радиус**. В prompt нет ложных тайлов.",
        "- `RuntimeParamsSpec.IntervalTicks` — только legacy fallback при нулевом typed `Targeting.IntervalTicks`; текущий Author требует положительный typed interval. `ShotEntity` и `SameTargetBias` в старом Params не потребляются: Author пишет typed `Targeting`.",
        "- `held generatedBuff`: snapshot ещё не имеет refresh generated utility buff при удержании; текущие held light/mining-speed поля не заменяют произвольный buff. Исторический consumer и его удаление описаны в A2 snapshot-аудита; возможное восстановление требует явного отдельного capability, не скрытого выбора по предмету.",
        "- Legacy `GameplaySpec.BuffCode`/`BuffTime` (`Item.buffType`/`buffTime`) сохраняются для старого wire. Новый Author использует явный многобафовый `ExtraBuffs` и не смешивает эти два пути; различие vanilla Item hook и пользовательского AddBuff не доказано эквивалентным.",
        "- `Archetype`, `Kind`, `Stage`, `PowerBudget` — исторические display/plan поля, не семантические маршрутизаторы. `Enabled`, opcodes, роли, `UseStyle` и DTO IDs выводятся из явно авторских calls.",
        "", '<a id="unsupported"></a>', "", "## Исторические возможности вне нынешнего executable surface", "",
        "Историческая проверка должна учитывать удалённые consumers отдельно от нынешнего AST. В pre-v5 `f04ee02` реальный `GeneratedProjectile.Sentry.cs:42–53` исполняет shotCount/spread за залп: этот механизм доказан. Вероятность собственного расхода сохранялась при импорте v5 и исчезла 2 августа (`3831d93`/`7f4e86a`). Ammo-side PickAmmo существует и не заменяет weapon Item.useAmmo. Старый Extractinator proxy хранил output в instance Data, но ExtractinatorUse неинстансный; intended per-instance output не доказан рабочим, а удаление произошло 15 июля (`5adb9fa`). Полная классификация с ранними архивами, source paths и ограничениями — [исторический snapshot-аудит](HISTORICAL_RUNTIME_AUDIT_2026_10_RU.md). Последующие restoration PR оцениваются отдельно: snapshot не является реестром текущих возможностей. Новая поддержка требует explicit bounded primitives и полного vertical slice, без whole-weapon macros.",
        "", '<a id="units"></a>', "", "## Единицы при extraUpdates > 0", "",
        "`set_projectile_collision.extraUpdates=n` даёт `n+1` AI/physics-обновлений снаряда за мировой тик. В Author-карточках исходная `Projectile.velocity`, гравитация, поворот, ускорение и скорость возврата обозначены **за projectile update**, а не как гарантированные пиксели за мировой тик. Длительности и event-периоды остаются в мировых тиках; C# переводит их через `AuthoredTicksToProjectileUpdates`. Это точное описание существующего wire/v5 поведения без смены старых рецептов и без приблизительного пересчёта нелинейного движения в px/сек.",
        "", '<a id="limits"></a>', "", "## Границы проверки", "",
        "AST audit анализирует нынешние DTO и названные C# executor seams. Удалённое вместе с consumer поле исчезает из этого множества: текущий PASS не доказывает исторический паритет. Audit не заменяет полноценный compiler/semantic analysis всех tML API. Headless C# тесты покрывают projection/equip и cooldown, но не Terraria world loop, GPU или multiplayer. Live20 проверяет Author pipeline на внешней модели, а не выполнение в игре.",
        "", '<a id="refresh"></a>', "", "## Обновление и проверка", "",
        "Из корня репозитория, с Python окружения проекта. Без `--check` generator записывает **только этот Markdown**, не JSON, DTO или bounds:", "",
        "```bash",
        "PYTHONPATH=LocalGenerator python tools/generate_primitive_parity.py",
        "PYTHONPATH=LocalGenerator python tools/generate_primitive_parity.py --check",
        "```", "",
        "Generation/check исполняют все пять surface audits выше и завершаются ошибкой при loss; freshness доказывает совпадение projection с owners, а не игровой smoke. "
        "Affected regressions: [test_registry_vertical_contract.py](../LocalGenerator/tests/test_registry_vertical_contract.py), "
        "[test_registry_author_packet.py](../LocalGenerator/tests/test_registry_author_packet.py).", ""]
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
