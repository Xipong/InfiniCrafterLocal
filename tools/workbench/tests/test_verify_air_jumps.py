"""Current AirJump fixtures and public verifier wiring; no native/game/GPU execution."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest.mock import patch

import workbench as w
from python import verify_air_jumps as jumps

sys.path.insert(0, str(w.ROOT / 'generator'))
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.vfx.validation import validate_vfx_manifest_wire
from infini_local.storage.image_store import publish


class AirJumpFixtureTests(unittest.TestCase):
    def test_direct_entrypoint_help_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(w.HERE / 'python/verify_air_jumps.py'), '--help'],
                cwd=directory, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            for flag in ('--out', '--native-dll', '--no-build', '--render'):
                self.assertIn(flag, result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cpu_fixture_is_current_and_creates_no_art(self):
        source = w.HERE / 'fixtures/synthetic-reaction-accessory.json'
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            item, scene = jumps.prepare(Path(directory), False)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertTrue(validate_runtime_wire(item)['ok'], validate_runtime_wire(item)['errors'])
            self.assertTrue(validate_vfx_manifest_wire(item)['ok'], validate_vfx_manifest_wire(item)['errors'])
            self.assertEqual(item['vfxManifest']['slots'], [])
            self.assertNotIn('nativeRender', scene)
            self.assertEqual(scene['playerUpdate'], 'full')
            self.assertEqual(scene['tiles'][0]['tileY'], 100)
            item['accessory']['playerEffect']['airJump']['count'] = 99
            self.assertEqual(jumps.prepare(Path(directory), False)[0]['accessory']['playerEffect']['airJump']['count'], 2)
        self.assertEqual(source.read_bytes(), before)

    def test_render_fixture_uses_current_particle_wire_and_scoped_publications(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item, scene = jumps.prepare(root, True)
            self.assertTrue(validate_runtime_wire(item)['ok'], validate_runtime_wire(item)['errors'])
            report = validate_vfx_manifest_wire(item)
            self.assertTrue(report['ok'], report['errors'])
            slot, = item['vfxManifest']['slots']
            self.assertEqual((slot['rendererKind'], slot['event'], slot['entityId']), ('libraryParticle', 'on_jump', 'item'))
            self.assertEqual(slot['particle']['textureId'], 'star')
            self.assertEqual(slot['particle']['spawn']['shape'], 'point')
            no_producer = copy.deepcopy(item)
            no_producer['accessory']['playerEffect'].pop('airJump')
            self.assertFalse(validate_vfx_manifest_wire(no_producer)['ok'])
            self.assertEqual(scene['playerUpdate'], 'client_vfx')
            files = [Path(p) for p in scene['nativeRender']['artworkFiles']]
            self.assertEqual(len(files), 2)
            for source, role, suffix in zip(files, ('item', 'equip_overlay'), ('', '_equip_overlay')):
                identity = json.dumps([item['id'], role, '', item['id'] + suffix], separators=(',', ':')).encode('ascii')
                canonical = publish(root / 'store', item, role, identity, source)
                self.assertEqual(source.name, canonical.name)
                self.assertEqual(source.read_bytes(), canonical.read_bytes())

    def test_cpu_verifier_uses_discovered_process_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dll = root / 'stand.dll'; dll.write_bytes(b'synthetic, never executed')
            (root / 'InfiniCrafterLocal.dll').write_bytes(b'synthetic, never executed')
            env = dict(DOTNET='/discovered/dotnet', INFINI_TML_NATIVE_DIR='/discovered/native')

            def execute(command: list[str], **kwargs: Any):
                self.assertEqual(command[0], env['DOTNET'])
                self.assertEqual(kwargs['env'], env)
                output = Path(command[command.index('--output') + 1])
                scenario = w.read_json(Path(command[command.index('--scenario') + 1]))
                controls = [a for a in scenario['actions'] if a['kind'] == 'controls']
                functional = scenario['actions'][0]['kind'] == 'equip'
                starts = [15, 25] if functional and len(controls) > 2 else []
                snapshots = []
                for tick in range(scenario['ticks']):
                    events = []
                    if controls:
                        events.append(dict(kind='native_jump_movement', groundJumpStarted=tick == 5,
                            sharedJumpSpeedBefore=5.0, sharedJumpSpeedAfter=5.0, vyAfter=-9.25))
                    if tick in starts:
                        events.extend([dict(kind='native_extra_jump_started', vyAfter=-9.25, jumpTicks=4),
                            dict(kind='native_air_jump_vfx_dispatch')])
                    snapshots.append(dict(tick=tick, player=dict(vy=-8.9), events=events))
                output.write_text(json.dumps(dict(status='passed', snapshots=snapshots)))
                return subprocess.CompletedProcess(command, 0, '', '')

            with patch.object(sys, 'argv', ['verify_air_jumps.py', '--native-dll', str(dll), '--no-build', '--out', str(root/'run')]), \
                 patch.object(w, 'native_environment', return_value=(env, {})), \
                 patch.object(jumps.subprocess, 'run', side_effect=execute), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(jumps.main(), 0)
            summary = w.read_json(root/'run/summary.json')
            self.assertTrue(summary['passed'])
            self.assertEqual([row['name'] for row in summary['checks']], ['extra', 'ground-only', 'no-input', 'vanity'])


if __name__ == '__main__':
    unittest.main()
