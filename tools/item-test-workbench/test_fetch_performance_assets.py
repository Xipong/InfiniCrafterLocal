"""Offline resource-integrity checks using synthetic PNGs, no game bytes/network."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
import fetch_performance_assets as f
import index_vanilla_assets as inventory
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

    def test_any_indexed_item_is_verified_by_git_blob_without_control_list(self):
        digest=hashlib.sha1(b'blob '+str(len(self.raw)).encode()+b'\0'+self.raw).hexdigest()
        index=dict(schemaVersion=1,communityCommit=f.COMMIT,entryFormat=['gitBlobSha1','bytes'],
                   items={'24':[digest,len(self.raw)],'3507':[digest,len(self.raw)]})
        result=f.provision(self.root,self.manifest,self.fetch,items=[24,3507],index=index)
        self.assertEqual(result['verifiedFiles'],2)
        self.assertEqual(self.calls,['Images/Item_24.png','Images/Item_3507.png'])
        path=self.root/'Images/Item_24.png'
        path.write_bytes(self.raw[:-1]+bytes([self.raw[-1]^1]))
        self.calls.clear()
        with self.assertRaisesRegex(ValueError,'Git blob mismatch'):
            f.provision(self.root,self.manifest,self.fetch,items=[24,3507],index=index)
        self.assertEqual(self.calls,[])

    def test_missing_ids_duplicates_and_wrong_source_are_not_replaced(self):
        index=dict(schemaVersion=1,communityCommit=f.COMMIT,entryFormat=['gitBlobSha1','bytes'],items={})
        for ids in ([24],[24,24],[],[-1],[True]):
            with self.subTest(ids=ids),self.assertRaises(ValueError):
                f.provision(self.root,self.manifest,self.fetch,items=ids,index=index)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.calls,[])

    def test_index_refresh_requires_complete_matching_git_tree(self):
        root=dict(truncated=False,tree=[dict(path='source-pngs',type='tree',sha='a'*40)])
        source=dict(sha='a'*40,truncated=False,tree=[dict(path='Item_24.png',type='blob',mode='100644',sha='b'*40,size=314)])
        self.assertEqual(inventory.build_index(root,source)['items'],{'24':['b'*40,314]})
        for mutation in ('truncated','wrong-tree','symlink','duplicate'):
            changed=copy.deepcopy(source)
            if mutation=='truncated':changed['truncated']=True
            elif mutation=='wrong-tree':changed['sha']='c'*40
            elif mutation=='symlink':changed['tree'][0]['mode']='120000'
            else:changed['tree'].append(copy.deepcopy(changed['tree'][0]))
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                inventory.build_index(root,changed)


if __name__ == '__main__': unittest.main()
