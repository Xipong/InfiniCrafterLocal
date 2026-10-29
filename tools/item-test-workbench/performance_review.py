#!/usr/bin/env python3
"""Run matched native lone/moving/grouped trials against exact authored parents.

This is a measurement report, not a balance verdict or a first-different-tick tool.
A caller supplies the actual use/hold/release/ammo/terrain scenario. Rendering may
be replaced by the native non-rendering client branch for vanilla controls only.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import workbench as w


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parent_candidates(item, supplied=None):
    supplied = supplied or {}
    identities = item.get('recipeMeta', {}).get('parentIdentities')
    if not isinstance(identities, list) or not identities or any(not isinstance(i, str) for i in identities):
        raise ValueError('Actual recipeMeta.parentIdentities required; display names and guessed parents are not accepted')
    result = []
    for index, identity in enumerate(dict.fromkeys(identities)):
        match = re.fullmatch(r'item:Terraria[/:]([A-Za-z][A-Za-z0-9_]*):([1-9][0-9]*)', identity)
        row = {'name': f'parent-{index + 1}', 'identity': identity, 'role': 'authoredParent'}
        if match:
            row.update(vanillaItem=match[1], recordedId=int(match[2]))
        elif identity.startswith('generated:') and identity in supplied:
            path = Path(supplied[identity]).resolve()
            if w.read_json(path).get('id') != identity.removeprefix('generated:'):
                raise ValueError('Supplied generated parent identity mismatch: ' + identity)
            row['item'] = str(path)
        else:
            row.update(status='notRun', reason='Exact generated parent JSON or supported vanilla stable identity unavailable; no substitution')
        result.append(row)
    return result


def requested_controls(identities):
    rows = []
    for index, identity in enumerate(dict.fromkeys(identities)):
        match = re.fullmatch(r'item:Terraria[/:]([A-Za-z][A-Za-z0-9_]*):([1-9][0-9]*)', identity)
        if match is None:
            raise ValueError('Requested control requires exact item:Terraria/StableName:ID identity')
        rows.append({'name': f'control-{index + 1}', 'identity': identity, 'role': 'requestedControl',
                     'vanillaItem': match[1], 'recordedId': int(match[2])})
    return rows


def scenarios(base):
    if type(base.get('seed')) is not int:
        raise ValueError('Explicit integer seed required for comparable trials')
    if base.get('playerUpdate') not in ('full', 'client_hybrid', 'client_vfx'):
        raise ValueError('Performance requires full native Player.Update (full/client_hybrid/client_vfx)')
    if not 2 <= base.get('ticks', 0) <= 600:
        raise ValueError('Compact performance trial requires2..600 ticks')
    if base.get('dummy', {}).get('mode', 'controlled') != 'controlled' or base.get('hostiles'):
        raise ValueError('Supply one controlled target; matrix explicitly owns secondary target layout')
    if any(a.get('kind') in ('equip', 'vanity', 'unequip', 'hurt_player', 'strike_hostile') for a in base.get('actions', [])):
        raise ValueError('Comparison uses identical unequipped loadout; equipment/reaction stimuli require separate review')
    if not any(a.get('kind') in ('primary', 'alt') for a in base.get('actions', [])):
        raise ValueError('Explicit native use input required')
    target = copy.deepcopy(base.get('dummy', {}))
    target.update(nativeType='zombie', mode='controlled', width=target.get('width', 32), height=target.get('height', 48),
                  life=target.get('life', 1000000), defense=target.get('defense', 0), vx=0, vy=0)
    if not all(k in target for k in ('x', 'y')):
        raise ValueError('Explicit comparable target x/y required')
    for name in ('lone', 'moving', 'grouped'):
        scene = copy.deepcopy(base)
        scene['dummy'] = copy.deepcopy(target)
        # Native NPC integration, not a scripted position trajectory. Keep all
        # starting positions identical; a bounded horizontal drift tests tracking.
        if name == 'moving':
            scene['dummy']['vx'] = .5
            if target['x'] + .5 * scene['ticks'] + target['width'] >= 1500:
                raise ValueError('Moving target would leave controlled world; shorten duration/reposition baseline')
        if name == 'grouped':
            scene['hostiles'] = [{k: v for k, v in target.items() if k in ('x', 'y', 'width', 'height', 'life', 'defense', 'vx', 'vy')} for _ in range(2)]
            scene['hostiles'][0]['x'] += target['width'] + 8
            scene['hostiles'][1]['y'] -= target['height'] + 8
            if scene['hostiles'][0]['x'] > 1500 or scene['hostiles'][1]['y'] < 16:
                raise ValueError('Grouped targets outside bounded world')
        # Outcome-specific expectations belong to item review, not copied from
        # one candidate to its parents. This detector only rejects invalid state.
        scene['assertions'] = [{'kind': 'no_nonfinite'}]
        yield name, scene


def repeated_schedule(base, every, hold, input_kind='primary'):
    if type(every) is not int or type(hold) is not int or not 1 <= hold < every <= 600:
        raise ValueError('Repeated input requires1 <= hold-ticks < repeat-every <=600')
    if input_kind not in ('primary', 'alt'):
        raise ValueError('Repeated input must be primary or alt')
    scene = copy.deepcopy(base)
    actions = [a for a in scene.get('actions', []) if a.get('kind') not in ('primary', 'alt', 'release')]
    for tick in range(0, scene['ticks'] - 1, every):
        actions.extend([{'tick': tick, 'kind': input_kind},
                        {'tick': min(tick + hold, scene['ticks'] - 1), 'kind': 'release'}])
    if len(actions) > 256:
        raise ValueError('Repeated input exceeds bounded256 native actions; increase interval')
    scene['actions'] = sorted(actions, key=lambda a: a['tick'])
    return scene


def target_rows(frame):
    return [frame['dummy'], *frame.get('hostiles', [])]


def measure(trace):
    w.validate_trace(trace)
    if trace['status'] != 'passed' or not trace.get('timeline', {}).get('complete'):
        return {'status': 'notMeasured', 'nativeStatus': trace['status'], 'reason': trace.get('error', 'Incomplete/failed native trial')}
    frames = [f for f in trace['snapshots'] if f['tick'] >= 0 and not f.get('phase')]
    before = next((f for f in trace['snapshots'] if f['tick'] == -1), None)
    if before is None or not frames or any('targetState' not in t for f in [before, *frames] for t in target_rows(f)):
        raise ValueError('Performance needs initial and post-update target state telemetry; older traces are not sufficient')
    if len({f['tick'] for f in frames}) != len(frames) or len(frames) != trace['timeline']['requestedTicks']:
        raise ValueError('Missing/duplicate native post-update performance ticks')
    events = [(f['tick'], e) for f in trace['snapshots'] for e in f.get('events', [])]
    channels = {}
    for kind, amount in [('item_hit', 'damageDone'), ('hit', 'damageDone'), ('native_direct_npc_damage', 'lifeLost')]:
        observed = [(tick, e) for tick, e in events if e.get('kind') == kind]
        channels[kind] = {'calls': len(observed), 'damage': sum(e.get(amount, 0) for _, e in observed),
                          'criticalHits': sum(bool(e.get('crit')) for _, e in observed),
                          'byTarget': dict(Counter_sum((str(e['npcId']), e.get(amount, 0)) for _, e in observed)),
                          'ticks': [tick for tick, _ in observed]}
    starts = {t['slot']: t for t in target_rows(before)}
    ends = {t['slot']: t for t in target_rows(frames[-1])}
    health = [{'slot': slot, 'nativeType': t['nativeType'], 'defense': t['targetState']['defense'],
               'initialLife': t['life'], 'finalLife': ends[slot]['life'], 'observedLifeLost': t['life'] - ends[slot]['life'],
               'activeAtEnd': ends[slot]['active'], 'start': [t['x'], t['y']], 'end': [ends[slot]['x'], ends[slot]['y']]}
              for slot, t in starts.items()]
    uptime = Counter()
    for frame in frames:
        for target in target_rows(frame):
            for buff in target['targetState']['nativeBuffs']:
                uptime[(target['slot'], buff['id'])] += 1
    inventory = lambda f: {i['slot']: i for i in f['player']['inventory']}
    initial, final = inventory(before), inventory(frames[-1])
    debits = [{'slot': slot, 'nativeType': item['nativeType'], 'initialStack': item['stack'],
               'finalStack': final.get(slot, {}).get('stack', 0),
               'netStackDebit': item['stack'] - final.get(slot, {}).get('stack', 0)} for slot, item in initial.items()]
    use_ticks = [tick for tick, e in events if e.get('kind') == 'native_item_time_applied']
    intervals = [b-a for a, b in zip(use_ticks, use_ticks[1:])]
    return {'status': 'measured', 'initialItem': before['player'].get('itemProjection', {}),
            'ammoAvailableAtStart': not before['player'].get('itemProjection', {}).get('useAmmo') or any(i.get('ammoCategory') == before['player']['itemProjection']['useAmmo'] and i['stack'] > 0 for i in before['player']['inventory']),
            'rng': trace.get('execution', {}).get('rng'),
            'initialPlayer': {k: before['player'].get(k) for k in ('x', 'y', 'life', 'mana', 'defense', 'genericCrit', 'armor')},
            'initialAmmo': [i for i in before['player']['inventory'] if i['slot'] != 0], 'durationTicks': len(frames), 'secondsAt60Hz': len(frames)/60,
            'targets': health, 'observedTargetLifeLost': sum(r['observedLifeLost'] for r in health),
            'channels': channels, 'channelScope': 'Native hit callbacks and direct-damage calls. Do not add channels blindly: direct callbacks may nest; total health loss also includes native DoT/regeneration.',
            'statusUptime': [{'target': slot, 'buffId': buff, 'observedTicks': count, 'fractionOfTrial': count/len(frames)} for (slot, buff), count in sorted(uptime.items())],
            'cadence': {'nativeUseClockTicks': use_ticks, 'intervalTicks': intervals, 'meanIntervalTicks': sum(intervals)/len(intervals) if intervals else None,
                        'scope': 'Actual Player.ApplyItemTime calls. One application can spawn several projectiles; not inferred from useTime or headline damage.'},
            'resources': {'observedManaPayments': sum(e.get('spent', 0) for _, e in events if e.get('kind') == 'native_mana_payment'),
                          'initialMana': before['player']['mana'], 'finalMana': frames[-1]['player']['mana'], 'inventory': debits,
                          'ammoConsumptionCallbacks': sum(e.get('kind') == 'native_ammo_consumption' for _, e in events)},
            'input': {'heldUseTicks': sum(bool(f['player']['controlUseItem']) for f in frames), 'channelTicks': sum(bool(f['player']['channel']) for f in frames)},
            'activeProjectilesAtEnd': sum(bool(p.get('active')) for p in frames[-1].get('projectiles', [])),
            'targetDied': any(not r['activeAtEnd'] or r['finalLife'] <= 0 for r in health)}


def Counter_sum(pairs):
    result = Counter()
    for key, value in pairs:
        result[key] += value
    return result


def mechanical_scene(scene):
    return {k: v for k, v in scene.items() if k not in ('nativeRender', 'vanillaAssetRoot', 'assertions', 'playerUpdate')}


def native_identity_matches(candidate, trace):
    actual = trace.get("input", {})
    return actual.get("nativeItemName") == candidate["vanillaItem"] and actual.get("nativeItemId") == candidate["recordedId"]


def assess_comparisons(rows, names):
    comparisons = []
    for name in names:
        group = [r for r in rows if r['scene'] == name]
        measured = [r for r in group if r['status'] == 'measured']
        reasons = []
        if len(measured) != len(group): reasons.append('Not all actual parents/candidates measured; missing/noncombat controls are not zero damage')
        if len({r['mechanicalSceneSha256'] for r in measured}) > 1: reasons.append('Requested mechanical scene differs')
        if len({r['executionMode'] for r in measured}) > 1: reasons.append('Mixed native client branches; update lifecycle equivalence is not established')
        if len({json.dumps(r.get('rng'), sort_keys=True) for r in measured}) > 1 or any(not r.get('rng') for r in measured): reasons.append('Native pre-gameplay seed reset not established equal')
        if len({json.dumps([r.get('initialPlayer'),r.get('initialAmmo')], sort_keys=True) for r in measured}) > 1: reasons.append('Observed initial native player/ammo loadout differs')
        if any(r.get('ammoAvailableAtStart') is False for r in measured): reasons.append('At least one ammo weapon starts without matching ammo; zero output is not a damage benchmark')
        if any(r.get('targetDied') for r in measured): reasons.append('At least one target died; remaining duration is censored')
        comparisons.append({'scene': name, 'status': 'limited' if reasons else 'matched', 'limitations': reasons, 'scope': 'Matched initial conditions, not identical weapon RNG outcomes or a balance verdict'})
    return comparisons


def run(args):
    item_path, scenario_path = args.item.resolve(), args.scenario.resolve()
    item, base = w.read_json(item_path), w.read_json(scenario_path)
    mappings = {}
    for value in args.parent_item:
        identity, path = value.split('=', 1)
        if identity in mappings:
            raise ValueError('Duplicate supplied parent identity')
        mappings[identity] = path
    candidates = [{'name': 'generated', 'identity': 'generated:' + item['id'], 'role': 'generated', 'item': str(item_path)}, *parent_candidates(item, mappings), *requested_controls(args.control)]
    matrix = []
    if args.input_pattern in ('supplied', 'both'):
        matrix += [(('supplied-' if args.input_pattern == 'both' else '') + name, scene) for name, scene in scenarios(base)]
    if args.input_pattern in ('repeated', 'both'):
        repeated = repeated_schedule(base, args.repeat_every, args.hold_ticks, args.repeat_input)
        matrix += [('repeated-' + name, scene) for name, scene in scenarios(repeated)]
    plan = {'candidates': candidates, 'scenarios': [name for name, _ in matrix], 'baseScenarioSha256': sha(scenario_path),
            'inputPattern': {'mode': args.input_pattern, 'repeatEveryTicks': args.repeat_every, 'holdTicks': args.hold_ticks, 'repeatInput': args.repeat_input if args.input_pattern != 'supplied' else None},
            'scope': 'Matched native item performance; separate processes, fixed seed/positions/input/duration/loadout. No quality verdict.'}
    if args.plan:
        print(json.dumps(plan, indent=2)); return 0
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a fresh performance evidence directory')
    out.mkdir(parents=True, exist_ok=True)
    if not args.native_dll:
        w.build()
    dll = (args.native_dll or w.HERE / 'bin/Release/net8.0/ItemTestWorkbench.dll').resolve()
    dll_hash = sha(dll)
    rows = []
    for scene_name, scenario in matrix:
        for candidate in candidates:
            row = {'candidate': candidate['name'], 'identity': candidate['identity'], 'role': candidate['role'], 'scene': scene_name}
            rows.append(row)
            if candidate.get('status') == 'notRun':
                row.update(status='notRun', reason=candidate['reason']); continue
            directory = out / (scene_name + '-' + candidate['name']); directory.mkdir()
            chosen = copy.deepcopy(scenario)
            if chosen['playerUpdate'] == 'client_vfx':
                settings = chosen.setdefault('nativeRender', {})
                # Same non-drawing client/VFX/dust update lifecycle for every candidate.
                # Keep generated publication loading; never remove required mechanics.
                settings.update(capture=False, drawPlayer=False, drawNativeDust=False)
                for key in ('drawPlacedBodies', 'drawDroppedItems', 'playerAssetRoot', 'dummyAssetRoot'):
                    settings.pop(key, None)
            if 'vanillaItem' in candidate and chosen['playerUpdate'] in ('client_vfx', 'client_hybrid'):
                if chosen['playerUpdate'] == 'client_vfx':
                    chosen['nativeRender'] = {k: v for k, v in chosen['nativeRender'].items() if k not in ('drawArtwork', 'artworkFiles')}
                    chosen['nativeRender']['drawArtwork'] = False
                if not args.vanilla_assets:
                    row.update(status='notRun', reason='Vanilla client contact requires --vanilla-assets'); continue
                chosen['vanillaAssetRoot'] = str(args.vanilla_assets.resolve())
            scene_path = directory / 'scenario.json'; scene_path.write_text(json.dumps(chosen, indent=2))
            command = [os.environ.get('DOTNET', 'dotnet'), str(dll)]
            if 'item' in candidate:
                original = Path(candidate['item']); archived = directory / 'item.json'; archived.write_bytes(original.read_bytes())
                command += ['--item', str(archived), '--item-boundary', args.item_boundary]
                row['itemSha256'] = sha(archived)
            else:
                command += ['--vanilla-item', candidate['vanillaItem']]
            command += ['--scenario', str(scene_path), '--output', str(directory/'native.json')]
            row.update(scenarioSha256=sha(scene_path), mechanicalSceneSha256=hashlib.sha256(json.dumps(mechanical_scene(chosen), sort_keys=True).encode()).hexdigest(), executionMode=chosen['playerUpdate'])
            try:
                result = subprocess.run(command, cwd=w.ROOT, capture_output=True, text=True, timeout=args.timeout)
                (directory/'stdout.log').write_text(result.stdout); (directory/'stderr.log').write_text(result.stderr)
                row['exitCode'] = result.returncode
                trace = w.read_json(directory/'native.json')
                row['traceSha256'] = sha(directory/'native.json')
                row.update(measure(trace))
                if result.returncode != {'passed': 0, 'failed': 1, 'error': 2}.get(trace['status']):
                    row.update(status='notMeasured', reason='Native process status disagrees with terminal trace')
                if 'vanillaItem' in candidate:
                    actual = trace.get('input', {}).get('nativeItemName')
                    row['resolvedNativeName'] = actual
                    if row['status'] == 'measured' and not native_identity_matches(candidate, trace):
                        row.update(status='notMeasured', reason='Native stable-name identity mismatch')
            except (subprocess.TimeoutExpired, OSError, ValueError, KeyError, TypeError) as error:
                if isinstance(error, subprocess.TimeoutExpired):
                    for name, output in [('stdout.log', error.stdout), ('stderr.log', error.stderr)]:
                        (directory/name).write_text(output.decode(errors='replace') if isinstance(output, bytes) else output or '')
                row.update(status='notMeasured', reason=str(error))
            (out/'performance.json').write_text(json.dumps({**plan, 'complete': False, 'trials': rows}, indent=2))
    comparisons = assess_comparisons(rows, [name for name, _ in matrix])
    unchanged = sha(dll) == dll_hash
    summary = {**plan, 'complete': True, 'nativeDllSha256': dll_hash, 'executableUnchanged': unchanged,
               'buildProvenance': 'Explicit native executable; preserve independent build receipt. This is not normal wrapper provenance certification.',
               'requestedControlComparisons': assess_comparisons([r for r in rows if r['role'] in ('generated', 'requestedControl')], [name for name, _ in matrix]) if args.control else [],
               'allRequestedControlsMeasured': bool(args.control) and unchanged and all(r['status'] == 'measured' for r in rows if r['role'] in ('generated', 'requestedControl')),
               'comparisons': comparisons, 'allTrialsMeasured': unchanged and all(r['status'] == 'measured' for r in rows), 'trials': rows,
               'caveats': ['No automatic balance/visual PASS. Noncombat or missing parents are not zero-damage controls.',
                           'Native RNG is seeded, but weapons consume RNG differently; one seed is not a population estimate.',
                           'Controlled target AI/gravity/contact disabled. Native armor, immunity, collision, buffs and DoT remain active.',
                           'Uptime counts end-of-tick presence; first/last sub-tick changes are not resolved.',
                           'Damage channels can overlap; actual target life loss is separate. Dead targets censor the remainder; still-active projectiles at the window end have not necessarily landed their damage.',
                           'Identical unarmored player and ammo inventory; no prefixes/accessory/set progression.',
                           'client_vfx trials execute equal native dust/lighting/VFX update phases with all drawing disabled. Assets still load for generated material admission and vanilla contact geometry. Effects requiring actual draw hooks may refuse; full-world parity not claimed.']}
    (out/'performance.json').write_text(json.dumps(summary, indent=2))
    lines = ['# Native item performance', '', 'Measurements only — no balance or visual approval.', '',
             '| Scene | Candidate / role | Status | Target HP lost | Item / projectile hits | Mana paid |', '|---|---|---|---:|---:|---:|']
    for r in rows:
        channels = r.get('channels', {})
        lines.append(f"| {r['scene']} | {r['identity']} ({r['role']}) | {r['status']} | {r.get('observedTargetLifeLost', '—')} | {channels.get('item_hit', {}).get('calls', '—')} / {channels.get('hit', {}).get('calls', '—')} | {r.get('resources', {}).get('observedManaPayments', '—')} |")
        if r.get('reason'): lines.append('\nReason: ' + r['reason'].replace('\n', ' ') + '\n')
    lines += ['', *[c['scene'] + ': ' + c['status'] + (' — ' + '; '.join(c['limitations']) if c['limitations'] else '') for c in comparisons], '', 'Detailed channels, target movement/defense, uptime, input, use-clock intervals and stack debits: `performance.json`.', '', *['- '+c for c in summary['caveats']]]
    if summary['requestedControlComparisons']:
        lines += ['', '## Requested controls (separate from authored parents)', *[c['scene'] + ': ' + c['status'] + (' — ' + '; '.join(c['limitations']) if c['limitations'] else '') for c in summary['requestedControlComparisons']]]
    (out/'performance.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'complete': True, 'allTrialsMeasured': summary['allTrialsMeasured'], 'allRequestedControlsMeasured': summary['allRequestedControlsMeasured'], 'trials': len(rows), 'report': str(out/'performance.md')}))
    return 0 if summary['allTrialsMeasured'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--item', type=Path, required=True); parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True); parser.add_argument('--native-dll', type=Path)
    parser.add_argument('--item-boundary', choices=('fresh', 'local_cache'), default='fresh')
    parser.add_argument('--vanilla-assets', type=Path); parser.add_argument('--parent-item', action='append', default=[], metavar='IDENTITY=PATH')
    parser.add_argument('--control', action='append', default=[], metavar='item:Terraria/StableName:ID', help='Additional explicitly requested vanilla benchmark, never relabeled as a recipe parent')
    parser.add_argument('--input-pattern', choices=('supplied', 'repeated', 'both'), default='supplied')
    parser.add_argument('--repeat-every', type=int); parser.add_argument('--hold-ticks', type=int)
    parser.add_argument('--repeat-input', choices=('primary', 'alt'), default='primary')
    parser.add_argument('--timeout', type=int, default=180); parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    if args.input_pattern == 'supplied' and (args.repeat_every is not None or args.hold_ticks is not None): parser.error('repeat timing requires --input-pattern repeated or both')
    if not 1 <= args.timeout <= 3600: parser.error('timeout must be1..3600')
    try: return run(args)
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({'status': 'error', 'error': str(error)})); return 2


if __name__ == '__main__':
    sys.exit(main())
