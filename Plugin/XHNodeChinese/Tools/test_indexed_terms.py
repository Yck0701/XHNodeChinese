import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core,personal
from xh_node_chinese.auto_translate import Translator
from xh_node_chinese.live import LiveSession,append_pairs
from xh_node_chinese.term_keys import canonical,Resolver

class IndexedTermsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'Dictionaries').mkdir()
        self.user=self.root/'Dictionaries/User.csv';self.user.write_text('Key,Value\n',encoding='utf-8')
        self.sources=['DynamicMaterialParameter'+i for i in ('','1','2','3')]

    def test_single_pending_row_and_one_translation_for_family(self):
        live=LiveSession(self.root,self.root/'Saved')
        report=live.sync(self.sources,{})
        self.assertEqual(report['pending'],1)
        self.assertEqual([r['Source'] for r in core.load_dictionary(live.path,True)],['DynamicMaterialParameter'])
        translator=Translator([],{'Dynamic Material Parameter':'动态材质参数'})
        report=live.sync(self.sources,{},translator)
        self.assertEqual(report['automatic'],1)
        self.assertEqual(report['pending'],0)
        rows=core.load_dictionary(self.user)
        self.assertEqual([(r['Source'],r['Translation']) for r in rows],[('DynamicMaterialParameter','动态材质参数')])
        self.assertEqual(live.sync(self.sources,{},translator)['automatic'],0)

    def test_legacy_export_cleanup_keeps_manual_numbered_override(self):
        live=LiveSession(self.root,self.root/'Saved')
        live.path.parent.mkdir()
        live.path.write_bytes(append_pairs(b'Key,Value\n',dict.fromkeys(self.sources,'')))
        live.path.write_bytes(append_pairs(live.path.read_bytes(),{'DynamicMaterialParameter2':'自定义第二通道'}))
        report=live.sync([],{'DynamicMaterialParameter':'动态材质参数'})
        self.assertEqual(report['pending'],0)
        self.assertEqual(core.load_dictionary(live.path)[0]['Translation'],'自定义第二通道')
        self.assertEqual(core.load_dictionary(self.user)[0]['Source'],'DynamicMaterialParameter2')
        self.assertTrue(list((self.root/'Saved/ExportBackups').glob('*.csv')))

    def test_no_dimension_version_or_sentence_collapsing(self):
        for source in ('Vector3','float4','DX12','Version 2','Texture2D','A label 10','One1'):
            self.assertEqual(canonical(source),source)
        self.assertEqual(canonical('DynamicMaterialParameter03'),'DynamicMaterialParameter')
        lookup=Resolver({'DynamicMaterialParameter':'动态材质参数','DynamicMaterialParameter2':'第二通道','Vector':'向量'})
        self.assertEqual(lookup.translated('DynamicMaterialParameter03'),'动态材质参数 03')
        self.assertEqual(lookup.translated('DynamicMaterialParameter2'),'第二通道')
        self.assertIsNone(lookup.translated('Vector3'))

    def test_camel_lookup_ambiguity_and_export(self):
        tr=Translator([],{'Sprite Size':'精灵尺寸'})
        self.assertEqual(tr.translate('SpriteSize')[0],'精灵尺寸')
        tr=Translator([],{'AB C':'甲','A BC':'乙'})
        self.assertIsNone(tr.translate('aBC'))
        path=self.root/'Pending.csv'
        self.assertEqual(core.export_pending(self.root,[],path,self.sources),1)
        self.assertEqual(core.load_dictionary(path,True)[0]['Source'],'DynamicMaterialParameter')
        personal.update(self.root,self.root/'Saved',{'DynamicMaterialParameter':'动态材质参数'})
        self.assertEqual(core.export_pending(self.root,[],path,self.sources),0)

if __name__=='__main__':unittest.main()
