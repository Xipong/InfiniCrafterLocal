"""Current indexed publications for explicit Workbench artwork, not native render evidence."""
import argparse
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from PIL import Image
import workbench as w


class ArtworkPublicationTests(unittest.TestCase):
    @staticmethod
    def png(color):
        stream = io.BytesIO()
        Image.new('RGBA', (16, 16), color).save(stream, format='PNG')
        return stream.getvalue()

    def test_current_index_owns_exact_bytes_without_mutating_definition(self):
        data = dict(id='fixture', recipeMeta=dict(worldId='0'))
        original = copy.deepcopy(data)
        identity = json.dumps(['fixture', 'item', '', 'fixture'], separators=(',', ':')).encode('ascii')
        raw = self.png((80, 200, 255, 255))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            published = w.publish_artwork(out, data, 'item', identity, raw)
            from infini_local.storage.image_store import publish, resolve
            self.assertEqual(published.read_bytes(), raw)
            self.assertEqual(resolve(out / 'images', published.name), published)
            self.assertRegex(published.name, r'^item--[a-f0-9]{64}\.png$')
            self.assertEqual(publish(out / 'independent', data, 'item', identity, published).name, published.name)
            self.assertEqual(w.publish_artwork(out, data, 'item', identity, raw), published)
            self.assertEqual(list(out.glob('.artwork-source-*')), [])
        self.assertEqual(data, original)

    def test_world_item_role_request_and_png_each_change_publication_identity(self):
        data = dict(id='fixture', recipeMeta=dict(worldId='0'))
        identity = b'["fixture","item","","fixture"]'
        raw = self.png((80, 200, 255, 255))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            original = w.publish_artwork(out, data, 'item', identity, raw)
            variants = [
                (dict(id='fixture', recipeMeta=dict(worldId='1')), 'item', identity, raw),
                (dict(id='other', recipeMeta=dict(worldId='0')), 'item', identity, raw),
                (data, 'equip_overlay', identity, raw),
                (data, 'item', b'["changed"]', raw),
                (data, 'item', identity, self.png((255, 80, 40, 255))),
            ]
            names = {original.name}
            for candidate, role, request, image in variants:
                path = w.publish_artwork(out, candidate, role, request, image)
                self.assertNotIn(path.name, names)
                names.add(path.name)
            self.assertEqual(original.read_bytes(), raw)

    def test_invalid_png_is_refused_and_temporary_source_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with self.assertRaises(ValueError):
                w.publish_artwork(out, dict(id='fixture'), 'item', b'[]', b'not a png')
            self.assertEqual(list(out.iterdir()), [])


class LunarPublicationTests(unittest.TestCase):
    def test_bundled_input_is_republished_and_delivery_uses_current_basename(self):
        builder = w.HERE / 'examples/lunar-harpoon/build.py'
        bundled, = (builder.parent / 'assets').glob('*.png')
        before = bundled.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / 'build'
            result = subprocess.run([sys.executable, str(builder), '--player-assets', str(root / 'player'),
                                     '--out', str(out)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = w.read_json(out / 'item.json')
            scene = w.read_json(out / 'scenario.json')
            self.assertEqual(data.get('recipeMeta'), {'worldScoped': True, 'worldId': '853355558'})
            self.assertEqual(scene['worldId'], 853355558)
            publication, = map(Path, scene['nativeRender']['artworkFiles'])
            self.assertEqual(publication.read_bytes(), before)
            self.assertRegex(publication.name, r'^item--[a-f0-9]{64}\.png$')
            self.assertEqual(data['visual']['spritePath'], publication.name)
            for entity in data['runtimeProgram']['entities']:
                self.assertEqual(entity['visual']['spritePath'], publication.name)
            from infini_local.storage.image_store import resolve
            self.assertEqual(resolve(out / 'images', publication.name), publication)
            index, = (out / 'images/.index').glob('*.json')
            self.assertEqual(w.read_json(index)['worldId'], data['recipeMeta']['worldId'])
            from python import probe
            parser = argparse.ArgumentParser()
            probe.add_parser(parser.add_subparsers(dest='command', required=True))
            args = parser.parse_args(['probe', '--item', str(out / 'item.json'), '--gif', '--prepare'])
            plan = probe.plan_probe(args)
            planned_scene, = plan['scenes'].values()
            self.assertEqual(planned_scene['worldId'], scene['worldId'])
        self.assertEqual(bundled.read_bytes(), before)

    def test_demo_refuses_missing_or_mismatched_authored_world_without_restamping(self):
        builder = w.HERE / 'examples/lunar-harpoon/build.py'
        spec = importlib.util.spec_from_file_location('lunar_builder_world_test', builder)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        scenario = dict(worldId=853355558)
        for source in [{}, dict(recipeMeta=dict(worldScoped=False, worldId='853355558')),
                       dict(recipeMeta=dict(worldScoped=True, worldId='0'))]:
            original = copy.deepcopy(source)
            with self.assertRaisesRegex(ValueError, 'same explicit Terraria world'):
                module.require_demo_world(source, scenario)
            self.assertEqual(source, original)
        current = dict(recipeMeta=dict(worldScoped=True, worldId='853355558'))
        module.require_demo_world(current, scenario)

    def test_demo_refuses_different_art_without_publishing(self):
        builder = w.HERE / 'examples/lunar-harpoon/build.py'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'changed.png'
            source.write_bytes(ArtworkPublicationTests.png((80, 200, 255, 255)))
            out = root / 'build'
            result = subprocess.run([sys.executable, str(builder), '--asset', str(source),
                                     '--player-assets', str(root / 'player'), '--out', str(out)],
                                    capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('exact supplied PNG', result.stderr)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
