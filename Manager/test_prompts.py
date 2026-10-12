"""Consent, cancellation and update selection without touching a running editor."""
import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import app
import manager_core as c
import editor_process as ep


class Var:
    def __init__(self,value=''):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value


EDITOR={'pid':999999,'name':'UnrealEditor','title':'Example - Unreal Editor','started':'12345','window':True}


class PromptTests(unittest.TestCase):
    def ui(self):
        ui=SimpleNamespace(busy=False,closing=False,project=Var('Project'),engine=Var('Engine'),feed_var=Var('feed'),
                           feed_origin='feed',status=Var(),log=Mock(),open_manager=Mock(),update_prompts=set())
        ui.start=lambda fn,done:done(fn())
        return ui

    def test_declining_editor_close_keeps_download_but_never_closes_or_applies(self):
        ui=self.ui();prepare=Mock(return_value='downloaded');apply=Mock();done=Mock()
        with (patch.object(c,'project_path'),patch.object(ep,'list_editors',return_value=[EDITOR]),
              patch.object(ep,'close_and_wait') as close,patch.object(app.messagebox,'askyesno',return_value=False)):
            app.App.start_file_update(ui,'Project',prepare,apply,done)
        prepare.assert_called_once();close.assert_not_called();apply.assert_not_called();done.assert_not_called()
        self.assertIn('暂停',ui.status.get())

    def test_approved_shutdown_finishes_before_file_replacement(self):
        ui=self.ui();events=[]
        with (patch.object(c,'project_path'),patch.object(ep,'list_editors',return_value=[EDITOR]),
              patch.object(ep,'close_and_wait',side_effect=lambda *a:events.append('closed')),
              patch.object(app.messagebox,'askyesno',return_value=True)):
            app.App.start_file_update(ui,'Project',lambda:events.append('download') or 'archive',
                                      lambda p:events.append('write') or p,lambda p:events.append('done'))
        self.assertEqual(events,['download','closed','write','done'])

    def test_ue_cancel_or_timeout_never_reaches_install(self):
        ui=self.ui();apply=Mock()
        with (patch.object(c,'project_path'),patch.object(ep,'list_editors',return_value=[EDITOR]),
              patch.object(ep,'close_and_wait',side_effect=RuntimeError('UE 未退出')),
              patch.object(app.messagebox,'askyesno',return_value=True)):
            with self.assertRaisesRegex(RuntimeError,'未退出'):
                app.App.start_file_update(ui,'Project',lambda:'archive',apply,Mock())
        apply.assert_not_called()

    def test_no_editor_needs_no_close_prompt(self):
        ui=self.ui();apply=Mock(return_value='backup')
        with (patch.object(c,'project_path'),patch.object(ep,'list_editors',return_value=[]),
              patch.object(app.messagebox,'askyesno') as ask,patch.object(ep,'close_and_wait') as close):
            app.App.start_file_update(ui,'Project',lambda:'archive',apply,Mock())
        ask.assert_not_called();close.assert_not_called();apply.assert_called_once_with('archive')

    def test_changed_project_cancels_before_closing_editor(self):
        ui=self.ui();apply=Mock()
        def prepare():ui.project.set('Other');return 'archive'
        with (patch.object(c,'project_path'),patch.object(ep,'list_editors',return_value=[EDITOR]),
              patch.object(app.messagebox,'askyesno') as ask):
            app.App.start_file_update(ui,'Project',prepare,apply,Mock())
        ask.assert_not_called();apply.assert_not_called()

    def test_download_question_can_be_declined_and_automatic_repeat_is_suppressed(self):
        ui=self.ui();ui.feed={'shared':{},'manager':{'version':'99.0','sha256':'a'*64}};ui.selected=None
        with (patch.object(app.messagebox,'askyesno',return_value=False) as ask,
              patch.object(c,'prepare_manager_update') as download):
            app.App.offer_updates(ui,{'shared_update':False},True)
            app.App.offer_updates(ui,{'shared_update':False},True)
        self.assertEqual(ask.call_count,1);download.assert_not_called()

    def test_confirmed_download_does_not_install_close_ue_or_launch_without_consent(self):
        ui=self.ui();ui.project.set('');ui.feed={'shared':{},'manager':{'version':'99.0','sha256':'a'*64}};ui.selected=None
        with (patch.object(app.messagebox,'askyesno',side_effect=[True,False]),
              patch.object(c,'prepare_manager_update',return_value=Path('new.exe')) as download,
              patch.object(c,'install') as install,patch.object(ep,'request_close') as close):
            app.App.offer_updates(ui,{},True)
        download.assert_called_once();install.assert_not_called();close.assert_not_called();ui.open_manager.assert_not_called()

    def test_newer_plugin_and_shared_offered_but_cached_or_older_feed_not_offered(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'P.uproject').write_text('{}')
            c.write_json(root/'Plugins/XHNodeChinese/XHNodeChinese.uplugin',{'VersionName':'0.2.11','XHSharedDictionaryVersion':1})
            c.write_json(root/c.SHARED_FILES[2],{'version':'2026.10.12'})
            feed={'shared':{'version':'2026.10.13'},'manager':{'version':'0.0'}}
            selected={'version':'0.2.12','verified':True}
            updates=c.available_updates(feed,root,selected,{'shared_update':True})
            self.assertEqual([u['kind'] for u in updates],['plugin','shared'])
            self.assertFalse(c.available_updates(dict(feed,_cached=True),root,selected))
            feed['shared']['version']='2026.10.11';selected['version']='0.2.10'
            self.assertFalse(c.available_updates(feed,root,selected,{'shared_update':True}))
            selected.update(version='0.2.12',verified=False)
            self.assertFalse(c.available_updates(feed,root,selected,{'shared_update':False}))


class EditorExitTests(unittest.TestCase):
    def test_normal_close_waits_until_editor_exits(self):
        with (patch.object(ep,'request_close') as request,patch.object(ep,'list_editors',side_effect=[[EDITOR],[]]),
              patch.object(ep.time,'sleep') as sleep):
            ep.close_and_wait([EDITOR])
        request.assert_called_once_with([EDITOR]);sleep.assert_called_once()

    def test_cancelled_exit_times_out_without_force_kill(self):
        with (patch.object(ep,'request_close'),patch.object(ep,'list_editors',return_value=[EDITOR]),
              patch.object(ep.time,'monotonic',side_effect=[0,91])):
            with self.assertRaisesRegex(RuntimeError,'尚未退出'):ep.close_and_wait([EDITOR])

    def test_new_editor_or_reused_pid_requires_a_new_confirmation(self):
        with (patch.object(ep,'request_close'),patch.object(ep,'list_editors',return_value=[dict(EDITOR,started='new')])):
            with self.assertRaisesRegex(RuntimeError,'新的虚幻进程'):ep.close_and_wait([EDITOR])

    def test_only_valid_editor_identities_with_windows_can_be_requested(self):
        for target in (dict(EDITOR,name='notepad'),dict(EDITOR,started=''),dict(EDITOR,window=False)):
            with patch.object(ep,'_powershell') as send:
                with self.assertRaises(RuntimeError):ep.request_close([target])
                send.assert_not_called()
        with patch.object(ep,'_powershell',return_value=[{'pid':EDITOR['pid'],'sent':True}]) as send:
            ep.request_close([EDITOR])
            self.assertEqual(send.call_args.args[1],[EDITOR])
            self.assertIn('CloseMainWindow',send.call_args.args[0])
            self.assertNotIn('Stop-Process',send.call_args.args[0])


if __name__=='__main__':unittest.main()
