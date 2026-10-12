import tempfile,unittest,zipfile
from pathlib import Path
import publish


class PackageDefaultsTests(unittest.TestCase):
    def test_all_defaults_are_current_and_personal_dictionary_is_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);plugin=root/'Plugin';d=plugin/'Dictionaries';d.mkdir(parents=True)
            (d/'UI.csv').write_text('Key,Value\nCollision Mode,碰撞模式\n',encoding='utf-8')
            (d/'Base.csv').write_bytes(b'Key,Value\n')
            (d/'Future.csv').write_bytes(b'Key,Value\n')
            (d/'SharedVersion.json').write_text('{"version":"test"}',encoding='utf-8')
            (d/'User.csv').write_text('Private,个人数据',encoding='utf-8')
            payloads=publish.default_dictionary_payloads(plugin)
            self.assertEqual(payloads['Dictionaries/User.csv'],b'Key,Value\n')
            self.assertIn('Dictionaries/Future.csv',payloads)
            package=root/'test.zip'
            def write(values):
                with zipfile.ZipFile(package,'w') as z:
                    for name,data in values.items():z.writestr('XHNodeChinese/'+name,data)
            write(payloads);self.assertTrue(publish.verify_packaged_defaults(package,plugin))
            stale=dict(payloads);stale['Dictionaries/UI.csv']=b'Key,Value\n';write(stale)
            with self.assertRaisesRegex(ValueError,'UI.csv'):publish.verify_packaged_defaults(package,plugin)
            missing=dict(payloads);missing.pop('Dictionaries/Future.csv');write(missing)
            with self.assertRaises(ValueError):publish.verify_packaged_defaults(package,plugin)


if __name__=='__main__':unittest.main()
