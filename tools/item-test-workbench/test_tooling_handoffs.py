"""Offline public-consumer regressions. Synthetic files/processes are not native proof."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import workbench as w
import performance_review
import quality_review
import verify_fishing_resources
from fetch_player_assets import COMMIT
from test_agent_evidence import saved_run
from test_native_review import png
from test_performance_review import sample


def write_padded(path, value, size):
    """Valid JSON above the real input limit, without a giant Python string."""
    raw = json.dumps(value).encode()
    with path.open('wb') as stream:
        stream.write(raw)
        left = size - len(raw)
        chunk = b' ' * (1024 * 1024)
        while left > 0:
            count = min(left, len(chunk))
            stream.write(chunk[:count])
            left -= count


def cli(main, *arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.object(sys, 'argv', ['offline-test', *map(str, arguments)]), \
         contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main()
    return code, stdout.getvalue(), stderr.getvalue()


class NativeOutputHandoffTests(unittest.TestCase):
    def test_public_run_and_toolbox_report_accept_large_output_preserve_hash_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace, _ = saved_run(root/'input')
            dll = root/'host.dll'; dll.write_bytes(b'synthetic, never executable')
            provenance = dict(sourceSha256='test', dllSha256=w.digest(dll), nativeAssetSha256={},
                              runtimeFilesSha256={}, configuredReferences={})

            def execute(command, **kwargs):
                target = Path(command[command.index('--output') + 1])
                write_padded(target, trace, w.LIMIT + 1)
                return subprocess.CompletedProcess(command, 0, '', '')

            with patch.object(w, 'native_executable', return_value=(dll, provenance)), \
                 patch.object(w, 'build_state', return_value=provenance), \
                 patch.object(w, 'native_environment', return_value=({}, {})), \
                 patch.object(w.subprocess, 'run', side_effect=execute):
                code, stdout, stderr = cli(w.main, 'run', '--item', root/'input/item.json',
                    '--scenario', root/'input/scenario.json', '--out', root/'run', '--no-build', '--review', 'none')
            self.assertEqual(code, 0, stderr + stdout)
            receipt = json.loads(stdout)
            target = root/'run/native.json'
            self.assertEqual(target.stat().st_size, 64 * 1024 * 1024 + 1)
            self.assertEqual(receipt['traceSha256'], w.digest(target))
            self.assertEqual(w.read_json(Path(receipt['agentReport']))['integrity']['status'], 'verified')
            command = [sys.executable, '-m', 'toolbox', 'workbench', 'report', str(root/'run')]
            result = subprocess.run(command, cwd=w.ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['integrity']['status'], 'verified')
            with target.open('ab') as stream:
                stream.write(b' ')
            result = subprocess.run(command, cwd=w.ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stdout)['integrity']['status'], 'invalid')

    def test_large_trace_reaches_all_offline_reviews_including_contact_sheet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace, receipt = saved_run(root/'run')
            for state in trace['snapshots']:
                state['player'].update(generatedBuffTicks=0, generatedItemExhaustion=[])
            frames = []
            for tick in range(3):
                path = root/f'run/{tick}.png'; path.write_bytes(png())
                frames.append(dict(tick=tick, path=path.name, sha256=w.digest(path), width=1, height=1))
            trace['nativeRender'] = dict(backend='original_mod_draw_layers', itemArtworkRendered=False,
                projectileArtworkRendered=False, worldRendered=False, frames=frames)
            target = root/'run/native.json'
            write_padded(target, trace, w.LIMIT + 1)
            receipt['traceSha256'] = w.digest(target)
            (root/'run/run.json').write_text(json.dumps(receipt))
            for arguments in [('report', root/'run', '--out', root/'report', '--contact-sheet'),
                              ('inspect', target, '--summary'),
                              ('native-review', target, '--out', root/'native-review'),
                              ('timeline', target, '--out', root/'timeline.svg'),
                              ('frame', target, '--tick', '0', '--out', root/'frame.svg'),
                              ('render', target, '--out', root/'replay')]:
                with self.subTest(command=arguments[0]):
                    code, stdout, stderr = cli(w.main, *arguments)
                    self.assertEqual(code, 0, stderr + stdout)
            code, stdout, stderr = cli(quality_review.main, 'report', target, '--out', root/'quality')
            self.assertEqual(code, 0, stderr + stdout)
            self.assertEqual(json.loads(stdout)['renderedFrames'], 3)
            self.assertEqual(w.digest(target), receipt['traceSha256'])
            # Pixel integrity remains mandatory on the large-output path.
            (root/'run/0.png').write_bytes(b'corrupt PNG')
            self.assertEqual(cli(w.main, 'report', root/'run')[0], 2)
            self.assertEqual(cli(w.main, 'native-review', target, '--out', root/'bad-review')[0], 2)

    def test_performance_public_entry_measures_large_traces_without_native_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'item.json').write_text(json.dumps({'id': 'child', 'recipeMeta': {
                'parentIdentities': ['generated:parent']}}))
            (root/'parent.json').write_text('{"id":"parent"}')
            (root/'scenario.json').write_text(json.dumps(dict(ticks=2, seed=1, playerUpdate='full',
                dummy=dict(x=800, y=700), actions=[dict(tick=0, kind='primary')])))
            dll = root/'host.dll'; dll.write_bytes(b'synthetic, never executable')
            large = root/'large.json'; write_padded(large, sample(), w.LIMIT + 1)

            def execute(command, **kwargs):
                os.link(large, command[command.index('--output') + 1])
                return subprocess.CompletedProcess(command, 0, '', '')

            with patch.object(w, 'native_environment', return_value=({}, {})), \
                 patch.object(performance_review.subprocess, 'run', side_effect=execute):
                code, stdout, stderr = cli(performance_review.main, '--native-dll', dll,
                    '--item', root/'item.json', '--scenario', root/'scenario.json',
                    '--parent-item', 'generated:parent='+str(root/'parent.json'), '--out', root/'performance')
            self.assertEqual(code, 0, stderr + stdout)
            report = w.read_json(root/'performance/performance.json')
            self.assertTrue(report['allTrialsMeasured'])
            self.assertEqual(len(report['trials']), 6)
            self.assertTrue(all(t['observedTargetLifeLost'] == 13 for t in report['trials']))

    def test_public_entries_keep_separate_input_and_output_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saved_run(root/'input')
            oversized = root/'large.json'
            with oversized.open('wb') as stream:
                stream.truncate(w.NATIVE_TRACE_LIMIT + 1)
            for command in ('report', 'inspect', 'native-review', 'timeline', 'frame', 'render'):
                args = [command, oversized]
                if command in ('native-review', 'timeline', 'frame', 'render'):
                    args += ['--out', root/(command+'.svg')]
                if command == 'frame': args += ['--tick', '0']
                code, _, stderr = cli(w.main, *args)
                self.assertEqual(code, 2)
                self.assertIn('268435456 bytes', stderr)
            with oversized.open('wb') as stream:
                stream.truncate(w.LIMIT + 1)
            for source in ('item', 'scenario'):
                with self.subTest(source=source), patch.object(w, 'native_executable') as native:
                    args = ['run', '--item', oversized if source == 'item' else root/'input/item.json',
                            '--scenario', oversized if source == 'scenario' else root/'input/scenario.json',
                            '--out', root/'unused', '--no-build']
                    code, _, stderr = cli(w.main, *args)
                    self.assertEqual(code, 2)
                    self.assertIn('67108864 bytes', stderr)
                    native.assert_not_called()
            self.assertFalse((root/'unused').exists())


class FishingResourceHandoffTests(unittest.TestCase):
    def test_public_verifier_accepts_current_refusals_but_not_unrelated_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root/'assets/Images'; assets.mkdir(parents=True)
            (assets/'Item_2290.png').write_bytes(png())
            dll = root/'host.dll'; dll.write_bytes(b'not executable')
            (root/'InfiniCrafterLocal.dll').write_bytes(b'not executable')
            expected = {
                'missing': 'System.IO.FileNotFoundException: Missing pinned native PNG: Item_2290.png; provision the exact source asset in test',
                'corrupt': 'System.IO.InvalidDataException: Vanilla asset PNG size differs from pinned source: test/Images/Item_2290.png',
            }
            mutations = [None, ('missing', 'wrong-resource'), ('corrupt', 'wrong-class'),
                         ('missing', 'wrong-status'), ('corrupt', 'rendered'), ('missing', 'wrong-exit'),
                         ('missing', 'stack-only')]
            for index, mutation in enumerate(mutations):
                def execute(command, **kwargs):
                    target = Path(command[command.index('--output') + 1]); name = target.parent.name
                    if name == 'loaded':
                        value = dict(status='passed', nativeRender=dict(frames=[{}]*12,
                            vanillaProjectileAssets=dict(textures=[dict(path=str(assets/'Item_2290.png'))])))
                        code = 0
                    else:
                        value = dict(status='error', nativeRender=dict(frames=[]), error=expected.get(name,
                            'System.ArgumentException: vanillaItemTextures requires at most16 unique native IDs and drawVanillaProjectiles'))
                        code = 2
                        if mutation and mutation[0] == name:
                            if mutation[1] == 'wrong-resource': value['error'] = value['error'].replace('Item_2290.png', 'Item_22900.png')
                            if mutation[1] == 'wrong-class': value['error'] = value['error'].replace('InvalidDataException', 'IOException')
                            if mutation[1] == 'wrong-status': value['status'] = 'passed'
                            if mutation[1] == 'rendered': value['nativeRender']['frames'] = [{}]
                            if mutation[1] == 'wrong-exit': code = 1
                            if mutation[1] == 'stack-only': value['error'] = 'System.Exception: other failure\n' + value['error']
                    target.write_text(json.dumps(value))
                    return subprocess.CompletedProcess(command, code, '', '')
                with self.subTest(mutation=mutation), patch.object(verify_fishing_resources.subprocess, 'run', side_effect=execute):
                    code, stdout, stderr = cli(verify_fishing_resources.main, '--native-dll', dll,
                        '--assets', assets.parent, '--out', root/f'result-{index}')
                    self.assertEqual(code, 0 if mutation is None else 1, stderr + stdout)


class CiAssetReceiptHandoffTests(unittest.TestCase):
    def test_actual_ci_gate_uses_canonical_loaded_byte_receipts_and_keeps_refusals(self):
        workflow = (w.ROOT/'.github/workflows/workbench-native.yml').read_text()
        step = workflow.split('- name: Capture native vanilla weapon effects through probe\n', 1)[1]
        script = textwrap.dedent(step.split("python - <<'PY'\n", 1)[1].split('          PY\n', 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); captures = root/'artifacts/workbench-ci'
            index = dict(schemaVersion=1, communityCommit=COMMIT, sourceTreeSha='synthetic-tree',
                         entryFormat=['gitBlobSha1', 'bytes'], entries={})
            data = png(); sha = hashlib.sha256(data).hexdigest()
            blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            rows = {}
            for folder, names in [('vanilla-assets', ('Projectile_14.png', 'Projectile_982.png', 'Extra_98.png')),
                                  ('vanilla-legacy-assets', ('Projectile_14.png',))]:
                rows[folder] = []
                for name in names:
                    path = root/folder/'Images'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
                    index['entries'][name] = [blob, len(data)]
                    rows[folder].append(dict(asset=name, path=str(path), state='Loaded', sha256=sha,
                        gitBlobSha1=blob, bytes=len(data), width=1, height=1,
                        communityCommit=COMMIT, sourceTreeSha=index['sourceTreeSha']))
            (root/'vanilla-draw-assets.json').write_text(json.dumps(index))
            for label, native_type in [('vanilla-bullet', 14), ('vanilla-excalibur', 982)]:
                folder = captures/label; (folder/'runs/one').mkdir(parents=True)
                gif = folder/'test.gif'; gif.write_bytes(b'synthetic existence fixture, not a rendered GIF')
                (folder/'probe-result.json').write_text(json.dumps(dict(passed=True, cases=[dict(run='one', gif=str(gif))])))
                trace = dict(nativeRender=dict(frames=[dict(heldItemDrawCount=1, projectileGeometry=[dict(nativeType=native_type)])],
                    vanillaProjectileAssets=dict(textures=rows['vanilla-assets'])),
                    snapshots=[dict(events=[dict(kind='spawn', ammoItemIdUsed=97)])])
                (folder/'runs/one/native.json').write_text(json.dumps(trace))
            (captures/'vanilla-legacy-bullet').mkdir()
            (captures/'vanilla-legacy-bullet/probe-result.json').write_text('{"passed":true}')
            refused = dict(status='error', error='System.IO.FileNotFoundException: Missing resource\n   at WNativeVanillaProjectileAssets.RequireReady(Int32 id)',
                nativeRender=dict(vanillaProjectileAssets=dict(textures=rows['vanilla-legacy-assets'])))
            target = captures/'vanilla-legacy-excalibur-run/native.json'; target.parent.mkdir()
            target.write_text(json.dumps(refused))
            complete_path = captures/'vanilla-excalibur/runs/one/native.json'
            original = json.loads(complete_path.read_text())

            def check():
                with contextlib.chdir(root), patch.object(w, 'HERE', root), patch.dict(os.environ, RUNNER_TEMP=str(root)):
                    exec(compile(script, '<actual-workbench-ci-gate>', 'exec'), {})

            check()  # Current format has neither nativeType nor loadedBytesSha256.
            for key, bad in [('asset', 'Extra_98'), ('state', 'NotLoaded'), ('sha256', '0'*64),
                             ('gitBlobSha1', '0'*40), ('bytes', 0), ('width', 2),
                             ('communityCommit', 'wrong'), ('sourceTreeSha', 'wrong')]:
                changed = copy.deepcopy(original)
                changed['nativeRender']['vanillaProjectileAssets']['textures'][-1][key] = bad
                complete_path.write_text(json.dumps(changed))
                with self.subTest(field=key), self.assertRaises(SystemExit): check()
            complete_path.write_text(json.dumps(original))
            for change in ('status', 'exception', 'site', 'missing-pair-present'):
                changed = copy.deepcopy(refused)
                if change == 'status': changed['status'] = 'passed'
                if change == 'exception': changed['error'] = changed['error'].replace('FileNotFoundException', 'IOException')
                if change == 'site': changed['error'] = changed['error'].replace('RequireReady', 'OtherMethod')
                if change == 'missing-pair-present': changed['nativeRender']['vanillaProjectileAssets']['textures'].append(rows['vanilla-assets'][-1])
                target.write_text(json.dumps(changed))
                with self.subTest(refusal=change), self.assertRaises(SystemExit): check()
            target.write_text(json.dumps(refused))
            asset = root/'vanilla-assets/Images/Extra_98.png'
            asset.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, 'Git blob mismatch'): check()


if __name__ == '__main__':
    unittest.main()
