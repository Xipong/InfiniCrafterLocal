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
    assert set(panels) == {'live10-midgame', 'live20-classic', 'live40-diverse'}
    assert panels['live40-diverse']['caseCount'] == 40
    assert panels['live40-diverse']['requiresRuntimeDump'] is True
    assert panels['live40-diverse']['runtimeDump'] is None


@pytest.mark.parametrize('command,preset,count', [
    ('live10', 'live10-midgame', 10),
    ('live20', 'live20-classic', 20),
    ('live40', 'live40-diverse', 40),
])
def test_explicit_preset_loads_its_versioned_cases_and_parent_fixture(tmp_path, command, preset, count):
    package = json.loads((ROOT / 'toolbox/fixtures/panels' / (preset + '.json')).read_text())
    names = sorted({row[k] for row in package['cases'] for k in ('itemA', 'itemB')})
    dump = tmp_path / 'synthetic-selection-only.jsonl'
    dump.write_text('\n'.join(json.dumps({'internalName': n, 'testOnly': True}) for n in names))
    result = subprocess.run(
        [sys.executable, '-m', 'toolbox', command, '--preset', preset, '--runtime-dump', str(dump)], cwd=ROOT,
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    source = ROOT / 'toolbox/fixtures/panels' / (preset + '.json')
    packaged = json.loads(source.read_text())
    assert report['caseCount'] == count
    assert report['cases'] == [{k: row[k] for k in ('case', 'itemA', 'itemB')} for row in packaged['cases']]
    assert report['preset'] == preset
    assert report['panelProvenance'] == packaged['provenance']
    assert report['preflightOnly'] is True


def test_revised_midgame_preserves_first_nine_routes():
    report = json.loads((ROOT / 'toolbox/fixtures/panels/live10-midgame.json').read_text())
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
        ('nebula_prism', 'NebulaBlaze', 'LastPrism'),
    ]
    assert [(row['case'], row['itemA'], row['itemB']) for row in report['cases']] == expected
    assert report['historical'] is False
    assert report['requiresRuntimeDump'] is True


@pytest.mark.parametrize('filename,count,original_sha', [
    ('items.jsonl', 39, '62b64ac70eaad27004e4d4e006c1bfb6ba44775b98a216ad2aaa4afaebb20e06'),
])
def test_historical_parent_rows_preserve_original_source_bytes(filename, count, original_sha):
    import hashlib
    raw = (ROOT / 'toolbox/fixtures' / filename).read_bytes()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    assert hashlib.sha256(raw).hexdigest() == original_sha
    assert len(rows) == len({row['internalName'] for row in rows}) == count
    if filename == 'items.jsonl':
        assert {row['sourceMod'] for row in rows} == {'Terraria'}


@pytest.mark.parametrize('flags,fragment', [
    (['--preset', 'live20-classic'], 'different live command'),
    (['--preset', 'live10-starter'], 'unknown built-in preset'),
    (['--preset', 'live20-classic-sprites'], 'unknown built-in preset'),
    (['--preset', '../live10-midgame'], 'invalid built-in preset'),
    (['--preset', 'live10-midgame', '--cases-file', 'unused.json'], 'mutually exclusive'),
])
def test_invalid_preset_selection_is_refused_before_running(flags, fragment):
    result = subprocess.run([sys.executable, '-m', 'toolbox', 'live10', *flags], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 2 and fragment in result.stderr


@pytest.mark.parametrize('command', ['live10', 'live40'])
def test_current_panels_require_external_dump(command):
    result = subprocess.run([sys.executable, '-m', 'toolbox', command], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 2
    assert 'requires an explicit current --runtime-dump' in result.stderr
    assert 'Traceback' not in result.stderr


def test_live40_keeps_original_order_orientation_and_control_pairs():
    rows = json.loads((ROOT / 'toolbox/fixtures/panels/live40-diverse.json').read_text())['cases']
    assert len(rows) == len({r['case'] for r in rows}) == 40
    for index, row in enumerate(rows, 1):
        assert row['sourceCase'] == f"{index:02d}-{row['itemA']}-{row['itemB']}"
        assert row['case'] == row['sourceCase'].lower().replace('-', '_')
    assert (rows[1]['itemA'], rows[1]['itemB']) == ('LastPrism', 'NebulaBlaze')
    assert (rows[39]['itemA'], rows[39]['itemB']) == ('NebulaBlaze', 'LastPrism')
    assert rows[38]['itemA'] == rows[38]['itemB'] == 'WoodenBow'


def test_live40_complete_ordered_roster_is_frozen():
    import hashlib
    rows = json.loads((ROOT / 'toolbox/fixtures/panels/live40-diverse.json').read_text())['cases']
    routes = [(r['case'], r['itemA'], r['itemB']) for r in rows]
    assert hashlib.sha256(json.dumps(routes, separators=(',', ':')).encode()).hexdigest() == 'bcc27d81a0aa9194f484cb04d4e612435d6700fe098dd51db6385563faa6ee98'


def test_live40_missing_parent_refuses_without_fixture_fallback(tmp_path):
    dump = tmp_path / 'partial.jsonl'
    dump.write_text('{"internalName":"LastPrism"}\n')
    result = subprocess.run([sys.executable, '-m', 'toolbox', 'live40', '--cases', '40_nebulablaze_lastprism', '--runtime-dump', str(dump)], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 2 and 'NebulaBlaze' in result.stderr
