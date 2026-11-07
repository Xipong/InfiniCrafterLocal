"""CPU-only contract/observer tests; synthetic telemetry is not native evidence."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from collections.abc import Callable
from typing import Any

from PIL import Image
import workbench as w
from python import verify_particles as particles

sys.path.insert(0, str(w.ROOT / 'generator'))
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.vfx.validation import validate_vfx_manifest_wire
from infini_local.qa.capability_witnesses import build_capability_witness


class CurrentFixtureTests(unittest.TestCase):
    def test_maintained_synthetic_inputs_are_current_without_adapters(self):
        paths = sorted((w.HERE / 'fixtures').glob('synthetic-*.json'))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path.name):
                data = json.loads(path.read_text())
                report = validate_runtime_wire(data)
                self.assertTrue(report['ok'], report['errors'])
                if 'vfxManifest' in data:
                    report = validate_vfx_manifest_wire(data)
                    self.assertTrue(report['ok'], report['errors'])

    def test_particle_variants_admit_with_current_producer(self):
        straight = compile_runtime_program(build_capability_witness('move_straight'))
        straight.pop('runtimeContract')  # Synthetic experiment authors its own slots, not compiler receipts.
        root = next(e for e in straight['runtimeProgram']['entities']
                    if e['id'] == straight['runtimeProgram']['primaryEntityId'])
        old_id = root['id']
        root['id'] = straight['runtimeProgram']['primaryEntityId'] = 'root'
        for binding in straight['runtimeProgram']['bindings']:
            if binding['usePolicy']['action'].get('targetId') == old_id:
                binding['usePolicy']['action']['targetId'] = 'root'
        straight['vfxManifest'] = dict(schema='infini.vfx.runtime-events.v16', recipeId='synthetic-particles',
            budget=dict(maxParticlesPerTick=32, maxParticlesTotal=1000, maxDrawCalls=64), slots=[])
        before = copy.deepcopy(straight)
        for texture in particles.TEXTURES:
            with self.subTest(texture=texture):
                item = particles.particle_fixture(straight, texture)
                self.assertEqual(straight, before)
                self.assertTrue(validate_runtime_wire(item)['ok'], validate_runtime_wire(item)['errors'])
                report = validate_vfx_manifest_wire(item)
                self.assertTrue(report['ok'], report['errors'])
                slot = item['vfxManifest']['slots'][0]
                self.assertEqual(slot['event'], 'on_hit')
                for required in ('spawn', 'sampling'):
                    invalid = copy.deepcopy(item)
                    del invalid['vfxManifest']['slots'][0]['particle'][required]
                    self.assertFalse(validate_vfx_manifest_wire(invalid)['ok'])


class ParticleObserverTests(unittest.TestCase):
    def test_resources_require_selected_texture_effect_and_magicpixel(self):
        for texture, (path, digest) in particles.TEXTURES.items():
            render = dict(resourceReady=True, originalParticleLibraryEffect=True, libraryBuffers=4,
                effectSha256=particles.EFFECT_SHA256, starSha256=digest,
                readyLibraryTexturePaths=[path],
                luminanceResources=dict(selectedTextureSha256={path: digest}),
                magicPixelResource=dict(sha256=particles.MAGIC_PIXEL_SHA256, playerArtworkLoaded=False),
                itemArtworkRendered=False, projectileArtworkRendered=False, worldRendered=False, soundValidated=False)
            self.assertTrue(all(particles.resource_checks(render, texture).values()))
            for key in ('effectSha256', 'starSha256' if texture == 'star' else 'luminanceResources',
                        'readyLibraryTexturePaths', 'magicPixelResource'):
                invalid = copy.deepcopy(render); del invalid[key]
                self.assertFalse(all(particles.resource_checks(invalid, texture).values()), key)

    def test_vfx_off_keeps_original_effect_without_inventing_selected_resources(self):
        render = dict(resourceReady=True, originalParticleLibraryEffect=True, libraryBuffers=0,
            effectSha256=particles.EFFECT_SHA256, readyLibraryTexturePaths=[],
            magicPixelResource=dict(sha256=particles.MAGIC_PIXEL_SHA256, playerArtworkLoaded=False),
            itemArtworkRendered=False, projectileArtworkRendered=False, worldRendered=False, soundValidated=False)
        self.assertTrue(all(particles.resource_checks(render, 'star', selected=False).values()))
        self.assertFalse(all(particles.resource_checks(render, 'star').values()))
        for key, value in [('libraryBuffers', 4), ('readyLibraryTexturePaths', [particles.TEXTURES['star'][0]]),
                           ('effectSha256', 'changed'), ('resourceReady', False)]:
            invalid = copy.deepcopy(render); invalid[key] = value
            self.assertFalse(all(particles.resource_checks(invalid, 'star', selected=False).values()), key)

    def test_lifecycle_requires_real_hit_exact_count_and_retirement(self):
        states = [dict(tick=t, particleCount=5 if 2 <= t < 16 else 0,
                       materialRecordCount=1 if 2 <= t < 16 else 0,
                       records=[dict(started=True, durationTicks=14)] if 2 <= t < 16 else [])
                  for t in range(20)]
        trace = dict(snapshots=[dict(tick=2, events=[dict(kind='hit')])], nativeRender=dict(snapshots=states))
        self.assertTrue(all(particles.lifecycle_checks(trace).values()))
        mutations: list[Callable[[dict[str, Any]], None]] = [lambda t: t.update(snapshots=[]),
                     lambda t: t['nativeRender']['snapshots'][2].update(particleCount=0),
                     lambda t: t['nativeRender']['snapshots'][3].update(particleCount=4),
                     lambda t: t['nativeRender']['snapshots'][-1].update(materialRecordCount=1)]
        for mutation in mutations:
            invalid = copy.deepcopy(trace); mutation(invalid)
            self.assertFalse(all(particles.lifecycle_checks(invalid).values()))

    def test_png_decoder_not_telemetry_controls_visible_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            frame = path / 'frame.png'
            image = Image.new('RGBA', (2, 2), (0, 0, 0, 255))
            image.putpixel((0, 0), (80, 220, 255, 255)); image.save(frame)
            receipt = dict(tick=0, path='frame.png', width=2, height=2, sha256=w.digest(frame),
                           nonblackPixels=1, drawChangedMainRng=False, mainRngBeforeDraw=1, mainRngAfterDraw=1)
            trace = dict(status='passed', timeline=dict(completedTicks=1), snapshots=[dict(tick=0)],
                nativeRender=dict(backend='original_mod_draw_layers', itemArtworkRendered=False,
                                  projectileArtworkRendered=False, worldRendered=False, frames=[receipt]))
            checks, visible = particles.frame_checks(trace, path / 'native.json', 1)
            self.assertTrue(all(checks.values())); self.assertEqual(visible, [0])
            receipt['nonblackPixels'] = 0
            checks, visible = particles.frame_checks(trace, path / 'native.json', 1)
            self.assertFalse(checks['native-pixel-telemetry-matches-decoded-pngs'])
            self.assertEqual(visible, [0])
            receipt['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'hash'):
                particles.frame_checks(trace, path / 'native.json', 1)


if __name__ == '__main__':
    unittest.main()
