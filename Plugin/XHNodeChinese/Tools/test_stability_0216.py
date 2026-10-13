"""Cache freshness, interrupted writes and redirected project protection."""
from pathlib import Path
import os, sys, tempfile, unittest, subprocess
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core, live

class StabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.csv=self.root/'terms.csv'
        core.atomic_write(self.csv,b'Key,Value\nSize,\xe5\xb0\xba\xe5\xaf\xb8\n')
        core._dictionary_cache.clear()
    def tearDown(self):self.tmp.cleanup()
    def test_cache_and_returned_rows_are_independent(self):
        rows=core.load_dictionary(self.csv);rows[0]['Translation']='poison'
        with patch.object(core,'_read_dictionary',side_effect=AssertionError('reparsed')):
            self.assertEqual(core.load_dictionary(self.csv)[0]['Translation'],'尺寸')
    def test_atomic_replacement_and_manual_edit_invalidate_cache(self):
        core.load_dictionary(self.csv)
        core.atomic_write(self.csv,'Key,Value\nSize,大小\n'.encode())
        self.assertEqual(core.load_dictionary(self.csv)[0]['Translation'],'大小')
        self.csv.write_text('Key,Value\nSize,尺寸设置\n',encoding='utf-8')
        self.assertEqual(core.load_dictionary(self.csv)[0]['Translation'],'尺寸设置')
    def test_invalid_update_never_returns_cached_success(self):
        core.load_dictionary(self.csv);self.csv.write_text('"broken',encoding='utf-8')
        with self.assertRaises(ValueError):core.load_dictionary(self.csv)
        core.atomic_write(self.csv,b'Key,Value\nScale,scale\n')
        self.assertEqual(core.load_dictionary(self.csv)[0]['Source'],'Scale')
    def test_delete_then_recreate_is_detected(self):
        core.load_dictionary(self.csv);self.csv.unlink()
        self.assertEqual(core.load_dictionary(self.csv),[])
        core.atomic_write(self.csv,b'Key,Value\nScale,scale\n')
        self.assertEqual(len(core.load_dictionary(self.csv)),1)
    def test_pending_and_filled_cache_are_separate(self):
        core.atomic_write(self.csv,b'Key,Value\nMissing,\n')
        self.assertEqual(core.load_dictionary(self.csv),[])
        self.assertEqual(len(core.load_dictionary(self.csv,True)),1)
    def test_failed_replace_preserves_original_and_removes_temp(self):
        before=self.csv.read_bytes();files=set(self.root.iterdir())
        with patch.object(core.os,'replace',side_effect=OSError('locked')):
            with self.assertRaises(OSError):core.atomic_write(self.csv,b'new data')
        self.assertEqual(before,self.csv.read_bytes());self.assertEqual(files,set(self.root.iterdir()))
    def test_failed_write_preserves_original_and_removes_temp(self):
        before=self.csv.read_bytes();files=set(self.root.iterdir())
        with patch.object(core.os,'fsync',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):core.atomic_write(self.csv,b'new data')
        self.assertEqual(before,self.csv.read_bytes());self.assertEqual(files,set(self.root.iterdir()))
    @unittest.skipUnless(os.name=='nt','Windows junction')
    def test_junction_cannot_write_into_another_project(self):
        other=self.root/'OtherProject';other.mkdir();sentinel=other/'keep.txt';sentinel.write_bytes(b'keep')
        link=self.root/'SavedLink'
        subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(link),str(other)],check=True,
                       capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            with self.assertRaisesRegex(ValueError,'目录联接'):core.atomic_write(link/'keep.txt',b'changed')
            with self.assertRaisesRegex(ValueError,'目录联接'):core.atomic_write(link/'new/file.txt',b'new')
            self.assertEqual(sentinel.read_bytes(),b'keep')
            self.assertEqual(list(other.iterdir()),[sentinel])
        finally:link.rmdir()
    def test_idle_sync_skips_reparse_and_imports_later_edit(self):
        plugin=self.root/'plugin';save=self.root/'save'
        core.atomic_write(plugin/'Dictionaries/User.csv',b'Key,Value\n')
        session=live.LiveSession(plugin,save)
        session.sync(['Missing Term'],{})
        with patch.object(core,'load_dictionary',side_effect=AssertionError('idle reparse')):
            self.assertEqual(session.sync(['Missing Term'],{})['imported'],0)
        core.atomic_write(session.path,'Key,Value\nMissing Term,我的词条\n'.encode())
        self.assertEqual(session.sync([],{})['imported'],1)
    def test_known_map_mutation_and_personal_edit_invalidate_idle_cache(self):
        plugin=self.root/'plugin';save=self.root/'save'
        core.atomic_write(plugin/'Dictionaries/User.csv',b'Key,Value\n')
        s=live.LiveSession(plugin,save);known={}
        s.sync(['Missing Term'],known);known['Missing Term']='已翻译'
        self.assertEqual(s.sync(['Missing Term'],known)['pending'],0)
        s.sync(['Second Term'],known)
        core.atomic_write(plugin/'Dictionaries/User.csv','Key,Value\nSecond Term,第二个词\n'.encode())
        self.assertEqual(s.sync(['Second Term'],known)['pending'],0)

if __name__=='__main__':unittest.main()
