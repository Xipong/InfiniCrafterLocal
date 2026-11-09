"""Offline resource-integrity checks using synthetic PNGs, no game bytes/network."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from python import fetch_performance_assets as f
from python import index_vanilla_assets as inventory
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
            projectileFiles=[row(Path(e['path']).name) for e in json.loads(f.MANIFEST.read_text())['projectileFiles']])
        self.calls = []
        digest=hashlib.sha1(b'blob '+str(len(self.raw)).encode()+b'\0'+self.raw).hexdigest()
        self.draw_index=dict(schemaVersion=1,communityCommit=f.COMMIT,entryFormat=['gitBlobSha1','bytes'],
                             entries={'Misc/Ripples.png':[digest,len(self.raw)]})
        index_path=self.root.parent/'draw-index.json';index_path.write_text(json.dumps(self.draw_index))
        patcher=patch.object(f,'DRAW_INDEX',index_path);patcher.start();self.addCleanup(patcher.stop)
    def fetch(self, row):
        self.calls.append(row['path'])
        return self.raw
    def test_optional_projectiles_and_verified_reuse(self):
        self.assertEqual(f.provision(self.root, self.manifest, self.fetch)['verifiedFiles'], 12)
        self.assertEqual(len(self.calls), 12)
        result = f.provision(self.root, self.manifest, self.fetch, include_projectiles=True)
        total = len(f.IDS) + len(self.manifest['projectileFiles']) + 1
        self.assertEqual((result['verifiedFiles'], len(self.calls)), (total, total))
        self.assertTrue(result['includesProjectiles'])
        self.assertFalse(result['officialByteIdentityVerified'])
        f.provision(self.root, self.manifest, self.fetch, include_projectiles=True)
        self.assertEqual(len(self.calls), total)
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

    def test_arbitrary_pinned_projectiles_extras_and_support_not_family_allowlist(self):
        digest=hashlib.sha1(b'blob '+str(len(self.raw)).encode()+b'\0'+self.raw).hexdigest()
        names=['Projectile_632.png','Projectile_932.png','Extra_0.png','Extra_200.png','FishingLine.png']
        index=dict(schemaVersion=1,communityCommit=f.COMMIT,entryFormat=['gitBlobSha1','bytes'],
                   entries={name:[digest,len(self.raw)] for name in names})
        result=f.provision(self.root,self.manifest,self.fetch,projectiles=[632,932],extras=[0,200],
                           draw_assets=['FishingLine.png'],draw_index=index)
        self.assertEqual(result['verifiedFiles'],len(f.IDS)+5)
        self.assertEqual(self.calls[-5:],['Images/'+name for name in names])
        self.assertFalse(result['officialByteIdentityVerified'])
        self.calls.clear()
        f.provision(self.root,self.manifest,self.fetch,projectiles=[632,932],extras=[0,200],
                    draw_assets=['FishingLine.png'],draw_index=index)
        self.assertEqual(self.calls,[])
        path=self.root/'Images/Projectile_632.png'
        path.write_bytes(self.raw[:-1]+bytes([self.raw[-1]^1]))
        with self.assertRaisesRegex(ValueError,'Git blob mismatch'):
            f.provision(self.root,self.manifest,self.fetch,projectiles=[632],draw_index=index)
        self.assertEqual(self.calls,[])

    def test_draw_selection_rejects_unknown_duplicate_traversal_and_wrong_pin(self):
        index=dict(schemaVersion=1,communityCommit=f.COMMIT,entryFormat=['gitBlobSha1','bytes'],entries={})
        for projectiles,extras,names in [([632],None,None),([1,1],None,None),([True],None,None),
                ([-1],None,None),(None,[],None),(None,None,['../Extra_1.png']),
                (None,None,['Extra_01.png']),([1],None,['Projectile_1.png'])]:
            with self.subTest(projectiles=projectiles,extras=extras,names=names),self.assertRaises(ValueError):
                f.provision(self.root,self.manifest,self.fetch,projectiles=projectiles,extras=extras,
                            draw_assets=names,draw_index=index)
        self.assertEqual(self.calls,[])
        self.assertFalse(self.root.exists())
        index['communityCommit']='wrong'
        with self.assertRaises(ValueError):f.draw_entries([1],None,None,index)

    def test_draw_index_complete_tree_provenance_and_future_ids(self):
        from python import index_vanilla_draw_assets as draw
        root=dict(sha=f.COMMIT,truncated=False,tree=[dict(path='source-pngs',type='tree',sha='a'*40)])
        source=dict(sha='a'*40,truncated=False,tree=[dict(path=n,type='blob',mode='100644',sha='b'*40,size=314)
                       for n in ['Projectile_12345.png','Extra_0.png','FishingLine.png','Item_3.png']])
        result=draw.build_index(root,source)
        self.assertEqual(set(result['entries']),{'Projectile_12345.png','Extra_0.png','FishingLine.png'})
        self.assertEqual(json.loads(draw.encode_index(result)),result)
        for mutation in ('truncated','wrong-tree','symlink','duplicate','size'):
            changed=copy.deepcopy(source)
            if mutation=='truncated':changed['truncated']=True
            elif mutation=='wrong-tree':changed['sha']='c'*40
            elif mutation=='symlink':changed['tree'][0]['mode']='120000'
            elif mutation=='size':changed['tree'][0]['size']=True
            else:changed['tree'].append(copy.deepcopy(changed['tree'][0]))
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):draw.build_index(root,changed)
        with self.assertRaises(ValueError):draw.build_index({**root,'sha':'wrong'},source)

    def test_generic_glow_backpack_and_exact_nested_water_texture(self):
        digest=hashlib.sha1(b'blob '+str(len(self.raw)).encode()+b'\0'+self.raw).hexdigest()
        names=['Glow_102.png','BackPack_3.png','Misc/Ripples.png']
        index=dict(schemaVersion=1,communityCommit=f.COMMIT,entryFormat=['gitBlobSha1','bytes'],
                   entries={name:[digest,len(self.raw)] for name in names})
        result=f.provision(self.root,self.manifest,self.fetch,glow=[102],backpacks=[3],
                           draw_assets=['Misc/Ripples.png'],draw_index=index)
        self.assertEqual(result['verifiedFiles'],len(f.IDS)+3)
        self.assertEqual(self.calls[-3:],['Images/'+name for name in names])
        self.assertEqual((self.root/'Images/Misc/Ripples.png').read_bytes(),self.raw)
        for name in ['Misc/Other.png','Misc/../Ripples.png','Misc\\Ripples.png']:
            with self.assertRaises(ValueError):f.draw_entries(None,None,[name],index)

    def test_nested_water_symlink_refused_before_fetch(self):
        nested=self.root/'Images/Misc';nested.parent.mkdir(parents=True)
        outside=self.root/'outside';outside.mkdir();nested.symlink_to(outside,target_is_directory=True)
        digest=hashlib.sha1(b'blob '+str(len(self.raw)).encode()+b'\0'+self.raw).hexdigest()
        index=dict(schemaVersion=1,communityCommit=f.COMMIT,entryFormat=['gitBlobSha1','bytes'],
                   entries={'Misc/Ripples.png':[digest,len(self.raw)]})
        with self.assertRaises(ValueError):
            f.provision(self.root,self.manifest,self.fetch,draw_assets=['Misc/Ripples.png'],draw_index=index)
        self.assertEqual(self.calls,[])

    def test_water_resource_must_be_in_complete_anchored_misc_tree(self):
        from python import index_vanilla_draw_assets as draw
        root=dict(sha=f.COMMIT,truncated=False,tree=[dict(path='source-pngs',type='tree',sha='a'*40)])
        source=dict(sha='a'*40,truncated=False,tree=[dict(path='Misc',type='tree',sha='c'*40),
                   dict(path='Glow_9999.png',type='blob',mode='100644',sha='b'*40,size=314)])
        misc=dict(sha='c'*40,truncated=False,tree=[dict(path='Ripples.png',type='blob',mode='100644',sha='d'*40,size=400)])
        self.assertEqual(draw.build_index(root,source,misc)['entries']['Misc/Ripples.png'],['d'*40,400])
        for mutation in ('wrong-tree','truncated','missing','duplicate','symlink'):
            changed=copy.deepcopy(misc)
            if mutation=='wrong-tree':changed['sha']='e'*40
            elif mutation=='truncated':changed['truncated']=True
            elif mutation=='missing':changed['tree']=[]
            elif mutation=='duplicate':changed['tree']*=2
            else:changed['tree'][0]['mode']='120000'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):draw.build_index(root,source,changed)

    def test_legacy_projectile_setup_includes_exact_water_dependency_once(self):
        f.provision(self.root,self.manifest,self.fetch,include_projectiles=True,
                    draw_assets=['Misc/Ripples.png'],draw_index=self.draw_index)
        self.assertEqual(self.calls.count('Images/Misc/Ripples.png'),1)
        self.assertEqual((self.root/'Images/Misc/Ripples.png').read_bytes(),self.raw)
        self.calls.clear()
        f.provision(self.root,self.manifest,self.fetch,include_projectiles=True)
        self.assertEqual(self.calls,[])
        with self.assertRaises(ValueError):
            f.provision(self.root,self.manifest,self.fetch,include_projectiles=True,
                        draw_assets=['Misc/Ripples.png','Misc/Ripples.png'],draw_index=self.draw_index)


if __name__ == '__main__': unittest.main()
