import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import manager_core as c


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.project=self.root/'Project';self.project.mkdir();(self.project/'Example.uproject').write_text('{}')
        self.closed=patch.object(c,'ensure_closed');self.closed.start()

    def tearDown(self):self.closed.stop();self.tmp.cleanup()

    def zip(self,name,files):
        p=self.root/name
        with zipfile.ZipFile(p,'w') as z:
            for key,value in files.items():z.writestr(key,value)
        return p

    def initial(self):
        for rel,data in zip(c.PROTECTED,[b'old terms\n',b'old long\n']):c.atomic(self.project/rel,data)

    def shared(self):return self.zip('shared.zip',{'User.csv':'Key,Value\nSize,尺寸\n','LongText.csv':'Key,Value\n"A long text.","长文本。"\n'})

    def test_backup_restore_roundtrip(self):
        self.initial();before={n:(self.project/n).read_bytes() for n in c.PROTECTED}
        backup=c.replace_shared(self.project,self.shared())
        self.assertIn('尺寸',(self.project/c.PROTECTED[0]).read_text(encoding='utf-8'))
        restore_backup=c.restore(self.project,backup)
        self.assertTrue(restore_backup.exists())
        self.assertEqual(before,{n:(self.project/n).read_bytes() for n in c.PROTECTED})

    def test_restore_original_absence(self):
        b=c.backup(self.project);c.replace_shared(self.project,self.shared());c.restore(self.project,b)
        self.assertTrue(all(not (self.project/n).exists() for n in c.PROTECTED))

    def test_two_file_failure_rolls_back(self):
        self.initial();original=c.atomic;calls=0
        def fail_second(path,data):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('disk error')
            return original(path,data)
        with patch.object(c,'atomic',side_effect=fail_second):
            with self.assertRaises(OSError):c.replace_shared(self.project,self.shared())
        self.assertEqual((self.project/c.PROTECTED[0]).read_bytes(),b'old terms\n')
        self.assertEqual((self.project/c.PROTECTED[1]).read_bytes(),b'old long\n')

    def test_corrupt_download_not_used(self):
        source=self.root/'source';source.write_bytes(b'bad');dest=self.root/'dest';dest.write_bytes(b'old')
        with self.assertRaises(ValueError):c.download(source,dest,'0'*64)
        self.assertEqual(dest.read_bytes(),b'old')

    def test_zip_traversal_rejected(self):
        with self.assertRaises(ValueError):c.safe_relative('XHNodeChinese/a\\b')
        for name in ('../escape','/absolute','XHNodeChinese/../outside','XHNodeChinese/C:foo','XHNodeChinese/CON'):
            with self.subTest(name=name):
                p=self.zip('evil.zip',{'XHNodeChinese/XHNodeChinese.uplugin':'{}',name:'bad'})
                with self.assertRaises(ValueError):c.unpack_plugin(p,self.root/'stage')
        self.assertFalse((self.root/'escape').exists())

    def test_symlink_archive_rejected(self):
        p=self.root/'link.zip'
        with zipfile.ZipFile(p,'w') as z:
            info=zipfile.ZipInfo('link');info.external_attr=(0o120777<<16);z.writestr(info,'outside')
        with zipfile.ZipFile(p) as z:
            with self.assertRaises(ValueError):c.zip_members(z)

    def test_case_insensitive_duplicates_rejected(self):
        p=self.zip('duplicate.zip',{'a':'1','A':'2'})
        with zipfile.ZipFile(p) as z:
            with self.assertRaises(ValueError):c.zip_members(z)

    def test_invalid_shared_does_not_touch_project(self):
        self.initial();p=self.zip('badshared.zip',{'User.csv':'Key,Value\nSize,\n','LongText.csv':'Key,Value\n'})
        with self.assertRaises(ValueError):c.replace_shared(self.project,p)
        self.assertEqual((self.project/c.PROTECTED[0]).read_bytes(),b'old terms\n')

    def test_multiline_csv(self):
        self.assertEqual(c.csv_validate('Key,Value\n"Line1\nLine2","第一行\n第二行"\n'.encode()),1)
        with self.assertRaises(ValueError):c.csv_validate(b'Key,Value\na,b\na,c\n')

    def test_engine_build_and_verification_required(self):
        info={'version':'5.8.3','sha256':{'a':'1'}}
        p={'engine':info,'verified':True}
        self.assertEqual(c.matching({'plugins':[p]},info),[p])
        self.assertFalse(c.matching({'plugins':[p]},{'version':'5.8.3','sha256':{'a':'2'}}))
        self.assertFalse(c.matching({'plugins':[dict(p,verified=False)]},info))

    def test_plugin_update_preserves_user_and_long_text(self):
        self.initial();dll=b'example'
        import hashlib
        info={'version':'5.8.3','sha256':{'engine':'value'}}
        m={'engine_sha256':info['sha256'],'bridge_file':'XHSlateBridge027.dll','bridge_sha256':hashlib.sha256(dll).hexdigest()}
        p=self.zip('plugin.zip',{'XHNodeChinese/XHNodeChinese.uplugin':'{}',
            'XHNodeChinese/Binaries/Win64/bridge-manifest.json':json.dumps(m),
            'XHNodeChinese/Binaries/Win64/XHSlateBridge027.dll':dll,'XHNodeChinese/Dictionaries/User.csv':'Key,Value\n'})
        c.install(self.project,p,info)
        self.assertEqual((self.project/c.PROTECTED[0]).read_bytes(),b'old terms\n')
        self.assertEqual((self.project/c.PROTECTED[1]).read_bytes(),b'old long\n')
        with self.assertRaises(ValueError):c.install(self.project,p,dict(info,sha256={'other':'value'}))
        self.assertEqual((self.project/c.PROTECTED[0]).read_bytes(),b'old terms\n')

    def test_offline_feed_and_hash(self):
        p=self.shared();item={'url':p.name,'sha256':c.digest(p)}
        f=self.root/'manifest.json';c.write_json(f,{'schema':1,'plugins':[],'shared':item})
        feed=c.load_feed(f,self.root/'cache')
        self.assertEqual(c.fetch(feed['shared'],self.root/'cache').read_bytes(),p.read_bytes())
        item['url']='../outside.zip';c.write_json(f,{'schema':1,'plugins':[],'shared':item})
        with self.assertRaises(ValueError):c.load_feed(f,self.root/'cache')

    def test_backup_hash_corruption(self):
        self.initial();b=c.backup(self.project)
        with zipfile.ZipFile(b) as z:files={n:z.read(n) for n in z.namelist()}
        files[c.PROTECTED[0]]=b'tampered'
        bad=self.zip('badbackup.zip',files)
        with self.assertRaises(ValueError):c.restore(self.project,bad)
        self.assertEqual((self.project/c.PROTECTED[0]).read_bytes(),b'old terms\n')

    def test_repository_url(self):
        self.assertEqual(c.feed_location(c.REPOSITORY),c.DEFAULT_FEED)
        self.assertNotEqual(c.SOURCE_REPOSITORY,c.REPOSITORY)
        self.assertIn('XHNodeChinese-new',c.DEFAULT_FEED)

    def test_public_plugin_removes_maintainer_source_preserves_runtime(self):
        import publish
        files={'XHNodeChinese/XHNodeChinese.uplugin':'{}',
            'XHNodeChinese/Source/SlateBridge/Bridge.cpp':'private C++',
            'XHNodeChinese/Tools/build_bridge.py':'private builder',
            'XHNodeChinese/Tools/CompilerHost/Module.cpp':'private host',
            'XHNodeChinese/Tools/ReloadInEditor.py':'reload runtime',
            'XHNodeChinese/Content/Python/init_unreal.py':'runtime code',
            'XHNodeChinese/Binaries/Win64/XHSlateBridge027.dll':b'dll bytes',
            'XHNodeChinese/ADVANCED.md':'# Doc\n## 引擎兼容与重新编译\nprivate build guide'}
        source=self.zip('source.zip',files);dest=self.root/'public.zip'
        publish.public_plugin(source,dest)
        with zipfile.ZipFile(dest) as z:
            self.assertFalse(any('/Source/' in n or '/CompilerHost/' in n or n.endswith('build_bridge.py') for n in z.namelist()))
            for n in ('XHNodeChinese/Content/Python/init_unreal.py','XHNodeChinese/Tools/ReloadInEditor.py','XHNodeChinese/Binaries/Win64/XHSlateBridge027.dll'):
                expected=files[n];self.assertEqual(z.read(n),expected.encode() if isinstance(expected,str) else expected)

    @unittest.skipUnless(c.os.name=='nt','Windows file locking')
    def test_concurrent_updater_rejected(self):
        import msvcrt
        lock=self.project/'Saved/XHNodeChinese/UpdaterBackups/operation.lock'
        lock.parent.mkdir(parents=True);lock.write_bytes(b'0')
        with lock.open('r+b') as handle:
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            try:
                with self.assertRaises(RuntimeError):c.replace_shared(self.project,self.shared())
            finally:
                handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)

    def test_publisher_shared_refresh_keeps_engine_packages(self):
        import publish
        folder=self.root/'shared';folder.mkdir()
        (folder/'User.csv').write_text('Key,Value\nSize,尺寸\n',encoding='utf-8')
        (folder/'LongText.csv').write_text('Key,Value\n',encoding='utf-8')
        manifest=self.root/'manifest.json';c.write_json(manifest,{'schema':1,'plugins':[{'label':'keep'}]})
        publish.update_shared(manifest,folder,'2026.10.11')
        after=c.json_read(manifest)
        self.assertEqual(after['plugins'],[{'label':'keep'}])
        self.assertEqual(after['shared']['terms'],1)


if __name__=='__main__':unittest.main(verbosity=2)
