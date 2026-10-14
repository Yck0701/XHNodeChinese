"""Project resolution and startup prompts; never launches UE or a compiler."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
import app
import engine_discovery as ed
import manager_core as c
from test_build_preflight import Var


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.project=self.root/'Project/P.uproject'
        self.set_association('')

    def tearDown(self):self.temp.cleanup()

    def set_association(self,value):c.write_json(self.project,dict(FileVersion=3,EngineAssociation=value))

    def engine(self,where):
        root=self.root/where/'Engine'
        c.write_json(root/'Build/Build.version',dict(MajorVersion=5,MinorVersion=8,PatchVersion=3))
        c.atomic(root/'Binaries/Win64/UnrealEditor.exe',b'fixture')
        return root

    def test_registered_guid_case_and_braces(self):
        target=self.engine('UE');self.set_association('{ABCD}')
        result=ed.discover(self.project,[('abcd',str(target.parent),'custom')])
        self.assertEqual(result['selected']['path'],str(target))

    def test_official_version_association(self):
        target=self.engine('Official');self.set_association('5.8')
        self.assertEqual(ed.discover(self.project,[('5.8',str(target),'launcher')])['selected']['path'],str(target))

    def test_stale_guid_uses_project_bundled_engine_without_editing_project(self):
        self.set_association('{old-guid}');target=self.engine('Project/UE')
        before=self.project.read_bytes()
        result=ed.discover(self.project,[])
        self.assertEqual(result['selected']['path'],str(target))
        self.assertEqual(before,self.project.read_bytes())

    def test_relative_path_association(self):
        target=self.engine('Portable');self.set_association('../Portable')
        self.assertEqual(ed.discover(self.project,[])['selected']['path'],str(target))

    def test_unrelated_single_install_is_not_silently_selected(self):
        target=self.engine('Other');self.set_association('unknown')
        result=ed.discover(self.project,[('5.7',str(target),'launcher')])
        self.assertIsNone(result['selected']);self.assertEqual(len(result['candidates']),1)

    def test_multiple_matches_require_choice(self):
        target=self.engine('Registered');self.engine('Project/UE');self.set_association('id')
        result=ed.discover(self.project,[('id',str(target),'registry')])
        self.assertIsNone(result['selected']);self.assertEqual(len(result['candidates']),2)

    def test_duplicate_registry_and_launcher_entry_are_one_candidate(self):
        target=self.engine('UE');self.set_association('5.8')
        result=ed.discover(self.project,[('5.8',str(target),'registry'),('5.8',str(target.parent),'launcher')])
        self.assertIsNotNone(result['selected']);self.assertEqual(len(result['candidates']),1)

    def test_source_tree_project_with_empty_association(self):
        target=self.engine('Source');self.project=self.root/'Source/Games/Game/Game.uproject';self.set_association('')
        self.assertEqual(ed.discover(self.project,[])['selected']['path'],str(target))

    def test_missing_executable_rejects_sdk_only_folder(self):
        target=self.engine('Project/UE');(target/'Binaries/Win64/UnrealEditor.exe').unlink()
        self.assertEqual(ed.discover(self.project,[])['candidates'],[])

    def test_multiple_projects_require_specific_file(self):
        c.write_json(self.project.with_name('Other.uproject'),{})
        with self.assertRaisesRegex(ValueError,'多个工程'):ed.discover(self.project.parent,[])


class StartupTests(unittest.TestCase):
    def ui(self):
        ui=SimpleNamespace(busy=False,closing=False,auto_check=Var(True),auto_engine=Var(True),
            project=Var('P.uproject'),engine=Var('UE'),feed_var=Var('feed'),source_package=Var('source.zip'),
            info=dict(version='5.8.3',sha256={'file':'hash'}),selected=None,out=Var('output'),
            cloud_status=Var(),package_label=Var(),status=Var(),compatibility_prompts=set(),start=Mock(),
            open_path=Mock(),build_engine=Var('other'),navigate=Mock(),check_versions=Mock(),auto_adapt=Mock(),
            engine_status=Var(),log=Mock(),setting_engine=False,check=Mock(),save_settings=Mock(),
            last_project_engine='',discovery_timer=None,select_engine_candidate=Mock(return_value=None))
        ui.set_discovered_engine=lambda item:app.App.set_discovered_engine(ui,item)
        return ui

    def test_installed_match_never_prompts_or_compiles(self):
        ui=self.ui()
        with patch.object(app.messagebox,'askyesno') as ask:
            app.App.offer_engine_compatibility(ui,[dict(kind='installed',version='0.2.16')],False,True)
        ask.assert_not_called();ui.start.assert_not_called();ui.check_versions.assert_not_called()
        self.assertIn('无需',ui.cloud_status.get())

    def test_offline_unknown_is_not_reported_as_needing_compile(self):
        ui=self.ui()
        with patch.object(app.messagebox,'askyesno') as ask:app.App.offer_engine_compatibility(ui,[],True,True)
        ask.assert_not_called();ui.check_versions.assert_not_called();self.assertIn('尚未确认',ui.cloud_status.get())

    def test_missing_declined_once_per_engine(self):
        ui=self.ui()
        with patch.object(app.messagebox,'askyesno',return_value=False) as ask:
            app.App.offer_engine_compatibility(ui,[],False,True)
            app.App.offer_engine_compatibility(ui,[],False,True)
        self.assertEqual(ask.call_count,1);ui.check_versions.assert_not_called()

    def test_missing_approved_checks_current_engine_before_compile(self):
        ui=self.ui()
        with patch.object(app.messagebox,'askyesno',return_value=True):app.App.offer_engine_compatibility(ui,[],False,True)
        self.assertEqual(ui.build_engine.get(),'UE');ui.auto_adapt.assert_called_once();ui.check_versions.assert_not_called()

    def test_cloud_offer_can_be_declined_without_compile(self):
        ui=self.ui();ui.selected={'version':'0.2.16'}
        with patch.object(app.messagebox,'askyesno',return_value=False):app.App.offer_engine_compatibility(ui,[],False,True)
        ui.start.assert_not_called();ui.check_versions.assert_not_called()

    def test_disabled_auto_check_suppresses_pending_question(self):
        ui=self.ui();ui.auto_check.set(False)
        with patch.object(app.messagebox,'askyesno') as ask:app.App.offer_engine_compatibility(ui,[],False,True)
        ask.assert_not_called()

    def test_failed_discovery_clears_previous_engine(self):
        ui=self.ui()
        with patch.object(ed,'discover',side_effect=ValueError('invalid project')):
            self.assertFalse(app.App.detect_project_engine(ui,run_check=False))
        self.assertEqual(ui.engine.get(),'');ui.check.assert_not_called()

    def test_cancelling_ambiguous_choice_leaves_no_stale_engine(self):
        ui=self.ui()
        with patch.object(ed,'discover',return_value={'selected':None,'candidates':[{}]}):
            self.assertFalse(app.App.detect_project_engine(ui,run_check=False))
        self.assertEqual(ui.engine.get(),'');ui.check.assert_not_called()

    def test_detected_install_target_preserves_separate_build_target(self):
        ui=self.ui();item=dict(path='new-engine',version='5.8.3',reasons=['工程附带引擎'])
        with patch.object(ed,'discover',return_value={'selected':item}),patch.object(c,'engine_path',side_effect=lambda p:p):
            self.assertTrue(app.App.detect_project_engine(ui,run_check=False))
        self.assertEqual(ui.engine.get(),'new-engine');self.assertEqual(ui.build_engine.get(),'other')

    def test_build_target_follows_previous_engine_when_linked(self):
        ui=self.ui();ui.build_engine.set('UE')
        item=dict(path='new-engine',version='5.8.3',reasons=['工程附带引擎'])
        with patch.object(ed,'discover',return_value={'selected':item}),patch.object(c,'engine_path',side_effect=lambda p:p):
            app.App.detect_project_engine(ui,run_check=False)
        self.assertEqual(ui.build_engine.get(),'new-engine')

    def test_manual_engine_edit_disables_automatic_overwrite(self):
        ui=self.ui();app.App.engine_changed(ui)
        self.assertFalse(ui.auto_engine.get())

    def check_ui(self):
        ui=self.ui();ui.checking=False;ui.shared_label=Var();ui.manager_button=Mock()
        ui.card_vars={key:Var() for key in ('manager','plugin','shared')}
        ui.start=lambda fn,done:done(fn());ui.offer_updates=Mock();ui.offer_engine_compatibility=Mock()
        return ui

    def test_cloud_failure_still_displays_valid_installed_adapter(self):
        ui=self.check_ui();info=ui.info
        with (patch.object(c,'cached_engine_info',return_value=info),
              patch.object(app.build_preflight,'local_candidates',return_value=[dict(kind='installed',version='0.2.16')]),
              patch.object(c,'load_feed',side_effect=OSError('offline'))):
            app.App.check(ui,compatibility=True)
        self.assertEqual(ui.card_vars['plugin'].get(),'已适配 v0.2.16')
        self.assertIn('无需重新编译',ui.package_label.get());ui.offer_updates.assert_not_called()

    def test_project_change_during_probe_discards_stale_result(self):
        ui=self.check_ui();info=ui.info
        def changed(*a,**kw):ui.project.set('other');return dict(plugins=[],shared={'version':'1'})
        with (patch.object(c,'cached_engine_info',return_value=info),
              patch.object(app.build_preflight,'local_candidates',return_value=[]),
              patch.object(c,'load_feed',side_effect=changed)):
            app.App.check(ui,compatibility=True)
        ui.offer_engine_compatibility.assert_not_called();self.assertIn('选择已改变',ui.status.get())

    def test_fresh_missing_cloud_is_distinguished_from_cached_cloud(self):
        for cached in (False,True):
            ui=self.check_ui();info=ui.info
            feed=dict(plugins=[],shared={'version':'1'},_cached=cached,_check_error='offline')
            with (patch.object(c,'cached_engine_info',return_value=info),
                  patch.object(app.build_preflight,'local_candidates',return_value=[]),
                  patch.object(c,'load_feed',return_value=feed)):
                app.App.check(ui,compatibility=True)
            ui.offer_engine_compatibility.assert_called_once_with([],cached,False)


if __name__=='__main__':unittest.main()
