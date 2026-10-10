import csv
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core, bridge

class DisplayDictionaryTests(unittest.TestCase):
    def test_dynamic_user_override_and_scoped_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'Dictionaries').mkdir()
            (p/'Dictionaries/Base.csv').write_text('"Initialize Particle","初始化粒子"\n',encoding='utf-8')
            (p/'Dictionaries/User.csv').write_text('Source,Translation,Namespace,Key,Category\nInitialize Particle,我的初始化,,,\nPrivate,私有,Scope,K,Niagara\n',encoding='utf-8')
            self.assertEqual(bridge.dictionary(p),{'Initialize Particle':'我的初始化'})

    def test_export_observed_dynamic_text_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'Dictionaries').mkdir()
            (p/'Dictionaries/Base.csv').write_text('Key,Value\nInitialize Particle,初始化粒子\n',encoding='utf-8')
            (p/'Dictionaries/User.csv').write_text('Key,Value\n',encoding='utf-8')
            dest=p/'Pending.csv'
            count=core.export_pending(p,[],dest,observed=['New Niagara Description','New Niagara Description','Initialize Particle','12','中文'])
            self.assertEqual(count,1)
            rows=core.load_dictionary(dest,include_empty=True)
            self.assertEqual(rows[0]['Source'],'New Niagara Description')
            rows[0]['Translation']='新的 Niagara 说明'
            with (p/'Dictionaries/User.csv').open('w',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=core.FIELDS);w.writeheader();w.writerows(rows)
            self.assertEqual(bridge.dictionary(p)['New Niagara Description'],'新的 Niagara 说明')

if __name__=='__main__':unittest.main()
