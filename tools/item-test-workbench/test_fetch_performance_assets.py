"""Offline resource-integrity checks using synthetic PNGs, no game bytes/network."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
import fetch_performance_assets as f
from test_fetch_player_assets import png


class PerformanceAssetsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'assets'
        self.raw = png()
        def row(name):
            return dict(path='Images/' + name, sourceURL=f.PREFIX + name,
                        sha256=hashlib.sha256(self.raw).hexdigest(), bytes=len(self.raw), width=1, height=1)
        self.manifest = dict(commit=f.COMMIT,
            files=[row(f'Item_{i}.png') for i in sorted(f.IDS)],
            projectileFiles=[row(f'Projectile_{i}.png') for i in sorted(f.PROJECTILE_IDS)])
        self.calls = []
    def fetch(self, row):
        self.calls.append(row['path'])
        return self.raw
    def test_optional_projectiles_and_verified_reuse(self):
        self.assertEqual(f.provision(self.root, self.manifest, self.fetch)['verifiedFiles'], 12)
        self.assertEqual(len(self.calls), 12)
        result = f.provision(self.root, self.manifest, self.fetch, include_projectiles=True)
        self.assertEqual((result['verifiedFiles'], len(self.calls)), (18, 18))
        self.assertTrue(result['includesProjectiles'])
        self.assertFalse(result['officialByteIdentityVerified'])
        f.provision(self.root, self.manifest, self.fetch, include_projectiles=True)
        self.assertEqual(len(self.calls), 18)
    def test_corrupt_existing_projectile_refuses_before_any_download(self):
        path = self.root / self.manifest['projectileFiles'][-1]['path']
        path.parent.mkdir(parents=True)
        path.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            f.provision(self.root, self.manifest, self.fetch, include_projectiles=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(path.read_bytes(), b'corrupt')
    def test_missing_duplicate_or_unpinned_projectiles_refuse(self):
        for mutation in ('missing', 'duplicate', 'url', 'traversal'):
            manifest = copy.deepcopy(self.manifest)
            if mutation == 'missing': manifest['projectileFiles'].pop()
            elif mutation == 'duplicate': manifest['projectileFiles'][0] = manifest['projectileFiles'][1]
            elif mutation == 'url': manifest['projectileFiles'][0]['sourceURL'] = 'https://example.invalid/asset'
            else: manifest['projectileFiles'][0]['path'] = '../escape.png'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                f.provision(self.root, manifest, self.fetch, include_projectiles=True)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.root.exists())
    def test_bad_download_cannot_publish_projectile(self):
        f.provision(self.root, self.manifest, self.fetch)
        with self.assertRaises(ValueError):
            f.provision(self.root, self.manifest, lambda _: b'corrupt', include_projectiles=True)
        self.assertEqual(list(self.root.glob('Images/Projectile_*.png')), [])
    def test_projectile_symlink_cannot_be_reused(self):
        path = self.root / self.manifest['projectileFiles'][0]['path']
        path.parent.mkdir(parents=True)
        target = self.root / 'target.png'
        target.write_bytes(self.raw)
        path.symlink_to(target)
        with self.assertRaises(ValueError):
            f.provision(self.root, self.manifest, self.fetch, include_projectiles=True)
        self.assertEqual(self.calls, [])


if __name__ == '__main__': unittest.main()
