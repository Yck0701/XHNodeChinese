import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core,bridge
from xh_node_chinese.long_text import LongTextSession

class CaptureCoverageTests(unittest.TestCase):
    def test_dropdown_dictionary_is_global_with_personal_priority(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(bridge.dictionary(root)['Surface'],'表面')
        self.assertEqual(bridge.dictionary(root)['User Interface'],'用户界面')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'Dictionaries').mkdir()
            (p/'Dictionaries/UI.csv').write_bytes((root/'Dictionaries/UI.csv').read_bytes())
            (p/'Dictionaries/User.csv').write_text('Key,Value\nSurface,自定义表面\n',encoding='utf-8')
            self.assertEqual(bridge.dictionary(p)['Surface'],'自定义表面')

    def test_long_tooltip_with_path_routes_to_long_queue_and_known_translation(self):
        root=Path(__file__).resolve().parents[1]
        rows=core.load_dictionary(root/'Dictionaries/Descriptions.csv')
        source=next(r['Source'] for r in rows if '/Niagara/' in r['Source'])
        value=bridge.dictionary(root)[source]
        self.assertIn('[Transient]CollisionValid',value)
        self.assertIn('/Niagara/Modules/Collision/Collision.Collision',value)
        self.assertIn('Write to Intrinsic Properties',value)
        with tempfile.TemporaryDirectory() as tmp:
            session=LongTextSession(tmp);session.sync([source],{})
            self.assertEqual(session.pending,1)
            session.sync([],bridge.dictionary(root))
            self.assertEqual(session.pending,0)

if __name__=='__main__':unittest.main()
