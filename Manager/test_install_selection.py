"""Exercise the actual install-button route, including local-only installations."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import zipfile
import app
import manager_core as c
import build_preflight as bp
from test_build_preflight import Var


class InstallSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.project=self.root/'Project';c.write_json(self.project/'P.uproject',{})
        self.output=self.root/'output';self.output.mkdir()
        self.info=dict(version='5.8.3',changelist=0,sha256={'Engine.dll':'engine fingerprint'})
        self.engine=self.root/'UE/Engine'
        c.write_json(self.engine/'Build/Build.version',dict(MajorVersion=5,MinorVersion=8,PatchVersion=3))
        self.feed=dict(plugins=[],shared={'version':'1'})
        self.patches=[patch.object(app,'STATE',self.root/'state'),patch.object(app,'BASE',self.root/'app'),
            patch.object(c,'engine_info',return_value=self.info),patch.object(c,'ensure_closed'),
            patch.object(app.editor_process,'list_editors',return_value=[]),
            patch.object(c,'load_feed',return_value=self.feed),patch.object(app.messagebox,'showinfo'),
            patch.object(app.messagebox,'askyesno',return_value=True)]
        self.mocks=[p.start() for p in self.patches]
        self.ui=SimpleNamespace(busy=False,engine=Var(str(self.engine)),project=Var(str(self.project/'P.uproject')),
            feed_var=Var('feed'),out=Var(str(self.output)),feed=self.feed,feed_origin='feed',selected=None,
            status=Var(),package_label=Var(),wizard_text=Var(),setup_button_text=Var(),log=Mock(),check=Mock())
        self.ui.start=lambda fn,done:done(fn())
        self.ui.resolve_install_package=lambda callback,download_only=False:app.App.resolve_install_package(self.ui,callback,download_only)
        self.ui.start_file_update=lambda *args:app.App.start_file_update(self.ui,*args)

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def package(self,version='0.2.16'):
        file=self.output/('plugin-'+version+'.zip');data=b'dll fixture'
        with zipfile.ZipFile(file,'w') as z:
            z.writestr('XHNodeChinese/XHNodeChinese.uplugin',json.dumps(dict(VersionName=version,XHModuleIndexVersion=1)))
            for manifest,dll in [('bridge-manifest.json','XHSlateBridge0216.dll'),('module-index-manifest.json','XHModuleIndex0216.dll')]:
                z.writestr('XHNodeChinese/Binaries/Win64/'+dll,data)
                z.writestr('XHNodeChinese/Binaries/Win64/'+manifest,json.dumps(dict(engine_sha256=self.info['sha256'],bridge_file=dll,bridge_sha256=hashlib.sha256(data).hexdigest())))
        c.write_json(file.with_suffix('.json'),dict(sha256=c.digest(file),engine=self.info))
        return file

    def installed(self,version='0.2.16'):
        file=self.package(version)
        plugin=self.project/'Plugins/XHNodeChinese';c.unpack_plugin(file,plugin)
        file.with_suffix('.json').unlink();file.unlink()
        return plugin

    def test_current_installed_without_cloud_selection_is_noop(self):
        self.installed();self.ui.feed=None
        with patch.object(c,'install') as install,patch.object(app.editor_process,'close_and_wait') as close:
            app.App.install(self.ui)
        install.assert_not_called();close.assert_not_called();self.mocks[-1].assert_not_called()
        self.assertEqual(self.mocks[-2].call_args.args[0],'当前插件已适配')
        self.assertIn('无需重复',self.ui.status.get())
        self.assertFalse((self.project/'Saved').exists())

    def test_local_archive_installs_through_button_and_preserves_project_files(self):
        file=self.package()
        protected={'P.uproject':b'{}','Content/FX.uasset':b'asset','Config/DefaultEngine.ini':b'config',
                   c.PROTECTED[0]:b'"Size","custom"\n',c.PROTECTED[1]:b'"long","personal"\n'}
        for name,data in protected.items():c.atomic(self.project/name,data)
        app.App.install(self.ui)
        self.assertEqual(c.json_read(self.project/'Plugins/XHNodeChinese/XHNodeChinese.uplugin')['VersionName'],'0.2.16')
        self.assertEqual(protected,{name:(self.project/name).read_bytes() for name in protected})
        self.assertTrue(list((self.project/'Saved/XHNodeChinese/UpdaterBackups').glob('dictionary-*.zip')))
        self.ui.check.assert_called_once_with(True,notify=False,compatibility=True)

    def test_newer_cloud_version_updates_existing_matching_plugin(self):
        self.installed('0.2.15');file=self.package('0.2.16')
        self.feed['plugins']=[dict(version='0.2.16',verified=True,engine=self.info,url=file.name,_location=str(file),sha256=c.digest(file))]
        app.App.install(self.ui)
        self.assertEqual(c.json_read(self.project/'Plugins/XHNodeChinese/XHNodeChinese.uplugin')['VersionName'],'0.2.16')

    def test_older_cloud_does_not_downgrade_installed_plugin(self):
        self.installed();file=self.package('0.2.15')
        self.feed['plugins']=[dict(version='0.2.15',verified=True,engine=self.info,url=file.name,_location=str(file),sha256=c.digest(file))]
        with patch.object(c,'install') as install:app.App.install(self.ui)
        install.assert_not_called();self.assertEqual(self.mocks[-2].call_args.args[0],'当前插件已适配')

    def test_changed_project_during_detection_cancels_install(self):
        self.package()
        def changed(*args):self.ui.project.set('other.uproject');return self.info
        self.mocks[2].side_effect=changed
        with patch.object(c,'install') as install:app.App.install(self.ui)
        install.assert_not_called();self.mocks[-1].assert_not_called();self.assertIn('选择已改变',self.ui.status.get())

    def test_changed_engine_after_confirmation_never_installs(self):
        self.package();changed=copy.deepcopy(self.info);changed['sha256']['Engine.dll']='updated'
        self.mocks[2].side_effect=[self.info,changed]
        with patch.object(c,'install') as install,self.assertRaisesRegex(ValueError,'引擎在检查后发生变化'):
            app.App.install(self.ui)
        install.assert_not_called()

    def test_tampered_local_archive_after_confirmation_rejected(self):
        file=self.package()
        def confirm(*args,**kwargs):file.write_bytes(b'corrupt');return True
        self.mocks[-1].side_effect=confirm
        with patch.object(c,'install') as install,self.assertRaisesRegex(ValueError,'下载校验失败'):
            app.App.install(self.ui)
        install.assert_not_called()

    def test_declining_local_install_does_not_write_or_close_ue(self):
        self.package();self.mocks[-1].return_value=False
        with patch.object(c,'install') as install,patch.object(app.editor_process,'list_editors') as editors:
            app.App.install(self.ui)
        install.assert_not_called();editors.assert_not_called()

    def test_cloud_failure_without_local_shows_unconfirmed_package_not_missing_engine(self):
        self.ui.feed=None;self.mocks[5].side_effect=OSError('offline')
        app.App.install(self.ui)
        self.assertEqual(self.mocks[-2].call_args.args[0],'未找到适配包')
        self.assertIn('已识别 UE 5.8.3',self.mocks[-2].call_args.args[1])
        self.assertIn('云端检查未完成',self.mocks[-2].call_args.args[1])

    def test_download_installed_only_reports_no_archive(self):
        self.installed()
        with patch.object(app.filedialog,'asksaveasfilename') as save:app.App.download_plugin(self.ui)
        save.assert_not_called();self.assertEqual(self.mocks[-2].call_args.args[0],'插件已经适配')

    def test_download_local_archive_reuses_validated_file(self):
        file=self.package();dest=self.root/'saved.zip'
        with patch.object(app.filedialog,'asksaveasfilename',return_value=str(dest)):
            app.App.download_plugin(self.ui)
        self.assertEqual(c.digest(file),c.digest(dest))

    def test_download_installed_only_checks_cloud_when_not_checked_before(self):
        self.installed();self.ui.feed=None;file=self.package();file.with_suffix('.json').unlink()
        self.feed['plugins']=[dict(version='0.2.16',verified=True,engine=self.info,url=file.name,_location=str(file),sha256=c.digest(file))]
        with patch.object(app.filedialog,'asksaveasfilename',return_value=''):app.App.download_plugin(self.ui)
        self.mocks[5].assert_called_once()

    def test_cloud_older_than_unpublished_local_package_does_not_win(self):
        local=[dict(kind='package',version='0.2.16',verified=False)]
        origin,item=bp.install_choice(local,dict(version='0.2.15'))
        self.assertEqual(origin,'local');self.assertEqual(item['version'],'0.2.16')

    def test_same_version_archive_does_not_trigger_reinstall(self):
        local=[dict(kind='installed',version='0.2.16'),dict(kind='package',version='0.2.16',verified=True)]
        self.assertEqual(bp.install_choice(local)[0],'installed')
        self.assertEqual(bp.install_choice(local,download_only=True)[0],'local')


if __name__=='__main__':unittest.main()
