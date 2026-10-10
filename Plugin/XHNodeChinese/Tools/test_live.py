import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core
from xh_node_chinese.live import LiveSession,append_pairs

class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'Dictionaries').mkdir()
        self.user=self.root/'Dictionaries/User.csv'
        self.original='# 我的词典\nKey,Value\n"Old","原文"\n'.encode('utf-8-sig')
        self.user.write_bytes(self.original)
        self.live=LiveSession(self.root,self.root/'Saved')

    def test_capture_import_and_preserve_direct_edits(self):
        self.live.sync(['New Term','New Term','123','中文'],{})
        rows=core.load_dictionary(self.live.path,include_empty=True)
        self.assertEqual([r['Source'] for r in rows],['New Term'])
        self.live.path.write_bytes(append_pairs(self.live.path.read_bytes(),{'New Term':'新的词条'}))
        self.assertEqual(self.live.sync(['New Term'],{})['imported'],1)
        self.assertEqual(core.load_dictionary(self.user)[0]['Translation'],'原文')
        self.assertTrue(any(p.read_bytes()==self.original for p in (self.root/'Saved/DictionaryBackups').glob('*.csv')))
        self.assertEqual(core.load_dictionary(self.user)[-1]['Translation'],'新的词条')
        self.user.write_bytes(append_pairs(self.user.read_bytes(),{'New Term':'后来直接编辑'}))
        self.assertEqual(self.live.sync(['New Term'],{})['imported'],0)
        self.assertEqual(core.load_dictionary(self.user)[-1]['Translation'],'后来直接编辑')
        again=LiveSession(self.root,self.root/'Saved')
        self.assertEqual(again.sync(['New Term'],{})['imported'],0)

    def test_invalid_import_is_atomic(self):
        self.live.sync([],{})
        for invalid in ['"Valid","有效"\n"Value {N}","数值"\n','"Valid","有效"\n"Broken']:
            self.live.path.write_text(invalid,encoding='utf-8')
            with self.assertRaises(ValueError):self.live.sync([],{})
            self.assertEqual(self.user.read_bytes(),self.original)

    def test_multiline_and_legacy_headers(self):
        for header in ['Source,Translation,Namespace,Key,Category\n','Value,Key\n','']:
            self.user.write_bytes(append_pairs(header.encode(),{'Line\n# Literal':'多行\n# 文本'}))
            rows=core.load_dictionary(self.user)
            self.assertEqual(rows[0]['Source'],'Line\n# Literal')
            self.assertEqual(rows[0]['Translation'],'多行\n# 文本')

    def test_preserves_existing_live_edits_while_appending(self):
        self.live.sync(['First Term'],{})
        before=self.live.path.read_bytes()
        self.live.sync(['First Term','Second Term'],{})
        self.assertTrue(self.live.path.read_bytes().startswith(before))
        self.assertEqual(len(core.load_dictionary(self.live.path,include_empty=True)),2)

if __name__=='__main__':unittest.main()
