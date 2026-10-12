"""Update workflow regressions: user data isolation, cache failure, portable updates."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import manager_core as c


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.project=self.root/'P';self.project.mkdir();(self.project/'P.uproject').write_text('{}')
        self.plugin=self.project/'Plugins/XHNodeChinese';self.plugin.mkdir(parents=True)
        c.write_json(self.plugin/'XHNodeChinese.uplugin',{'VersionName':'0.2.10','XHSharedDictionaryVersion':1})
        self.closed=patch.object(c,'ensure_closed');self.closed.start()

    def tearDown(self):self.closed.stop();self.temp.cleanup()

    def archive(self,name,contents):
        p=self.root/name
        with zipfile.ZipFile(p,'w') as z:
            for key,data in contents.items():z.writestr(key,data)
        return p

    def shared(self):
        return self.archive('shared.zip',{'User.csv':'Key,Value\nSize,尺寸\n',
                           'LongText.csv':'Key,Value\n"A long explanation.","一段长说明。"\n'})

    def test_default_update_preserves_user_and_assets_and_can_restore(self):
        sentinels={c.PROTECTED[0]:b'Key,Value\nSize,my own translation\n',c.PROTECTED[1]:b'my notes',
                   'Content/FX.uasset':b'asset-bytes','Content/Level.umap':b'map-bytes','Config/DefaultEngine.ini':b'config'}
        for n,data in sentinels.items():c.atomic(self.project/n,data)
        archive=self.shared();backup=c.update_shared_defaults(self.project,archive,'2026.10.12')
        self.assertEqual(c.json_read(self.project/c.SHARED_FILES[2])['version'],'2026.10.12')
        self.assertEqual(c.csv_validate((self.project/c.SHARED_FILES[0]).read_bytes()),1)
        self.assertEqual(sentinels,{n:(self.project/n).read_bytes() for n in sentinels})
        report=c.update_summary({'shared':{'version':'2026.10.12','sha256':c.digest(archive)}},self.project)
        self.assertFalse(report['shared_update'])
        c.restore(self.project,backup)
        self.assertTrue(all(not (self.project/n).exists() for n in c.SHARED_FILES))
        self.assertEqual(sentinels,{n:(self.project/n).read_bytes() for n in sentinels})

    def test_default_update_rolls_back_all_three_files(self):
        original={n:b'original-'+str(i).encode() for i,n in enumerate(c.SHARED_FILES)}
        for n,data in original.items():c.atomic(self.project/n,data)
        atomic=c.atomic;count=0
        def fail(path,data):
            nonlocal count
            count+=1
            if count==3:raise OSError('disk full')
            return atomic(path,data)
        with patch.object(c,'atomic',side_effect=fail):
            with self.assertRaises(OSError):c.update_shared_defaults(self.project,self.shared(),'2026.10.12')
        self.assertEqual(original,{n:(self.project/n).read_bytes() for n in original})

    def test_legacy_plugin_does_not_accept_unused_shared_files(self):
        c.write_json(self.plugin/'XHNodeChinese.uplugin',{'VersionName':'0.2.8'})
        with self.assertRaisesRegex(ValueError,'先更新插件'):c.update_shared_defaults(self.project,self.shared(),'2026.10.12')
        self.assertFalse((self.project/c.SHARED_FILES[0]).exists())

    def test_feed_cache_is_validated_and_scoped_to_source(self):
        archive=self.shared();source=self.root/'manifest.json';cache=self.root/'cache'
        c.write_json(source,{'schema':1,'plugins':[],'shared':{'url':archive.name,'sha256':c.digest(archive),'version':'1'}})
        self.assertNotIn('_cached',c.load_feed(source,cache))
        source.write_text('{broken')
        cached=c.load_feed(source,cache,allow_cached=True)
        self.assertTrue(cached['_cached']);self.assertEqual(cached['shared']['version'],'1')
        with self.assertRaises(OSError):c.load_feed(self.root/'different.json',cache,allow_cached=True)

    def test_manager_update_is_staged_without_changing_current_files(self):
        old=self.root/'old.exe';old.write_bytes(b'old')
        archive=self.archive('manager.zip',{'XHPluginManager/XHPluginManager.exe':b'new',
                                           'XHPluginManager/_internal/a.dll':b'dependency'})
        exe=c.prepare_manager_update({'version':'1.0.3','_location':str(archive),'sha256':c.digest(archive)},self.root/'cache')
        self.assertEqual(exe.read_bytes(),b'new');self.assertEqual(old.read_bytes(),b'old')
        bad=self.archive('bad-manager.zip',{'XHPluginManager/XHPluginManager.exe':b'new','../evil':b'bad'})
        with self.assertRaises(ValueError):c.prepare_manager_update({'version':'1.0.3','_location':str(bad),'sha256':c.digest(bad)},self.root/'cache')
        self.assertFalse((self.root/'evil').exists())

    def test_versions_are_numeric_and_trailing_zeros_equivalent(self):
        self.assertTrue(c.newer_version('0.2.10','0.2.9'))
        self.assertFalse(c.newer_version('1.0.0','1.0'))

    def test_update_prefers_new_chinese_name_with_legacy_entry_present(self):
        archive=self.archive('renamed.zip',{'XHPluginManager/XHPluginManager.exe':b'legacy',
            'XHPluginManager/虚幻翻译插件.exe':b'renamed','XHPluginManager/_internal/a.dll':b'dependency'})
        exe=c.prepare_manager_update({'version':'1.0.11','_location':str(archive),'sha256':c.digest(archive)},self.root/'cache')
        self.assertEqual(exe.name,'虚幻翻译插件.exe');self.assertEqual(exe.read_bytes(),b'renamed')
        self.assertTrue((exe.parent/'XHPluginManager.exe').is_file())


if __name__=='__main__':unittest.main()
