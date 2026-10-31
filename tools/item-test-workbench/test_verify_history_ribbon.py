"""Synthetic detector controls, not native execution or visual approval."""
import copy
from pathlib import Path
import tempfile
import unittest
from typing import Any, Callable

from verify_history_ribbon import current_vfx_checks, current_vfx_slots, missing_selected_texture_root


def detector_trace() -> dict[str, Any]:
    return {
        'nativeRender': {
            'fullProjectilePreDrawExecuted': True, 'libraryBuffers': 4,
            'readyLibraryTexturePaths': ['ParticleLibrary/Assets/Textures/WhitePixel',
                                         'ParticleLibrary/Assets/Textures/Star'],
            'snapshots': [{'particleCount': 4, 'activeProjectileVfx': {'historyTrailDraws': [
                {'submittedSegments': 3, 'nativeMagicPixel': True, 'draw': 'stroke', 'source': 'center'}]}}],
        },
        'snapshots': [{'events': [
            {'kind': 'native_phase', 'phase': 'controlled hostile NPC.UpdateNPC', 'dedServ': True,
             'restoredDedServ': False, 'artworkRendered': False},
            {'kind': 'hit', 'entityId': 'root', 'npcId': 2, 'dedServ': False, 'damageDone': 10},
        ]}],
    }


class CurrentVfxDetectorTests(unittest.TestCase):
    def test_missing_texture_fixture_retains_bootstrap_and_source(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source'
            files={'Assets/Textures/WhitePixel.png':b'selected',
                   'Assets/Textures/EmptyPixel.png':b'bootstrap',
                   'Assets/Textures/Star.png':b'star',
                   'Assets/Effects/InstancedParticle.xnb':b'effect'}
            for name,data in files.items():
                path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            target=missing_selected_texture_root(source,Path(temp)/'negative')
            self.assertFalse((target/'Assets/Textures/WhitePixel.png').exists())
            for name,data in files.items():
                self.assertEqual((source/name).read_bytes(),data)
                if name!='Assets/Textures/WhitePixel.png':self.assertEqual((target/name).read_bytes(),data)

    def test_explicit_fixture_is_fresh_and_selects_both_resources(self):
        slots = current_vfx_slots()
        self.assertEqual([s['particle']['textureId'] for s in slots if 'particle' in s], ['solidPixel', 'star'])
        self.assertEqual(slots[0]['trail']['draw'], 'stroke')
        self.assertEqual(slots[0]['trail']['source'], 'center')
        self.assertNotIn('texture', slots[0]['trail'])
        slots[0]['trail']['widthPx'] = 999
        self.assertEqual(current_vfx_slots()[0]['trail']['widthPx'], 3)

    def test_detectors_do_not_mutate_evidence(self):
        trace = detector_trace()
        before = copy.deepcopy(trace)
        self.assertTrue(all(current_vfx_checks(trace).values()))
        self.assertEqual(trace, before)

    def test_emission_or_admission_is_not_a_draw(self):
        mutations: tuple[Callable[[dict[str, Any]], Any], ...] = (
            lambda r: r.update(fullProjectilePreDrawExecuted=False),
            lambda r: r['snapshots'][0]['activeProjectileVfx'].update(historyTrailDraws=[]),
            lambda r: r['snapshots'][0]['activeProjectileVfx']['historyTrailDraws'][0].update(submittedSegments=0),
            lambda r: r['snapshots'][0]['activeProjectileVfx']['historyTrailDraws'][0].update(nativeMagicPixel=False),
            lambda r: r['snapshots'][0]['activeProjectileVfx']['historyTrailDraws'][0].update(draw='sprites'),
            lambda r: r['snapshots'][0]['activeProjectileVfx']['historyTrailDraws'][0].update(source='tip'),
        )
        for mutation in mutations:
            trace = detector_trace()
            mutation(trace['nativeRender'])
            self.assertFalse(current_vfx_checks(trace)['current-trail-original-submissions'])

    def test_texture_substitution_and_empty_particles_fail_independently(self):
        trace = detector_trace()
        trace['nativeRender']['readyLibraryTexturePaths'] = ['ParticleLibrary/Assets/Textures/Star']
        checks = current_vfx_checks(trace)
        self.assertFalse(checks['current-selected-textures-ready'])
        self.assertTrue(checks['current-native-particles-started'])
        trace = detector_trace()
        trace['nativeRender']['snapshots'][0]['particleCount'] = 0
        self.assertFalse(current_vfx_checks(trace)['current-native-particles-started'])
        self.assertFalse(any(current_vfx_checks({}).values()))

    def test_hostile_scope_leak_or_missing_hit_cannot_pass(self):
        for key, value in (('dedServ', False), ('restoredDedServ', True), ('artworkRendered', True)):
            trace = detector_trace()
            trace['snapshots'][0]['events'][0][key] = value
            self.assertFalse(current_vfx_checks(trace)['controlled-hostile-update-restores-client'])
        for key, value in (('dedServ', True), ('entityId', 'child'), ('npcId', 100), ('damageDone', 0), ('kind', 'spawn')):
            trace = detector_trace()
            trace['snapshots'][0]['events'][1][key] = value
            self.assertFalse(current_vfx_checks(trace)['controlled-hostile-hit-remains-native-client'])


if __name__ == '__main__':
    unittest.main()
