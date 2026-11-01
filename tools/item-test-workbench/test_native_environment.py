"""Dependency discovery checks; fake files are never native execution evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from native_environment import discover


class NativeEnvironmentTests(unittest.TestCase):
    def test_restored_references_and_conventional_assets_are_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); repo = base / 'repo'; home = base / 'home'; packages = base / 'packages'
            reference = packages / 'tmodloader/1.2.3/lib/net8.0/tModLoader.dll'
            deps = repo / 'artifacts/dependencies'
            installation = home / '.local/share/Steam/steamapps/common/tModLoader'
            paths = [reference, deps / 'ParticleLibrary/ParticleLibrary.dll',
                     deps / 'Luminance/bin/Debug/net8.0/Luminance.dll',
                     deps / 'player-assets/Images/MagicPixel.png',
                     deps / 'particle-assets/Assets/Textures/Star.png',
                     installation / 'Libraries/Native/Linux/libFNA3D.so.0',
                     installation / 'Content/PixelShader.xnb']
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture')
            assets = repo / 'ModSources/InfiniCrafterLocal/obj/project.assets.json'
            assets.parent.mkdir(parents=True)
            assets.write_text(json.dumps({'libraries': {'tModLoader/1.2.3': {'path': 'tmodloader/1.2.3'}},
                                          'packageFolders': {str(packages): {}}}))
            original = {}
            env, notes = discover(repo, original, home)
            self.assertEqual(original, {})
            self.assertEqual(env['INFINI_TML_REFERENCE_DIR'], str(reference.parent))
            self.assertEqual(env['INFINI_TML_DEPS_SRC'], str(deps))
            self.assertEqual(env['INFINI_PLAYER_ASSET_DIR'], str(deps / 'player-assets'))
            self.assertEqual(env['INFINI_PARTICLE_ASSET_DIR'], str(deps / 'particle-assets'))
            self.assertEqual(env['INFINI_TML_NATIVE_DIR'], str(installation / 'Libraries/Native/Linux'))
            self.assertEqual(env['INFINI_TML_CONTENT_DIR'], str(installation / 'Content'))
            self.assertEqual(notes['INFINI_TML_REFERENCE_DIR'], 'restored project.assets.json')
            self.assertEqual(notes['INFINI_TML_CONTENT_DIR'], 'standard Linux Steam installation')

    def test_explicit_paths_take_precedence_and_ambiguous_restore_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp); assets = repo / 'ModSources/InfiniCrafterLocal/obj/project.assets.json'
            assets.parent.mkdir(parents=True)
            folders = [repo / 'p1', repo / 'p2']
            for folder in folders:
                ref = folder / 'tmodloader/1/lib/net8.0/tModLoader.dll'
                ref.parent.mkdir(parents=True); ref.write_bytes(b'fixture')
            assets.write_text(json.dumps({'libraries': {'tModLoader/1': {'path': 'tmodloader/1'}},
                                          'packageFolders': {str(folder): {} for folder in folders}}))
            env, notes = discover(repo, {}, repo)
            self.assertNotIn('INFINI_TML_REFERENCE_DIR', env)
            self.assertIn('multiple', notes['referenceDiscovery'])
            explicit = {'INFINI_TML_REFERENCE_DIR': '/missing/on/purpose',
                        'INFINI_PLAYER_ASSET_DIR': '/explicit/player', 'INFINI_TML_DIR': str(repo / 'custom')}
            (repo / 'custom/Content').mkdir(parents=True)
            (repo / 'custom/Content/PixelShader.xnb').write_bytes(b'fixture')
            env, notes = discover(repo, explicit, repo)
            self.assertEqual(env['INFINI_TML_REFERENCE_DIR'], '/missing/on/purpose')
            self.assertEqual(env['INFINI_PLAYER_ASSET_DIR'], '/explicit/player')
            self.assertEqual(env['INFINI_TML_CONTENT_DIR'], str(repo / 'custom/Content'))
            self.assertEqual(notes['INFINI_TML_REFERENCE_DIR'], 'environment')
            self.assertEqual(notes['INFINI_TML_CONTENT_DIR'], 'INFINI_TML_DIR')

    def test_malformed_restore_does_not_prevent_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); assets = root / 'ModSources/InfiniCrafterLocal/obj/project.assets.json'
            assets.parent.mkdir(parents=True); assets.write_text('{')
            env, notes = discover(root, {}, root)
            self.assertNotIn('INFINI_TML_REFERENCE_DIR', env)
            self.assertIn('cannot inspect', notes['referenceDiscovery'])

class WorkbenchDiscoveryIntegrationTests(unittest.TestCase):
    def test_discovered_paths_reach_build_and_changes_invalidate_no_build(self):
        from unittest.mock import patch
        import workbench as w
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); here = root / 'tools/item-test-workbench'
            here.mkdir(parents=True)
            (here / 'vanilla-item-assets.json').write_text('{}')
            mod = root / 'ModSources/InfiniCrafterLocal'
            (mod / 'obj').mkdir(parents=True)
            (mod / 'build.txt').write_text('version=1')
            packages = root / 'packages'
            reference = packages / 'tml/1/lib/net8.0/tModLoader.dll'
            deps = root / 'artifacts/dependencies'
            for path in [reference, deps / 'ParticleLibrary/ParticleLibrary.dll',
                         deps / 'Luminance/bin/Debug/net8.0/Luminance.dll',
                         deps / 'player-assets/Images/MagicPixel.png']:
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture')
            (mod / 'obj/project.assets.json').write_text(json.dumps({
                'libraries': {'tModLoader/1': {'path': 'tml/1'}}, 'packageFolders': {str(packages): {}}}))
            dll = here / 'bin/Release/net8.0/ItemTestWorkbench.dll'
            def build(command, **kwargs):
                self.assertIn('-p:InfiniTmlReferenceDir=' + str(reference.parent), command)
                self.assertEqual(kwargs['env']['INFINI_PLAYER_ASSET_DIR'], str(deps / 'player-assets'))
                self.assertEqual(kwargs['env']['INFINI_TML_DEPS_SRC'], str(deps))
                dll.parent.mkdir(parents=True); dll.write_bytes(b'host')
            with patch.dict(w.os.environ, {'DOTNET': '/bin/true'}, clear=True), \
                 patch.object(w, 'ROOT', root), patch.object(w, 'HERE', here), \
                 patch.object(w.subprocess, 'run', side_effect=build):
                w.build()
                self.assertEqual(w.native_executable(True)[0], dll)
                reference.write_bytes(b'different tML bytes')
                with self.assertRaisesRegex(RuntimeError, 'stale or modified'):
                    w.native_executable(True)


    def test_native_process_receives_discovered_graphics_environment(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import workbench as w
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); here = root / 'tools/item-test-workbench'; here.mkdir(parents=True)
            player = root / 'artifacts/dependencies/player-assets/Images/MagicPixel.png'
            player.parent.mkdir(parents=True); player.write_bytes(b'fixture')
            scene = root / 'scene.json'; scene.write_text('{}')
            dll = root / 'host.dll'; dll.write_bytes(b'fixture')
            args = SimpleNamespace(timeout=10, review='none', png=False, gif=False,
                                   vanilla_item='WoodenSword', item_boundary='fresh', item=None,
                                   scenario=scene, out=root / 'out', no_build=True)
            def process(command, **kwargs):
                self.assertEqual(kwargs['env']['INFINI_PLAYER_ASSET_DIR'], str(player.parent.parent))
                raise ValueError('native subprocess reached')
            with patch.dict(w.os.environ, {}, clear=True), patch.object(w, 'ROOT', root), \
                 patch.object(w, 'HERE', here), patch.object(w, 'native_executable', return_value=(dll, {})), \
                 patch.object(w.subprocess, 'run', side_effect=process):
                with self.assertRaisesRegex(ValueError, 'native subprocess reached'):
                    w.execute_run(args)


if __name__ == '__main__':
    unittest.main()
