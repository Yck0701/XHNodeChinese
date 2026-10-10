import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import bridge,core

class GraphDictionaryTests(unittest.TestCase):
    def test_scoped_terms_and_personal_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'Dictionaries';d.mkdir()
            (d/'Base.csv').write_text('Source,Translation,Namespace,Key,Category\nNormal,法线,,,Material\nPrint String,打印,,,Blueprint\n',encoding='utf-8')
            (d/'Graph.csv').write_text('Key,Value\nPrint String,打印字符串\n',encoding='utf-8')
            (d/'User.csv').write_text('Key,Value\nPrint String,个人打印\n',encoding='utf-8')
            self.assertNotIn('Normal',bridge.dictionary(tmp))
            self.assertEqual(bridge.graph_dictionary(tmp)['Normal'],'法线')
            self.assertEqual(bridge.graph_dictionary(tmp)['Print String'],'个人打印')

    def test_export_does_not_repeat_translated_graph_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);d=p/'Dictionaries';d.mkdir()
            for name in ('Base.csv','User.csv'):(d/name).write_text('Key,Value\n',encoding='utf-8')
            (d/'Graph.csv').write_text('Key,Value\nPrint String,打印字符串\n',encoding='utf-8')
            self.assertNotIn('Print String',bridge.dictionary(p))
            self.assertEqual(core.export_pending(p,[],p/'Pending.csv',observed=['Print String','Unknown Node']),1)
            self.assertEqual(core.load_dictionary(p/'Pending.csv',True)[0]['Source'],'Unknown Node')

    def test_shipped_common_names(self):
        terms=bridge.graph_dictionary(Path(__file__).resolve().parents[1])
        for source in ('Material Layer Constructors','Path Tracing','Vector Ops','Print String','Create Dynamic Material Instance','Texture Sample','TextureSample','CoordinateBasis: Triplanar (Dithered POM)'):
            self.assertIn(source,terms)
            self.assertNotEqual(source,terms[source])

if __name__=='__main__':unittest.main()
