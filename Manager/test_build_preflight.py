import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import zipfile
import app
import build_preflight as bp
import build_process
import manager_core as c


class Var:
    def __init__(self,value=''):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.output=self.root/'out';self.cache=self.root/'cache';self.bundled=self.root/'release'
        for p in (self.output,self.cache,self.bundled):p.mkdir()
        self.engine={'version':'5.8.3','sha256':{'target.dll':'a'*64}}

    def tearDown(self):self.temp.cleanup()

    def package(self,folder,engine=None,version='0.2.14',report=False):
        path=folder/'plugin.zip';data=b'dll fixture';engine=engine or self.engine
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('XHNodeChinese/XHNodeChinese.uplugin',json.dumps(dict(VersionName=version,XHModuleIndexVersion=1)))
            for manifest,dll in (('bridge-manifest.json','XHSlateBridge0214.dll'),('module-index-manifest.json','XHModuleIndex0214.dll')):
                z.writestr('XHNodeChinese/Binaries/Win64/'+dll,data)
                z.writestr('XHNodeChinese/Binaries/Win64/'+manifest,json.dumps(dict(engine_sha256=engine['sha256'],bridge_file=dll,bridge_sha256=bp.hashlib.sha256(data).hexdigest())))
        item=dict(engine=engine,version=version,sha256=c.digest(path),url=path.name,verified=True)
        if report:c.write_json(path.with_suffix('.json'),dict(sha256=item['sha256'],engine=engine,verified=False))
        return path,item

    def scan(self):return bp.local_candidates(self.engine,'0.2.14',self.output,self.cache,self.bundled)

    def test_bundled_verified_package_reused_without_network(self):
        path,item=self.package(self.bundled);c.write_json(self.bundled/'manifest.json',dict(schema=1,plugins=[item]))
        with patch.object(c,'engine_info',return_value=self.engine),patch.object(c,'load_feed') as network:
            result=bp.probe('engine','',self.output,self.cache,self.bundled)
        self.assertTrue(result['local'][0]['verified']);network.assert_not_called()
        copied=bp.reuse(result['local'][0],self.output);self.assertEqual(c.digest(copied),item['sha256'])

    def test_same_version_different_engine_rejected(self):
        engine=copy.deepcopy(self.engine);engine['sha256']['target.dll']='b'*64
        path,item=self.package(self.bundled,engine);c.write_json(self.bundled/'manifest.json',dict(schema=1,plugins=[item]))
        self.assertEqual(self.scan(),[])

    def test_old_plugin_not_reused(self):
        path,item=self.package(self.bundled,version='0.2.13');c.write_json(self.bundled/'manifest.json',dict(schema=1,plugins=[item]))
        self.assertEqual(self.scan(),[])

    def test_local_test_package_remains_unverified(self):
        path,item=self.package(self.output,report=True);items=self.scan()
        self.assertEqual(len(items),1);self.assertFalse(items[0]['verified'])
        self.assertEqual(bp.reuse(items[0],self.output),path)

    def test_bad_report_hash_rejected(self):
        path,item=self.package(self.output,report=True);c.write_json(path.with_suffix('.json'),dict(sha256='f'*64,engine=self.engine))
        self.assertEqual(self.scan(),[])

    def test_package_cannot_be_trusted_by_filename_alone(self):
        path,item=self.package(self.cache);path.rename(self.cache/(item['sha256']+'.zip'))
        self.assertEqual(self.scan(),[])

    def test_corrupt_component_rejected(self):
        path,item=self.package(self.output,report=True)
        with zipfile.ZipFile(path) as z:files={n:z.read(n) for n in z.namelist()}
        files['XHNodeChinese/Binaries/Win64/XHModuleIndex0214.dll']=b'corrupt'
        with zipfile.ZipFile(path,'w') as z:
            for n,d in files.items():z.writestr(n,d)
        c.write_json(path.with_suffix('.json'),dict(sha256=c.digest(path),engine=self.engine))
        self.assertEqual(self.scan(),[])

    def test_tampering_after_check_is_detected(self):
        path,item=self.package(self.output,report=True);candidate=self.scan()[0];path.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):bp.reuse(candidate,self.output)

    def test_cloud_failure_not_misreported_as_missing(self):
        with patch.object(c,'engine_info',return_value=self.engine),patch.object(c,'load_feed',side_effect=OSError('offline')):
            result=bp.probe('engine','',self.output,self.cache,self.bundled)
        self.assertEqual(result['local'],[]);self.assertEqual(result['cloud_error'],'offline')

    def ui(self):
        ui=SimpleNamespace(build_engine=Var('official'),engine=Var('custom'),sdk=Var('sdk'),vcvars=Var('vc'),python=Var('python'),
            msvc=Var('14.50'),out=Var(str(self.output)),source_package=Var(''),project=Var('project'),feed_var=Var('feed'),
            cloud_status=Var(),log=Mock(),open_path=Mock(),compile_local=Mock())
        ui.build_args=lambda:app.App.build_args(ui);ui.start=lambda fn,done:done(fn())
        return ui

    def test_compile_target_separate_from_install_target(self):
        self.assertEqual(self.ui().build_args()['engine'],'official')

    def test_pending_contribution_can_prevent_duplicate_compile(self):
        path,item=self.package(self.output,report=True);ui=self.ui();ui.source_package.set(str(path))
        result=dict(engine=self.engine,local=[],cloud=None,cloud_error='',contribution={'state':'pending_review'})
        with patch.object(bp,'probe',return_value=result),patch.object(app.messagebox,'askyesno',return_value=False):
            app.App.check_versions(ui,then_compile=True)
        ui.compile_local.assert_not_called()

    def test_preflight_preserves_pending_contribution_state(self):
        path,item=self.package(self.root)
        with patch.object(c,'engine_info',return_value=self.engine),patch.object(c,'load_feed',return_value={'plugins':[]}),\
             patch.object(bp.community,'check',return_value={'state':'pending_review'}) as community_check:
            result=bp.probe('engine',str(path),self.output,self.cache,self.bundled)
        self.assertEqual(result['contribution']['state'],'pending_review');community_check.assert_called_once()

    def test_declining_existing_local_never_starts_compile(self):
        path,item=self.package(self.output,report=True);ui=self.ui()
        result=dict(engine=self.engine,local=self.scan(),cloud=None,cloud_error='')
        with patch.object(bp,'probe',return_value=result),patch.object(app.messagebox,'askyesno',return_value=False):
            app.App.check_versions(ui,then_compile=True)
        ui.compile_local.assert_not_called();ui.open_path.assert_not_called()

    def test_accepting_cloud_download_never_starts_compile(self):
        path,item=self.package(self.bundled);ui=self.ui()
        result=dict(engine=self.engine,local=[],cloud=item,cloud_error='')
        with patch.object(bp,'probe',return_value=result),patch.object(app.messagebox,'askyesno',return_value=True),patch.object(c,'fetch',return_value=path):
            app.App.check_versions(ui,then_compile=True)
        ui.compile_local.assert_not_called();self.assertTrue((self.output/path.name).exists())


class BuildProcessTests(unittest.TestCase):
    def test_cancel_preserves_log_and_stops_spawned_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            cancel=threading.Event();timer=threading.Timer(.5,cancel.set);timer.start()
            path=Path(tmp)/'build.log';start=time.monotonic()
            try:
                with self.assertRaisesRegex(RuntimeError,'取消'):
                    build_process.run([sys.executable,'-c',"import time;print('started',flush=True);time.sleep(30)"],tmp,lambda _:None,path,cancel,timeout=10)
            finally:timer.cancel()
            self.assertLess(time.monotonic()-start,8);self.assertIn('started',path.read_text(encoding='utf-8'))

    def test_idle_timeout_even_when_heartbeat_is_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'build.log';logs=[]
            with self.assertRaisesRegex(RuntimeError,'没有日志输出'):
                build_process.run([sys.executable,'-c','import time; time.sleep(30)'],tmp,logs.append,path,timeout=10,idle_timeout=.5,heartbeat=.1)
            self.assertTrue(any('进行中' in s for s in logs));self.assertTrue(path.exists())

    def test_nonzero_exit_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError,'退出码 7'):
                build_process.run([sys.executable,'-c','raise SystemExit(7)'],tmp,lambda _:None,Path(tmp)/'build.log')


if __name__=='__main__':unittest.main()
