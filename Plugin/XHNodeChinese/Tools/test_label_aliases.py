import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese.term_keys import Resolver
from xh_node_chinese import core

class LabelAliasTests(unittest.TestCase):
    def test_complete_label_variants_and_explicit_indices(self):
        r=Resolver({'Combined Collision Normal':'合并碰撞法线','Module Collision {Index} Normal':'模块碰撞 {Index} 法线',
                    'Dynamic Material Parameter':'动态材质参数','ModuleCollision2Normal':'用户二号法线'})
        for source,expected in [('CombinedCollisionNormal','合并碰撞法线'),('ModuleCollision 1 Normal','模块碰撞 1 法线'),
                                ('Module Collision 001 Normal','模块碰撞 001 法线'),('ModuleCollision2Normal','用户二号法线'),
                                ('DynamicMaterialParameter3','动态材质参数 3')]:
            self.assertEqual(r.translated(source),expected)
        for source in ('Output.Collision.CombinedCollisionNormal','/Game/CombinedCollisionNormal','CombinedCollisionNormal()',
                       'ModuleCollision1Normal2','ModuleCollision-1Normal','float4','Vector3','Texture2D','A sentence with CombinedCollisionNormal.'):
            self.assertIsNone(r.translated(source),source)

    def test_ambiguous_alias_and_exact_personal_override(self):
        r=Resolver({'AB C':'甲','A BC':'乙','ABC':'用户译文'})
        self.assertEqual(r.translated('ABC'),'用户译文')
        self.assertIsNone(r.translated('A B C'))
        self.assertEqual(r.translated('AB C'),'甲')

    def test_known_output_labels_are_not_exported_again(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'Dictionaries').mkdir()
            (p/'Dictionaries/Shared.csv').write_text('Source,Translation,Namespace,Key,Category\nCombined Collision Normal,合并碰撞法线,,,Niagara\nModule Collision {Index} Normal,模块碰撞 {Index} 法线,,,Niagara\n',encoding='utf-8')
            target=p/'Pending.csv'
            self.assertEqual(core.export_pending(p,[],target,['CombinedCollisionNormal','ModuleCollision 1 Normal','ModuleCollision12Normal']),0)

if __name__=='__main__':unittest.main()
