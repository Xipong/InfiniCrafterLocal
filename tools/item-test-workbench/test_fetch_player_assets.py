"""Offline integrity and path safety tests; no network or game bytes."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
import fetch_player_assets as fetcher


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\0\xff\xff\xff\xff')) + chunk(b'IEND', b'')


class PlayerAssetsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'output'
        self.data = png()
        self.manifest = {'commit': fetcher.COMMIT, 'files': [dict(path='Images/' + name, sourceURL=fetcher.PREFIX + name, sha256=hashlib.sha256(self.data).hexdigest(), bytes=len(self.data), width=1, height=1) for name in sorted(fetcher.REQUIRED)]}
        self.calls = []
    def download(self, entry):
        self.calls.append(entry['path'])
        return self.data
    def provision(self):
        return fetcher.provision(self.root, self.manifest, self.download)
    def test_download_and_reuse(self):
        self.assertEqual(self.provision()['downloaded'], 19)
        self.assertEqual(self.provision()['reused'], 19)
        self.assertEqual(len(self.calls), 19)
        self.assertFalse(self.provision()['officialByteIdentityVerified'])
        self.assertEqual(list(self.root.rglob('.player-asset-*')), [])
    def test_wrong_bytes(self):
        with self.assertRaisesRegex(ValueError, 'Integrity'):
            fetcher.provision(self.root, self.manifest, lambda _: self.data[:-1] + b'X')
        self.assertFalse(self.root.exists())
    def test_existing_mismatch_refuses_before_download(self):
        path = self.root / self.manifest['files'][-1]['path']
        path.parent.mkdir(parents=True); path.write_bytes(b'wrong')
        with self.assertRaises(ValueError): self.provision()
        self.assertEqual(self.calls, [])
        self.assertEqual(path.read_bytes(), b'wrong')
    def test_geometry(self):
        self.manifest['files'][0]['width'] = 2
        with self.assertRaisesRegex(ValueError, 'geometry'): self.provision()
    def test_png_signature(self):
        self.data = b'X' * 32
        for entry in self.manifest['files']:
            entry.update(bytes=32, sha256=hashlib.sha256(self.data).hexdigest())
        with self.assertRaisesRegex(ValueError, 'PNG'): self.provision()
    def test_url(self):
        self.manifest['files'][0]['sourceURL'] = 'https://example.invalid/file'
        with self.assertRaisesRegex(ValueError, 'URL'): self.provision()
        self.assertEqual(self.calls, [])
    def test_commit(self):
        self.manifest['commit'] = 'other'
        with self.assertRaises(ValueError): self.provision()
    def test_allowlist_and_duplicate(self):
        for mutation in ('traversal', 'duplicate', 'missing'):
            with self.subTest(mutation=mutation):
                manifest = copy.deepcopy(self.manifest)
                if mutation == 'traversal': manifest['files'][0]['path'] = '../escape.png'
                elif mutation == 'duplicate': manifest['files'][0] = manifest['files'][1]
                else: manifest['files'].pop()
                with self.assertRaises(ValueError): fetcher.provision(self.root, manifest, self.download)
        self.assertEqual(self.calls, [])
    def test_symlink_output(self):
        self.root.symlink_to(Path(self.tmp.name), target_is_directory=True)
        with self.assertRaises(ValueError): self.provision()
    def test_symlink_ancestor(self):
        alias = Path(self.tmp.name) / "alias"
        actual = Path(self.tmp.name) / "actual"; actual.mkdir()
        alias.symlink_to(actual, target_is_directory=True)
        self.root = alias / "nested"
        with self.assertRaises(ValueError): self.provision()
    def test_symlink_child(self):
        self.root.mkdir(); (self.root / 'Images').symlink_to(Path(self.tmp.name), target_is_directory=True)
        with self.assertRaises(ValueError): self.provision()
        self.assertEqual(self.calls, [])
    def test_existing_file_symlink(self):
        path = self.root / self.manifest['files'][0]['path']
        path.parent.mkdir(parents=True)
        target = Path(self.tmp.name) / 'source.png'; target.write_bytes(self.data)
        path.symlink_to(target)
        with self.assertRaises(ValueError): self.provision()
    def test_optional_dummy_download_and_default_unchanged(self):
        self.manifest['trainingDummyFiles'] = [dict(path='Images/' + name, sourceURL=fetcher.PREFIX + name, sha256=hashlib.sha256(self.data).hexdigest(), bytes=len(self.data), width=1, height=1) for name in sorted(fetcher.DUMMY_REQUIRED)]
        self.assertEqual(self.provision()['verifiedFiles'], 19)
        result = fetcher.provision(self.root, self.manifest, self.download, include_dummy=True)
        self.assertEqual((result['downloaded'], result['reused'], result['verifiedFiles']), (2, 19, 21))
        self.assertTrue(result['includesTrainingDummy'])
        self.assertEqual(self.provision()['verifiedFiles'], 19)
    def test_optional_dummy_missing_or_wrong_manifest(self):
        with self.assertRaises(ValueError): fetcher.provision(self.root, self.manifest, self.download, include_dummy=True)
        self.manifest['trainingDummyFiles'] = self.manifest['files'][:2]
        with self.assertRaises(ValueError): fetcher.provision(self.root, self.manifest, self.download, include_dummy=True)
        self.assertEqual(self.calls, [])
    def test_bundled_metadata_exact_allowlist(self):
        manifest = json.loads(fetcher.MANIFEST.read_text())
        self.assertEqual(manifest['commit'], fetcher.COMMIT)
        self.assertEqual({Path(e['path']).name for e in manifest['files']}, fetcher.REQUIRED)
        self.assertEqual(len(manifest['files']), 19)
        for entry in manifest['files']:
            self.assertEqual(entry['sourceURL'], fetcher.PREFIX + Path(entry['path']).name)
            self.assertEqual(len(entry['sha256']), 64)


if __name__ == '__main__': unittest.main()
