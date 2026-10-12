"""Installer regressions using real Windows sharing locks and injected I/O faults."""
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import manager_core as c


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.project=self.root/'Project';self.project.mkdir()
        self.plugin=self.project/'Plugins/XHNodeChinese'
        self.sentinels={'Project.uproject':b'{}','Content/FX.uasset':b'asset',
                        'Content/Level.umap':b'map','Config/DefaultEngine.ini':b'config',
                        c.PROTECTED[0]:b'personal terms',c.PROTECTED[1]:b'personal long text'}
        for name,data in self.sentinels.items():c.atomic(self.project/name,data)
        c.atomic(self.plugin/'XHNodeChinese.uplugin',b'{"VersionName":"old"}')
        c.atomic(self.plugin/'Saved/custom.json',b'original settings')
        self.before=self.files(self.plugin)
        self.info={'sha256':{'engine':'test'}}
        dll=b'test DLL';manifest={'engine_sha256':self.info['sha256'],'bridge_file':'XHSlateBridge027.dll',
                                'bridge_sha256':hashlib.sha256(dll).hexdigest()}
        self.archive=self.root/'plugin.zip'
        with zipfile.ZipFile(self.archive,'w') as z:
            for name,data in {'XHNodeChinese.uplugin':'{"VersionName":"new"}',
                              'Binaries/Win64/bridge-manifest.json':json.dumps(manifest),
                              'Binaries/Win64/XHSlateBridge027.dll':dll}.items():z.writestr('XHNodeChinese/'+name,data)
        self.closed=patch.object(c,'ensure_closed');self.closed.start()
        self.recovery=self.project/'Saved/XHNodeChinese/UpdaterBackups/install-recovery.json'

    def tearDown(self):self.closed.stop();self.temp.cleanup()

    @staticmethod
    def files(path):return {p.relative_to(path).as_posix():p.read_bytes() for p in path.rglob('*') if p.is_file()}

    def check_personal(self):self.assertEqual(self.sentinels,{n:(self.project/n).read_bytes() for n in self.sentinels})

    def test_complete_backup_and_personal_and_assets_preserved(self):
        saved=c.install(self.project,self.archive,self.info)
        old=saved.parent/('plugin-'+saved.stem)
        self.assertEqual(self.before,self.files(old));self.check_personal()
        self.assertEqual(c.json_read(self.plugin/'XHNodeChinese.uplugin')['VersionName'],'new')
        self.assertFalse(self.recovery.exists())

    def test_transient_winerror_5_retries_then_succeeds(self):
        replace=c.os.replace;attempts=[];logs=[]
        def flaky(src,dst):
            if Path(src)==self.plugin:
                attempts.append(1)
                if len(attempts)<3:
                    error=PermissionError('simulated access denial');error.winerror=5;raise error
            return replace(src,dst)
        with patch.object(c.os,'replace',side_effect=flaky),patch.object(c.time,'sleep'):
            c.install(self.project,self.archive,self.info,logs.append)
        self.assertEqual(len(attempts),3);self.assertTrue(any('重试' in text for text in logs));self.check_personal()

    @unittest.skipUnless(os.name=='nt','Windows directory lock')
    def test_real_locked_directory_updates_files_and_preserves_data(self):
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
        k.CreateFileW.restype=w.HANDLE;k.CloseHandle.argtypes=[w.HANDLE]
        handle=k.CreateFileW(str(self.plugin),0x80000000,3,None,3,0x02000000,None)
        self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
        try:
            with patch.object(c.time,'sleep'):
                saved=c.install(self.project,self.archive,self.info)
            self.assertEqual(self.before,self.files(saved.parent/('plugin-'+saved.stem)));self.check_personal()
            self.assertEqual(c.json_read(self.plugin/'XHNodeChinese.uplugin')['VersionName'],'new')
            self.assertFalse(self.recovery.exists())
        finally:k.CloseHandle(handle)

    @unittest.skipUnless(os.name=='nt','Windows file lock')
    def test_locked_file_refuses_fallback_before_changing_any_files(self):
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
        k.CreateFileW.restype=w.HANDLE;k.CloseHandle.argtypes=[w.HANDLE]
        handle=k.CreateFileW(str(self.plugin/'XHNodeChinese.uplugin'),0x80000000,1,None,3,0,None)
        self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
        try:
            with patch.object(c.time,'sleep'),self.assertRaisesRegex(RuntimeError,'文件被占用'):
                c.install(self.project,self.archive,self.info)
            self.assertEqual(self.before,self.files(self.plugin));self.check_personal()
            self.assertFalse(self.recovery.exists())
        finally:k.CloseHandle(handle)

    def run_file_failure(self,fail_rollback=False):
        replace=c.os.replace;count=0
        def fail(src,dst):
            nonlocal count
            if Path(src)==self.plugin:
                error=PermissionError('directory locked');error.winerror=5;raise error
            if self.plugin in Path(dst).parents and Path(src).is_relative_to(self.recovery.parent):
                count+=1
                if count==2:raise OSError('file install failed')
            return replace(src,dst)
        atomic=c.atomic
        def restore(path,data):
            if fail_rollback and self.plugin in Path(path).parents:raise OSError('rollback blocked')
            return atomic(path,data)
        with patch.object(c.os,'replace',side_effect=fail),patch.object(c,'atomic',side_effect=restore),patch.object(c.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'部分文件未能自动恢复' if fail_rollback else '已恢复原插件'):
                c.install(self.project,self.archive,self.info)

    def test_file_fallback_rolls_back_after_partial_install(self):
        self.run_file_failure()
        self.assertEqual(self.before,self.files(self.plugin));self.check_personal()
        self.assertFalse(self.recovery.exists())

    def test_file_fallback_retains_recovery_when_rollback_fails(self):
        # Ensure the first replaced file existed so rollback needs to write it.
        c.atomic(self.plugin/'Binaries/Win64/XHSlateBridge027.dll',b'old DLL')
        self.before=self.files(self.plugin)
        self.run_file_failure(True)
        record=c.json_read(self.recovery)
        self.assertEqual(record['mode'],'files')
        self.assertEqual(self.before,self.files(Path(record['old_plugin'])))
        self.assertTrue(Path(record['staged_plugin']).is_dir())

    def test_failed_install_restores_original(self):
        replace=c.os.replace
        def fail(src,dst):
            if Path(src).name.startswith('install-stage-') and Path(dst)==self.plugin:raise OSError('disk error')
            return replace(src,dst)
        with patch.object(c.os,'replace',side_effect=fail),self.assertRaisesRegex(RuntimeError,'已恢复原插件'):
            c.install(self.project,self.archive,self.info)
        self.assertEqual(self.before,self.files(self.plugin));self.check_personal()
        self.assertFalse(self.recovery.exists())

    def test_failed_rollback_retains_complete_backup_and_recovery(self):
        replace=c.os.replace
        def fail(src,dst):
            if Path(dst)==self.plugin:raise OSError('destination blocked')
            return replace(src,dst)
        with patch.object(c.os,'replace',side_effect=fail),self.assertRaisesRegex(RuntimeError,'完整旧插件已保留'):
            c.install(self.project,self.archive,self.info)
        record=c.json_read(self.recovery)
        self.assertEqual(self.before,self.files(Path(record['old_plugin'])))
        self.assertTrue(Path(record['staged_plugin']).is_dir())
        with self.assertRaisesRegex(RuntimeError,'上次安装尚未恢复'):c.install(self.project,self.archive,self.info)

    def test_interruption_retains_original_and_recovery_record(self):
        replace=c.os.replace
        def interrupt(src,dst):
            if Path(src).name.startswith('install-stage-') and Path(dst)==self.plugin:raise KeyboardInterrupt()
            return replace(src,dst)
        with patch.object(c.os,'replace',side_effect=interrupt),self.assertRaises(KeyboardInterrupt):
            c.install(self.project,self.archive,self.info)
        record=c.json_read(self.recovery)
        self.assertEqual(self.before,self.files(Path(record['old_plugin'])))
        self.assertTrue(Path(record['staged_plugin']).is_dir())

    @unittest.skipUnless(os.name=='nt','Windows process list')
    def test_commandlet_editor_is_detected(self):
        self.closed.stop()
        for exe in ('UnrealEditor-Cmd.exe','UE4Editor.exe','UnrealEditor.exe'):
            with self.subTest(exe=exe),patch.object(c.subprocess,'run') as run:
                run.return_value.stdout=('"'+exe+'","123"').encode()
                with self.assertRaisesRegex(RuntimeError,'关闭 UE'):c.ensure_closed()


if __name__=='__main__':unittest.main()
