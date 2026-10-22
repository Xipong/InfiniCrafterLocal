from __future__ import annotations

from argparse import Namespace
from collections.abc import Iterable
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROUTES: list[tuple[str, str, str]] = [
    ("woodwork_blade", "WoodenSword", "WorkBench"),
    ("astral_mirror", "MagicMirror", "FallenStar"),
    ("bee_boomstick", "Boomstick", "BeeWax"),
    ("swift_boots", "HermesBoots", "Aglet"),
    ("ropebound_spear", "Spear", "Rope"),
    ("infernal_boomerang", "EnchantedBoomerang", "HellstoneBar"),
    ("meteor_spacegun", "SpaceGun", "MeteoriteBar"),
    ("astral_minishark", "Minishark", "FallenStar"),
    ("chained_ball", "BallOHurt", "Chain"),
    ("corrupt_yoyo", "CorruptYoyo", "DemoniteBar"),
    ("jungle_whip", "ThornWhip", "JungleSpores"),
    ("lens_finch_staff", "BabyBirdStaff", "Lens"),
    ("spider_sentry", "QueenSpiderStaff", "SpiderFang"),
    ("gel_grenade", "Grenade", "Gel"),
    ("jester_bow", "WoodenBow", "JestersArrow"),
    ("obsidian_pickaxe", "MoltenPickaxe", "Obsidian"),
    ("vital_regen_band", "BandofRegeneration", "LifeCrystal"),
    ("torch_mining_helmet", "MiningHelmet", "Torch"),
    ("glowing_healing_potion", "HealingPotion", "GlowingMushroom"),
    ("silt_extractinator", "Extractinator", "SiltBlock"),
    ("gel_slime_staff", "SlimeStaff", "Gel"),
    ("torch_iron_sword", "IronBroadsword", "Torch"),
    ("feather_cloud_bottle", "CloudinaBottle", "Feather"),
    ("astral_star_cannon", "StarCannon", "FallenStar"),
    ("wax_bee_gun", "BeeGun", "BeeWax"),
    ("infernal_flamarang", "Flamarang", "HellstoneBar"),
]
LIVE20_IDS = tuple(case_id for case_id, _, _ in ROUTES[:20])
# Explicit thematic subset, not a claim about historical Live10 results.
LIVE10_IDS = (
    "woodwork_blade", "astral_mirror", "bee_boomstick", "swift_boots",
    "ropebound_spear", "corrupt_yoyo", "jungle_whip", "lens_finch_staff",
    "obsidian_pickaxe", "glowing_healing_potion",
)
PANEL_PROVENANCE = "Live20 tracked Terraria panel; Live10 is an explicit 10-case thematic subset (not historical Live10 evidence)"


def select_case_routes(routes: Iterable[tuple[str, str, str]], selected_ids: set[str]) -> list[tuple[str, str, str]]:
    rows = list(routes)
    unknown = selected_ids - {row[0] for row in rows}
    if unknown:
        raise ValueError(f"unknown case IDs: {', '.join(sorted(unknown))}")
    return [row for row in rows if not selected_ids or row[0] in selected_ids]


def load_selection(args: Namespace):
    runtime_dump = (args.runtime_dump or Path(__file__).resolve().parents[1] / "fixtures/items.jsonl").expanduser().resolve()
    if not runtime_dump.is_file():
        raise ValueError(f"parent runtime dump is missing: {runtime_dump}")
    items: dict[str, dict[str, Any]] = {}
    with runtime_dump.open(encoding="utf-8-sig") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            internal = str(row.get("internalName") or "")
            if internal:
                if internal in items:
                    raise ValueError(f"duplicate parent identity: {internal}")
                items[internal] = row

    active_routes = ROUTES
    cases_file_path = ""
    cases_file_sha256 = ""
    if args.cases_file:
        source_path = args.cases_file.expanduser().resolve()
        raw_payload = json.loads(source_path.read_text(encoding="utf-8"))
        raw_cases = raw_payload.get("cases") if isinstance(raw_payload, dict) else raw_payload
        if not isinstance(raw_cases, list):
            raise ValueError("--cases-file must contain a list or an object with a cases list")
        parsed_routes: list[tuple[str, str, str]] = []
        seen_case_ids: set[str] = set()
        for index, row in enumerate(raw_cases):
            if not isinstance(row, dict):
                raise ValueError(f"--cases-file row {index} must be an object")
            case_id = str(row.get("case") or "").strip()
            parent_a = str(row.get("itemA") or "").strip()
            parent_b = str(row.get("itemB") or "").strip()
            if (
                not case_id
                or len(case_id) > 64
                or not case_id.replace("_", "").isalnum()
                or case_id.lower() != case_id
            ):
                raise ValueError(f"--cases-file row {index} has invalid case ID {case_id!r}")
            if not parent_a or not parent_b:
                raise ValueError(f"--cases-file row {index} requires itemA and itemB")
            if case_id in seen_case_ids:
                raise ValueError(f"--cases-file repeats case ID {case_id!r}")
            seen_case_ids.add(case_id)
            parsed_routes.append((case_id, parent_a, parent_b))
        if not parsed_routes:
            raise ValueError("--cases-file has no cases")
        active_routes = parsed_routes
        cases_file_path = str(source_path)
        cases_file_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()

    requested_ids = [value.strip() for value in args.cases.split(',')] if args.cases is not None else []
    if args.cases is not None and (not all(requested_ids) or len(requested_ids) != len(set(requested_ids))):
        raise ValueError('--cases must contain distinct nonempty IDs')
    case_filter = set(requested_ids)
    if not case_filter and not args.cases_file:
        case_filter = set(LIVE10_IDS if args.panel == "live10" else LIVE20_IDS)
    selected_routes = select_case_routes(active_routes, case_filter)
    missing_items = sorted({
        name for _, a_name, b_name in selected_routes
        for name in (a_name, b_name) if name not in items
    })
    if missing_items:
        raise ValueError(f"runtime dump is missing: {', '.join(missing_items)}")
    selected_cases = [
        (case_id, copy.deepcopy(items[parent_a]), copy.deepcopy(items[parent_b]))
        for case_id, parent_a, parent_b in selected_routes
    ]
    if not selected_cases:
        raise ValueError("no live cases selected")
    if args.expected_case_count is not None and len(selected_cases) != args.expected_case_count:
        raise ValueError(f"selected {len(selected_cases)} cases, expected {args.expected_case_count}")
    if args.min_first_author < 0 or args.min_first_author > len(selected_cases):
        raise ValueError(f"--min-first-author must be within 0..{len(selected_cases)}")

    return runtime_dump, selected_routes, selected_cases, cases_file_path, cases_file_sha256
