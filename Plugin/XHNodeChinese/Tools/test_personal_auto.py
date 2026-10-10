import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core, personal, bridge
from xh_node_chinese.auto_translate import Translator
from xh_node_chinese.live import LiveSession, append_pairs, useful


class PersonalAutoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'Dictionaries').mkdir()
        self.user=self.root/'Dictionaries/User.csv'
        self.user.write_text('Key,Value\n"Old","旧词"\n',encoding='utf-8')
        self.save=self.root/'Saved'

    def test_compaction_keeps_effective_scopes_and_order(self):
        self.user.write_text('Source,Translation,Namespace,Key,Category\nBranch,旧分支,,,\nBranch,作用域分支,A,K,\nBranch,新分支,,,\nBranch,新分支,,,\nEmpty,,,,\n',encoding='utf-8')
        before=self.user.read_bytes()
        cat=[dict(source='Branch',namespace=n,key='K',hash=1,category='Blueprint') for n in ('A','B')]
        translations=core.select_translations(cat,[self.user])[0]
        result=personal.update(self.root,self.save)
        self.assertEqual(result['removed'],3)
        self.assertEqual(core.select_translations(cat,[self.user])[0],translations)
        self.assertEqual(bridge.dictionary(self.root),{'Branch':'新分支'})
        self.assertTrue(any(p.read_bytes()==before for p in (self.save/'DictionaryBackups').glob('*.csv')))
        self.assertEqual(personal.update(self.root,self.save)['removed'],0)

    def test_repeated_upsert_no_duplicates_manual_priority_and_atomic_guard(self):
        personal.update(self.root,self.save,{'Old':'手动新译文'})
        personal.update(self.root,self.save,{'Old':'第二次修改'})
        self.assertEqual(len(core.load_dictionary(self.user)),1)
        self.assertEqual(personal.update(self.root,self.save,{'Old':'自动译文'},overwrite=False)['written'],0)
        before=self.user.read_bytes()
        with self.assertRaises(RuntimeError):personal.update(self.root,self.save,{'New':'新'},guard=lambda:False)
        with self.assertRaises(ValueError):personal.update(self.root,self.save,{'Value {0}':'数值'})
        self.assertEqual(self.user.read_bytes(),before)

    def test_local_memory_rejects_ambiguous_and_incomplete_results(self):
        cat=[dict(source='Bank',builtin=t) for t in ('银行','河岸')]
        cat+=[dict(source='Value {0}',builtin='值 {0}')]
        tr=Translator(cat,{'Particle':'粒子','Size':'大小'})
        self.assertIsNone(tr.translate('Bank'))
        self.assertIsNone(tr.translate('Unknown Particle'))
        self.assertIsNone(tr.translate('Particle Size'))
        self.assertEqual(tr.translate('Value {0}')[0],'值 {0}')
        self.assertIsNone(tr.translate('Set Particle Size to Unknown.'))

    def test_auto_import_cleans_pending_and_respects_manual_override(self):
        live=LiveSession(self.root,self.save)
        tr=Translator([dict(source='Initial Mesh Orientation',builtin='初始网格朝向')],{})
        result=live.sync(['Initial Mesh Orientation','Mystery Label','SM_Cube10','64 actors (64 loaded)'],{},tr)
        self.assertEqual(result['automatic'],1)
        self.assertEqual(result['pending'],1)
        self.assertEqual(core.load_dictionary(self.user)[-1]['Translation'],'初始网格朝向')
        self.assertEqual(core.load_dictionary(live.path,True)[0]['Source'],'Mystery Label')
        personal.update(self.root,self.save,{'Initial Mesh Orientation':'我的朝向'})
        self.assertEqual(live.sync(['Initial Mesh Orientation'],{},tr)['automatic'],0)
        self.assertEqual(core.load_dictionary(self.user)[-1]['Translation'],'我的朝向')
        live.path.write_bytes(append_pairs(live.path.read_bytes(),{'Mystery Label':'神秘标签'}))
        live.sync([],{},tr)
        live.path.write_bytes(append_pairs(live.path.read_bytes(),{'Mystery Label':'自选标签'}))
        live.sync([],{},tr)
        self.assertEqual(sum(r['Source']=='Mystery Label' for r in core.load_dictionary(self.user)),1)
        self.assertEqual(core.load_dictionary(self.user)[-1]['Translation'],'自选标签')

    def test_export_deduplicates_contexts_and_filters_noise(self):
        cat=[dict(source='New Label',namespace=n,key='K',hash=1,category='Niagara',builtin='') for n in ('A','B')]
        path=self.save/'Pending.csv'
        count=core.export_pending(self.root,cat,path,observed=['new   label','SM_Cube10','C:/Temp/thing.csv','60 fps','8 actors (8 loaded)'])
        self.assertEqual(count,1)
        self.assertEqual(len(core.load_dictionary(path,True)),1)
        self.assertTrue(path.with_suffix('.contexts.json').exists())
        self.assertTrue(useful('Apply Force to Position'))
        self.assertFalse(useful('GPU'))
        self.assertFalse(useful('JX3_Unreal_Artwork'))

    def test_pending_file_imports_and_known_blank_rows_disappear(self):
        pending=LiveSession(self.root,self.save,'Pending.csv')
        pending.sync(['Old','New Term'],{'Old':'旧词'})
        pending.path.write_bytes(append_pairs(pending.path.read_bytes(),{'New Term':'新术语'}))
        self.assertEqual(pending.sync([],{'Old':'旧词'})['imported'],1)
        self.assertEqual(core.load_dictionary(self.user)[-1]['Translation'],'新术语')
        restarted=LiveSession(self.root,self.save,'Pending.csv')
        self.assertEqual(restarted.sync([],{})['imported'],0)


if __name__=='__main__':unittest.main()
