import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core,bridge
from xh_node_chinese.long_text import LongTextSession,eligible
from xh_node_chinese.live import LiveSession,append_pairs

SOURCE='This module uses the value {Value} to control the initial particle position and applies the selected force to every particle in the system.'

class LongTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'Dictionaries').mkdir()
        self.user=self.root/'Dictionaries/User.csv';self.user.write_text('Key,Value\n',encoding='utf-8')
        self.session=LongTextSession(self.root/'Saved')

    def test_manual_roundtrip_independent_and_clear(self):
        before=self.user.read_bytes()
        self.assertTrue(eligible(SOURCE))
        self.assertFalse(self.session.sync([SOURCE,SOURCE,'Short label'],{}))
        self.assertEqual(self.session.total,1)
        self.session.path.write_bytes(append_pairs(self.session.path.read_bytes(),{SOURCE:'此模块使用 {Value} 控制粒子的初始位置。'}))
        self.assertTrue(self.session.sync([],{}))
        self.assertIn(SOURCE,self.session.terms)
        again=LongTextSession(self.root/'Saved');again.sync([],{})
        self.assertEqual(again.terms,self.session.terms)
        self.assertEqual(self.user.read_bytes(),before)
        self.session.path.write_bytes(append_pairs(self.session.path.read_bytes(),{SOURCE:''}))
        self.assertTrue(self.session.sync([],{}))
        self.assertFalse(self.session.terms)

    def test_invalid_edit_preserves_last_valid_translation(self):
        self.session.sync([SOURCE],{})
        self.session.path.write_bytes(append_pairs(self.session.path.read_bytes(),{SOURCE:'有效译文 {Value}'}))
        self.session.sync([],{})
        valid=self.session.terms.copy()
        self.session.path.write_bytes(append_pairs(self.session.path.read_bytes(),{SOURCE:'错误译文缺少占位符'}))
        with self.assertRaises(ValueError):self.session.sync([],{})
        self.assertEqual(self.session.terms,valid)
        self.assertTrue(self.session.error)

    def test_priority_and_long_export_separation(self):
        translated='完整中文 {Value}'
        self.assertEqual(bridge.dictionary(self.root,{SOURCE:translated})[SOURCE],translated)
        self.user.write_bytes(append_pairs(self.user.read_bytes(),{SOURCE:'个人优先 {Value}'}))
        self.assertEqual(bridge.dictionary(self.root,{SOURCE:translated})[SOURCE],'个人优先 {Value}')
        live=LiveSession(self.root,self.root/'Saved')
        live.sync([SOURCE,'New Label'],{},separate_long=True)
        self.assertEqual([r['Source'] for r in core.load_dictionary(live.path,True)],['New Label'])

    def test_explicit_open_can_prefill_existing_complete_translation(self):
        self.session.sync([SOURCE],{SOURCE:'已知中文 {Value}'})
        self.assertEqual(self.session.total,0)
        self.session.sync([SOURCE],{SOURCE:'已知中文 {Value}'},include_known=True)
        self.assertEqual(self.session.terms[SOURCE],'已知中文 {Value}')

if __name__=='__main__':unittest.main()
