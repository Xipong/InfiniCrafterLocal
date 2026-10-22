"""Packaged classic inputs are discoverable without model/runtime bootstrap."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_panels_command_lists_readable_case_packages():
    result = subprocess.run(
        [sys.executable, '-m', 'toolbox', 'panels'], cwd=ROOT,
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    catalog = json.loads(result.stdout)
    panels = {entry['id']: entry for entry in catalog['panels']}
    assert catalog['offlineOnly'] is True
    assert panels['live20-classic']['caseCount'] == 20
    assert panels['live20-classic']['command'] == 'live20'
    assert panels['live20-classic']['casesFile'].endswith('live20-classic.json')
    assert panels['live10-starter']['caseCount'] == 10
    assert panels['live10-starter']['historical'] is False


@pytest.mark.parametrize('command,preset,count', [
    ('live10', 'live10-starter', 10),
    ('live10', 'live10-midgame', 10),
    ('live20', 'live20-classic', 20),
    ('live20', 'live20-classic-sprites', 20),
])
def test_explicit_preset_loads_its_versioned_cases_and_parent_fixture(command, preset, count):
    result = subprocess.run(
        [sys.executable, '-m', 'toolbox', command, '--preset', preset], cwd=ROOT,
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    source = ROOT / 'toolbox/fixtures/panels' / (preset + '.json')
    packaged = json.loads(source.read_text())
    assert report['caseCount'] == count
    assert report['cases'] == packaged['cases']
    assert report['preset'] == preset
    assert report['panelProvenance'] == packaged['provenance']
    assert report['preflightOnly'] is True


def test_default_live10_is_exact_historical_midgame_order_not_a_starter_subset():
    result = subprocess.run(
        [sys.executable, '-m', 'toolbox', 'live10'], cwd=ROOT,
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['preset'] == 'live10-midgame'
    expected = [
        ('night_missile', 'NightsEdge', 'MagicMissile'),
        ('crystal_repeater', 'AdamantiteRepeater', 'CrystalShard'),
        ('shadow_frost', 'ShadowFlameKnife', 'Frostbrand'),
        ('rain_spiders', 'SpiderStaff', 'NimbusRod'),
        ('ichor_spider_queen', 'QueenSpiderStaff', 'GoldenShower'),
        ('holy_storm', 'DaedalusStormbow', 'HolyArrow'),
        ('precision_titanium', 'TitaniumPickaxe', 'MechanicalLens'),
        ('frost_obsidian_guard', 'FrostsparkBoots', 'ObsidianShield'),
        ('radiant_forge', 'OrichalcumAnvil', 'SoulofLight'),
        ('meteor_star_cannon', 'StarCannon', 'MeteorStaff'),
    ]
    assert [(row['case'], row['itemA'], row['itemB']) for row in report['cases']] == expected
    assert report['historicalPreset'] is True and report['fullPreset'] is True


@pytest.mark.parametrize('filename,count,original_sha', [
    ('parents/live10-midgame.jsonl', 20, 'addb002f3bd6ace73daf250aad2307c010257528836ce3638dc2b17f7015075b'),
    ('items.jsonl', 39, '62b64ac70eaad27004e4d4e006c1bfb6ba44775b98a216ad2aaa4afaebb20e06'),
    ('parents/live20-classic-sprites.jsonl', 39, 'ea85bb4a86dbe5795c7fea41b40040688b0b1d3ce309f10bc79a239454543d40'),
])
def test_historical_parent_rows_preserve_original_source_bytes(filename, count, original_sha):
    import hashlib
    raw = (ROOT / 'toolbox/fixtures' / filename).read_bytes()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    assert hashlib.sha256(raw).hexdigest() == original_sha
    assert len(rows) == len({row['internalName'] for row in rows}) == count


def test_panel_specific_parent_context_is_not_merged_by_internal_name():
    from toolbox.live.options import build_parser
    from toolbox.live.panels import load_selection
    selected = {}
    for command in ('live10', 'live20'):
        args = build_parser().parse_args([])
        args.panel = command
        _, _, cases, _, _, _ = load_selection(args)
        selected[command] = {parent['internalName']: parent for _, a, b in cases for parent in (a, b)}
    assert set(selected['live10']) & set(selected['live20']) == {'QueenSpiderStaff'}
    assert selected['live10']['QueenSpiderStaff'] != selected['live20']['QueenSpiderStaff']


def test_original_sprite_request_variant_changes_only_sprite_reference():
    fixture = ROOT / 'toolbox/fixtures'
    plain = {row['internalName']: row for row in map(json.loads, (fixture / 'items.jsonl').read_bytes().splitlines())}
    sprites = {row['internalName']: row for row in map(json.loads, (fixture / 'parents/live20-classic-sprites.jsonl').read_bytes().splitlines())}
    assert plain.keys() == sprites.keys()
    for name, enriched in sprites.items():
        assert 'spriteReferenceRaw' in enriched
        assert plain[name] == {key: value for key, value in enriched.items() if key != 'spriteReferenceRaw'}


@pytest.mark.parametrize('flags,fragment', [
    (['--preset', 'live20-classic'], 'different live command'),
    (['--preset', '../live10-midgame'], 'invalid built-in preset'),
    (['--preset', 'live10-midgame', '--cases-file', 'unused.json'], 'mutually exclusive'),
])
def test_invalid_preset_selection_is_refused_before_running(flags, fragment):
    result = subprocess.run([sys.executable, '-m', 'toolbox', 'live10', *flags], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 2 and fragment in result.stderr
