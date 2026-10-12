"""Bundled translations work on first run; personal translations retain precedence."""
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core,bridge
from xh_node_chinese.term_keys import Resolver

class SharedTests(unittest.TestCase):
    def test_initial_labels_long_text_and_personal_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin=Path(tmp);d=plugin/'Dictionaries';d.mkdir()
            (d/'Shared.csv').write_text('Key,Value\nRotationalInertia,旋转惯量\nDynamicMaterialParameter,动态材质参数\n',encoding='utf-8')
            (d/'SharedLongText.csv').write_text('Key,Value\n"A long module explanation.","模块的完整说明。"\n',encoding='utf-8')
            self.assertEqual(bridge.dictionary(plugin)['RotationalInertia'],'旋转惯量')
            self.assertEqual(bridge.graph_dictionary(plugin)['A long module explanation.'],'模块的完整说明。')
            self.assertEqual(Resolver(bridge.export_dictionary(plugin)).translated('DynamicMaterialParameter3'),'动态材质参数 3')
            (d/'User.csv').write_text('Key,Value\nRotationalInertia,我的惯量译名\n',encoding='utf-8')
            self.assertEqual(bridge.dictionary(plugin)['RotationalInertia'],'我的惯量译名')
            self.assertEqual(bridge.dictionary(plugin,{'A long module explanation.':'我的说明'})['A long module explanation.'],'我的说明')
            catalogue=[{'namespace':'Niagara','key':'R','source':'RotationalInertia','hash':0,'category':'Niagara'}]
            report=core.compile_dictionary(plugin,catalogue)
            self.assertEqual(report['translated_entries'],1)
            self.assertFalse((plugin/'Saved').exists())

    def test_scoped_translation_does_not_leak_to_other_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin=Path(tmp);d=plugin/'Dictionaries';d.mkdir()
            (d/'Shared.csv').write_text('Source,Translation,Namespace,Key,Category\nNormal,法线,,,Material\n',encoding='utf-8')
            self.assertNotIn('Normal',bridge.dictionary(plugin))
            self.assertEqual(bridge.graph_dictionary(plugin)['Normal'],'法线')

if __name__=='__main__':unittest.main()
