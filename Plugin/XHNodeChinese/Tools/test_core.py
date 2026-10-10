import struct
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'Content/Python'))
from xh_node_chinese import core, locres


class ResourceValidation(unittest.TestCase):
    def test_independent_legacy_fixture(self):
        # Known legacy layout, built independently of the production serializer.
        raw = (struct.pack('<I', 1) + b'\x02\0\0\0N\0' + struct.pack('<I', 1)
               + b'\x02\0\0\0K\0' + struct.pack('<I', 123) + struct.pack('<i', -2) + '中\0'.encode('utf-16-le'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.locres'
            path.write_bytes(raw)
            self.assertEqual(locres.read(path), [('N', 'K', 123, '中')])

    def test_corrupt_resource_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.locres'
            path.write_bytes(locres.MAGIC + b'\x03' + struct.pack('<q', 99999999))
            with self.assertRaises(ValueError):
                locres.read(path)

    def test_unicode_and_surrogate_pairs(self):
        entries = [('命名空间', '键', 1234, '中文 🎨'), ('命名空间', '另一个键', 5678, '中文 🎨')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'unicode.locres'
            path.write_bytes(locres.encode(entries))
            self.assertEqual(set(locres.read(path)), set(entries))

    def test_scoped_user_override_does_not_change_other_namespace(self):
        catalogue = [{'namespace': ns, 'key': 'k', 'source': 'Branch', 'hash': 4, 'category': 'Blueprint'} for ns in ('A', 'B')]
        with tempfile.TemporaryDirectory() as directory:
            base, user = Path(directory) / 'base.csv', Path(directory) / 'user.csv'
            base.write_text('Source,Translation\nBranch,分支\n', encoding='utf-8')
            user.write_text('Source,Translation,Namespace,Key\nBranch,条件分支,A,k\n', encoding='utf-8')
            entries, unmatched = core.select_translations(catalogue, [base, user])
            self.assertEqual({(n, k): text for n, k, h, text in entries}, {('A', 'k'): '条件分支', ('B', 'k'): '分支'})
            self.assertFalse(unmatched)

    def test_invalid_placeholders_preserve_resource(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory)
            (plugin / 'Dictionaries').mkdir()
            path = plugin / 'Dictionaries/User.csv'
            path.write_text('Source,Translation\nValue {0},值 {0}\n', encoding='utf-8')
            cat = [{'namespace': 'N', 'key': 'K', 'hash': 100, 'source': 'Value {0}', 'category': 'Niagara'}]
            core.compile_dictionary(plugin, cat)
            resource = plugin / 'Content/Localization/XHNodeChinese/zh-Hans-CN/XHNodeChinese.locres'
            before = resource.read_bytes()
            path.write_text('Source,Translation\nValue {0},值\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                core.compile_dictionary(plugin, cat)
            self.assertEqual(resource.read_bytes(), before)

    def test_pending_export_preserves_work_in_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = root / 'Pending.csv'
            original = b'Source,Translation\nBranch,work-in-progress\n'
            pending.write_bytes(original)
            cat = [{'namespace': 'N', 'key': 'K', 'hash': 1, 'source': 'Branch', 'builtin': '', 'category': 'Blueprint'}]
            self.assertEqual(core.export_pending(root, cat, pending), 0)
            self.assertEqual(core.load_dictionary(pending)[0]['Translation'], 'work-in-progress')
            backups = list(root.glob('Pending.backup-*.csv'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)


    def test_headerless_user_examples_keep_first_row(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'User.csv'
            path.write_text('\ufeff\n"MyCustomTerm","我的自定义词条"\n"MyOtherTerm","我的另一个词条"\n', encoding='utf-8')
            rows = core.load_dictionary(path)
            self.assertEqual([(r['Source'], r['Translation']) for r in rows], [('MyCustomTerm', '我的自定义词条'), ('MyOtherTerm', '我的另一个词条')])
            self.assertTrue(all(not r['Namespace'] and not r['Key'] for r in rows))

    def test_headerless_quotes_commas_and_multiline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'User.csv'
            path.write_text('"A, B","甲，乙"\n"Say ""Hello""","说“你好”"\n"First\nSecond","第一行\n第二行"\n', encoding='utf-8', newline='')
            rows = core.load_dictionary(path)
            self.assertEqual(rows[0]['Source'], 'A, B')
            self.assertEqual(rows[1]['Source'], 'Say "Hello"')
            self.assertEqual(rows[2]['Source'], 'First\nSecond')

    def test_headerless_invalid_columns_and_quotes_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'User.csv'
            for invalid in ('A,B,C\n', '"unfinished,中文\n'):
                path.write_text(invalid, encoding='utf-8')
                with self.assertRaises(ValueError):
                    core.load_dictionary(path)

    def test_headerless_placeholder_validation_and_user_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, user = root / 'Base.csv', root / 'User.csv'
            base.write_text('Source,Translation\nBranch,分支\n', encoding='utf-8')
            user.write_text('"Branch","自定义分支"\n', encoding='utf-8')
            cat = [{'namespace': 'K2Node', 'key': 'Branch', 'hash': 4, 'source': 'Branch', 'category': 'Blueprint'}]
            entries, _ = core.select_translations(cat, [base, user])
            self.assertEqual(entries[0][3], '自定义分支')
            user.write_text('"Value {0}","数值"\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                core.load_dictionary(user)

    def test_user_pasted_comment_and_key_value_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'User.csv'
            path.write_text('# 用户自定义词典：一行一条，格式 "英文","中文"（请以 UTF-8 编码保存）\nKey,Value\n"MyCustomTerm","我的自定义词条"\n# 第二条\n"MyOtherTerm","我的另一个词条"\n', encoding='utf-8')
            rows = core.load_dictionary(path)
            self.assertEqual([(r['Source'], r['Translation']) for r in rows], [('MyCustomTerm', '我的自定义词条'), ('MyOtherTerm', '我的另一个词条')])

    def test_hash_in_quoted_and_multiline_fields_is_not_a_comment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'User.csv'
            path.write_text('"#Term","井号词条"\n"First\n#Second","第一行\n#第二行"\n', encoding='utf-8', newline='')
            rows = core.load_dictionary(path)
            self.assertEqual(rows[0]['Source'], '#Term')
            self.assertEqual(rows[1]['Source'], 'First\n#Second')


if __name__ == '__main__':
    unittest.main()
