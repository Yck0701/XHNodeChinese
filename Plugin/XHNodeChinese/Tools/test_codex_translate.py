import hashlib,json,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core,personal,codex_translate as ct
from xh_node_chinese.live import append_pairs
from xh_node_chinese.long_text import LongTextSession

LONG='This module uses {Value} to determine the initial particle lifetime and updates every particle with the selected force on every frame.'

class CodexTests(unittest.TestCase):
    def test_percentage_prose_and_real_placeholders(self):
        for source, translated in (
            ('Vivid Light darkens colors below 50% gray and lightens colors above 50% gray.',
             '亮光模式使低于50%灰的颜色变暗，高于50%灰的颜色变亮。'),
            ('Reset to 100% and center. 50% probability. 100% of A.',
             '重置为100%并居中。50%的概率。100%的A。'),
        ):
            self.assertEqual(core.placeholders(source), core.placeholders(translated))
            req={'request_id':'percent','items':[{'id':'1','kind':'long','source':source}]}
            resp={'request_id':'percent','translations':[{'id':'1','translation':translated}],'skipped':[]}
            self.write('LongText.csv',{source:''})
            self.assertEqual(ct.apply_response(self.plugin,self.save,req,resp)['long_texts'],1)
        formats='v2%d %s % g %0.2f %1$d %lld {Value} {Value}'
        self.assertEqual(sum(core.placeholders(formats).values()),8)
        self.assertNotEqual(core.placeholders(formats),core.placeholders(formats.replace('% g','')))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.plugin=Path(self.tmp.name)/'Plugin';self.save=Path(self.tmp.name)/'Saved'
        (self.plugin/'Dictionaries').mkdir(parents=True);self.save.mkdir()
        self.user=self.plugin/'Dictionaries/User.csv';self.user.write_bytes(b'Key,Value\n')
        self.write('Live.csv',{'DynamicMaterialParameter1':'','DynamicMaterialParameter2':'','New Label':''})
        self.write('Pending.csv',{'Historical Export':''})
        self.write('LongText.csv',{LONG:''})
        core.write_json(self.save/'CodexConnection.json',{'thread_id':'00000000-0000-0000-0000-000000000001',
            'cli_path':sys.executable,'workspace':str(self.save),'exchange_dir':str(self.save/'Requests')})

    def write(self,name,pairs):core.atomic_write(self.save/name,append_pairs(b'Key,Value\n',pairs))
    def request(self):return {'request_id':'test','items':ct.collect(self.save,{})}
    def response(self,request):return {'request_id':request['request_id'],'translations':[
        {'id':i['id'],'translation':'完整中文 {Value}' if i['kind']=='long' else '中文标签'} for i in request['items']], 'skipped':[]}

    def test_collection_canonical_scope_and_manual_protection(self):
        items=ct.collect(self.save,{})
        self.assertEqual(len(items),3)
        self.assertEqual({i['source'] for i in items},{'DynamicMaterialParameter','New Label',LONG})
        self.assertEqual(len(ct.collect(self.save,{},True)),4)
        self.write('Pending.csv',{'New Label':'用户已填'})
        self.assertNotIn('New Label',{i['source'] for i in ct.collect(self.save,{},True)})

    def test_response_writes_long_separately_preserves_new_manual_edits(self):
        req=self.request();resp=self.response(req)
        personal.update(self.plugin,self.save,{'New Label':'新的手工译文'})
        result=ct.apply_response(self.plugin,self.save,req,resp)
        self.assertEqual((result['terms'],result['long_texts'],result['preserved']),(1,1,1))
        user={r['Source']:r['Translation'] for r in core.load_dictionary(self.user)}
        self.assertEqual(user['New Label'],'新的手工译文');self.assertNotIn(LONG,user)
        self.assertEqual(core.load_dictionary(self.save/'LongText.csv')[0]['Translation'],'完整中文 {Value}')
        self.assertTrue(list((self.save/'LongTextBackups').glob('*.csv')))
        again=ct.apply_response(self.plugin,self.save,req,resp)
        self.assertEqual((again['terms'],again['long_texts']),(0,0))

    def test_invalid_or_incomplete_response_is_atomic(self):
        req=self.request();before=self.user.read_bytes();long_before=(self.save/'LongText.csv').read_bytes()
        for damage in ('missing','unknown','duplicate','placeholder','request_id'):
            resp=self.response(req)
            if damage=='missing':resp['translations'].pop()
            elif damage=='unknown':resp['translations'][0]['id']='unknown'
            elif damage=='duplicate':resp['translations'].append(resp['translations'][0])
            elif damage=='placeholder':resp['translations'][-1]['translation']='缺少占位符'
            else:resp['request_id']='wrong'
            with self.assertRaises(ValueError):ct.apply_response(self.plugin,self.save,req,resp)
            self.assertEqual(self.user.read_bytes(),before)
            self.assertEqual((self.save/'LongText.csv').read_bytes(),long_before)

    def test_async_persist_restart_and_response(self):
        session=ct.Session(self.plugin,self.save);sent=[]
        self.assertTrue(session.start({},sender=lambda *args:sent.append(args)))
        session.worker.join(2);session.poll()
        self.assertEqual(session.state['phase'],'waiting');self.assertEqual(len(sent),1)
        self.assertFalse(session.start({},sender=lambda *args:None))
        restarted=ct.Session(self.plugin,self.save)
        folder=Path(restarted.state['folder']);req=json.loads((folder/'request.json').read_text(encoding='utf-8'))
        core.write_json(folder/'response.json',self.response(req))
        self.assertTrue(restarted.poll());self.assertEqual(restarted.state['phase'],'done')
        self.assertTrue((folder/'applied.json').exists());self.assertFalse(restarted.poll())

    def test_cancel_does_not_accept_late_delivery(self):
        session=ct.Session(self.plugin,self.save)
        session.start({},sender=lambda *args:None);session.worker.join(2)
        session.cancel();session.poll()
        self.assertEqual(session.state['phase'],'cancelled')

    def test_sender_failure_and_invalid_response_recovery(self):
        def fail(*args):raise RuntimeError('test offline')
        session=ct.Session(self.plugin,self.save);session.start({},sender=fail)
        session.worker.join(2);session.poll();self.assertEqual(session.state['phase'],'error')
        self.assertIn('test offline',session.display()['tooltip'])
        folder=Path(session.state['folder']);req=json.loads((folder/'request.json').read_text(encoding='utf-8'))
        core.write_json(folder/'response.json',{})
        self.assertFalse(session.poll());self.assertEqual(session.state['phase'],'error')
        core.write_json(folder/'response.json',self.response(req))
        self.assertTrue(session.poll());self.assertEqual(session.state['phase'],'done')

    def start_session(self):
        session=ct.Session(self.plugin,self.save)
        session.start({},sender=lambda *args:None);session.worker.join(2);session.poll()
        folder=Path(session.state['folder'])
        request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
        return session,folder,request,self.response(request)

    def test_progressive_import_restart_and_out_of_order(self):
        session,folder,req,resp=self.start_session()
        self.assertEqual([i['id'] for i in req['items']],['1','2','3'])
        self.assertEqual(req['items'][-1]['kind'],'long')
        first=dict(resp,translations=resp['translations'][:1])
        core.write_json(folder/'response-0002.json',first)
        self.assertTrue(session.poll())
        self.assertEqual(session.state['phase'],'waiting')
        self.assertEqual(session.state['completed'],1)
        self.assertIn('1/3',session.display()['label'])
        self.assertFalse(json.loads((folder/'applied.json').read_text())['complete'])
        self.assertEqual(len(core.load_dictionary(self.user)),1)
        restarted=ct.Session(self.plugin,self.save)
        self.assertFalse(restarted.poll())
        core.write_json(folder/'response-0001.json',dict(resp,translations=resp['translations'][1:]))
        self.assertTrue(restarted.poll())
        self.assertEqual(restarted.state['phase'],'done')
        self.assertEqual(restarted.state['result']['terms'],2)
        self.assertEqual(restarted.state['result']['long_texts'],1)
        receipt=json.loads((folder/'applied.json').read_text())
        self.assertTrue(receipt['complete']);self.assertEqual(receipt['completed'],3)
        self.assertFalse(restarted.poll())

    def test_partial_batch_rejects_invalid_placeholder_and_duplicate_across_files(self):
        session,folder,req,resp=self.start_session()
        core.write_json(folder/'response-0001.json',dict(resp,translations=resp['translations'][:1]))
        self.assertTrue(session.poll());before=self.user.read_bytes()
        core.write_json(folder/'response-0002.json',dict(resp,translations=resp['translations'][:2]))
        self.assertFalse(session.poll());self.assertEqual(self.user.read_bytes(),before)
        self.assertEqual(session.state['completed'],1)
        bad=dict(resp,translations=[dict(resp['translations'][-1],translation='缺少参数')])
        core.write_json(folder/'response-0002.json',bad)
        self.assertFalse(session.poll());self.assertEqual(self.user.read_bytes(),before)
        core.write_json(folder/'response-0002.json',dict(resp,translations=resp['translations'][1:]))
        self.assertTrue(session.poll());self.assertEqual(session.state['phase'],'done')

    def test_large_accepted_queue_stays_idle_but_detects_new_and_edited_batches(self):
        session,folder,req,resp=self.start_session()
        previous=[{'id':'old-'+str(i),'kind':'term','source':'Old Label '+str(i)} for i in range(600)]
        req['items']=previous+req['items'];core.write_json(folder/'request.json',req)
        accepted={}
        for index,item in enumerate(previous,1):
            path=folder/f'response-{index:04}.json'
            core.write_json(path,{'request_id':req['request_id'],'translations':[],
                                 'skipped':[{'id':item['id'],'reason':'已处理'}]})
            accepted[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        session.state.update(processed_ids=[i['id'] for i in previous],accepted_files=accepted,
                             total=len(req['items']),completed=len(previous))
        session.persist()
        # Startup verifies persisted hashes once. Subsequent unchanged polls must
        # neither reopen files nor call Path.stat() once per accepted batch.
        self.assertFalse(session.poll())
        with (patch.object(Path,'stat',side_effect=AssertionError('per-file stat')),
              patch.object(Path,'read_bytes',side_effect=AssertionError('unchanged file reopened'))):
            self.assertFalse(session.poll())
        core.write_json(folder/'response-0601.json',dict(resp,translations=resp['translations'][:1]))
        self.assertTrue(session.poll());self.assertEqual(session.state['completed'],601)
        self.assertEqual(len(core.load_dictionary(self.user)),1)
        core.write_json(folder/'response-0001.json',{'modified':'已导入批次不允许改写'})
        self.assertFalse(session.poll())
        self.assertEqual(session.state['phase'],'error')
        self.assertIn('response-0001.json',session.state['error'])
        self.assertEqual(session.state['completed'],601)

    def test_missing_queue_and_temporary_or_directory_responses_are_ignored(self):
        session,folder,req,resp=self.start_session()
        (folder/'response-0001.json').mkdir()
        core.write_json(folder/'response-0002.json.tmp',resp)
        self.assertFalse(session.poll())
        session.state['folder']=str(folder/'missing')
        self.assertFalse(session.poll())

    def test_partial_preserves_manual_edit_and_cancelled_remaining(self):
        session,folder,req,resp=self.start_session()
        personal.update(self.plugin,self.save,{req['items'][0]['source']:'我的译名'})
        core.write_json(folder/'response-0001.json',dict(resp,translations=resp['translations'][:1]))
        self.assertTrue(session.poll());self.assertEqual(session.state['result']['preserved'],1)
        session.cancel();before=self.user.read_bytes()
        core.write_json(folder/'response-0002.json',dict(resp,translations=resp['translations'][1:]))
        self.assertFalse(session.poll());self.assertEqual(self.user.read_bytes(),before)
        self.assertEqual(session.state['phase'],'cancelled')

    def test_skipped_part_counts_toward_completion_and_legacy_response(self):
        session,folder,req,resp=self.start_session()
        skipped=[{'id':req['items'][0]['id'],'reason':'专有名称保持原样'}]
        core.write_json(folder/'response-0001.json',dict(resp,translations=[],skipped=skipped))
        self.assertTrue(session.poll());self.assertEqual(session.state['completed'],1)
        core.write_json(folder/'response-0002.json',dict(resp,translations=resp['translations'][1:]))
        self.assertTrue(session.poll());self.assertEqual(len(session.state['result']['skipped']),1)
        # Pending v1 requests created before the upgrade continue to import.
        session.state['phase']='waiting';session.state.pop('processed_ids');session.state.pop('accepted_files')
        session.state.pop('result');session.state['completed']=0;session.persist()
        for p in folder.glob('response-*.json'):p.unlink()
        req.pop('protocol');core.write_json(folder/'request.json',req)
        restarted=ct.Session(self.plugin,self.save)
        core.write_json(folder/'response.json',resp)
        self.assertTrue(restarted.poll());self.assertEqual(restarted.state['phase'],'done')

if __name__=='__main__':unittest.main()
