#!/usr/bin/env python3
from __future__ import annotations

"""Generate the Lowery reference technical-mapping and alias inventory."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

from infini_local.core.runtime_authoring.capability_registry import (  # noqa: E402
    CAPABILITY_REGISTRY,
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
    capability_fixed_outputs,
    declared_neutral_omissions,
)
from infini_local.core.runtime_authoring.terraria_vocabulary import (  # noqa: E402
    AMMO_CATEGORY_TMODLOADER_NAMES,
    DAMAGE_CLASS_TMODLOADER_NAMES,
    ITEM_USE_STYLE_TMODLOADER_NAMES,
)

from infini_local.pipelines.author_item_contract import author_item_repair_prompt_shape_card  # noqa: E402
from infini_local.pipelines.llm_authoring_prompt import concise_terraria_tick_guide_for_llm  # noqa: E402

OUTPUT = ROOT / "docs/reference/generated/LOWERY_RU.md"


def table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> list[str]:
    def cell(value: object) -> str:
        return (str(value).replace("\r\n", "\n").replace("\r", "\n")
                .replace("|", "\\|").replace("\n", "<br>"))

    out = ["| " + " | ".join(cell(header) for header in headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return out


def render() -> str:
    lines: list[str] = [
        "# Low-level authoring и Lowery — канонический контракт",
        "",
        "> Generated: [`tools/generate/generate_lowery.py`](../../../tools/generate/generate_lowery.py). Не редактировать вручную; менять canonical owner и [обновлять projection](#refresh).",
        "> Sources: [registry](../../../LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py), "
        "[Author shape](../../../LocalGenerator/infini_local/core/runtime_authoring/program_schema.py), "
        "[lowering](../../../LocalGenerator/infini_local/core/runtime_authoring/technical_lowering.py), "
        "[tModLoader vocabulary](../../../LocalGenerator/infini_local/core/runtime_authoring/terraria_vocabulary.py), "
        "[Author/Repair prose](../../../LocalGenerator/infini_local/pipelines/author_item_contract.py), "
        "[unit guide](../../../LocalGenerator/infini_local/pipelines/llm_authoring_prompt.py).",
        "",
        f"Schemas: `{RUNTIME_PROGRAM_API_VERSION}` / `{RUNTIME_PROGRAM_SCHEMA}` / `{RUNTIME_WIRE_SCHEMA}`.",
        "",
        "**Навигация:** [граница](#boundary) · [owners](#owners) · [Author → wire](#wire) · "
        "[manifest](#lowering) · [технические отображения](#mappings) · [текст и единицы игрока](#player-text) · [config/UI aliases](#config-aliases) · "
        "[proxy runtime](#runtime) · [обновление и проверка](#refresh).",
        "",
        '<a id="boundary"></a>',
        "",
        "## READ THIS FIRST — замороженная граница",
        "",
        "1. Gameplay Author сам выбирает механику, entities, bindings, calls, params, events, references и metadata. "
        "Ни имя, tooltip, category, family, parent tag или capability prose не разрешают коду дописать дизайн.",
        "2. Deterministic Python имеет право только проверить exact authored graph, ограничить его, отфильтровать exact Repair scope и выполнить lossless technical lowering.",
        "3. Lowery не является вторым Author. Он не выбирает movement, attachment, delivery, lifecycle, input, target, entity kind, event, damage, visual topology, hitbox topology, root executor или fallback mechanic. Он может скрывать неудобство API, но не сжимать пространство дизайна.",
        "4. Сжатие буквально повторённых low-level параметров допускается от "
        f"**{EXACT_REPETITION_COMPRESSION_POLICY['minimumRepeatedPlacements']}** одинаковых placements и сохраняет literal equality. "
        "Этот threshold не запрещает точный выбранный alias или one-to-one technical projection; ни один из них не добавляет design choice.",
        "5. Обязательная wire projection из уже authored identity (например, exact entity kind → renderer role или exact primary id/target equality → binding role) не считается authoring compression: она сериализует одно решение, а не заменяет несколько решений модели.",
        "6. Repair получает конечные registry-derived alternatives и exact permissions. Модель выбирает и явно пишет полный вариант; patch не заполняет пропуски и после frozen-first merge повторно запускается canonical validator.",
        "7. Только optional params с явно объявленным registry default=neutral допускают пропуск в полном Author как точный выбор этой нейтрали. При omission_condition должна выполняться точная объявленная неисполняемая ветвь; вне её поле обязательно. Compiler материализует нейтраль после validation с отдельным receipt declared_neutral_omission. Это явное изменение контракта, не fallback невалидного значения и не правило для всех нулей. Связанные эффекты/обязательные группы проверяются совместно; omission в Repair означает не менять. Если разрешённый Repair меняет ветвь на исполняемую, он должен явно добавить ставший обязательным leaf.",
        "",
        '<a id="owners"></a>',
        "",
        "## Единственные owners",
        "",
    ]
    lines += table(("что меняется", "единственный owner", "derived consumers"), [
        ("Author JSON shape, primaryEntity fields, repair patch shape", "runtime_authoring/program_schema.py", "prompt schema, validator, Repair filter"),
        ("capabilities, entity/input/action/event facts and event producers", "runtime_authoring/capability_registry.py", "Author catalog, validator, Repair alternatives, docs"),
        ("lossless projections, exact outputs, receipts, repetition policy", "runtime_authoring/technical_lowering.py", "compiler, audits, this document"),
        ("Author/Repair model-facing prose and unit explanation", "pipelines/author_item_contract.py + pipelines/llm_authoring_prompt.py", "serialized Author/Repair messages, this document"),
        ("validation truth", "runtime_authoring/validator.py", "Repair requirements and final acceptance"),
        ("Repair permissions/filter", "runtime_authoring/repair_scope.py", "conditional Repair dossier and merge report"),
        ("wire materialization", "runtime_authoring/compiler.py", "RuntimeProgram wire + finalWireReceipts"),
        ("runtime execution", "ModSources/.../RuntimeProgramSpec.cs + executors", "tModLoader behavior"),
    ])
    lines += [
        "",
        "Правило меняется у owner-а. Нельзя создавать facade, shadow constant, prose-router или второй event/primary contract рядом. "
        "Generated projections обновляются командами в [«Обновление и проверка»](#refresh).",
        "",
        '<a id="wire"></a>',
        "",
        "## Authoring → wire boundary",
        "",
        f"- `{PRIMARY_ENTITY_AUTHOR_PATH}` — ровно один model-authored существующий entity id.",
        "- Author bindings/calls не содержат `role`. Compiler сравнивает exact `binding.action.targetId` (либо exact unique item-body identity на registry-fixed ветви) с exact `primaryEntityId`: equality → wire `primary`, иначе wire `secondary`. Wire сохраняет `binding.usePolicy`; эта one-to-one projection не выбирает entity, input, action, attachment, delivery или gameplay importance.",
        "- `primaryOwner` выводится только из exact kind выбранной entity через `ENTITY_KIND_REGISTRY.projectile`; неизвестный kind fail-closed валидатором, а не становится projectile default.",
        "- Каждая такая projection имеет manifest row и compiler receipt с authored paths, exact final path и value.",
        f"- Repair может менять primary identity только через `{PRIMARY_ENTITY_SELECTION_FIELD}` и только выбирая один id из transaction candidates.",
        "",
        "### Event producer contract",
        "",
        "`EventKindSpec` владеет producer calls, producer binding inputs, exact producer params и playerEffect predicate; `EntityKindSpec.base_events` владеет producer-free availability для конкретного kind. "
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
        player_effect_member = getattr(event, "producer_player_effect_member", "")
        event_rows.append((
            event.name,
            ", ".join(event.producer_capabilities) or "—",
            ", ".join(event.producer_binding_inputs) or "—",
            ", ".join(base_kinds) or "—",
            exact,
            f"playerEffect.{player_effect_member} present" if player_effect_member else "—",
        ))
    lines += table(("event", "producer calls", "producer binding inputs", "producer-free kinds", "exact params", "playerEffect predicate"), event_rows)
    lines += [
        "",
        '<a id="lowering"></a>',
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
        "### Точные выбранные проекции capabilities",
        "",
        "Это не второй список политик: значения ниже получены из registry fixed_wire_literals, "
        "MOVEMENT_OPCODE/CONTROLLER_OPCODE/EVENT_ACTION_OPCODE и cap.wire_action через canonical lowerer. "
        "Каждый fn-selected выход требует ровно один technical_projection receipt с exact source .fn, callId, finalPath и типизированным значением. "
        "Source-aware audit связывает его с реально выбранным executor и authored target; согласованно изменить wire и receipt недостаточно. "
        "Без Author `authoredSourceChecked=false`: это только проверка согласованности сохранённых утверждений, не восстановление неизвестного намерения. "
        "Старые wire/opcodes/отсутствия не переписываются на чтении. "
        "`fresh Author` означает доступный модели самостоятельный fn; `retained runtime` сохраняется для принятого runtime wire, но не предлагается как самостоятельный fn в новом Author.",
        "",
    ]
    lines += table(("capability", "availability", "fn-selected wire output", "exact value"), [
        (fn, "fresh Author" if cap.author_visible else "retained runtime", path, repr(value))
        for fn, cap in CAPABILITY_REGISTRY.items()
        for path, value in capability_fixed_outputs(fn).items()
    ])
    lines += ["", "### Явные event-проекции", "",
              "Разное authored имя может выбирать точную зарегистрированную проекцию существующего event executor. "
              "Это полезный отдельный выбор, не разрешение угадывать действие из prose и не whole-weapon macro.", ""]
    lines += table(("capability", "availability", "wire action", "fixed outputs"), [
        (fn, "fresh Author" if cap.author_visible else "retained runtime", cap.wire_action, repr(dict(cap.fixed_wire_literals)))
        for fn, cap in CAPABILITY_REGISTRY.items() if cap.wire_action
    ])
    lines += ["", "### Structured и enum projections", "",
              "Typed structured choices и конечные enum-отображения также принадлежат ParamSpec; "
              "они сохраняют явно выбранную ветвь и полезные независимые параметры.", ""]
    lines += table(("capability.param", "declared projection"), [
        (f"{fn}.{name}", repr(spec.projection_paths(name) if spec.structured else dict(spec.wire_enum)))
        for fn, cap in CAPABILITY_REGISTRY.items() for name, spec in cap.params.items()
        if spec.structured or spec.wire_enum
    ])
    lines += ["", "### Разрешённые neutral omissions", "",
              "Это только объявленные default=neutral, не универсальное правило для нуля. "
              "При условии вне указанной ветви leaf остаётся обязательным; contradictory-present не исправляется. "
              "Compiler выдаёт declared_neutral_omission receipt, а Repair отсутствие сохраняет.", ""]
    lines += table(("capability.param", "exact neutral", "omission condition"), [
        (f"{fn}.{name}", repr(value),
         repr({"targetKinds": spec.omission_condition.target_kinds,
               "paramEquals": spec.omission_condition.param_equals,
               "targetCapabilities": spec.omission_condition.target_capabilities}) if spec.omission_condition else
         next(("all timing absent: " + ", ".join((rule.param, rule.other_param, *rule.any_of))
               for rule in cap.requirements if rule.kind == "timing_pair_or_window" and rule.allow_absent
               and name.split(".", 1)[0] in rule.any_of), "unconditional declared neutral"))
        for fn, cap in CAPABILITY_REGISTRY.items()
        for name, value in declared_neutral_omissions(fn, {}).items()
        for spec in (cap.params[name.split(".", 1)[0]],)
    ])
    lines += [
        "",
        "## Каноническая vocabulary",
        "",
        "Точные event/structured/enum projections перечислены выше; технический alias сам по себе не запрещён. "
        "Синонимы spelling, напротив, не образуют дополнительный Author API. Старые `passive`, `drink`, `eat`, plural ammo spellings и `rogue` не принимаются. `throwing` сохранён только как точное каноническое отображение stable `DamageClass.Throwing`. `damageClass` имеет одну identity-форму: built-in token либо точный tModLoader `ModName/ClassName`, скопированный из loaded parent facts; псевдотокены `none`/`modded` и параллельное `damageClassFullName` запрещены.",
        "",
        '<a id="mappings"></a>',
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
        "`configure_vanilla_ammo_item` отдельно принимает `projectileId` и `shootSpeedContributionBlocksPerSecond`, переводя базовый ammo-вклад в native `Item.shootSpeed`; `projectileId` задаёт `Item.shoot`. Категория не выбирает projectile автоматически. `Item.ammo` означает «этот предмет является боеприпасом». Отдельная capability `configure_weapon_ammo` задаёт `Item.useAmmo` для active spawn_entity shots: native selection/conservation и damage/knockback сохраняются, поведение projectile принадлежит authored entity. Author явно выбирает `speedBasis=authored_spawn|native_shot`. Другие use lanes и passive hold не расходуют ammo. Одновременная роль ammo stack и ammo consumer у одного generated item отклоняется.",
        "",
        "### Loaded content IDs",
        "",
        "`rarity`, `buffId`, `tileId` и `wallId` не имеют aliases и не угадываются по имени. Сейчас это точные IDs текущего loaded content set, прошедшие `RarityLoader`/`BuffLoader`/`TileLoader`/`WallLoader`; их можно только копировать из parent facts. Modded `DamageClass` является исключением: он хранится устойчивой exact content identity `ModName/ClassName` и разрешается через `ModContent.TryFind`.",
        "",
        "### Поля с неочевидными Terraria units",
        "",
        "- `valueCopper` напрямую пишет `Item.value`; это base/shop value в copper, а не обещание конкретной суммы resale игроком.",
        "- Author `configure_tool.axePowerTooltipPercent` задаёт целое 0..500 с шагом 5 в видимых процентах tooltip; compiler точно пишет старое целое `gameplay.axePower = value / 5` в `Item.axe` 0..100. Старое имя `axePower` не принимается как Author alias.",
        "- Author `apply_generated_buff_on_use.lifeRegen` задаёт вклад в HP/с (-50..60, шаг 0.5); compiler точно пишет старое целое `gameplay.generatedBuff.lifeRegen = value × 2`. Это вклад в engine stat до остальных эффектов, не обещание итогового лечения.",
        "- `lifeRegen`/`regenWhen` и `treasureSense`/`treasureWhen` — единственные Author-входы для этих эффектов. Условия переводятся в typed native condition fields, не создают вторую stat-величину и сами по себе не являются эффектом. Nested `playerEffect.lifeRegen…`/`highlightTreasure` отвергаются.",
        "",
        '<a id="player-text"></a>',
        "",
        "### Описание игроку и engine units — разные представления",
        "",
        "Lowery — технический lowering, не lore и не автор дополнительной механики. "
        "Author задаёт игровые расстояния в блоках, длительности в секундах, скорости в блоках/с. "
        "Меняется schema авторинга; сохранённый engine wire остаётся в прежних единицах. "
        "Canonical lowering выполняет объявленные проекции с учётом updatesPerTick именно затронутой сущности. "
        "Секунды разрешаются до ближайшего целого world tick, половина тика округляется вверх; "
        "неположенное обнуление ненулевого эффекта отклоняется, а не скрыто меняет механику. "
        "Pixel-labelled collision/sprite geometry и texture/UV units сохраняют своё объявленное пространство. "
        "Описание остаётся optional advisory: оно не требует нового отчёта и не запускает validator/Repair. "
        "Механическая истина — явно emitted runtimeProgram, а не красивое обещание в тексте.",
        "",
        "Ниже — тот же model-facing текст из существующих prompt owners, а не отдельный prose-контракт. "
        "Initial Author получает единицы в `runtimeCapabilityContract.technicalNotes` и generation-only provider schema с кратким concept и разделёнными realization.description (применение) / selfEvaluation (отладка). "
        "Legacy acceptance и Repair сохраняют эти optional advisory поля; "
        "Repair — в `requiredJsonShape.realizationReplacement` и `runtimeExecutionTruth.units.playerFacingUnits`. "
        "Он передаётся в JSON messages при json_schema и json_object; schema annotations для этого не требуются. "
        "Если Repair добровольно возвращает описание, оно относится к post-merge программе; read-only context не даёт права менять frozen механику.",
        "",
    ]
    realization = author_item_repair_prompt_shape_card()["realizationReplacement"]
    lines += table(("optional prose", "shared guidance"), [
        (f"realization.{name}", realization[name]) for name in ("description", "playerExperience")
    ])
    lines += [""]
    lines += table(("единицы / scope", "shared model-facing guide"), list(concise_terraria_tick_guide_for_llm().items()))
    lines += [
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
        "Whole-pattern aliases и archetype routers не входят в текущий контракт. Name/category/prose не выбирают композицию; compatibility importer и старые spelling не являются вторым API.",
        "",
        '<a id="config-aliases"></a>',
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
        "Это только выбор существующего image backend в конфигурации; visual topology и gameplay от spelling не зависят.",
        "",
        "### Явные presentation choices",
        "",
        "Категория результата проходит strict Author enum без UI/category alias routing. VFX цвет задаётся local RGB objects в slots/profile knots/library endpoints; Visual palette остаётся art context. Технические config aliases выше не выбирают механику, renderer или цвет.",
        "",
        '<a id="runtime"></a>',
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
        '<a id="refresh"></a>',
        "",
        "## Обновление и проверка",
        "",
        "Из корня репозитория, с Python окружения проекта. Без `--check` этот generator записывает **только `docs/reference/generated/LOWERY_RU.md`**. "
        "[Inventory и audit](LOW_LEVEL_CAPABILITY_INVENTORY_RU.md#refresh) и [primitive parity](PRIMITIVE_PARITY_RU.md#refresh) обновляются своими generators.",
        "",
        "```bash",
        "PYTHONPATH=LocalGenerator python tools/generate/generate_lowery.py",
        "PYTHONPATH=LocalGenerator python tools/generate/generate_lowery.py --check",
        "PYTHONPATH=LocalGenerator python tools/generate/generate_low_level_runtime_docs.py --check",
        "PYTHONPATH=LocalGenerator python tools/generate/generate_primitive_parity.py --check",
        "PYTHONPATH=LocalGenerator python -m pytest -q LocalGenerator/tests/test_registry_*.py LocalGenerator/tests/test_low_level_three_stage_pipeline.py LocalGenerator/tests/test_pipeline_repair_contract.py",
        "```",
        "",
        'Type check: `python tools/testing/run_pyright.py --pythonpath "$(python -c \'import sys; print(sys.executable)\')"`. Полные delivery gates: [AGENTS.md](../../../AGENTS.md).',
        "",
        "Change-locality acceptance: изменить один canonical owner, обновить generated projections, пройти affected replay; не редактировать параллельные prose contracts и не запускать Live как замену локальному доказательству.",
        "",
        "## Добавление точной projection",
        "",
        "Новая projection объявляется у существующего registry/ParamSpec owner и исполняется canonical lowerer/compiler. "
        "Нужны полный явный selector и единственный результат, receipt, source→wire identity, negative для contradictory-present "
        "и frozen Repair отсутствие. Полезные независимые параметры остаются у Author; старое ограничение compound controller "
        "не становится универсальным engine invariant новых primitives. Alias не даёт права добавлять meaningful defaults, "
        "выбирать channel/target/collision из имени или переписывать исторические saved items. "
        "После изменения owner обновить generated projections и пройти affected acceptance.",
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
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(expected, encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
