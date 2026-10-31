"""Read-only stat/unit presentation of recognized native source contributions.

No execution, active-state inference, branch selection, or capability routing.
The captured parent stays unchanged. Unknown rows remain literal in the prompt.
"""
from __future__ import annotations

import copy
from decimal import Decimal
import math
from typing import Any


_RULE = (
    "Read-only source stat/unit view, not active effects or final player stats. "
    "operation=add adds the signed contribution; multiply scales the named component; set/assign replaces it. "
    "All enclosing conditions, source-reach requirements and unknowns still apply. HP/s denotes a regeneration "
    "contribution before other effects, not guaranteed healing/DPS. additive_percent changes a bonus component, "
    "not final speed/damage; percentage_points changes a percentage directly. additive_multiplier changes a "
    "multiplier itself: miningUseTimeMultiplier add -0.1 is -0.1 to use-time factor, NOT +10% mining speed. "
    "Item lifeRegen is a stored item contribution, not a measured player rate. Unrecognized native rows retain "
    "their original units and opaque semantics; Boolean flags alone do not prove a quantified mechanic."
)

# Exact source member + declared source stat/unit, not item names or categories.
# Native Player.lifeRegen is twice the HP/s contribution; fraction bonuses use
# percent in Author context. Distinct multiplier components are not inverted.
_FIELDS = {
    "lifeRegen": ("lifeRegeneration", "lifeRegen", "HP/s", "0.5"),
    "moveSpeed": ("movementSpeed", "moveSpeedBonus", "additive_percent", "100"),
    "pickSpeed": ("pickUseTimeMultiplier", "miningUseTimeMultiplier", "additive_multiplier", "1"),
    "whipRangeMultiplier": ("whipRangeMultiplier", "whipRangeBonus", "additive_percent", "100"),
    "fishingSkill": ("fishingPower", "fishingPower", "points", "1"),
    "statLifeMax2": ("maximumLife", "maxLifePoints", "life_points", "1"),
    "statManaMax2": ("maximumMana", "maxManaPoints", "mana_points", "1"),
    "maxMinions": ("maximumMinions", "minionSlotsBonus", "slots", "1"),
    "maxTurrets": ("maximumSentries", "sentrySlotsBonus", "slots", "1"),
    "manaCost": ("manaCostMultiplier", "manaCostMultiplier", "additive_multiplier", "1"),
    "manaRegenBonus": ("manaRegenerationBonus", "manaRegen", "native_bonus_points", "1"),
    "aggro": ("aggro", "aggroPoints", "points", "1"),
    "endurance": ("damageReduction", "damageReduction", "percentage_points", "100"),
}
_GETTERS = {
    "allCrit": ("critChance", "generic", "critChance", "percentage_points", "1"),
    "meleeCrit": ("critChance", "melee", "critChance", "percentage_points", "1"),
    "rangedCrit": ("critChance", "ranged", "critChance", "percentage_points", "1"),
    "magicCrit": ("critChance", "magic", "critChance", "percentage_points", "1"),
    "meleeSpeed": ("attackSpeed", "melee", "attackSpeedBonus", "additive_percent", "100"),
    "armorPenetration": ("armorPenetration", "generic", "armorPenetration", "armor_points", "1"),
    **{name + "Damage": ("damage", damage_class, "damageBonus", "additive_percent", "100")
       for name, damage_class in (("all", "generic"), ("melee", "melee"), ("ranged", "ranged"),
                                  ("magic", "magic"), ("minion", "summon"))},
}
_EQUIPMENT_UNITS = {
    "lifeRegeneration": "native_half_hp_per_second_units", "fishingPower": "points", "maximumMana": "points",
    "maximumMinions": "slots", "maximumSentries": "slots", "manaRegenerationBonus": "native_units",
    "aggro": "native_units", "critChance": "percentage_points", "armorPenetration": "points",
}
_EFFECT_FIELDS = {"stat", "damageClass", "nativeMember", "operation", "value", "units", "ilOffset",
                  "sourceIlOffset", "storageType", "clampPositiveToZeroFirst"}


def _number(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _scaled(value: int | float, factor: str) -> float:
    # Change declared units, not the arithmetic/runtime storage of the source.
    return float(Decimal(str(value)) * Decimal(factor))


def _npc_regen(row: dict[str, Any]) -> dict[str, Any]:
    """Use the producer's proved counter relation, not assumed NPC scheduling."""
    keys = _EFFECT_FIELDS | {"unitEvidence", "nominalHpLossPerSecondAt60Updates", "nominalRateScope"}
    evidence = row.get("unitEvidence")
    evidence_keys = {"accumulatorUnitsPerHealthPoint", "healthPointsPerLoopBody", "accumulatorAddIlOffset",
                     "negativeAccumulatorStepIlOffset", "healthStoreIlOffset", "loopCheckIlOffset",
                     "targetRouting", "damageCondition", "scope"}
    if (not set(row) <= keys or row.get("nativeMember") != "Terraria.NPC.lifeRegen"
            or row.get("operation") != "add" or row.get("units") != "native_lifeRegen_units"
            or row.get("storageType") != "int32" or row.get("clampPositiveToZeroFirst") is not True
            or type(row.get("value")) is not int or not _number(row["value"]) or row["value"] >= 0
            or not isinstance(evidence, dict) or set(evidence) != evidence_keys
            or not isinstance(row.get("nominalRateScope"), str)):
        return copy.deepcopy(row)
    counter, hp = evidence["accumulatorUnitsPerHealthPoint"], evidence["healthPointsPerLoopBody"]
    if (type(counter) is not int or type(hp) is not int or not _number(counter) or not _number(hp)
            or counter <= 0 or hp <= 0
            or not _number(row.get("nominalHpLossPerSecondAt60Updates"))):
        return copy.deepcopy(row)
    nominal = float(-Decimal(row["value"]) * 60 * hp / counter)
    if not math.isfinite(nominal) or nominal != row["nominalHpLossPerSecondAt60Updates"]:
        return copy.deepcopy(row)
    result = {key: copy.deepcopy(value) for key, value in row.items()
              if key not in {"nativeMember", "value", "units", "nominalHpLossPerSecondAt60Updates"}}
    result.update(stat="lifeRegen", receiver="npc", value=-nominal, units="HP/s at 60 accumulator updates/s")
    return result


def _effect(row: dict[str, Any], source: str, receiver: str | None) -> dict[str, Any]:
    if source == "certified_native_buff_operation_fragments" and receiver == "npc":
        return _npc_regen(row)
    if (not set(row) <= _EFFECT_FIELDS or not _number(row.get("value"))
            or not isinstance(row.get("operation"), str) or row["operation"] not in {"add", "multiply"}):
        return copy.deepcopy(row)
    member = row.get("nativeMember")
    if not isinstance(member, str) or not member.startswith("Terraria.Player."):
        return copy.deepcopy(row)
    if source == "certified_native_buff_operation_fragments" and receiver != "player":
        return copy.deepcopy(row)
    field = member.removeprefix("Terraria.Player.")
    damage_class = None
    if field in _FIELDS:
        source_stat, stat, unit, factor = _FIELDS[field]
    elif field.startswith("get_") and field[4:] in _GETTERS:
        source_stat, damage_class, stat, unit, factor = _GETTERS[field[4:]]
    else:
        return copy.deepcopy(row)
    if source == "verified_native_equipment_source_branches":
        if (row.get("stat") != source_stat or row.get("units") != _EQUIPMENT_UNITS.get(source_stat, "additive_fraction")
                or row.get("operation") != "add" or row.get("damageClass") != damage_class):
            return copy.deepcopy(row)
    elif (row.get("units") != ("dimensionless_factor" if row["operation"] == "multiply" else "native_member_units")
          or not isinstance(row.get("storageType"), str)
          or row["storageType"] not in {"int32", "float32", "float64", "ref_int32", "ref_float32"}
          or "stat" in row or "damageClass" in row):
        return copy.deepcopy(row)
    if row["operation"] == "multiply":
        # A factor itself is not converted to HP/s or percentage points.
        stat = "lifeRegen" if source_stat == "lifeRegeneration" else source_stat
        unit, factor = "dimensionless_factor", "1"
    scaled = _scaled(row["value"], factor)
    if not math.isfinite(scaled):
        return copy.deepcopy(row)
    result = {key: copy.deepcopy(value) for key, value in row.items()
              if key not in {"nativeMember", "stat", "units", "value"}}
    result.update(stat=stat, receiver="player", value=scaled, units=unit)
    if damage_class is not None:
        result["damageClass"] = damage_class
    return result


_EQUIPMENT_AUDIT_KEYS = {
    "source", "scope", "equippedContributions", "conditionalArmorSets", "equipmentSourceCertificate", "setSourceCertificate",
    "itemId", "fullName", "condition", "branches", "guardIlOffset", "effects", "conditionalEffects",
    "nativeMember", "equals", "observed", "functionalEquipSlots", "head", "body", "legs", "allSlotsRequired",
    "vanitySatisfies", "setBonusLocalizationKey", "literalSetBonusText", "literalTextLanguage", "literalTextStatus",
} | _EFFECT_FIELDS
_BUFF_AUDIT_KEYS = {
    "source", "scope", "receiver", "buffId", "buffFullName", "completeness", "fragments", "sourceFlags", "unsupported",
    "sourceCertificate", "sourceUnitDescriptors", "applicationSource", "requestedDurationTicks", "applicationScope",
    "condition", "buffTypeEquals", "slotLocal", "nativeControlFlowMustReachTest", "testBranchIlOffset", "conditionScope",
    "operations", "sourceMethod",
} | _EFFECT_FIELDS


def _known_stat_audit_tree(value: Any, source: str, receiver: str | None = None) -> bool:
    """Audit removal is refused for unfamiliar source keys anywhere in the envelope.

    Buff flag/DoT/placement graphs outside this narrow shape keep their proof
    metadata. We never remove a key by a hash/offset substring heuristic.
    """
    allowed = _EQUIPMENT_AUDIT_KEYS if source == "verified_native_equipment_source_branches" else _BUFF_AUDIT_KEYS
    if isinstance(value, list):
        return all(_known_stat_audit_tree(child, source, receiver) for child in value)
    if not isinstance(value, dict):
        return value is None or type(value) in {str, int, float, bool}
    if not set(value) <= allowed:
        return False
    if "nativeMember" in value and "operation" in value and _effect(value, source, receiver) == value:
        return False
    for key, child in value.items():
        if key == "sourceUnitDescriptors":
            if not isinstance(child, dict) or not all(isinstance(text, str) for text in child.values()):
                return False
        elif key == "sourceCertificate":
            if (not isinstance(child, dict) or set(child) != {"assemblySha256", "sourceModuleVersionId", "methods"}
                    or not isinstance(child["assemblySha256"], str) or not isinstance(child["sourceModuleVersionId"], str)
                    or not isinstance(child["methods"], list)
                    or any(not isinstance(method, dict) or set(method) != {"owner", "name", "sourceMethodSha256"}
                           or not all(isinstance(text, str) for text in method.values()) for method in child["methods"])):
                return False
        elif key in {"equipmentSourceCertificate", "setSourceCertificate"}:
            if not isinstance(child, str):
                return False
        elif not _known_stat_audit_tree(child, source, receiver):
            return False
    return True


def parent_stat_context(raw: dict[str, Any]) -> dict[str, Any]:
    """Project only certified source rows; keep all condition wrappers intact."""
    if "generatedParent" in raw:
        return copy.deepcopy(raw)
    changed = False

    def visit(value: Any, source: str = "", receiver: str | None = None, audit_safe: bool = False) -> Any:
        nonlocal changed
        if isinstance(value, list):
            return [visit(child, source, receiver, audit_safe) for child in value]
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        declared = value.get("source")
        if isinstance(declared, str) and declared in {"verified_native_equipment_source_branches", "certified_native_buff_operation_fragments",
                        "certified_native_environment_reference"}:
            source, receiver = declared, value.get("receiver")
            audit_safe = source != "certified_native_environment_reference" and _known_stat_audit_tree(value, source, receiver)
        elif declared is not None:
            # Do not lend a recognized parent's meaning to an opaque child.
            source, receiver, audit_safe = "", None, False
        if source in {"verified_native_equipment_source_branches", "certified_native_buff_operation_fragments"} and "nativeMember" in value and "operation" in value:
            projected = _effect(value, source, receiver)
            if audit_safe and projected != value:
                # These are positions of the represented writes, not guard IDs
                # or targets. Their surrounding order/conditions stay explicit.
                projected.pop("ilOffset", None)
                projected.pop("sourceIlOffset", None)
            changed |= projected != value
            return projected
        if (source == "certified_native_environment_reference"
                and set(value) == {"field", "add", "condition", "units", "scope"}
                and value.get("field") == "Player.lifeRegen" and _number(value.get("add"))
                and value.get("units") == "native_life_regen_counter_units"):
            changed = True
            return {"stat": "lifeRegen", "receiver": "player", "operation": "add",
                    "value": _scaled(value["add"], "0.5"), "units": "HP/s",
                    "condition": copy.deepcopy(value["condition"]), "scope": value["scope"]}
        omitted = {"equipmentSourceCertificate", "setSourceCertificate", "sourceCertificate"} if audit_safe else set()
        changed |= bool(omitted.intersection(value))
        return {key: visit(child, source, receiver, audit_safe) for key, child in value.items() if key not in omitted}

    result = visit(raw)
    source_changed = changed
    item = result.get("item")
    if isinstance(item, dict) and _number(item.get("lifeRegen")):
        item["lifeRegen"] = {"value": _scaled(item["lifeRegen"], "0.5"), "units": "HP/s"}
        changed = True
    if changed:
        result["sourceStatReading"] = _RULE if source_changed else (
            "Item lifeRegen is a stored regeneration contribution in HP/s before other effects, "
            "not a measured player rate or guaranteed healing. Original captured parents are unchanged."
        )
    return result
