"""In-place update regressions: original path, rollback and unrelated files."""
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest
import manager_core as core
import manager_update as update


class ManagerUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.target=self.root/'旧版 中文路径';self.stage=self.root/'download'
        for base,value in ((self.target,b'old'),(self.stage,b'new')):
            for name in update.EXECUTABLES+('_internal/runtime.dll','release/package.zip'):
                core.atomic(base/name,value)
            core.write_json(base/'release/manifest.json',{'manager_version':'1.0.17'})
        self.executable=update.EXECUTABLES[0]
        self.protected={n:b'unchanged' for n in ('source-packages/custom.zip','settings.json','my-notes.txt','Content/demo.uasset')}
        for n,d in self.protected.items():core.atomic(self.target/n,d)
        self.record=self.root/'result.json'

    def plan(self):return core.json_read(update.prepare(self.stage,self.target,self.executable,self.root/'state'))

    def assert_protected(self):
        self.assertEqual({n:(self.target/n).read_bytes() for n in self.protected},self.protected)

    def test_replaces_same_executable_and_both_aliases_preserves_user_files(self):
        exe=update.replace_files(self.plan(),self.record)
        self.assertEqual(exe,self.target/self.executable)
        for name in update.EXECUTABLES:self.assertEqual((self.target/name).read_bytes(),b'new')
        record=core.json_read(self.record)
        self.assertEqual(record['status'],'installed')
        self.assertEqual((Path(record['backup'])/self.executable).read_bytes(),b'old')
        self.assert_protected()

    def test_locked_old_runtime_rolls_back_executables(self):
        plan=self.plan();rename=update.os.replace
        def locked(src,dst):
            if Path(src)==self.target/'_internal':raise PermissionError('runtime in use')
            return rename(src,dst)
        with patch.object(update.os,'replace',side_effect=locked):
            with self.assertRaisesRegex(RuntimeError,'恢复'):update.replace_files(plan,self.record)
        self.assertEqual((self.target/self.executable).read_bytes(),b'old')
        self.assertEqual((self.target/'_internal/runtime.dll').read_bytes(),b'old')
        self.assertEqual(core.json_read(self.record)['status'],'rolled_back');self.assert_protected()

    def test_failed_new_copy_leaves_old_files(self):
        plan=self.plan()
        with patch.object(update.shutil,'copytree',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(RuntimeError,'disk full'):update.replace_files(plan,self.record)
        self.assertEqual((self.target/self.executable).read_bytes(),b'old');self.assert_protected()

    def test_changed_stage_never_overwrites_target(self):
        plan=self.plan();(self.stage/self.executable).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'变化'):update.replace_files(plan,self.record)
        self.assertEqual((self.target/self.executable).read_bytes(),b'old')

    def test_other_update_changed_target_is_rejected(self):
        plan=self.plan();(self.target/self.executable).write_bytes(b'newer')
        with self.assertRaisesRegex(ValueError,'其他更新'):update.replace_files(plan,self.record)
        self.assertEqual((self.target/self.executable).read_bytes(),b'newer')

    def test_unrelated_folder_or_nested_cache_rejected(self):
        for target in (self.root,self.stage,self.stage/'child'):
            with self.assertRaises(ValueError):update.prepare(self.stage,target,self.executable,self.root/'state')
        with self.assertRaises(ValueError):update.prepare(self.stage,self.target,'other.exe',self.root/'state')
        self.assert_protected()

    def test_second_update_does_not_overwrite_rollback_files(self):
        update.replace_files(self.plan(),self.record)
        first=core.json_read(self.record)['backup']
        update.replace_files(self.plan(),self.record)
        second=core.json_read(self.record)['backup']
        self.assertNotEqual(first,second)
        self.assertEqual((Path(first)/self.executable).read_bytes(),b'old')

    def test_reparse_point_target_rejected(self):
        # Real symlink creation requires Windows privileges; exercise the guard without granting them.
        original=Path.is_symlink
        with patch.object(Path,'is_symlink',lambda p:p==self.target or original(p)):
            with self.assertRaises(ValueError):self.plan()


if __name__=='__main__':unittest.main()
