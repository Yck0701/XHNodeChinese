from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import json
import tempfile
import sys
import unittest
import zipfile
import auto_setup as setup
import app
import manager_core as core
from test_build_preflight import Var


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.source=self.root/'XHNodeChinese-source-r2.zip'
        with zipfile.ZipFile(self.source,'w') as z:
            files={'XHNodeChinese.uplugin':json.dumps({'VersionName':'0.2.16'}),
                   'Tools/build-config.json':json.dumps({'compiler_selection':'ubt_response_file'}),
                   'Tools/build_bridge.py':'for relative in ("Source/Test.h",):\n    pass\n',
                   'Tools/msvc_toolchain.py':'', 'Source/SlateBridge/Bridge.cpp':'', 'Source/SlateBridge/ModuleIndex.cpp':''}
            for name,data in files.items():z.writestr('XHNodeChinese/'+name,data)

    def test_authorized_source_is_copied_once_and_original_unchanged(self):
        before=self.source.read_bytes()
        a=setup.remember_source(self.source,self.root/'state')
        b=setup.remember_source(self.source,self.root/'state')
        self.assertEqual(a,b);self.assertEqual(Path(a).read_bytes(),before)
        self.assertEqual(self.source.read_bytes(),before)
        self.assertEqual(setup.discover_source('',self.root/'empty',self.root/'state',self.root/'empty')['path'],a)

    def test_installation_zip_cannot_be_used_as_source(self):
        with zipfile.ZipFile(self.root/'install.zip','w') as z:z.writestr('XHNodeChinese/XHNodeChinese.uplugin','{}')
        with self.assertRaisesRegex(ValueError,'源码'):setup.source_info(self.root/'install.zip')

    def test_source_inspection_does_not_execute_code(self):
        with zipfile.ZipFile(self.source,'a') as z:z.writestr('unused.py','raise SystemExit("must not run")')
        self.assertEqual([Path(p) for p in setup.source_info(self.source)['headers']],[Path('Source/Test.h')])

    def test_ue_banned_and_minimum_compilers_rejected(self):
        policy={'MinimumVisualCppVersion':'14.38.33130','BannedVisualCppVersions':['14.40.0-14.43.99999']}
        self.assertFalse(setup.supported_toolset('14.29.30037',policy))
        self.assertFalse(setup.supported_toolset('14.42.34433',policy))
        self.assertTrue(setup.supported_toolset('14.44.35211',policy))

    def test_missing_source_does_not_hide_other_dependency_checks(self):
        with patch.object(core,'engine_path',return_value=self.root),patch.object(setup,'find_python',return_value=''),patch.object(setup,'find_vcvars',return_value=''),patch.object(setup,'find_windows_sdk',return_value=''),patch.object(setup.engine_discovery,'registered_engines',return_value=[]):
            result=setup.inspect(str(self.root),'','','','',str(self.root/'out'),self.root/'none',self.root/'state')
        self.assertEqual([i['kind'] for i in result['issues']],['source','vcvars','python'])

    def test_source_present_but_sdk_mismatch_has_one_clear_next_step(self):
        with patch.object(core,'engine_path',return_value=self.root),patch.object(setup,'sdk_problem',return_value='headers mismatch'),patch.object(setup,'find_python',return_value='python'),patch.object(setup,'find_vcvars',return_value='vcvars'),patch.object(setup,'find_windows_sdk',return_value='sdk'),patch.object(setup.engine_discovery,'registered_engines',return_value=[]):
            result=setup.inspect(str(self.root),str(self.source),'','','',str(self.root/'out'),self.root/'none',self.root/'state')
        self.assertEqual([i['kind'] for i in result['issues']],['sdk'])

    def test_ready_environment_uses_auto_compiler(self):
        with patch.object(core,'engine_path',return_value=self.root),patch.object(setup,'sdk_problem',return_value=''),patch.object(setup,'find_python',return_value='python'),patch.object(setup,'find_vcvars',return_value='vcvars'),patch.object(setup,'find_windows_sdk',return_value='sdk'),patch.object(setup.engine_discovery,'registered_engines',return_value=[]):
            result=setup.inspect(str(self.root),str(self.source),'','','',str(self.root/'out'),self.root/'none',self.root/'state')
        self.assertFalse(result['issues']);self.assertEqual(result['compiler_version'],'auto')

    def test_sdk_version_and_headers_must_match_target(self):
        target=self.root/'target';sdk=self.root/'sdk'
        for path in (target,sdk):core.write_json(path/'Build/Build.version',dict(MajorVersion=5,MinorVersion=8,PatchVersion=3))
        core.write_json(sdk/'Build/Build.version',dict(MajorVersion=5,MinorVersion=7,PatchVersion=3))
        self.assertIn('版本',setup.sdk_problem(target,sdk,[]))

    def test_invalid_installer_signature_never_executes_installer(self):
        response=SimpleNamespace(returncode=0,stdout=b'{"status":"NotSigned","subject":""}')
        with patch.object(core,'download'),patch.object(setup.subprocess,'run',return_value=response) as run:
            with self.assertRaisesRegex(ValueError,'签名'):setup.install_dependency('python',self.root,lambda _:None)
        self.assertEqual(run.call_count,1)

    def test_install_exit_reboot_is_returned_to_ui(self):
        responses=[SimpleNamespace(returncode=0,stdout=b'{"status":"Valid","subject":"CN=Python Software Foundation"}'),SimpleNamespace(returncode=3010)]
        with patch.object(core,'download'),patch.object(setup.subprocess,'run',side_effect=responses) as run:
            self.assertEqual(setup.install_dependency('python',self.root,lambda _:None),3010)
        args=run.call_args.args[0]
        self.assertIn('InstallAllUsers=0',args);self.assertIn('PrependPath=0',args)

    def test_cpp_installer_selects_workload_and_elevates_only_verified_installer(self):
        responses=[SimpleNamespace(returncode=0,stdout=b'{"status":"Valid","subject":"CN=Microsoft Corporation"}'),SimpleNamespace(returncode=0)]
        with patch.object(core,'download'),patch.object(setup.subprocess,'run',side_effect=responses) as run:
            self.assertEqual(setup.install_dependency('vcvars',self.root,lambda _:None),0)
        self.assertIn('-Verb RunAs',run.call_args.args[0][-1])
        args=run.call_args.kwargs['env']['XH_INSTALLER_ARGS']
        self.assertIn('Microsoft.VisualStudio.Workload.VCTools',args);self.assertIn('--includeRecommended',args)
        self.assertIn('--norestart',args)

    def test_cancelled_uac_returns_actionable_error_without_retry_loop(self):
        responses=[SimpleNamespace(returncode=0,stdout=b'{"status":"Valid","subject":"CN=Microsoft Corporation"}'),SimpleNamespace(returncode=1223)]
        with patch.object(core,'download'),patch.object(setup.subprocess,'run',side_effect=responses) as run:
            with self.assertRaisesRegex(ValueError,'取消'):setup.install_dependency('vcvars',self.root,lambda _:None)
        self.assertEqual(run.call_count,2)

    def test_source_auto_download_hash_check_and_offline_fallback(self):
        release=self.root/'base/release';release.mkdir(parents=True)
        import shutil
        archive=release/self.source.name;shutil.copy2(self.source,archive)
        feed=dict(schema=1,plugins=[],shared=dict(url=archive.name,sha256=core.digest(archive)),
                  source=dict(version='0.2.16',url=archive.name,sha256=core.digest(archive)))
        core.write_json(release/'manifest.json',feed)
        saved=setup.obtain_source(self.root/'unavailable.json',release.parent,self.root/'state',lambda _:None)
        self.assertEqual(Path(saved).read_bytes(),self.source.read_bytes())
        self.assertTrue(Path(saved).is_relative_to(self.root/'state/source-packages'))
        feed['source']['sha256']='0'*64;core.write_json(release/'manifest.json',feed)
        with self.assertRaisesRegex(ValueError,'校验'):setup.obtain_source(self.root/'missing',release.parent,self.root/'other',lambda _:None)

    def test_large_resource_output_keeps_full_file_without_flooding_ui(self):
        import build_process
        shown=[];logfile=self.root/'large.log'
        build_process.run([sys.executable,'-c','for i in range(400): print("line-"+str(i))'],self.root,shown.append,logfile,display_limit=12)
        self.assertIn('line-399',logfile.read_text(encoding='utf-8'))
        self.assertLess(len(shown),20);self.assertIn('本阶段完成',shown[-1])


class WizardTests(unittest.TestCase):
    def ui(self):
        ui=SimpleNamespace(busy=False,closing=False,project=Var('P'),engine=Var('UE'),feed_var=Var('feed'),out=Var('out'),
            source_package=Var('source'),sdk=Var(),vcvars=Var(),python=Var(),msvc=Var(),build_engine=Var(),
            wizard_state='idle',wizard_context=None,wizard_result=None,wizard_text=Var(),setup_text=Var(),setup_button_text=Var(),
            auto_flow=False,dependency_attempts=set(),after=Mock(),compile_auto=Mock(),setup_next=Mock(),
            log=Mock(),navigate=Mock(),install=Mock(),prepare_environment=Mock(),save_settings=Mock(),cancel_build_button=Mock())
        ui.start=lambda fn,done:done(fn())
        ui.setup_context=lambda:app.App.setup_context(ui)
        return ui

    def test_installed_plugin_skips_compile_environment(self):
        ui=self.ui()
        result=dict(local=[dict(kind='installed',version='0.2.16')],cloud=None)
        with patch.object(core,'project_path'),patch.object(core,'engine_path'),patch.object(setup,'discover_source',return_value=None),patch.object(app.build_preflight,'probe',return_value=result):app.App.auto_adapt(ui)
        ui.prepare_environment.assert_not_called();ui.install.assert_not_called()
        self.assertIn('直接打开',ui.wizard_text.get())

    def test_cloud_package_goes_straight_to_install_not_folder(self):
        ui=self.ui();result=dict(local=[],cloud=dict(version='0.2.16'))
        with patch.object(core,'project_path'),patch.object(core,'engine_path'),patch.object(setup,'discover_source',return_value=None),patch.object(app.build_preflight,'probe',return_value=result):app.App.auto_adapt(ui)
        ui.install.assert_called_once();ui.prepare_environment.assert_not_called()

    def test_offline_is_not_reported_as_cloud_missing(self):
        ui=self.ui();result=dict(local=[],cloud=None,cloud_error='offline')
        with patch.object(core,'project_path'),patch.object(core,'engine_path'),patch.object(setup,'discover_source',return_value=None),patch.object(app.build_preflight,'probe',return_value=result):app.App.auto_adapt(ui)
        self.assertTrue(ui.wizard_offline);ui.prepare_environment.assert_called_once()

    def test_changed_engine_during_probe_cannot_install(self):
        ui=self.ui()
        def probe(*a):ui.engine.set('Other');return dict(local=[],cloud=dict(version='0.2.16'))
        with patch.object(core,'project_path'),patch.object(core,'engine_path'),patch.object(setup,'discover_source',return_value=None),patch.object(app.build_preflight,'probe',side_effect=probe):app.App.auto_adapt(ui)
        ui.install.assert_not_called();ui.prepare_environment.assert_not_called()

    def test_ready_result_fills_fields_without_starting_compile(self):
        ui=self.ui()
        result=dict(engine='UE',source='source',sdk='sdk',vcvars='vc',python='py',issues=[],diagnostics=[],compiler_version='auto')
        with patch.object(setup,'inspect',return_value=result):app.App.prepare_environment(ui)
        self.assertEqual(ui.wizard_state,'ready');self.assertEqual(ui.sdk.get(),'sdk');self.assertEqual(ui.msvc.get(),'auto')
        ui.install.assert_not_called()

    def test_compilation_finishes_at_install_button_without_upload(self):
        ui=self.ui();ui.wizard_context=ui.setup_context()
        ui.wizard_result=dict(engine='UE',source='src',sdk='sdk',vcvars='vc',python='py',output='out',compiler_version='auto')
        with patch.object(core,'compile_package',return_value=Path('compiled.zip')) as compile:app.App.compile_auto(ui)
        compile.assert_called_once();self.assertEqual(ui.wizard_state,'install');ui.install.assert_not_called()
        self.assertIn('尚未',ui.wizard_text.get())

    def test_selection_check_works_even_when_startup_update_check_disabled(self):
        ui=self.ui();ui.checking=False;ui.auto_check=Var(False);ui.check=Mock()
        with patch.object(core,'project_path'),patch.object(core,'engine_path'):app.App.selection_check(ui)
        ui.check.assert_called_once_with(True,automatic=True,notify=False,compatibility=True)

    def test_manual_engine_change_clears_old_selection_and_schedules_check(self):
        ui=self.ui();ui.setting_engine=False;ui.auto_engine=Var(True);ui.engine_status=Var();ui.schedule_compatibility=Mock()
        app.App.engine_changed(ui)
        ui.schedule_compatibility.assert_called_once();self.assertFalse(ui.auto_engine.get())

    def test_source_is_fetched_without_requesting_local_zip(self):
        ui=self.ui();ui.wizard_state='needs';ui.wizard_context=ui.setup_context()
        ui.wizard_result={'issues':[{'kind':'source'}]}
        with patch.object(app.filedialog,'askopenfilename') as ask,patch.object(setup,'obtain_source',return_value='cached.zip') as fetch:app.App.setup_next(ui)
        ask.assert_not_called();fetch.assert_called_once();self.assertEqual(ui.source_package.get(),'cached.zip')
        ui.prepare_environment.assert_called_once()

    def test_auto_ready_queues_compile_and_changed_selection_blocks_it(self):
        ui=self.ui();ui.auto_flow=True
        result=dict(engine='UE',source='source',sdk='sdk',vcvars='vc',python='py',windows_sdk='win',issues=[],diagnostics=[],compiler_version='auto')
        with patch.object(setup,'inspect',return_value=result):app.App.prepare_environment(ui)
        self.assertEqual(ui.after.call_count,1)
        context=ui.setup_context();ui.engine.set('Other')
        app.App.run_setup_step(ui,context,ui.compile_auto);ui.compile_auto.assert_not_called()

    def test_cpp_direct_button_works_without_source_or_project(self):
        ui=self.ui();ui.engine.set('');ui.project.set('');ui.source_package.set('')
        with patch.object(setup,'install_dependency',return_value=0) as install:app.App.install_environment(ui)
        install.assert_called_once();ui.prepare_environment.assert_not_called()
        self.assertIn('安装完成',ui.wizard_text.get())

    def test_reboot_stops_flow_instead_of_compiling(self):
        ui=self.ui();ui.auto_flow=True
        with patch.object(setup,'install_dependency',return_value=3010):app.App.install_environment(ui)
        self.assertFalse(ui.auto_flow);ui.prepare_environment.assert_not_called();self.assertIn('重启',ui.wizard_text.get())

    def test_installed_dependency_not_discovered_does_not_loop(self):
        ui=self.ui();ui.auto_flow=True;ui.dependency_attempts={'vcvars'}
        result=dict(engine='UE',source='source',sdk='sdk',vcvars='',python='py',windows_sdk='',issues=[dict(kind='vcvars',title='安装 C++',detail='需要工具链')],diagnostics=[])
        with patch.object(setup,'inspect',return_value=result):app.App.prepare_environment(ui)
        self.assertFalse(ui.auto_flow);ui.after.assert_not_called();self.assertIn('仍未',ui.wizard_text.get())


if __name__=='__main__':unittest.main()
