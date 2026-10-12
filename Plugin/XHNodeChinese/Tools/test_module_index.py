import sys,tempfile,unittest,types,json
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import asset_index
from xh_node_chinese.term_keys import Resolver

class ModuleIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'Dictionaries').mkdir()
        (self.root/'Dictionaries/User.csv').write_text('Key,Value\n')
        self.index=asset_index.Indexer(self.root,self.root,[])
        self.index.phase='deep';self.index.resolver=Resolver({'Particle Radius Scale':'粒子半径缩放'})
        self.index.translator=Mock();self.index.translator.translate.return_value=None
        self.index.assets=[types.SimpleNamespace(package_name='/Niagara/Test',asset_name='Test'),types.SimpleNamespace(package_name='/Niagara/Bad',asset_name='Bad')]
        self.index.reader=Mock();self.index.reader.read.side_effect=[['Particle Radius Scale','Enable Rest State','This is a previously unopened module parameter description. It explains the collision calculation and how to adjust the simulation.'],RuntimeError('unavailable')]

    def test_deep_scan_one_asset_per_step_and_pause(self):
        with patch.dict(sys.modules,{'unreal':types.SimpleNamespace()}):
            self.assertFalse(self.index.step())
            self.assertEqual(self.index.deep_position,1)
            self.assertNotIn('Particle Radius Scale',self.index.pending)
            self.assertIn('Enable Rest State',self.index.pending)
            self.index.pause();self.assertFalse(self.index.step())
            self.assertEqual(self.index.reader.read.call_count,1)
            self.index.resume();self.index.next_step=0
            self.assertFalse(self.index.step());self.index.next_step=0
            self.assertTrue(self.index.step())
        self.assertEqual(self.index.phase,'done')
        self.assertEqual(len(self.index.failures),1)
        status=json.loads((self.root/'ModuleIndexStatus.json').read_text())
        self.assertEqual(status['deep_position'],2)
        self.assertIn('Enable Rest State',(self.root/'Indexed.csv').read_text(encoding='utf-8-sig'))
        self.assertIn('previously unopened',(self.root/'LongText.csv').read_text(encoding='utf-8-sig'))
        self.assertEqual((self.root/'Dictionaries/User.csv').read_text(),'Key,Value\n')

    def test_cached_startup_and_paused_waiting_do_not_load_assets(self):
        i=asset_index.Indexer(self.root,self.root,[],cached_only=True)
        with patch.dict(sys.modules,{'unreal':types.SimpleNamespace()}):self.assertFalse(i.step())
        self.index.phase='waiting';self.index.pause();self.index.resume()
        self.assertEqual(self.index.phase,'waiting')

if __name__=='__main__':unittest.main()
