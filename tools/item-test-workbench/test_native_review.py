"""Synthetic PNG container tests, not native runtime or visual-parity evidence."""
import copy,hashlib,json,struct,tempfile,unittest,zlib
from pathlib import Path
import native_review as n


def png():
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\xff\xff\xff'))+chunk(b'IEND',b'')


class NativeReviewTests(unittest.TestCase):
    def fixture(self,root):
        p=root/'native-frames/0.png';p.parent.mkdir();p.write_bytes(png())
        trace={'status':'passed','snapshots':[{'tick':0,'player':{'mana':193},'events':[{'kind':'input','input':'primary'}]}],'timeline':{'completedTicks':1},'nativeRender':{'backend':'original_mod_draw_layers','itemArtworkRendered':False,'projectileArtworkRendered':False,'worldRendered':False,'frames':[{'tick':0,'path':'native-frames/0.png','sha256':hashlib.sha256(png()).hexdigest(),'width':1,'height':1}]}}
        tp=root/'native.json';tp.write_text(json.dumps(trace));return trace,tp,p
    def test_export_copies_exact_png_without_redraw(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);t,tp,p=self.fixture(root);before=p.read_bytes();out=root/'review';r=n.export_native_review(t,tp,out)
            self.assertEqual((out/'frames/000000.png').read_bytes(),before);self.assertEqual(p.read_bytes(),before)
            self.assertEqual(r['nativeFrames'],1);self.assertIn('Exact same-tick telemetry',(out/'native.html').read_text());self.assertIn('Not a complete Terraria world render',(out/'native.html').read_text())
            self.assertFalse(json.loads((out/'native-review.json').read_text())['pixelsRedrawn'])
    def test_bad_hash_dimensions_and_truncated_frame_refused(self):
        with tempfile.TemporaryDirectory() as d:
            t,tp,p=self.fixture(Path(d))
            for change in [{'sha256':'0'*64},{'width':2},{'width':1.0}]:
                bad=copy.deepcopy(t);bad['nativeRender']['frames'][0].update(change)
                with self.assertRaises(ValueError):n.native_frames(bad,tp)
            p.write_bytes(png()[:33]);t['nativeRender']['frames'][0]['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):n.native_frames(t,tp)
    def test_paths_and_coverage_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            t,tp,p=self.fixture(Path(d))
            for path in ['../outside.png',str(p)]:
                bad=copy.deepcopy(t);bad['nativeRender']['frames'][0]['path']=path
                with self.assertRaises(ValueError):n.native_frames(bad,tp)
            del t['nativeRender']['worldRendered']
            with self.assertRaises(ValueError):n.native_frames(t,tp)
    def test_missing_tick_frames_and_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);t,tp,p=self.fixture(root);t['timeline']['completedTicks']=2
            with self.assertRaises(ValueError):n.native_frames(t,tp)
            t['timeline']['completedTicks']=1
            with self.assertRaises(ValueError):n.export_native_review(t,tp,root)
    def test_explicit_gif_stride_preserves_complete_html_frames(self):
        try:import PIL
        except ImportError:self.skipTest('Optional Pillow is not installed')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);t,tp,p=self.fixture(root)
            t['snapshots']=[{**t['snapshots'][0],'tick':i} for i in range(5)]
            t['timeline']['completedTicks']=5
            t['nativeRender']['frames']=[{**t['nativeRender']['frames'][0],'tick':i} for i in range(5)]
            tp.write_text(json.dumps(t));out=root/'review';n.export_native_review(t,tp,out,True,2)
            m=json.loads((out/'native-review.json').read_text());self.assertEqual(len(m['frames']),5)
            self.assertEqual(m['gif']['sourceTicks'],[0,2,4]);self.assertEqual(m['gif']['omittedFrames'],2)
            with self.assertRaises(ValueError):n.export_native_review(t,tp,root/'bad',True,0)
    def test_observed_bookmarks_do_not_invent_engine_events(self):
        trace={'snapshots':[{'tick':0,'player':{'generatedBuffTicks':1},'projectiles':[{'id':0,'returning':False}]},{'tick':1,'player':{'generatedBuffTicks':0},'projectiles':[{'id':0,'returning':True}]}]}
        marks=n.observed_bookmarks(trace)
        self.assertEqual(len(marks),2);self.assertTrue(all(m['tick']==1 and m['kind']=='observed-state-transition' for m in marks))
        self.assertNotIn('events',trace['snapshots'][1])
    def test_projectile_lifecycle_bookmarks_are_identity_scoped(self):
        trace={'snapshots':[
            {'tick':0,'projectiles':[{'id':1,'active':True,'released':False,'returning':False}]},
            {'tick':1,'phase':'after_input_before_update','projectiles':[{'id':1,'active':True,'released':True}]},
            {'tick':1,'projectiles':[{'id':1,'active':True,'released':True,'returning':False}]},
            {'tick':2,'projectiles':[{'id':1,'active':False,'released':True,'returning':False},{'id':2,'active':True,'released':False}]},
            {'tick':3,'projectiles':[{'id':2,'active':True,'released':False}]}]}
        marks=n.observed_bookmarks(trace)
        self.assertEqual([(m['tick'],m['sourceField']) for m in marks],[(1,'projectiles.released'),(2,'projectiles.active')])
        self.assertTrue(all('projectile 1' in m['label'] for m in marks))
        self.assertIn('see native event for cause',marks[1]['label'])
        self.assertNotIn('arrived',str(marks))

    def test_ready_bookmark_requires_canonical_status_transition(self):
        trace={'snapshots':[{'tick':0,'projectiles':[{'id':1,'chargeTicks':50,'chargeStatus':{'ready':False}}]},
            {'tick':1,'projectiles':[{'id':1,'chargeTicks':51,'chargeStatus':{'ready':True}}]},
            {'tick':2,'projectiles':[{'id':1,'chargeTicks':52,'chargeStatus':None}]}]}
        marks=n.observed_bookmarks(trace)
        self.assertEqual([(m['tick'],m['sourceField']) for m in marks],[(1,'projectiles.chargeStatus.ready')])
        for s in trace['snapshots']:s['projectiles'][0].pop('chargeStatus',None)
        self.assertEqual(n.observed_bookmarks(trace),[])

    def test_png_crc_and_scanline_integrity(self):
        self.assertEqual(n.png_dimensions(png()),(1,1))
        raw=bytearray(png());raw[29]^=1
        with self.assertRaises(ValueError):n.png_dimensions(raw)

if __name__=='__main__':unittest.main()
